#!/usr/bin/env python
"""Import structured curriculum content into an SSync tenant.

Ingests curriculum topic hierarchies, subtopics, learning objectives, and guidance:
    CurriculumSubject
        -> Topic
        -> CurriculumTopic
            -> SubTopic
            -> LearningObjective
            -> CurriculumGuidance

Usage:
    uv run python scripts/import_curriculum_content.py \\
        --tenant green_valley_curriculum_test \\
        --curriculum "Nigerian Basic Education Curriculum" \\
        --file scripts/test_curriculum_jss1_mathematics.json \\
        --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")

import django

django.setup()

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django_tenants.utils import schema_context

from academic.models import Curriculum
from academic.services.curriculum_import_service import (
    CurriculumImportError,
    CurriculumImportService,
    ImportMetrics,
)
from tenants.models import Client, Domain


def detect_environment():
    explicit = os.getenv("ENVIRONMENT") or os.getenv("DJANGO_ENV") or os.getenv("APP_ENV")
    if explicit:
        label = explicit.strip().upper()
        return label, label in {"PRODUCTION", "PROD", "LIVE"}
    base_domain = getattr(settings, "BASE_DOMAIN", "localhost")
    if not settings.DEBUG and base_domain != "localhost":
        return "PRODUCTION", True
    if not settings.DEBUG:
        return "STAGING / PRODUCTION (DEBUG=False)", True
    return "LOCAL DEVELOPMENT", False


def resolve_tenant(identifier: str) -> Client:
    clean = identifier.strip()
    if clean.lower() in {"public", "public_schema", "public_tenant"}:
        raise ValueError("The public tenant is forbidden.")
    tenants = Client.objects.exclude(schema_name="public")
    matches = list(tenants.filter(schema_name__iexact=clean))
    if len(matches) == 1:
        return matches[0]
    domains = list(
        Domain.objects.filter(Q(domain__iexact=clean) | Q(domain__istartswith=f"{clean}."))
        .exclude(tenant__schema_name="public").select_related("tenant")
    )
    domain_tenants = {item.tenant_id: item.tenant for item in domains}
    if len(domain_tenants) == 1:
        return next(iter(domain_tenants.values()))
    exact_names = list(tenants.filter(name__iexact=clean))
    if len(exact_names) == 1:
        return exact_names[0]
    partial = list(tenants.filter(name__icontains=clean))
    if len(partial) == 1:
        return partial[0]
    candidates = matches or list(domain_tenants.values()) or exact_names or partial
    if candidates:
        rendered = ", ".join(f"{t.name} [{t.schema_name}]" for t in candidates)
        raise ValueError(f"Ambiguous tenant '{clean}': {rendered}")
    raise ValueError(f"No non-public tenant matches '{clean}'.")


def print_metrics_table(metrics: ImportMetrics):
    summary = metrics.get_summary()
    statuses = ["CREATED", "UPDATED", "REUSED", "UNCHANGED", "SKIPPED", "CONFLICT"]
    entities = ["CurriculumSource", "Topic", "CurriculumTopic", "SubTopic", "LearningObjective", "CurriculumGuidance"]

    print("\n" + "=" * 78)
    print(f"{'Entity':<22} " + " ".join(f"{s:>9}" for s in statuses))
    print("=" * 78)
    for entity in entities:
        row = summary.get(entity, {})
        row_str = " ".join(f"{row.get(s, 0):>9}" for s in statuses)
        print(f"{entity:<22} {row_str}")
    print("-" * 78)
    totals_str = " ".join(f"{metrics.total(s):>9}" for s in statuses)
    print(f"{'TOTAL':<22} {totals_str}")
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser(
        description="Import structured curriculum content (topics, subtopics, objectives, guidance) from JSON."
    )
    parser.add_argument("--tenant", required=True, help="Tenant schema, domain, or unambiguous school name.")
    parser.add_argument("--file", required=True, help="Path to canonical curriculum JSON file.")
    parser.add_argument("--curriculum", help="Curriculum ID, name, or version; optional if defined in payload.")
    parser.add_argument("--grade", help="Filter import to specific grade level (e.g. JSS_1, Year 7).")
    parser.add_argument("--subject", help="Filter import to specific subject (e.g. Mathematics, MATH).")
    parser.add_argument("--strict", action="store_true", help="Abort on any warning.")
    parser.add_argument("--dry-run", action="store_true", help="Execute validation and real ORM saves, then roll back.")
    parser.add_argument("--confirm-production", action="store_true", help="Required for live production writes.")
    args = parser.parse_args()

    environment, is_production = detect_environment()
    if is_production and not args.dry_run and not args.confirm_production:
        parser.error(f"{environment}: live production writes require --confirm-production")

    try:
        tenant = resolve_tenant(args.tenant)
        data = CurriculumImportService.load_json(args.file)

        with schema_context(tenant.schema_name):
            curriculum_obj = CurriculumImportService.resolve_curriculum(
                data=data, curriculum=args.curriculum
            )

            print("\n" + "=" * 78)
            print("SSync Curriculum Content Importer")
            print("=" * 78)
            print(f"Environment : {environment}")
            print(f"Database    : {connection.settings_dict.get('ENGINE')} / {connection.settings_dict.get('NAME')}")
            print(f"Tenant      : {tenant.name} [{tenant.schema_name}]")
            print(f"Curriculum  : {curriculum_obj.name} (Version: {curriculum_obj.version or 'N/A'}, ID: {curriculum_obj.pk})")
            print(f"Source File : {args.file}")
            print(f"Grade Filter: {args.grade or 'ALL'}")
            print(f"Subj Filter : {args.subject or 'ALL'}")
            print(f"Mode        : {'DRY RUN (rollback)' if args.dry_run else 'LIVE COMMIT'}")

            # Preflight validation
            errors = CurriculumImportService.validate(
                data=data,
                curriculum=curriculum_obj,
                grade_filter=args.grade,
                subject_filter=args.subject,
                strict=args.strict,
            )
            if errors:
                print("\nPREFLIGHT VALIDATION FAILED:")
                for err in errors:
                    print(f"  [ERROR] {err}")
                sys.exit(1)

            print("\nPreflight validation passed. Executing import...")
            metrics, source_obj, batch_obj = CurriculumImportService.import_content(
                data=data,
                curriculum=curriculum_obj,
                grade_filter=args.grade,
                subject_filter=args.subject,
                dry_run=args.dry_run,
                strict=args.strict,
            )

            if source_obj:
                print(f"\n[Provenance] Source Document: {source_obj.title} ({source_obj.version or source_obj.publication_year or 'N/A'})")
                if source_obj.checksum_sha256:
                    print(f"             SHA-256 Hash   : {source_obj.checksum_sha256}")
            if batch_obj:
                print(f"[Provenance] Import Batch   : #{batch_obj.id} (UUID: {batch_obj.public_id})")

            print_metrics_table(metrics)

            if args.dry_run:
                print("\nDRY RUN: Validation and ORM save paths executed; transaction rolled back cleanly.")
            else:
                print("\nLIVE COMMIT: Curriculum content imported successfully.")

    except (ValueError, CurriculumImportError) as exc:
        print(f"\nIMPORT ERROR: {exc}")
        if hasattr(exc, "errors") and len(exc.errors) > 1:
            for e in exc.errors:
                print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
