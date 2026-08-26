#!/usr/bin/env python
"""Create the 2025 Nigerian Basic Education Curriculum and CurriculumSubject mappings in an SSync tenant.

Usage:
    uv run python scripts/create_curriculum_2025.py --tenant green_valley_curriculum_test --dry-run
    uv run python scripts/create_curriculum_2025.py --tenant green_valley_curriculum_test
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
from django.db import connection, transaction
from django.db.models import Q
from django_tenants.utils import schema_context

from academic.models import (
    Curriculum,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    Subject,
    Topic,
)
from academic.models.choices import CurriculumAuthority
from tenants.models import Client, Domain


class DryRunRollback(Exception):
    pass


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


def setup_curriculum_2025(dry_run: bool = False) -> dict:
    """Creates Curriculum 2025 and replicates the 249 canonical CurriculumSubject mappings."""
    results = {
        "curriculum_created": False,
        "curriculum_reused": False,
        "curriculum_id": None,
        "mappings_created": 0,
        "mappings_reused": 0,
        "mappings_2024_count": 0,
        "mappings_2025_count": 0,
        "topics_created": 0,
        "curriculum_topics_created": 0,
    }

    # 1. Verify 2024 curriculum exists as the canonical mapping baseline
    curr_2024 = Curriculum.objects.filter(
        name__iexact="Nigerian Basic Education Curriculum",
        version="2024",
    ).first()

    if not curr_2024:
        raise ValueError("Baseline 2024 curriculum not found. Run academic bootstrap first.")

    mappings_2024 = list(CurriculumSubject.objects.filter(curriculum=curr_2024).select_related("subject", "grade_level"))
    results["mappings_2024_count"] = len(mappings_2024)

    # 2. Get or create 2025 curriculum
    curr_2025 = Curriculum.objects.filter(
        name="Nigerian Basic Education Curriculum",
        version="2025",
    ).first()

    if curr_2025:
        results["curriculum_reused"] = True
        results["curriculum_id"] = curr_2025.id
    else:
        curr_2025 = Curriculum.objects.create(
            name="Nigerian Basic Education Curriculum",
            version="2025",
            authority_type=CurriculumAuthority.NERDC,
            authority_name="Nigerian Educational Research and Development Council",
            description="Nigerian Basic Education Curriculum (2025 Edition)",
            is_active=True,
        )
        results["curriculum_created"] = True
        results["curriculum_id"] = curr_2025.id

    # 3. Create 2025 CurriculumSubject mappings matching 2024 baseline
    for m in mappings_2024:
        cs, created = CurriculumSubject.objects.get_or_create(
            curriculum=curr_2025,
            subject=m.subject,
            grade_level=m.grade_level,
            defaults={
                "description": m.description,
                "is_active": m.is_active,
            },
        )
        if created:
            results["mappings_created"] += 1
        else:
            results["mappings_reused"] += 1

    results["mappings_2025_count"] = CurriculumSubject.objects.filter(curriculum=curr_2025).count()
    return results


def main():
    parser = argparse.ArgumentParser(description="Create 2025 Curriculum and CurriculumSubject mappings in an SSync tenant.")
    parser.add_argument("--tenant", required=True, help="Tenant schema, domain, or school name.")
    parser.add_argument("--dry-run", action="store_true", help="Execute validation and creation, then roll back.")
    parser.add_argument("--confirm-production", action="store_true", help="Required for live production writes.")
    args = parser.parse_args()

    environment, is_production = detect_environment()
    if is_production and not args.dry_run and not args.confirm_production:
        parser.error(f"{environment}: live production writes require --confirm-production")

    tenant = resolve_tenant(args.tenant)

    print("\n" + "=" * 78)
    print("SSync 2025 Curriculum Setup")
    print("=" * 78)
    print(f"Environment : {environment}")
    print(f"Database    : {connection.settings_dict.get('ENGINE')} / {connection.settings_dict.get('NAME')}")
    print(f"Tenant      : {tenant.name} [{tenant.schema_name}]")
    print(f"Mode        : {'DRY RUN (rollback)' if args.dry_run else 'LIVE COMMIT'}")
    print("=" * 78)

    with schema_context(tenant.schema_name):
        initial_topics = Topic.objects.count()
        initial_cts = CurriculumTopic.objects.count()
        initial_subjects = Subject.objects.count()
        initial_grades = GradeLevel.objects.count()

        try:
            with transaction.atomic():
                res = setup_curriculum_2025(dry_run=args.dry_run)

                print("\nExecution Summary:")
                print(f"  Curriculum 2024 mappings  : {res['mappings_2024_count']}")
                print(f"  Curriculum 2025 ID        : {res['curriculum_id']}")
                print(f"  Curriculum 2025 Created   : {res['curriculum_created']}")
                print(f"  Curriculum 2025 Reused    : {res['curriculum_reused']}")
                print(f"  2025 Mappings Created     : {res['mappings_created']}")
                print(f"  2025 Mappings Reused      : {res['mappings_reused']}")
                print(f"  2025 Total Mappings       : {res['mappings_2025_count']}")
                print(f"  Topics Created            : {Topic.objects.count() - initial_topics}")
                print(f"  CurriculumTopics Created  : {CurriculumTopic.objects.count() - initial_cts}")
                print(f"  Subjects Created          : {Subject.objects.count() - initial_subjects}")
                print(f"  GradeLevels Created       : {GradeLevel.objects.count() - initial_grades}")

                if args.dry_run:
                    raise DryRunRollback()

            print("\nLIVE COMMIT completed successfully.")

        except DryRunRollback:
            print("\nDRY RUN: All operations executed and rolled back cleanly.")


if __name__ == "__main__":
    main()
