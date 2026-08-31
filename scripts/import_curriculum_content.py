#!/usr/bin/env python
"""Import structured curriculum content into an SSync tenant.

Supports:

    Curriculum
        -> CurriculumSubject
            -> CurriculumTopic
                -> optional operational Topic mapping
                    -> SubTopic
                    -> LearningObjective
                    -> CurriculumGuidance

Features:
- Resolves tenant by schema/domain/name.
- Can create Curriculum if missing.
- Can pre-create canonical CurriculumSubject records and enrich optional school Subject mappings.
- Normalizes subject names so "&", "And", and "and" match consistently.
- Prefixes duplicate cross-term topic names with their term/theme.
- Supports grade and subject filters.
- Supports dry-run rollback across curriculum creation, canonical subjects, and content.
- Protects production writes behind --confirm-production.
- Preserves existing CurriculumImportService validation/import behavior.

Examples:

Dry-run one subject:

    uv run python scripts/import_curriculum_content.py \
        --tenant green_valley_curriculum_test \
        --curriculum "JSS & SSS - NERDC Scheme (2025)" \
        --file data/nerdc_2025_jss_sss_ssync.json \
        --grade "JSS 1" \
        --subject "Mathematics" \
        --create-curriculum \
        --create-mappings \
        --dry-run

Live import one subject:

    uv run python scripts/import_curriculum_content.py \
        --tenant green_valley_curriculum_test \
        --curriculum "JSS & SSS - NERDC Scheme (2025)" \
        --file data/nerdc_2025_jss_sss_ssync.json \
        --grade "JSS 1" \
        --subject "Mathematics" \
        --create-curriculum \
        --create-mappings

Full curriculum dry-run:

    uv run python scripts/import_curriculum_content.py \
        --tenant green_valley_curriculum_test \
        --curriculum "JSS & SSS - NERDC Scheme (2025)" \
        --file data/nerdc_2025_jss_sss_ssync.json \
        --create-curriculum \
        --create-mappings \
        --dry-run
"""

import argparse
from collections import Counter
import os
import re
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "school.settings",
)

import django

django.setup()

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django_tenants.utils import schema_context

from academic.models import (
    Curriculum,
    CurriculumSubject,
    GradeLevel,
    Subject,
)
from academic.services.curriculum_import_service import (
    CurriculumImportError,
    CurriculumImportService,
    ImportMetrics,
    normalize_text,
)
from tenants.models import Client, Domain

# Module-level aliases delegating to the canonical service implementations.
normalize_grade_key = CurriculumImportService.normalize_grade_key


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def detect_environment() -> tuple[str, bool]:
    """Return environment label and whether it should be treated as production."""

    explicit = (
        os.getenv("ENVIRONMENT")
        or os.getenv("DJANGO_ENV")
        or os.getenv("APP_ENV")
    )

    if explicit:
        label = explicit.strip().upper()

        return (
            label,
            label in {
                "PRODUCTION",
                "PROD",
                "LIVE",
            },
        )

    base_domain = getattr(
        settings,
        "BASE_DOMAIN",
        "localhost",
    )

    if not settings.DEBUG and base_domain != "localhost":
        return "PRODUCTION", True

    if not settings.DEBUG:
        return "STAGING / PRODUCTION (DEBUG=False)", True

    return "LOCAL DEVELOPMENT", False


# ---------------------------------------------------------------------------
# Tenant resolution
# ---------------------------------------------------------------------------


def resolve_tenant(identifier: str) -> Client:
    """Resolve tenant using schema, domain, exact name, or unique partial name."""

    clean = identifier.strip()

    if clean.lower() in {
        "public",
        "public_schema",
        "public_tenant",
    }:
        raise ValueError(
            "The public tenant is forbidden."
        )

    tenants = Client.objects.exclude(
        schema_name="public"
    )

    # Exact schema.
    schema_matches = list(
        tenants.filter(
            schema_name__iexact=clean
        )
    )

    if len(schema_matches) == 1:
        return schema_matches[0]

    # Domain.
    domains = list(
        Domain.objects.filter(
            Q(domain__iexact=clean)
            | Q(domain__istartswith=f"{clean}.")
        )
        .exclude(
            tenant__schema_name="public"
        )
        .select_related("tenant")
    )

    domain_tenants = {
        item.tenant_id: item.tenant
        for item in domains
    }

    if len(domain_tenants) == 1:
        return next(
            iter(domain_tenants.values())
        )

    # Exact tenant name.
    exact_names = list(
        tenants.filter(
            name__iexact=clean
        )
    )

    if len(exact_names) == 1:
        return exact_names[0]

    # Partial tenant name.
    partial_names = list(
        tenants.filter(
            name__icontains=clean
        )
    )

    if len(partial_names) == 1:
        return partial_names[0]

    candidates = (
        schema_matches
        or list(domain_tenants.values())
        or exact_names
        or partial_names
    )

    if candidates:
        rendered = ", ".join(
            f"{tenant.name} [{tenant.schema_name}]"
            for tenant in candidates
        )

        raise ValueError(
            f"Ambiguous tenant '{clean}': {rendered}"
        )

    raise ValueError(
        f"No non-public tenant matches '{clean}'."
    )


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


def normalize_subject_name(
    value: str | None,
) -> str | None:
    """Return canonical subject display form.

    Examples:

        Physical & Health Education
        Physical And Health Education
        Physical AND Health Education

    become:

        Physical and Health Education
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return value

    value = re.sub(
        r"\s*&\s*",
        " and ",
        value,
    )

    value = re.sub(
        r"\bAND\b",
        "and",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def normalize_lookup_key(
    value: str | None,
) -> str:
    """Normalize names for loose DB matching.

    Handles:
        JSS 1
        JSS_1
        JSS-1

    and subject conjunction variations.
    """

    if value is None:
        return ""

    value = normalize_subject_name(
        str(value)
    ) or ""

    value = value.lower()

    value = re.sub(
        r"[_\-\s]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------


def model_field_names(model) -> set[str]:
    """Return writable concrete field names."""

    names: set[str] = set()

    for field in model._meta.get_fields():
        if not getattr(
            field,
            "concrete",
            False,
        ):
            continue

        if getattr(
            field,
            "auto_created",
            False,
        ):
            continue

        if getattr(
            field,
            "primary_key",
            False,
        ):
            continue

        names.add(field.name)

    return names


# ---------------------------------------------------------------------------
# Curriculum resolution / creation
# ---------------------------------------------------------------------------


def curriculum_create_kwargs(
    *,
    data: dict[str, Any],
    explicit_identifier: str | None,
) -> dict[str, Any]:
    """Build safe Curriculum kwargs from payload metadata."""

    payload = data.get(
        "curriculum"
    ) or {}

    name = (
        explicit_identifier
        or payload.get("name")
    )

    if not name:
        raise CurriculumImportError(
            "Cannot create curriculum: "
            "no curriculum name was supplied."
        )

    candidate_values = {
        "name": str(name).strip(),
        "version": payload.get("version"),
        "authority_type": payload.get(
            "authority_type"
        ),
        "description": payload.get(
            "description"
        ),
        "effective_from": payload.get(
            "effective_from"
        ),
        "effective_to": payload.get(
            "effective_to"
        ),
        "is_active": payload.get(
            "is_active",
            True,
        ),
    }

    allowed_fields = model_field_names(
        Curriculum
    )

    kwargs: dict[str, Any] = {}

    for field_name, value in candidate_values.items():
        if field_name not in allowed_fields:
            continue

        if value is None:
            continue

        kwargs[field_name] = value

    return kwargs


def resolve_or_create_curriculum(
    *,
    data: dict[str, Any],
    curriculum_identifier: str | None,
    create_if_missing: bool,
) -> tuple[Curriculum, bool]:
    """Resolve curriculum or create it when explicitly requested."""

    try:
        obj = CurriculumImportService.resolve_curriculum(
            data=data,
            curriculum=curriculum_identifier,
        )

        return obj, False

    except CurriculumImportError as exc:
        if not create_if_missing:
            raise

        message = str(exc).lower()

        expected_missing_messages = (
            "does not exist",
            "not found",
            "no curriculum",
            "no active curriculum",
        )

        if not any(
            marker in message
            for marker in expected_missing_messages
        ):
            raise

        kwargs = curriculum_create_kwargs(
            data=data,
            explicit_identifier=curriculum_identifier,
        )

        name = kwargs["name"]

        # Defensive duplicate check.
        existing_qs = Curriculum.objects.filter(
            name__iexact=name,
        )

        version = kwargs.get("version")
        if version:
            existing_qs = existing_qs.filter(
                version__iexact=version,
            )

        existing = existing_qs.first()

        if existing:
            if not existing.is_active:
                raise CurriculumImportError(
                    f"Curriculum '{name}'"
                    + (
                        f" version '{version}'"
                        if version
                        else ""
                    )
                    + " already exists but is inactive."
                )

            return existing, False

        obj = Curriculum(
            **kwargs
        )

        obj.full_clean()
        obj.save()

        return obj, True


# ---------------------------------------------------------------------------
# Subject resolution
# ---------------------------------------------------------------------------

def resolve_subject(
    subject_name: str,
) -> Subject:
    """Resolve through the canonical CurriculumImportService resolver."""

    subject = CurriculumImportService.resolve_subject(
        subject_name
    )

    if subject:
        return subject

    raise CurriculumImportError(
        f"Subject '{subject_name}' does not exist "
        f"in this tenant or configured curriculum-import aliases."
    )


# ---------------------------------------------------------------------------
# CurriculumSubject creation
# ---------------------------------------------------------------------------


def ensure_curriculum_subject_mappings(
    *,
    data: dict[str, Any],
    curriculum: Curriculum,
    grade_filter: str | None,
    subject_filter: str | None,
) -> tuple[int, int, int]:
    """Pre-create canonical curriculum subjects for the selected payload scope.

    Canonical identity is curriculum + grade level + normalized name. For V2,
    an operational Subject is optional enrichment. V1 retains its legacy
    requirement for an existing operational Subject.

    Returns:
        created_count,
        reused_count,
        skipped_count
    """

    created_count = 0
    reused_count = 0
    skipped_count = 0

    wanted_grade = (
        normalize_grade_key(
            grade_filter
        )
        if grade_filter
        else None
    )

    wanted_subject = (
        normalize_lookup_key(
            subject_filter
        )
        if subject_filter
        else None
    )

    is_v2 = CurriculumImportService._is_v2(data)

    payload_grades = data.get(
        "grades"
    ) or []

    for grade_payload in payload_grades:
        payload_grade_name = grade_payload.get(
            "grade"
        )

        if not payload_grade_name:
            skipped_count += 1
            continue

        if (
            wanted_grade
            and normalize_grade_key(
                payload_grade_name
            )
            != wanted_grade
        ):
            continue

        grade_level = CurriculumImportService.resolve_grade(
            payload_grade_name
        )
        if grade_level is None:
            raise CurriculumImportError(
                f"Grade '{payload_grade_name}' could not be resolved."
            )

        payload_subjects = (
            grade_payload.get(
                "subjects"
            )
            or []
        )

        for subject_payload in payload_subjects:
            payload_subject_name = (
                subject_payload.get(
                    "subject"
                )
            )

            if not payload_subject_name:
                skipped_count += 1
                continue

            normalized_subject = (
                normalize_subject_name(
                    payload_subject_name
                )
            )

            if (
                wanted_subject
                and normalize_lookup_key(
                    normalized_subject
                )
                != wanted_subject
            ):
                continue

            subject = CurriculumImportService.resolve_subject(normalized_subject)
            if subject is None and not is_v2:
                # Preserve legacy V1 behavior.
                resolve_subject(normalized_subject)

            mapping = CurriculumSubject.objects.filter(
                curriculum=curriculum,
                grade_level=grade_level,
                name__iexact=normalized_subject,
            ).first()
            created = mapping is None
            if created:
                mapping = CurriculumSubject.objects.create(
                    curriculum=curriculum,
                    grade_level=grade_level,
                    name=normalized_subject,
                    code=(subject.subject_code or "") if subject else "",
                    subject=subject,
                    is_active=True,
                )
            elif mapping.subject_id is None and subject is not None:
                mapping.subject = subject
                update_fields = ["subject", "updated_at"]
                if not mapping.code and subject.subject_code:
                    mapping.code = subject.subject_code
                    update_fields.append("code")
                mapping.save(update_fields=update_fields)

            if created:
                created_count += 1

                print(
                    "[Created Curriculum Subject] "
                    f"{mapping.name} -> "
                    f"{grade_level.default_name} "
                    f"[{grade_level.system_code}]"
                    + (f" · mapped to {subject.name}" if subject else " · no school Subject mapping")
                )

            else:
                reused_count += 1

    return (
        created_count,
        reused_count,
        skipped_count,
    )


# ---------------------------------------------------------------------------
# Payload subject normalization
# ---------------------------------------------------------------------------


def normalize_payload_subjects(
    data: dict[str, Any],
) -> int:
    """Normalize subject display names in-memory before validation/import.

    This does not modify the JSON file itself.

    Returns the number of subject names changed.
    """

    changed = 0

    for grade_payload in data.get(
        "grades"
    ) or []:
        for subject_payload in (
            grade_payload.get(
                "subjects"
            )
            or []
        ):
            original = subject_payload.get(
                "subject"
            )

            if not original:
                continue

            normalized = normalize_subject_name(
                original
            )

            if normalized != original:
                subject_payload[
                    "subject"
                ] = normalized

                changed += 1

    return changed


def normalize_topic_name_key(value: str | None) -> str:
    """Normalize topic names for duplicate detection only."""
    if not value:
        return ""

    value = str(value).strip().lower()
    value = value.replace("&", "and")
    value = re.sub(r"[_\-\s]+", " ", value)

    return re.sub(r"\s+", " ", value).strip()


def make_payload_topic_names_unique(
    data: dict[str, Any],
) -> int:
    """Guarantee unique topic names within each subject/grade payload.

    Stage 1:
        Repeated names across terms are prefixed with their term/theme.

        Midterm Exams
        Midterm Exams

    becomes:

        First Term - Midterm Exams
        Second Term - Midterm Exams

    Stage 2:
        If names are still duplicated within the same term, append a
        deterministic Part suffix.

        Third Term - Week 8
        Third Term - Week 8

    becomes:

        Third Term - Week 8 - Part 1
        Third Term - Week 8 - Part 2

    Only the in-memory payload is changed. The source JSON file is not
    modified.

    Returns the number of topic names changed.
    """

    changed = 0

    for grade_payload in data.get("grades") or []:
        for subject_payload in grade_payload.get("subjects") or []:
            topics = subject_payload.get("topics") or []

            # -------------------------------------------------------
            # Stage 1:
            # Prefix duplicates with their term/theme.
            # -------------------------------------------------------

            initial_counts = Counter(
                normalize_topic_name_key(
                    topic.get("name")
                )
                for topic in topics
                if topic.get("name")
            )

            for topic in topics:
                name = normalize_text(
                    topic.get("name")
                )

                if not name:
                    continue

                key = normalize_topic_name_key(
                    name
                )

                if initial_counts[key] <= 1:
                    continue

                term = normalize_text(
                    topic.get("theme")
                )

                if not term:
                    raise CurriculumImportError(
                        "Duplicate topic name "
                        f"'{name}' cannot be disambiguated because "
                        "the topic has no term/theme."
                    )

                prefix = f"{term} - "

                if not name.casefold().startswith(
                    prefix.casefold()
                ):
                    topic["name"] = (
                        f"{prefix}{name}"
                    )

                    changed += 1

            # -------------------------------------------------------
            # Stage 2:
            # Some source tables contain multiple rows for the same
            # week inside the same term, especially English.
            #
            # Add stable Part suffixes when Stage 1 still leaves
            # duplicate names.
            # -------------------------------------------------------

            post_prefix_counts = Counter(
                normalize_topic_name_key(
                    topic.get("name")
                )
                for topic in topics
                if topic.get("name")
            )

            duplicate_groups: dict[
                str,
                list[dict[str, Any]]
            ] = {}

            for topic in topics:
                name = normalize_text(
                    topic.get("name")
                )

                if not name:
                    continue

                key = normalize_topic_name_key(
                    name
                )

                if post_prefix_counts[key] <= 1:
                    continue

                duplicate_groups.setdefault(
                    key,
                    [],
                ).append(topic)

            for duplicate_topics in (
                duplicate_groups.values()
            ):
                # Preserve source/import ordering.
                duplicate_topics.sort(
                    key=lambda topic: (
                        topic.get("order")
                        if isinstance(
                            topic.get("order"),
                            int,
                        )
                        else 999999
                    )
                )

                for part_number, topic in enumerate(
                    duplicate_topics,
                    start=1,
                ):
                    original_name = normalize_text(
                        topic.get("name")
                    )

                    topic["name"] = (
                        f"{original_name} "
                        f"- Part {part_number}"
                    )

                    changed += 1

            # -------------------------------------------------------
            # Final safety assertion
            # -------------------------------------------------------

            final_seen: set[str] = set()

            grade_name = normalize_text(
                grade_payload.get("grade")
            )

            subject_name = normalize_text(
                subject_payload.get("subject")
            )

            for topic in topics:
                final_name = normalize_text(
                    topic.get("name")
                )

                if not final_name:
                    continue

                final_key = (
                    normalize_topic_name_key(
                        final_name
                    )
                )

                if final_key in final_seen:
                    raise CurriculumImportError(
                        "Topic normalization could not "
                        "produce unique names for "
                        f"{grade_name} > {subject_name}: "
                        f"'{final_name}'."
                    )

                final_seen.add(
                    final_key
                )

    return changed
# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def print_metrics_table(
    metrics: ImportMetrics,
) -> None:
    summary = metrics.get_summary()

    statuses = [
        "CREATED",
        "UPDATED",
        "REUSED",
        "UNCHANGED",
        "SKIPPED",
        "CONFLICT",
    ]

    entities = [
        "CurriculumSource",
        "CurriculumSubject",
        "Topic",
        "CurriculumTopic",
        "SubTopic",
        "LearningObjective",
        "CurriculumGuidance",
        "PublishedScheme",
        "PublishedSchemeEntry",
        "CurriculumResource",
    ]

    print(
        "\n"
        + "=" * 90
    )

    print(
        f"{'Entity':<22} "
        + " ".join(
            f"{status:>10}"
            for status in statuses
        )
    )

    print(
        "=" * 90
    )

    for entity in entities:
        row = summary.get(
            entity,
            {},
        )

        values = " ".join(
            f"{row.get(status, 0):>10}"
            for status in statuses
        )

        print(
            f"{entity:<22} {values}"
        )

    print(
        "-" * 90
    )

    totals = " ".join(
        f"{metrics.total(status):>10}"
        for status in statuses
    )

    print(
        f"{'TOTAL':<22} {totals}"
    )

    print(
        "=" * 90
    )


# ---------------------------------------------------------------------------
# CLI display
# ---------------------------------------------------------------------------


def print_import_header(
    *,
    environment: str,
    tenant: Client,
    curriculum_obj: Curriculum,
    curriculum_created: bool,
    source_file: str,
    grade_filter: str | None,
    subject_filter: str | None,
    create_mappings: bool,
    dry_run: bool,
) -> None:
    print(
        "\n"
        + "=" * 78
    )

    print(
        "SSync Curriculum Content Importer"
    )

    print(
        "=" * 78
    )

    print(
        f"Environment : {environment}"
    )

    print(
        "Database    : "
        f"{connection.settings_dict.get('ENGINE')} / "
        f"{connection.settings_dict.get('NAME')}"
    )

    print(
        f"Tenant      : "
        f"{tenant.name} "
        f"[{tenant.schema_name}]"
    )

    print(
        f"Curriculum  : "
        f"{curriculum_obj.name} "
        f"(Version: "
        f"{curriculum_obj.version or 'N/A'}, "
        f"ID: {curriculum_obj.pk})"
    )

    print(
        "Curriculum  : "
        + (
            "NEW — will be created"
            if curriculum_created
            else "EXISTING"
        )
    )

    print(
        f"Source File : {source_file}"
    )

    print(
        f"Grade Filter: "
        f"{grade_filter or 'ALL'}"
    )

    print(
        f"Subj Filter : "
        f"{subject_filter or 'ALL'}"
    )

    print(
        f"Pre-create  : "
        f"{'CANONICAL SUBJECTS + OPTIONAL MAPPINGS' if create_mappings else 'SERVICE-MANAGED'}"
    )

    print(
        "Mode        : "
        + (
            "DRY RUN (rollback)"
            if dry_run
            else "LIVE COMMIT"
        )
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Import structured curriculum content "
            "(topics, subtopics, objectives, guidance, "
            "published schemes, scheme entries and resources) "
            "from canonical JSON."
        )
    )

    parser.add_argument(
        "--tenant",
        required=True,
        help=(
            "Tenant schema, domain, or "
            "unambiguous school name."
        ),
    )

    parser.add_argument(
        "--file",
        required=True,
        help=(
            "Path to canonical curriculum JSON file."
        ),
    )

    parser.add_argument(
        "--curriculum",
        help=(
            "Curriculum ID, name, or version. "
            "Optional if defined in the payload."
        ),
    )

    parser.add_argument(
        "--create-curriculum",
        action="store_true",
        help=(
            "Create the Curriculum record if it "
            "does not already exist."
        ),
    )

    parser.add_argument(
        "--create-mappings",
        action="store_true",
        help=(
            "Pre-create canonical CurriculumSubject records in the selected payload scope "
            "and attach optional matching school Subjects when available. Canonical V2 "
            "imports do this automatically and do not require this flag."
        ),
    )

    parser.add_argument(
        "--grade",
        help=(
            "Filter import to one grade level "
            "(e.g. JSS 1, JSS_1, Primary 1)."
        ),
    )

    parser.add_argument(
        "--subject",
        help=(
            "Filter import to one subject. "
            "'&', 'And', and 'and' are treated equivalently."
        ),
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Abort on any importer warning."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Execute all validation and ORM save paths "
            "inside a transaction and roll everything back."
        ),
    )

    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help=(
            "Required for live production writes."
        ),
    )

    args = parser.parse_args()

    environment, is_production = (
        detect_environment()
    )

    if (
        is_production
        and not args.dry_run
        and not args.confirm_production
    ):
        parser.error(
            f"{environment}: live production writes "
            "require --confirm-production"
        )

    source_path = Path(
        args.file
    )

    if not source_path.exists():
        parser.error(
            f"Curriculum JSON file does not exist: "
            f"{source_path}"
        )

    if not source_path.is_file():
        parser.error(
            f"Curriculum JSON path is not a file: "
            f"{source_path}"
        )

    grade_filter = (
        args.grade.strip()
        if args.grade
        else None
    )

    subject_filter = (
        normalize_subject_name(
            args.subject
        )
        if args.subject
        else None
    )

    try:
        tenant = resolve_tenant(
            args.tenant
        )

        data = (
            CurriculumImportService
            .load_json(
                str(source_path)
            )
        )

        normalized_count = (
            normalize_payload_subjects(
                data
            )
        )

        is_v2 = CurriculumImportService._is_v2(data)

        # Topic-name deduplication (term-prefix + Part-N suffix) must NEVER run
        # for V2 payloads. V2 canonical JSON uses topic_key for identity, and
        # duplicate topic names in V2 are intentional (same topic, multiple terms).
        if is_v2:
            topic_name_normalized_count = 0
        else:
            topic_name_normalized_count = (
                make_payload_topic_names_unique(
                    data
                )
            )

        with schema_context(
            tenant.schema_name
        ):
            # One outer transaction controls the entire lifecycle:
            #
            # Curriculum creation
            # Optional canonical CurriculumSubject pre-creation/enrichment
            # Source/batch creation
            # Topic import
            #
            # This guarantees --dry-run rolls everything back.
            with transaction.atomic():

                (
                    curriculum_obj,
                    curriculum_created,
                ) = resolve_or_create_curriculum(
                    data=data,
                    curriculum_identifier=args.curriculum,
                    create_if_missing=args.create_curriculum,
                )

                print_import_header(
                    environment=environment,
                    tenant=tenant,
                    curriculum_obj=curriculum_obj,
                    curriculum_created=curriculum_created,
                    source_file=str(source_path),
                    grade_filter=grade_filter,
                    subject_filter=subject_filter,
                    create_mappings=args.create_mappings,
                    dry_run=args.dry_run,
                )

                if normalized_count:
                    print(
                        "\n[Normalization] "
                        f"{normalized_count} payload subject "
                        f"name(s) normalized."
                    )

                if topic_name_normalized_count:
                    print(
                        "\n[Normalization] "
                        f"{topic_name_normalized_count} duplicate topic "
                        f"name(s) prefixed with their term/theme."
                    )

                # ---------------------------------------------------
                # Optionally pre-create canonical CurriculumSubjects and enrich mappings
                # ---------------------------------------------------

                if args.create_mappings:
                    (
                        mapping_created,
                        mapping_reused,
                        mapping_skipped,
                    ) = ensure_curriculum_subject_mappings(
                        data=data,
                        curriculum=curriculum_obj,
                        grade_filter=grade_filter,
                        subject_filter=subject_filter,
                    )

                    print(
                        "\nCanonical CurriculumSubjects:"
                    )

                    print(
                        f"  Created : "
                        f"{mapping_created}"
                    )

                    print(
                        f"  Reused  : "
                        f"{mapping_reused}"
                    )

                    print(
                        f"  Skipped : "
                        f"{mapping_skipped}"
                    )

                # ---------------------------------------------------
                # Preflight
                # ---------------------------------------------------

                errors = (
                    CurriculumImportService
                    .validate(
                        data=data,
                        curriculum=curriculum_obj,
                        grade_filter=grade_filter,
                        subject_filter=subject_filter,
                        strict=args.strict,
                    )
                )

                if errors:
                    print(
                        "\nPREFLIGHT VALIDATION FAILED:"
                    )

                    for error in errors:
                        print(
                            f"  [ERROR] {error}"
                        )

                    raise CurriculumImportError(
                        "Preflight validation failed: "
                        + "; ".join(
                            str(error)
                            for error in errors
                        )
                    )

                print(
                    "\nPreflight validation passed. "
                    "Executing import..."
                )

                # ---------------------------------------------------
                # Content import
                # ---------------------------------------------------

                (
                    metrics,
                    source_obj,
                    batch_obj,
                ) = (
                    CurriculumImportService
                    .import_content(
                        data=data,
                        curriculum=curriculum_obj,
                        grade_filter=grade_filter,
                        subject_filter=subject_filter,

                        # The outer transaction controls dry-run.
                        dry_run=False,

                        strict=args.strict,
                    )
                )

                # ---------------------------------------------------
                # Provenance
                # ---------------------------------------------------

                if source_obj:
                    source_version = (
                        source_obj.version
                        or source_obj.publication_year
                        or "N/A"
                    )

                    print(
                        "\n[Provenance] "
                        f"Source Document: "
                        f"{source_obj.title} "
                        f"({source_version})"
                    )

                    if (
                        source_obj.checksum_sha256
                    ):
                        print(
                            "[Provenance] "
                            "SHA-256 Hash   : "
                            f"{source_obj.checksum_sha256}"
                        )

                if batch_obj:
                    print(
                        "[Provenance] "
                        f"Import Batch   : "
                        f"#{batch_obj.id} "
                        f"(UUID: "
                        f"{batch_obj.public_id})"
                    )

                print_metrics_table(
                    metrics
                )

                # ---------------------------------------------------
                # Dry-run rollback
                # ---------------------------------------------------

                if args.dry_run:
                    print(
                        "\nDRY RUN SUCCESSFUL."
                    )

                    print(
                        "All curriculum, optional mapping, provenance, "
                        "and content changes will be rolled back."
                    )

                    transaction.set_rollback(
                        True
                    )

                else:
                    if curriculum_created:
                        print(
                            "\n[Created] Curriculum: "
                            f"{curriculum_obj.name} "
                            f"(ID: {curriculum_obj.pk})"
                        )

                    print(
                        "\nLIVE COMMIT SUCCESSFUL."
                    )

                    print(
                        "Curriculum content imported "
                        "successfully."
                    )

    except (
        ValueError,
        CurriculumImportError,
    ) as exc:
        print(
            f"\nIMPORT ERROR: {exc}"
        )

        errors = getattr(
            exc,
            "errors",
            None,
        )

        if errors:
            for error in errors:
                print(
                    f"  - {error}"
                )

        sys.exit(1)

    except Exception as exc:
        print(
            f"\nUNEXPECTED IMPORT ERROR: "
            f"{type(exc).__name__}: {exc}"
        )

        raise


if __name__ == "__main__":
    main()
