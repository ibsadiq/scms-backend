#!/usr/bin/env python
"""
Correct the incorrectly combined NERDC 2025 curriculum.

Splits:

    Nigerian Basic Education Curriculum (2025)

into:

    PRE-PRIMARY & PRIMARY SCHOOLS - NERDC Scheme (2025)
    JSS & SSS - NERDC Scheme (2025)

Existing CurriculumSubject rows are MOVED in place so their primary keys
and downstream relationships remain intact.

Usage:

    uv run python scripts/correct_curriculum_2025.py \
        --tenant green_valley_curriculum_test \
        --dry-run

    uv run python scripts/correct_curriculum_2025.py \
        --tenant green_valley_curriculum_test
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

from academic.models import Curriculum, CurriculumSubject
from academic.models.choices import CurriculumAuthority, SectionType
from tenants.models import Client, Domain


OLD_NAME = "Nigerian Basic Education Curriculum"

PRIMARY_NAME = "PRE-PRIMARY & PRIMARY SCHOOLS - NERDC Scheme"
SECONDARY_NAME = "JSS & SSS - NERDC Scheme"

VERSION = "2025"


class DryRunRollback(Exception):
    pass


def detect_environment():
    explicit = (
        os.getenv("ENVIRONMENT")
        or os.getenv("DJANGO_ENV")
        or os.getenv("APP_ENV")
    )

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

    if clean.lower() in {
        "public",
        "public_schema",
        "public_tenant",
    }:
        raise ValueError("The public tenant is forbidden.")

    tenants = Client.objects.exclude(schema_name="public")

    # Exact schema.
    matches = list(
        tenants.filter(schema_name__iexact=clean)
    )

    if len(matches) == 1:
        return matches[0]

    # Exact/prefix domain.
    domains = list(
        Domain.objects.filter(
            Q(domain__iexact=clean)
            | Q(domain__istartswith=f"{clean}.")
        )
        .exclude(tenant__schema_name="public")
        .select_related("tenant")
    )

    domain_tenants = {
        item.tenant_id: item.tenant
        for item in domains
    }

    if len(domain_tenants) == 1:
        return next(iter(domain_tenants.values()))

    # Exact school name.
    exact_names = list(
        tenants.filter(name__iexact=clean)
    )

    if len(exact_names) == 1:
        return exact_names[0]

    # Partial school name.
    partial = list(
        tenants.filter(name__icontains=clean)
    )

    if len(partial) == 1:
        return partial[0]

    candidates = (
        matches
        or list(domain_tenants.values())
        or exact_names
        or partial
    )

    if candidates:
        rendered = ", ".join(
            f"{t.name} [{t.schema_name}]"
            for t in candidates
        )
        raise ValueError(
            f"Ambiguous tenant '{clean}': {rendered}"
        )

    raise ValueError(
        f"No non-public tenant matches '{clean}'."
    )


def get_or_create_curricula():
    common = {
        "version": VERSION,
        "authority_type": CurriculumAuthority.NERDC,
        "authority_name": (
            "Nigerian Educational Research and "
            "Development Council"
        ),
        "is_active": True,
    }

    primary, primary_created = Curriculum.objects.get_or_create(
        name=PRIMARY_NAME,
        version=VERSION,
        defaults={
            **common,
            "description": (
                "NERDC 2025 scheme for Pre-Primary "
                "and Primary Schools."
            ),
        },
    )

    secondary, secondary_created = Curriculum.objects.get_or_create(
        name=SECONDARY_NAME,
        version=VERSION,
        defaults={
            **common,
            "description": (
                "NERDC 2025 scheme for Junior and "
                "Senior Secondary Schools."
            ),
        },
    )

    return (
        primary,
        primary_created,
        secondary,
        secondary_created,
    )


def target_curriculum_for_mapping(
    mapping,
    primary_curriculum,
    secondary_curriculum,
):
    section = mapping.grade_level.section

    if section in {
        SectionType.PRE_PRIMARY,
        SectionType.PRIMARY,
    }:
        return primary_curriculum

    if section in {
        SectionType.JUNIOR_SECONDARY,
        SectionType.SENIOR_SECONDARY,
    }:
        return secondary_curriculum

    raise ValueError(
        f"Unsupported section '{section}' for "
        f"{mapping.grade_level}."
    )


def correct_curriculum_2025():
    results = {
        "old_curriculum_id": None,
        "old_mapping_count": 0,

        "primary_created": False,
        "primary_id": None,
        "primary_moved": 0,
        "primary_existing": 0,

        "secondary_created": False,
        "secondary_id": None,
        "secondary_moved": 0,
        "secondary_existing": 0,

        "conflicts": [],
        "old_retired": False,
    }

    old = Curriculum.objects.filter(
        name__iexact=OLD_NAME,
        version=VERSION,
    ).first()

    if old:
        results["old_curriculum_id"] = old.id

    (
        primary,
        primary_created,
        secondary,
        secondary_created,
    ) = get_or_create_curricula()

    results["primary_created"] = primary_created
    results["primary_id"] = primary.id

    results["secondary_created"] = secondary_created
    results["secondary_id"] = secondary.id

    # Nothing to migrate means the correction may already
    # have been performed.
    if not old:
        results["primary_existing"] = (
            CurriculumSubject.objects.filter(
                curriculum=primary
            ).count()
        )

        results["secondary_existing"] = (
            CurriculumSubject.objects.filter(
                curriculum=secondary
            ).count()
        )

        return results

    mappings = list(
        CurriculumSubject.objects.filter(
            curriculum=old
        ).select_related(
            "subject",
            "grade_level",
        )
    )

    results["old_mapping_count"] = len(mappings)

    # Preflight before modifying anything.
    moves = []

    for mapping in mappings:
        target = target_curriculum_for_mapping(
            mapping,
            primary,
            secondary,
        )

        duplicate = CurriculumSubject.objects.filter(
            curriculum=target,
            subject=mapping.subject,
            grade_level=mapping.grade_level,
        ).exclude(pk=mapping.pk).first()

        if duplicate:
            results["conflicts"].append(
                {
                    "source_mapping_id": mapping.pk,
                    "existing_mapping_id": duplicate.pk,
                    "subject": mapping.subject.name,
                    "grade": str(mapping.grade_level),
                    "target": target.name,
                }
            )
            continue

        moves.append((mapping, target))

    if results["conflicts"]:
        rendered = "\n".join(
            (
                f"  - {item['subject']} / "
                f"{item['grade']} -> "
                f"{item['target']} "
                f"(source #{item['source_mapping_id']}, "
                f"existing #{item['existing_mapping_id']})"
            )
            for item in results["conflicts"]
        )

        raise ValueError(
            "Existing target CurriculumSubject mappings "
            "would conflict with the migration:\n"
            f"{rendered}\n"
            "No automatic merge was attempted."
        )

    # Move existing rows IN PLACE.
    for mapping, target in moves:
        mapping.curriculum = target
        mapping.full_clean()
        mapping.save(update_fields=["curriculum"])

        if target.pk == primary.pk:
            results["primary_moved"] += 1
        else:
            results["secondary_moved"] += 1

    results["primary_existing"] = (
        CurriculumSubject.objects.filter(
            curriculum=primary
        ).count()
    )

    results["secondary_existing"] = (
        CurriculumSubject.objects.filter(
            curriculum=secondary
        ).count()
    )

    remaining = CurriculumSubject.objects.filter(
        curriculum=old
    ).count()

    # Preserve the old record for audit/history but make sure
    # nobody selects it for future setup.
    if remaining == 0 and old.is_active:
        old.is_active = False
        old.save(update_fields=["is_active"])
        results["old_retired"] = True

    return results


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Split the incorrectly combined NERDC 2025 "
            "curriculum into Pre-Primary/Primary and "
            "JSS/SSS curricula."
        )
    )

    parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant schema, domain, or school name.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Execute the real migration path and roll "
            "back the transaction."
        ),
    )

    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required for live production writes.",
    )

    args = parser.parse_args()

    environment, is_production = detect_environment()

    if (
        is_production
        and not args.dry_run
        and not args.confirm_production
    ):
        parser.error(
            f"{environment}: live production writes "
            "require --confirm-production"
        )

    tenant = resolve_tenant(args.tenant)

    print("\n" + "=" * 78)
    print("SSync NERDC 2025 Curriculum Correction")
    print("=" * 78)
    print(f"Environment : {environment}")
    print(
        "Database    : "
        f"{connection.settings_dict.get('ENGINE')} / "
        f"{connection.settings_dict.get('NAME')}"
    )
    print(
        f"Tenant      : {tenant.name} "
        f"[{tenant.schema_name}]"
    )
    print(
        "Mode        : "
        f"{'DRY RUN (rollback)' if args.dry_run else 'LIVE COMMIT'}"
    )
    print("=" * 78)

    with schema_context(tenant.schema_name):
        try:
            with transaction.atomic():
                result = correct_curriculum_2025()

                print("\nSource curriculum:")
                print(
                    "  Old curriculum ID       : "
                    f"{result['old_curriculum_id']}"
                )
                print(
                    "  Old mappings found      : "
                    f"{result['old_mapping_count']}"
                )

                print("\nPre-Primary / Primary:")
                print(
                    f"  Curriculum ID           : "
                    f"{result['primary_id']}"
                )
                print(
                    f"  Curriculum created      : "
                    f"{result['primary_created']}"
                )
                print(
                    f"  Mappings moved          : "
                    f"{result['primary_moved']}"
                )
                print(
                    f"  Total mappings          : "
                    f"{result['primary_existing']}"
                )

                print("\nJSS / SSS:")
                print(
                    f"  Curriculum ID           : "
                    f"{result['secondary_id']}"
                )
                print(
                    f"  Curriculum created      : "
                    f"{result['secondary_created']}"
                )
                print(
                    f"  Mappings moved          : "
                    f"{result['secondary_moved']}"
                )
                print(
                    f"  Total mappings          : "
                    f"{result['secondary_existing']}"
                )

                print("\nOld combined curriculum:")
                print(
                    f"  Retired                 : "
                    f"{result['old_retired']}"
                )

                if args.dry_run:
                    raise DryRunRollback()

            print(
                "\nLIVE COMMIT completed successfully."
            )

        except DryRunRollback:
            print(
                "\nDRY RUN: correction executed and "
                "rolled back cleanly."
            )


if __name__ == "__main__":
    main()