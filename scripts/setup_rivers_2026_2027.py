#!/usr/bin/env python
"""
SSync Academic Calendar Setup Script
Rivers State 2026/2027 Academic Calendar

Environment-agnostic standalone script for populating AcademicYear, Term,
and SchoolEvent records for a target tenant.

Usage:
  Local Dry-Run:
    python scripts/setup_rivers_2026_2027.py --tenant green_valley_academy --dry-run

  Local Live Run:
    python scripts/setup_rivers_2026_2027.py --tenant green_valley_academy

  Production Dry-Run:
    python scripts/setup_rivers_2026_2027.py --tenant <production_schema> --dry-run

  Production Live Run:
    python scripts/setup_rivers_2026_2027.py --tenant <production_schema> --confirm-production
"""

import os
import sys
import argparse
from datetime import date
from pathlib import Path

# ── 1. Django Initialization ──────────────────────────────────────────────────
BASE_DIR = (
    Path(__file__).resolve().parent.parent
    if Path(__file__).resolve().parent.name == "scripts"
    else Path(__file__).resolve().parent
)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")

import django
django.setup()

from django.conf import settings
from django.db import transaction, connection
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context
from tenants.models import Client, Domain
from administration.models import AcademicYear, Term, SchoolEvent
from finance.models import FeeStructure


# ── 2. Environment Detection ──────────────────────────────────────────────────
def detect_environment() -> tuple[str, bool]:
    """
    Detects current environment from explicit env variables or Django settings.
    Returns: (environment_label, is_production)
    """
    explicit_env = (
        os.getenv("ENVIRONMENT")
        or os.getenv("DJANGO_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENV")
    )
    if explicit_env:
        label = explicit_env.upper().strip()
        is_prod = label in ("PRODUCTION", "PROD", "LIVE")
        return label, is_prod

    if not settings.DEBUG and settings.BASE_DOMAIN != "localhost":
        return "PRODUCTION", True
    elif not settings.DEBUG:
        return "STAGING / PRODUCTION (DEBUG=False)", True
    else:
        return "LOCAL DEVELOPMENT (DEBUG=True)", False


# ── 3. Hardened Tenant Resolution ─────────────────────────────────────────────
def resolve_tenant(identifier: str) -> Client:
    """
    Resolves tenant in strict deterministic precedence:
      1. Exact schema_name
      2. Exact domain
      3. Domain prefix (unambiguous only)
      4. Exact school name
      5. Partial school name (unambiguous only)

    Strictly forbids running against the public schema.
    Aborts with candidate list if any match is ambiguous.
    """
    raw_clean = identifier.strip()
    identifier_clean = raw_clean.lower()

    if identifier_clean in ("public", "public_tenant", "public_schema"):
        raise ValueError("Cannot run calendar setup against the 'public' tenant schema.")

    non_public_tenants = Client.objects.exclude(schema_name="public")

    # 1. Exact schema_name match
    by_schema = list(non_public_tenants.filter(schema_name__iexact=identifier_clean))
    if len(by_schema) == 1:
        return by_schema[0]

    # 2. Exact domain match
    by_exact_domain = list(
        Domain.objects.filter(domain__iexact=identifier_clean)
        .exclude(tenant__schema_name="public")
        .select_related("tenant")
    )
    if len(by_exact_domain) == 1 and by_exact_domain[0].tenant:
        return by_exact_domain[0].tenant

    # 3. Domain prefix match (e.g., 'greenvalley' matching 'greenvalley.localhost')
    by_domain_prefix = list(
        Domain.objects.filter(domain__istartswith=f"{identifier_clean}.")
        .exclude(tenant__schema_name="public")
        .select_related("tenant")
    )
    unique_prefix_tenants = list({d.tenant for d in by_domain_prefix if d.tenant})
    if len(unique_prefix_tenants) == 1:
        return unique_prefix_tenants[0]
    elif len(unique_prefix_tenants) > 1:
        candidates = ", ".join(f"{t.name} (schema: {t.schema_name})" for t in unique_prefix_tenants)
        raise ValueError(f"Ambiguous domain match for '{raw_clean}'. Matching tenants: {candidates}")

    # 4. Exact school name match (case-insensitive)
    by_exact_name = list(non_public_tenants.filter(name__iexact=raw_clean))
    if len(by_exact_name) == 1:
        return by_exact_name[0]
    elif len(by_exact_name) > 1:
        candidates = ", ".join(f"{t.name} (schema: {t.schema_name})" for t in by_exact_name)
        raise ValueError(f"Ambiguous exact name match for '{raw_clean}'. Matching tenants: {candidates}")

    # 5. Partial school name match (case-insensitive)
    by_partial_name = list(non_public_tenants.filter(name__icontains=raw_clean))
    if len(by_partial_name) == 1:
        return by_partial_name[0]
    elif len(by_partial_name) > 1:
        candidates = ", ".join(f"{t.name} (schema: {t.schema_name})" for t in by_partial_name)
        raise ValueError(f"Ambiguous partial name match for '{raw_clean}'. Matching tenants: {candidates}")

    # No match found — list available schemas
    available = ", ".join(non_public_tenants.values_list("schema_name", flat=True))
    raise ValueError(
        f"No tenant found matching '{raw_clean}'. Available tenant schemas: [{available}]"
    )


# ── 4. Rivers State 2026/2027 Calendar Specification ─────────────────────────
# Official Academic Session: 2026/2027
# Session start: 2026-09-07 (First Term resumption)
# Session end:   2027-09-03 (End of Long Vacation before 2027/2028 resumption)
ACADEMIC_YEAR_DATA = {
    "name": "2026/2027",
    "start_date": date(2026, 9, 7),
    "end_date": date(2027, 9, 3),
    "active_year": True,
}

TERMS_DATA = [
    {
        "name": "First Term",
        "start_date": date(2026, 9, 7),
        "end_date": date(2026, 12, 11),
    },
    {
        "name": "Second Term",
        "start_date": date(2027, 1, 4),
        "end_date": date(2027, 3, 25),
    },
    {
        "name": "Third Term",
        "start_date": date(2027, 4, 19),
        "end_date": date(2027, 7, 16),
    },
]

EVENTS_DATA = [
    # ── First Term ──
    {
        "name": "First Term Begins",
        "event_type": "other",
        "start_date": date(2026, 9, 7),
        "end_date": date(2026, 9, 7),
        "term_name": "First Term",
        "description": "Resumption of academic activities for First Term 2026/2027.",
    },
    {
        "name": "First Term Mid-Term Break",
        "event_type": "holiday",
        "start_date": date(2026, 10, 23),
        "end_date": date(2026, 10, 26),
        "term_name": "First Term",
        "description": "Mid-term break for First Term 2026/2027.",
    },
    {
        "name": "First Term Ends",
        "event_type": "other",
        "start_date": date(2026, 12, 11),
        "end_date": date(2026, 12, 11),
        "term_name": "First Term",
        "description": "Conclusion of First Term examinations and academic activities.",
    },
    {
        "name": "First Term Holiday / Christmas Vacation",
        "event_type": "holiday",
        "start_date": date(2026, 12, 14),
        "end_date": date(2027, 1, 1),
        "term_name": "First Term",
        "description": "Christmas and New Year holiday between First and Second Terms.",
    },
    # ── Second Term ──
    {
        "name": "Second Term Begins",
        "event_type": "other",
        "start_date": date(2027, 1, 4),
        "end_date": date(2027, 1, 4),
        "term_name": "Second Term",
        "description": "Resumption of academic activities for Second Term 2026/2027.",
    },
    {
        "name": "Second Term Mid-Term Break",
        "event_type": "holiday",
        "start_date": date(2027, 2, 12),
        "end_date": date(2027, 2, 15),
        "term_name": "Second Term",
        "description": "Mid-term break for Second Term 2026/2027.",
    },
    {
        "name": "Second Term Ends",
        "event_type": "other",
        "start_date": date(2027, 3, 25),
        "end_date": date(2027, 3, 25),
        "term_name": "Second Term",
        "description": "Conclusion of Second Term academic activities.",
    },
    {
        "name": "Good Friday",
        "event_type": "holiday",
        "start_date": date(2027, 3, 26),
        "end_date": date(2027, 3, 26),
        "term_name": "Second Term",
        "description": "Good Friday public holiday.",
    },
    {
        "name": "Easter Sunday",
        "event_type": "holiday",
        "start_date": date(2027, 3, 28),
        "end_date": date(2027, 3, 28),
        "term_name": "Second Term",
        "description": "Easter Sunday.",
    },
    {
        "name": "Easter Monday",
        "event_type": "holiday",
        "start_date": date(2027, 3, 29),
        "end_date": date(2027, 3, 29),
        "term_name": "Second Term",
        "description": "Easter Monday public holiday.",
    },
    {
        "name": "Easter Holiday / Second Term Vacation",
        "event_type": "holiday",
        "start_date": date(2027, 3, 29),
        "end_date": date(2027, 4, 16),
        "term_name": "Second Term",
        "description": "Easter vacation between Second and Third Terms.",
    },
    # ── Third Term ──
    {
        "name": "Third Term Begins",
        "event_type": "other",
        "start_date": date(2027, 4, 19),
        "end_date": date(2027, 4, 19),
        "term_name": "Third Term",
        "description": "Resumption of academic activities for Third Term 2026/2027.",
    },
    {
        "name": "World Book Day",
        "event_type": "other",
        "start_date": date(2027, 4, 23),
        "end_date": date(2027, 4, 23),
        "term_name": "Third Term",
        "description": "World Book Day celebration.",
    },
    {
        "name": "Third Term Mid-Term Break",
        "event_type": "holiday",
        "start_date": date(2027, 5, 28),
        "end_date": date(2027, 5, 31),
        "term_name": "Third Term",
        "description": "Mid-term break for Third Term 2026/2027.",
    },
    {
        "name": "Third Term Ends",
        "event_type": "other",
        "start_date": date(2027, 7, 16),
        "end_date": date(2027, 7, 16),
        "term_name": "Third Term",
        "description": "Conclusion of Third Term and end of 2026/2027 academic session.",
    },
    {
        "name": "End of Session Long Vacation",
        "event_type": "holiday",
        "start_date": date(2027, 7, 19),
        "end_date": date(2027, 9, 3),
        "term_name": "Third Term",
        "description": "Long vacation preceding the 2027/2028 academic session resumption.",
    },
]

SKIPPED_RECORDS = [
    (
        "Boarders Report (2026-09-05)",
        "Falls prior to official session start date (2026-09-07). Excluded to preserve academic year boundary integrity.",
    ),
    (
        "WASSCE Examination (April-May 2027)",
        "Source provides month range only. Exact exam timetable should be populated when official WAEC dates are published.",
    ),
    (
        "Basic Education Certificate Examination (BECE) (June 2027)",
        "Source provides month only. Exact exam timetable should be populated when published.",
    ),
    (
        "NECO Senior School Certificate Examination (June-July 2027)",
        "Source provides month range only. Exact exam timetable should be populated when published.",
    ),
    (
        "Placement for JSS 1 and SSS 1 (July 2026)",
        "Pre-session event occurring prior to 2026/2027 academic year.",
    ),
    (
        "First Term 2027/2028 Begins (2027-09-06)",
        "Belongs to subsequent 2027/2028 academic session calendar.",
    ),
    (
        "International Literacy Day (2027-09-08)",
        "Belongs to subsequent 2027/2028 academic session calendar.",
    ),
    (
        "World Teachers' Day (2027-10-05)",
        "Belongs to subsequent 2027/2028 academic session calendar.",
    ),
]


class DryRunRollback(Exception):
    """Internal sentinel exception to cleanly rollback dry-run transactions."""
    pass


# ── 5. Change Plan Evaluation ─────────────────────────────────────────────────
def evaluate_planned_changes(ay_existing, terms_existing, events_existing, set_active: bool):
    """
    Computes planned actions (CREATE, UPDATE, UNCHANGED) for all objects
    based on current database state.
    """
    plan = {"year": None, "terms": [], "events": []}

    # Academic Year
    if not ay_existing:
        plan["year"] = ("CREATE", ACADEMIC_YEAR_DATA["name"])
    else:
        diffs = []
        if ay_existing.start_date != ACADEMIC_YEAR_DATA["start_date"]:
            diffs.append(f"start_date: {ay_existing.start_date} -> {ACADEMIC_YEAR_DATA['start_date']}")
        if ay_existing.end_date != ACADEMIC_YEAR_DATA["end_date"]:
            diffs.append(f"end_date: {ay_existing.end_date} -> {ACADEMIC_YEAR_DATA['end_date']}")
        if set_active and not ay_existing.active_year:
            diffs.append(f"active_year: {ay_existing.active_year} -> True")

        if diffs:
            plan["year"] = ("UPDATE", f"{ay_existing.name} ({', '.join(diffs)})")
        else:
            plan["year"] = ("UNCHANGED", ay_existing.name)

    # Terms
    terms_by_name = {t.name: t for t in terms_existing}
    for t_spec in TERMS_DATA:
        t_name = t_spec["name"]
        t_obj = terms_by_name.get(t_name)
        if not t_obj:
            plan["terms"].append(("CREATE", t_name, f"{t_spec['start_date']} -> {t_spec['end_date']}"))
        else:
            diffs = []
            if t_obj.start_date != t_spec["start_date"]:
                diffs.append(f"start_date: {t_obj.start_date} -> {t_spec['start_date']}")
            if t_obj.end_date != t_spec["end_date"]:
                diffs.append(f"end_date: {t_obj.end_date} -> {t_spec['end_date']}")

            if diffs:
                plan["terms"].append(("UPDATE", t_name, ", ".join(diffs)))
            else:
                plan["terms"].append(("UNCHANGED", t_name, f"{t_obj.start_date} -> {t_obj.end_date}"))

    # Events
    events_by_name = {e.name: e for e in events_existing}
    for e_spec in EVENTS_DATA:
        e_name = e_spec["name"]
        e_obj = events_by_name.get(e_name)
        if not e_obj:
            plan["events"].append(("CREATE", e_name, f"{e_spec['start_date']} -> {e_spec.get('end_date')} [{e_spec['event_type']}]"))
        else:
            diffs = []
            if e_obj.event_type != e_spec["event_type"]:
                diffs.append(f"event_type: {e_obj.event_type} -> {e_spec['event_type']}")
            if e_obj.start_date != e_spec["start_date"]:
                diffs.append(f"start_date: {e_obj.start_date} -> {e_spec['start_date']}")
            if e_obj.end_date != e_spec.get("end_date"):
                diffs.append(f"end_date: {e_obj.end_date} -> {e_spec.get('end_date')}")
            if e_obj.description != e_spec.get("description", ""):
                diffs.append("description updated")

            if diffs:
                plan["events"].append(("UPDATE", e_name, ", ".join(diffs)))
            else:
                plan["events"].append(("UNCHANGED", e_name, f"{e_obj.start_date} -> {e_obj.end_date} [{e_obj.event_type}]"))

    return plan


# ── 6. Setup Execution Engine ─────────────────────────────────────────────────
def run_setup(
    tenant: Client,
    dry_run: bool = False,
    set_active: bool = True,
    broadcast_notifications: bool = False,
):
    env_name, is_prod = detect_environment()

    print("\n" + "=" * 70)
    print(" SSync Academic Calendar Setup (Rivers State 2026/2027)")
    print("=" * 70)

    # ── Section 1: Preflight ──
    with schema_context(tenant.schema_name):
        existing_years = list(AcademicYear.objects.all())
        existing_year_names = [y.name for y in existing_years]
        existing_terms_count = Term.objects.count()
        existing_events_count = SchoolEvent.objects.count()

        # Finance Preflight Check (evaluated eagerly inside tenant schema)
        fee_structures_count = FeeStructure.objects.filter(academic_year__name="2026/2027").count()
        mandatory_fees_count = FeeStructure.objects.filter(
            academic_year__name="2026/2027", is_mandatory=True
        ).count()
        fee_schedule_will_trigger = "YES" if mandatory_fees_count > 0 else "NO"

        ay_current = AcademicYear.objects.filter(name=ACADEMIC_YEAR_DATA["name"]).first()
        terms_current = list(Term.objects.filter(academic_year=ay_current)) if ay_current else []
        events_current = list(SchoolEvent.objects.filter(academic_year=ay_current)) if ay_current else []

        plan = evaluate_planned_changes(ay_current, terms_current, events_current, set_active)

    if dry_run:
        mode_str = "DRY RUN - ALL DB CHANGES WILL ROLLBACK"
    elif is_prod:
        mode_str = "PRODUCTION LIVE WRITE CONFIRMED"
    else:
        mode_str = "LOCAL LIVE COMMIT"

    notifications_mode = (
        "BROADCAST (--broadcast-notifications enabled)"
        if broadcast_notifications
        else "SUPPRESSED (Local instance-level flag / safe bulk setup)"
    )

    domain_list = list(tenant.domains.values_list("domain", flat=True))

    print("\nPreflight Summary")
    print("-" * 70)
    print(f"  Environment:                   {env_name}")
    print(f"  Database Engine:               {connection.settings_dict.get('ENGINE')}")
    print(f"  Database Name:                 {connection.settings_dict.get('NAME')}")
    print(f"  Tenant School:                 {tenant.name}")
    print(f"  Tenant ID:                     {tenant.id}")
    print(f"  Schema:                        {tenant.schema_name}")
    print(f"  Domain(s):                     {', '.join(domain_list) if domain_list else 'None assigned'}")
    print(f"  Existing AcademicYears in DB:  {len(existing_years)} ({', '.join(existing_year_names) if existing_year_names else 'None'})")
    print(f"  Existing Terms in DB:          {existing_terms_count}")
    print(f"  Existing SchoolEvents in DB:   {existing_events_count}")
    print(f"  FeeStructures for 2026/2027:   {fee_structures_count} ({mandatory_fees_count} mandatory)")
    print(f"  Term post_save schedules fees: {fee_schedule_will_trigger}")
    print(f"  Event Notifications:           {notifications_mode}")
    print(f"  Execution Mode:                {mode_str}")
    print("-" * 70)

    # ── Section 2: Planned Changes ──
    print("\nPlanned Changes")
    print("-" * 70)
    print(f"  Academic Year: [{plan['year'][0]}] {plan['year'][1]}")
    print("  Terms:")
    for action, name, details in plan["terms"]:
        print(f"    [{action:<9}] {name} ({details})")
    print("  Events & Holidays:")
    for action, name, details in plan["events"]:
        print(f"    [{action:<9}] {name} ({details})")
    print("  Skipped Calendar Items:")
    for item_name, reason in SKIPPED_RECORDS:
        print(f"    [SKIPPED  ] {item_name}")
        print(f"                Reason: {reason}")
    print("-" * 70 + "\n")

    # ── Section 3: Database Execution ──
    counts = {
        "year_created": 0,
        "year_updated": 0,
        "year_unchanged": 0,
        "terms_created": 0,
        "terms_updated": 0,
        "terms_unchanged": 0,
        "events_created": 0,
        "events_updated": 0,
        "events_unchanged": 0,
        "events_skipped": len(SKIPPED_RECORDS),
    }

    with schema_context(tenant.schema_name):
        try:
            with transaction.atomic():
                print("Executing Operations:")

                # ── Step 3.1: Academic Year ──
                year_name = ACADEMIC_YEAR_DATA["name"]
                ay = AcademicYear.objects.filter(name=year_name).first()

                if not ay:
                    ay = AcademicYear(
                        name=year_name,
                        start_date=ACADEMIC_YEAR_DATA["start_date"],
                        end_date=ACADEMIC_YEAR_DATA["end_date"],
                        active_year=set_active,
                    )
                    try:
                        ay.full_clean()
                    except ValidationError as ve:
                        print(f"  [ERROR] ValidationError on AcademicYear '{year_name}': {ve}")
                        raise
                    ay.save()
                    counts["year_created"] += 1
                    print(f"  [CREATED]   AcademicYear {ay.name} ({ay.start_date} -> {ay.end_date}) [Active: {ay.active_year}]")
                else:
                    changed = False
                    if ay.start_date != ACADEMIC_YEAR_DATA["start_date"]:
                        ay.start_date = ACADEMIC_YEAR_DATA["start_date"]
                        changed = True
                    if ay.end_date != ACADEMIC_YEAR_DATA["end_date"]:
                        ay.end_date = ACADEMIC_YEAR_DATA["end_date"]
                        changed = True
                    if set_active and not ay.active_year:
                        ay.active_year = True
                        changed = True

                    if changed:
                        try:
                            ay.full_clean()
                        except ValidationError as ve:
                            print(f"  [ERROR] ValidationError on AcademicYear '{year_name}': {ve}")
                            raise
                        ay.save()
                        counts["year_updated"] += 1
                        print(f"  [UPDATED]   AcademicYear {ay.name} ({ay.start_date} -> {ay.end_date}) [Active: {ay.active_year}]")
                    else:
                        counts["year_unchanged"] += 1
                        print(f"  [UNCHANGED] AcademicYear {ay.name} ({ay.start_date} -> {ay.end_date}) [Active: {ay.active_year}]")

                # ── Step 3.2: Terms ──
                terms_by_name = {}
                for t_spec in TERMS_DATA:
                    t_name = t_spec["name"]
                    term = Term.objects.filter(academic_year=ay, name=t_name).first()

                    if not term:
                        term = Term(
                            academic_year=ay,
                            name=t_name,
                            start_date=t_spec["start_date"],
                            end_date=t_spec["end_date"],
                        )
                        try:
                            term.full_clean()
                        except ValidationError as ve:
                            print(f"  [ERROR] ValidationError on Term '{t_name}': {ve}")
                            raise
                        term.save()
                        counts["terms_created"] += 1
                        print(f"  [CREATED]   Term {term.name} ({term.start_date} -> {term.end_date})")
                    else:
                        changed = False
                        if term.start_date != t_spec["start_date"]:
                            term.start_date = t_spec["start_date"]
                            changed = True
                        if term.end_date != t_spec["end_date"]:
                            term.end_date = t_spec["end_date"]
                            changed = True

                        if changed:
                            try:
                                term.full_clean()
                            except ValidationError as ve:
                                print(f"  [ERROR] ValidationError on Term '{t_name}': {ve}")
                                raise
                            term.save()
                            counts["terms_updated"] += 1
                            print(f"  [UPDATED]   Term {term.name} ({term.start_date} -> {term.end_date})")
                        else:
                            counts["terms_unchanged"] += 1
                            print(f"  [UNCHANGED] Term {term.name} ({term.start_date} -> {term.end_date})")

                    terms_by_name[t_name] = term

                # ── Step 3.3: School Events ──
                for e_spec in EVENTS_DATA:
                    e_name = e_spec["name"]
                    linked_term = terms_by_name.get(e_spec.get("term_name"))
                    event = SchoolEvent.objects.filter(academic_year=ay, name=e_name).first()

                    if not event:
                        event = SchoolEvent(
                            academic_year=ay,
                            term=linked_term,
                            name=e_name,
                            event_type=e_spec["event_type"],
                            start_date=e_spec["start_date"],
                            end_date=e_spec.get("end_date"),
                            description=e_spec.get("description", ""),
                        )
                        if not broadcast_notifications:
                            event._skip_notifications = True

                        try:
                            event.full_clean()
                        except ValidationError as ve:
                            print(f"  [ERROR] ValidationError on SchoolEvent '{e_name}': {ve}")
                            raise
                        event.save()
                        counts["events_created"] += 1
                        print(f"  [CREATED]   Event {event.name} ({event.start_date} -> {event.end_date}) [{event.event_type}]")
                    else:
                        changed = False
                        if event.term != linked_term:
                            event.term = linked_term
                            changed = True
                        if event.event_type != e_spec["event_type"]:
                            event.event_type = e_spec["event_type"]
                            changed = True
                        if event.start_date != e_spec["start_date"]:
                            event.start_date = e_spec["start_date"]
                            changed = True
                        if event.end_date != e_spec.get("end_date"):
                            event.end_date = e_spec.get("end_date")
                            changed = True
                        if event.description != e_spec.get("description", ""):
                            event.description = e_spec.get("description", "")
                            changed = True

                        if not broadcast_notifications:
                            event._skip_notifications = True

                        if changed:
                            try:
                                event.full_clean()
                            except ValidationError as ve:
                                print(f"  [ERROR] ValidationError on SchoolEvent '{e_name}': {ve}")
                                raise
                            event.save()
                            counts["events_updated"] += 1
                            print(f"  [UPDATED]   Event {event.name} ({event.start_date} -> {event.end_date}) [{event.event_type}]")
                        else:
                            counts["events_unchanged"] += 1
                            print(f"  [UNCHANGED] Event {event.name} ({event.start_date} -> {event.end_date}) [{event.event_type}]")

                if dry_run:
                    raise DryRunRollback()

        except DryRunRollback:
            print("\n" + "=" * 70)
            print(" DRY RUN COMPLETE — All operations and validations succeeded.")
            print(" NO DATABASE CHANGES COMMITTED (Transaction rolled back).")
            print("=" * 70)

        except ValidationError as ve:
            print(f"\n[VALIDATION FAILED]: {ve}")
            raise

    # ── Section 4: Final Summary ──
    print("\nExecution Summary")
    print("-" * 70)
    print("  AcademicYear:")
    print(f"    Created:   {counts['year_created']:<4} | Updated: {counts['year_updated']:<4} | Unchanged: {counts['year_unchanged']:<4}")
    print("  Terms:")
    print(f"    Created:   {counts['terms_created']:<4} | Updated: {counts['terms_updated']:<4} | Unchanged: {counts['terms_unchanged']:<4}")
    print("  Events & Holidays:")
    print(f"    Created:   {counts['events_created']:<4} | Updated: {counts['events_updated']:<4} | Unchanged: {counts['events_unchanged']:<4} | Skipped: {counts['events_skipped']:<4}")
    print("-" * 70)
    total_created = counts["year_created"] + counts["terms_created"] + counts["events_created"]
    total_updated = counts["year_updated"] + counts["terms_updated"] + counts["events_updated"]
    total_unchanged = counts["year_unchanged"] + counts["terms_unchanged"] + counts["events_unchanged"]
    print(f"  Total Created:   {total_created}")
    print(f"  Total Updated:   {total_updated}")
    print(f"  Total Unchanged: {total_unchanged}")
    print(f"  Total Skipped:   {counts['events_skipped']}")

    if not dry_run:
        print("\n✓ SETUP COMPLETE — DATABASE CHANGES COMMITTED")


# ── 7. CLI Entry Point ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Populate Rivers State 2026/2027 academic calendar into a tenant."
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="Target tenant schema_name, domain, or school name (Required).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform all validations and simulations without committing changes.",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required confirmation flag to apply live changes in production.",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create the academic year without making it the current active year.",
    )
    parser.add_argument(
        "--broadcast-notifications",
        action="store_true",
        help="Broadcast notification emails to all active school users for future events (Default: False).",
    )

    args = parser.parse_args()

    env_name, is_prod = detect_environment()

    # Production safety check
    if is_prod and not args.dry_run and not args.confirm_production:
        print("\n" + "!" * 70)
        print(" ERROR: PRODUCTION ENVIRONMENT DETECTED")
        print("!" * 70)
        print(f" Environment: {env_name}")
        print(" Live write operations against production require explicit confirmation.")
        print("\n Please test with --dry-run first:")
        print(f"     python {sys.argv[0]} --tenant {args.tenant} --dry-run\n")
        print(" To execute live in production, re-run with:")
        print(f"     python {sys.argv[0]} --tenant {args.tenant} --confirm-production\n")
        sys.exit(1)

    try:
        tenant = resolve_tenant(args.tenant)
        run_setup(
            tenant=tenant,
            dry_run=args.dry_run,
            set_active=not args.inactive,
            broadcast_notifications=args.broadcast_notifications,
        )
    except ValueError as ve:
        print(f"\n[CONFIGURATION ERROR]: {ve}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[EXECUTION ERROR]: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
