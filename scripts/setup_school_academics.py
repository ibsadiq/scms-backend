#!/usr/bin/env python
"""Configure a fresh SSync tenant's school structure and curriculum mappings.

This script configures a fresh/new school tenant with canonical 2024 academic data:
- GradeLevel aliases (Pre-Nursery, Nursery 1-3, Year 1-12)
- ClassRoom names (<GradeLevel.alias> <GroupName>)
- Canonical Departments (Languages, Mathematics, Sciences, Humanities, Business, Trade)
- Canonical Subject Catalog (2024 NERDC curriculum subjects)
- Nigerian Basic Education Curriculum (2024)
- Grade-specific CurriculumSubject mappings

This script intentionally does not create AllocatedSubject rows or Topic/SubTopic data:
those are managed operationally or imported from detailed curriculum documents later.
"""

import argparse
import os
import sys
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")

import django

django.setup()

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django_tenants.utils import schema_context

from academic.models import (
    ClassRoom,
    Curriculum,
    CurriculumSubject,
    Department,
    GradeLevel,
    Subject,
)
from academic.models.choices import CurriculumAuthority, SectionType
from tenants.models import Client, Domain


class DryRunRollback(Exception):
    pass


class ConflictRollback(Exception):
    pass


GRADE_SPECS = [
    ("PRE_NURSERY", SectionType.PRE_PRIMARY, "Pre-Nursery", "Pre-Nursery", 2, 2, 3, "Little Orchard"),
    ("NURSERY_1", SectionType.PRE_PRIMARY, "Nursery 1", "Nursery 1", 3, 3, 4, "Buttercup"),
    ("NURSERY_2", SectionType.PRE_PRIMARY, "Nursery 2", "Nursery 2", 4, 4, 5, "Jasmine"),
    ("NURSERY_3", SectionType.PRE_PRIMARY, "Nursery 3", "Nursery 3", 5, 5, 6, "Daisy"),
    ("BASIC_1", SectionType.PRIMARY, "Basic 1", "Year 1", 6, 6, 6, "Lavender"),
    ("BASIC_2", SectionType.PRIMARY, "Basic 2", "Year 2", 7, 7, 7, "Primrose"),
    ("BASIC_3", SectionType.PRIMARY, "Basic 3", "Year 3", 8, 8, 8, "Orchid"),
    ("BASIC_4", SectionType.PRIMARY, "Basic 4", "Year 4", 9, 9, 9, "Dahlia"),
    ("BASIC_5", SectionType.PRIMARY, "Basic 5", "Year 5", 10, 10, 10, "Carnation"),
    ("BASIC_6", SectionType.PRIMARY, "Basic 6", "Year 6", 11, 11, 11, "Lily"),
    ("JSS_1", SectionType.JUNIOR_SECONDARY, "JSS 1", "Year 7", 12, 12, 12, "Oleander"),
    ("JSS_2", SectionType.JUNIOR_SECONDARY, "JSS 2", "Year 8", 13, 13, 13, "Tulip"),
    ("JSS_3", SectionType.JUNIOR_SECONDARY, "JSS 3", "Year 9", 14, 14, 14, "Ixora"),
    ("SS_1", SectionType.SENIOR_SECONDARY, "SS 1", "Year 10", 15, 15, 15, "Marigold"),
    ("SS_2", SectionType.SENIOR_SECONDARY, "SS 2", "Year 11", 16, 16, 16, "Diamond"),
    ("SS_3", SectionType.SENIOR_SECONDARY, "SS 3", "Year 12", 17, 17, 17, "Platinum"),
]

DEPARTMENT_NAMES = ["Languages", "Mathematics", "Sciences", "Humanities", "Business", "Trade"]

SUBJECT_SPECS = {
    "Number Work": ("NUMW", None, False),
    "Letter Work": ("LETW", None, False),
    "Language Domain": ("LANG", None, False),
    "Health Habits": ("HLTH", None, False),
    "Social Habits": ("SOCH", None, False),
    "Personal Development": ("PDEV", None, False),
    "Social Norms": ("SOCN", None, False),
    "Christian Religious Studies": ("CRS", None, False),
    "Handwriting": ("HAND", None, False),
    "Colouring": ("COLR", None, False),
    "Science": ("SCI", None, False),
    "Creative Art": ("CART", None, False),
    "Rhymes": ("RHY", None, False),
    "Quantitative Reasoning": ("QTR", None, False),
    "Verbal Reasoning": ("VRB", None, False),
    "English Language": ("ENG", "Languages", False),
    "Mathematics": ("MATH", "Mathematics", False),
    "Basic Science": ("BSCI", None, False),
    "Physical & Health Education": ("PHE", None, False),
    "Islamic Studies": ("ISL", None, False),
    "Nigerian History": ("NGH", None, False),
    "Social & Citizenship Studies": ("SCS", None, False),
    "Cultural & Creative Arts": ("CCA", None, False),
    "Basic Science and Technology": ("BST", "Sciences", False),
    "Basic Digital Literacy": ("BDL", None, False),
    "Pre-Vocational Studies": ("PVS", None, True),
    "French": ("FRE", "Languages", False),
    "Intermediate Science": ("ISCI", "Sciences", False),
    "Digital Technologies": ("DTECH", None, False),
    "Business Studies": ("BSTD", "Business", False),
    "Solar": ("SOLAR", "Trade", True),
    "Fashion": ("FASH", "Trade", True),
    "Livestock Farming": ("LSTK", "Trade", True),
    "Beauty & Cosmetology": ("BEAUTY", "Trade", True),
    "Computer Hardware": ("CHW", "Trade", True),
    "Horticulture & Crop Production": ("HORT", "Trade", True),
    "Citizenship and Heritage Studies": ("CHS", None, False),
    "Biology": ("BIO", "Sciences", True),
    "Chemistry": ("CHEM", "Sciences", True),
    "Physics": ("PHY", "Sciences", True),
    "Agricultural Science": ("AGR", "Sciences", True),
    "Further Mathematics": ("FMATH", "Sciences", True),
    "Foods & Nutrition": ("FNT", "Sciences", True),
    "Geography": ("GEO", "Sciences", True),
    "Technical Drawing": ("TDR", "Sciences", True),
    "Government": ("GOV", "Humanities", True),
    "Visual Arts": ("VART", "Humanities", True),
    "Literature-in-English": ("LITENG", "Humanities", True),
    "Catering and Craft Practice": ("CCP", "Humanities", True),
    "Financial Accounting": ("FA", "Business", True),
    "Commerce": ("COM", "Business", True),
    "Marketing": ("MKT", "Business", True),
    "Economics": ("ECON", "Business", True),
}

NURSERY = [
    "Number Work", "Letter Work", "Language Domain", "Health Habits",
    "Social Habits", "Personal Development", "Social Norms",
    "Christian Religious Studies", "Handwriting", "Colouring", "Science",
    "Creative Art", "Rhymes", "Quantitative Reasoning", "Verbal Reasoning",
]
PRIMARY_1_3 = [
    "English Language", "Mathematics", "Basic Science", "Physical & Health Education",
    "Christian Religious Studies", "Islamic Studies", "Nigerian History",
    "Social & Citizenship Studies", "Cultural & Creative Arts",
]
PRIMARY_4_6 = [
    "English Language", "Mathematics", "Basic Science and Technology",
    "Physical & Health Education", "Christian Religious Studies", "Islamic Studies",
    "Basic Digital Literacy", "Nigerian History", "Social & Citizenship Studies",
    "Cultural & Creative Arts", "Pre-Vocational Studies", "French",
]
TRADE = [
    "Solar", "Fashion", "Livestock Farming", "Beauty & Cosmetology",
    "Computer Hardware", "Horticulture & Crop Production",
]
JSS = [
    "English Language", "Mathematics", "Physical & Health Education",
    "Christian Religious Studies", "Islamic Studies", "Nigerian History",
    "Social & Citizenship Studies", "Cultural & Creative Arts", "French",
    "Intermediate Science", "Digital Technologies", "Business Studies", *TRADE,
]
SSS = [
    "English Language", "Mathematics", "Citizenship and Heritage Studies",
    "Digital Technologies", "Biology", "Chemistry", "Physics", "Agricultural Science",
    "Further Mathematics", "Foods & Nutrition", "Geography", "Technical Drawing",
    "Nigerian History", "Government", "Christian Religious Studies", "Visual Arts",
    "Literature-in-English", "Catering and Craft Practice", "Financial Accounting",
    "Commerce", "Marketing",
    "Economics", *TRADE,
]

GRADE_SUBJECTS = {
    "PRE_NURSERY": NURSERY,
    "NURSERY_1": NURSERY,
    "NURSERY_2": NURSERY,
    "NURSERY_3": NURSERY,
    "BASIC_1": PRIMARY_1_3,
    "BASIC_2": PRIMARY_1_3,
    "BASIC_3": PRIMARY_1_3,
    "BASIC_4": PRIMARY_4_6,
    "BASIC_5": PRIMARY_4_6,
    "BASIC_6": PRIMARY_4_6,
    "JSS_1": JSS,
    "JSS_2": JSS,
    "JSS_3": JSS,
    "SS_1": SSS,
    "SS_2": SSS,
    "SS_3": SSS,
}


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


def resolve_tenant(identifier):
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


def validate_freshness(tenant):
    """
    Ensures the target tenant is either genuinely fresh or was previously
    configured by this exact catalog setup script.
    Rejects foreign/legacy partial academic data.
    """
    allowed_depts = {name.lower() for name in DEPARTMENT_NAMES}
    existing_depts = list(Department.objects.all())
    for dept in existing_depts:
        if dept.name.lower() not in allowed_depts:
            raise ValueError(
                f"FRESHNESS CHECK FAILED: Unexpected department '{dept.name}' found in tenant '{tenant.schema_name}'. "
                f"This setup script is intended for fresh school tenants or idempotent reruns of the canonical catalog. "
                f"Allowed departments are: {', '.join(DEPARTMENT_NAMES)}."
            )

    allowed_subjects = {name.lower() for name in SUBJECT_SPECS.keys()}
    existing_subjects = list(Subject.objects.all())
    for subj in existing_subjects:
        if subj.name.lower() not in allowed_subjects:
            raise ValueError(
                f"FRESHNESS CHECK FAILED: Unexpected subject '{subj.name}' (code: {subj.subject_code}) found in tenant '{tenant.schema_name}'. "
                f"This setup script is intended for fresh school tenants or idempotent reruns of the canonical catalog."
            )

    expected_rooms = {
        f"{alias or default_name} {group_name}".strip().lower()
        for _, _, default_name, alias, _, _, _, group_name in GRADE_SPECS
    }
    expected_rooms |= {
        f"{default_name} {group_name}".strip().lower()
        for _, _, default_name, _, _, _, _, group_name in GRADE_SPECS
    }
    existing_rooms = list(ClassRoom.objects.all())
    for room in existing_rooms:
        if room.name.lower() not in expected_rooms:
            raise ValueError(
                f"FRESHNESS CHECK FAILED: Unexpected classroom '{room.name}' found in tenant '{tenant.schema_name}'."
            )


def ensure_curriculum(counts, selector=None):
    queryset = Curriculum.objects.all()
    if selector:
        if selector.isdigit():
            matches = list(queryset.filter(pk=int(selector)))
        else:
            matches = list(queryset.filter(name__iexact=selector))
        if len(matches) != 1:
            options = ", ".join(f"{c.id}:{c}" for c in queryset)
            raise ValueError(f"Expected exactly one curriculum matching '{selector}'; found {len(matches)}. Available: {options or 'none'}")
        curriculum = matches[0]
        report("REUSE", "Curriculum", str(curriculum), f"PK={curriculum.pk}")
        counts["REUSE"] += 1
        return curriculum

    curriculum = queryset.filter(
        name__iexact="Nigerian Basic Education Curriculum",
        version="2024",
        is_active=True,
    ).first()

    if not curriculum:
        active_list = list(queryset.filter(is_active=True))
        if len(active_list) == 1:
            curriculum = active_list[0]
            report("REUSE", "Curriculum", str(curriculum), f"PK={curriculum.pk}")
            counts["REUSE"] += 1
            return curriculum
        elif len(active_list) > 1:
            options = ", ".join(f"{c.id}:{c}" for c in active_list)
            raise ValueError(f"Multiple active curricula found: {options}. Use --curriculum to specify one.")

    if curriculum:
        report("UNCHANGED", "Curriculum", str(curriculum), f"PK={curriculum.pk}")
        counts["UNCHANGED"] += 1
        return curriculum

    curriculum = Curriculum(
        name="Nigerian Basic Education Curriculum",
        authority_type=CurriculumAuthority.NERDC,
        authority_name="Nigerian Educational Research and Development Council",
        version="2024",
        is_active=True,
    )
    save_validated(curriculum)
    report("CREATED", "Curriculum", str(curriculum), f"version={curriculum.version}")
    counts["CREATED"] += 1
    return curriculum


def print_header(tenant, curriculum, dry_run):
    environment, _ = detect_environment()
    print("\n" + "=" * 78)
    print("SSync Fresh School Academics Setup")
    print("=" * 78)
    print(f"Environment : {environment}")
    print(f"Database    : {connection.settings_dict.get('ENGINE')} / {connection.settings_dict.get('NAME')}")
    print(f"Tenant      : {tenant.name}")
    print(f"Schema      : {tenant.schema_name}")
    print(f"Curriculum  : {curriculum.id} - {curriculum}")
    print(f"Mode        : {'DRY RUN (rollback)' if dry_run else 'LIVE COMMIT'}")


def report(action, category, label, detail=""):
    suffix = f" — {detail}" if detail else ""
    print(f"  [{action:<9}] {category:<20} {label}{suffix}")


def save_validated(instance):
    instance.full_clean()
    instance.save()


def ensure_grade_levels(counts, conflicts):
    grades = {}
    for code, section, default_name, alias, order, min_age, max_age, _ in GRADE_SPECS:
        grade = GradeLevel.objects.filter(system_code=code).first()
        if grade is None:
            grade = GradeLevel(
                system_code=code, section=section, default_name=default_name, alias=alias,
                sequence_order=order, min_age=min_age, max_age=max_age,
            )
            save_validated(grade)
            report("CREATED", "GradeLevel", f"{code} ({alias})")
            counts["CREATED"] += 1
        elif grade.section != section:
            detail = f"existing section={grade.section}; expected={section}"
            report("CONFLICT", "GradeLevel", code, detail)
            conflicts.append(f"GradeLevel {code}: {detail}")
            counts["CONFLICT"] += 1
            continue
        elif grade.alias != alias:
            old = grade.alias or grade.default_name
            grade.alias = alias
            save_validated(grade)
            report("UPDATED", "GradeLevel", code, f"alias {old!r} -> {alias!r}")
            counts["UPDATED"] += 1
        else:
            report("UNCHANGED", "GradeLevel", f"{code} ({alias})")
            counts["UNCHANGED"] += 1
        grades[code] = grade

    return grades


def ensure_classrooms(grades, counts, conflicts):
    for code, _, _, _, _, _, _, group_name in GRADE_SPECS:
        grade = grades.get(code)
        if not grade:
            report("SKIPPED", "ClassRoom", group_name, f"grade {code} unavailable")
            counts["SKIPPED"] += 1
            continue

        classroom_name = f"{grade.alias or grade.default_name} {group_name}".strip()
        rooms = list(ClassRoom.objects.filter(grade_level=grade, name__iexact=classroom_name, stream__isnull=True))
        if len(rooms) > 1:
            detail = f"{len(rooms)} matching streamless classrooms for grade {code}"
            report("CONFLICT", "ClassRoom", classroom_name, detail)
            conflicts.append(f"ClassRoom {classroom_name}: {detail}")
            counts["CONFLICT"] += 1
        elif rooms:
            report("UNCHANGED", "ClassRoom", f"{classroom_name} ({code})")
            counts["UNCHANGED"] += 1
        else:
            room = ClassRoom(name=classroom_name, grade_level=grade, stream=None)
            save_validated(room)
            report("CREATED", "ClassRoom", f"{classroom_name} ({code})")
            counts["CREATED"] += 1


def ensure_departments(counts):
    departments = {}
    for display_name in DEPARTMENT_NAMES:
        department = Department.objects.filter(name__iexact=display_name).first()
        if department:
            report("UNCHANGED", "Department", department.name)
            counts["UNCHANGED"] += 1
        else:
            department = Department(name=display_name)
            save_validated(department)
            report("CREATED", "Department", display_name)
            counts["CREATED"] += 1
        departments[display_name] = department
    return departments


def ensure_subjects(departments, counts, conflicts):
    subjects = {}
    for name, (preferred_code, department_name, selectable) in SUBJECT_SPECS.items():
        matches = list(Subject.objects.filter(name__iexact=name))
        if len(matches) > 1:
            detail = f"{len(matches)} case-insensitive name matches"
            report("CONFLICT", "Subject", name, detail)
            conflicts.append(f"Subject {name}: {detail}")
            counts["CONFLICT"] += 1
            continue

        target_department = departments.get(department_name) if department_name else None
        if matches:
            subject = matches[0]
            if target_department and subject.department_id != target_department.id:
                subject.department = target_department
                save_validated(subject)
                report("UPDATED", "Subject", name, f"department -> {target_department.name}; PK={subject.pk}")
                counts["UPDATED"] += 1
            else:
                report("REUSE", "Subject", name, f"code={subject.subject_code}; PK={subject.pk}")
                counts["REUSE"] += 1
        else:
            code_owner = Subject.objects.filter(subject_code__iexact=preferred_code).first()
            if code_owner:
                detail = f"code {preferred_code} already belongs to {code_owner.name}"
                report("CONFLICT", "Subject", name, detail)
                conflicts.append(f"Subject {name}: {detail}")
                counts["CONFLICT"] += 1
                continue
            subject = Subject(
                name=name,
                subject_code=preferred_code,
                department=target_department,
                is_selectable=selectable,
                graded=True,
            )
            save_validated(subject)
            report("CREATED", "Subject", name, f"code={preferred_code}; department={department_name or 'none'}")
            counts["CREATED"] += 1
        subjects[name] = subject
    return subjects


def ensure_curriculum_mappings(curriculum, grades, subjects, counts):
    for code, subject_names in GRADE_SUBJECTS.items():
        grade = grades.get(code)
        if not grade:
            for subject_name in subject_names:
                report("SKIPPED", "CurriculumSubject", f"{subject_name} -> {code}", "grade unavailable")
                counts["SKIPPED"] += 1
            continue
        for subject_name in subject_names:
            subject = subjects.get(subject_name)
            if not subject:
                report("SKIPPED", "CurriculumSubject", f"{subject_name} -> {code}", "subject unavailable")
                counts["SKIPPED"] += 1
                continue
            mapping = CurriculumSubject.objects.filter(
                curriculum=curriculum, subject=subject, grade_level=grade
            ).first()
            if mapping:
                if not mapping.is_active:
                    mapping.is_active = True
                    save_validated(mapping)
                    report("UPDATED", "CurriculumSubject", f"{subject_name} -> {code}", "reactivated")
                    counts["UPDATED"] += 1
                else:
                    report("UNCHANGED", "CurriculumSubject", f"{subject_name} -> {code}")
                    counts["UNCHANGED"] += 1
            else:
                mapping = CurriculumSubject(curriculum=curriculum, subject=subject, grade_level=grade, is_active=True)
                save_validated(mapping)
                report("CREATED", "CurriculumSubject", f"{subject_name} -> {code}")
                counts["CREATED"] += 1


def print_existing_counts():
    def render(values):
        items = [str(value) for value in values]
        return ", ".join(items) if items else "none"

    print("\nExisting tenant records")
    print(f"  GradeLevels ({GradeLevel.objects.count()}): {render(GradeLevel.objects.values_list('system_code', flat=True))}")
    print(f"  ClassRooms ({ClassRoom.objects.count()}): {render(str(room) for room in ClassRoom.objects.select_related('grade_level', 'stream'))}")
    print(f"  Departments ({Department.objects.count()}): {render(Department.objects.values_list('name', flat=True))}")
    print(f"  Subjects ({Subject.objects.count()}): {render(Subject.objects.values_list('name', flat=True))}")
    mappings = CurriculumSubject.objects.select_related("curriculum", "subject", "grade_level")
    print(f"  CurriculumSubjects ({mappings.count()}): {render(str(mapping) for mapping in mappings)}")


def run_setup(tenant, curriculum_selector=None, dry_run=False):
    counts = Counter()
    conflicts = []
    with schema_context(tenant.schema_name):
        validate_freshness(tenant)
        print_existing_counts()
        print("\nPlanned/executed operations")
        try:
            with transaction.atomic():
                curriculum = ensure_curriculum(counts, curriculum_selector)
                print_header(tenant, curriculum, dry_run)
                grades = ensure_grade_levels(counts, conflicts)
                ensure_classrooms(grades, counts, conflicts)
                departments = ensure_departments(counts)
                subjects = ensure_subjects(departments, counts, conflicts)
                ensure_curriculum_mappings(curriculum, grades, subjects, counts)
                if dry_run:
                    raise DryRunRollback()
                if conflicts:
                    raise ConflictRollback()
        except DryRunRollback:
            print("\nDRY RUN: validation/save paths executed; transaction rolled back.")
        except ConflictRollback:
            print("\nLIVE WRITE BLOCKED: unresolved conflicts caused a full transaction rollback.")

    print("\nSummary")
    for status in ("CREATED", "UPDATED", "REUSE", "UNCHANGED", "SKIPPED", "CONFLICT"):
        print(f"  {status:<9}: {counts[status]}")
    if conflicts:
        print("\nUnresolved conflicts")
        for conflict in conflicts:
            print(f"  - {conflict}")
        print("\nLive execution is not recommended until these conflicts are reviewed.")
    elif not dry_run:
        print("\nSetup committed successfully.")
    return conflicts


def duplicate_report(tenant):
    with schema_context(tenant.schema_name):
        grade_keys = Counter(code.lower() for code in GradeLevel.objects.values_list("system_code", flat=True))
        department_keys = Counter(name.lower() for name in Department.objects.values_list("name", flat=True))
        subject_name_keys = Counter(name.lower() for name in Subject.objects.values_list("name", flat=True))
        subject_code_keys = Counter(code.lower() for code in Subject.objects.values_list("subject_code", flat=True))
        curriculum_keys = Counter(
            CurriculumSubject.objects.values_list("curriculum_id", "subject_id", "grade_level_id")
        )
        room_keys = Counter(
            (grade_id, stream_id, name.lower())
            for grade_id, stream_id, name in ClassRoom.objects.values_list("grade_level_id", "stream_id", "name")
        )
        checks = {
            "grade levels": sum(value > 1 for value in grade_keys.values()),
            "classrooms": sum(value > 1 for value in room_keys.values()),
            "departments": sum(value > 1 for value in department_keys.values()),
            "subject names": sum(value > 1 for value in subject_name_keys.values()),
            "subject codes": sum(value > 1 for value in subject_code_keys.values()),
            "curriculum subjects": sum(value > 1 for value in curriculum_keys.values()),
        }
        print("\nDuplicate natural-key report")
        for label, count in checks.items():
            print(f"  {label:<20}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Configure fresh tenant grade, classroom, department, subject, and curriculum data.")
    parser.add_argument("--tenant", required=True, help="Tenant schema, domain, or unambiguous school name.")
    parser.add_argument("--curriculum", help="Curriculum ID or exact name; optional for fresh tenant.")
    parser.add_argument("--dry-run", action="store_true", help="Execute validation and saves, then roll back.")
    parser.add_argument("--confirm-production", action="store_true", help="Required for production live writes.")
    args = parser.parse_args()

    environment, is_production = detect_environment()
    if is_production and not args.dry_run and not args.confirm_production:
        parser.error(f"{environment}: live production writes require --confirm-production")
    try:
        tenant = resolve_tenant(args.tenant)
        conflicts = run_setup(tenant, args.curriculum, args.dry_run)
        duplicate_report(tenant)
        if conflicts:
            sys.exit(2)
    except (ValueError, ValidationError) as exc:
        print(f"\nCONFIGURATION ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
