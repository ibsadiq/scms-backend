"""Canonical Curriculum JSON V2 Validator.

Validates Canonical V2 payloads (schema_version == "2.0") without database access.
Returns a ValidationReport containing ERRORs, WARNINGs, and INFOs.

This module is intentionally dependency-free (no Django, no DB models) so it can
be used from standalone scripts and CI pipelines without a configured Django
environment.

Usage::

    from academic.services.curriculum_v2_validator import validate_v2

    report = validate_v2(data)
    if report.has_errors:
        for issue in report.get_errors():
            print(issue)
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "2.0"

VALID_ENTRY_TYPES: frozenset[str] = frozenset([
    "INSTRUCTION",
    "REVISION",
    "ASSESSMENT",
    "EXAMINATION",
    "BREAK",
    "PREPARATION",
    "CLOSING",
    "OTHER",
])

VALID_RESOURCE_TYPES: frozenset[str] = frozenset([
    "PRESCRIBED_TEXT",
    "RECOMMENDED_TEXT",
    "REFERENCE",
    "INSTRUCTIONAL_NOTE",
    "EVALUATION",
    "ASSIGNMENT",
    "PRACTICAL",
    "EXAMPLE",
    "OTHER",
])

# A theme that looks like a term label is an error: it belongs on a scheme entry.
_TERM_LABEL_RE = re.compile(
    r"^(first|second|third|1st|2nd|3rd)\s+term\b",
    re.IGNORECASE,
)

# Heuristics for quality warnings on text fields.
_MERGED_WORD_RE = re.compile(r"[a-z][A-Z]|[a-zA-Z]{25,}")
_TRUNCATED_ENDINGS_RE = re.compile(
    r"\b(?:activi|assess|histo|learni|muham|niger|peopl|pharao|prono|"
    r"revie|simpl|stori|writ)$",
    re.IGNORECASE,
)
_HEADER_FOOTER_RE = re.compile(
    r"(?:scheme\s+of\s+wor?k|back\s+to\s+table|get\s+access|\d+\s*\|\s*\d{3})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    location: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.location}: {self.message} (code={self.code})"


@dataclass
class ValidationReport:
    """Aggregated result of V2 payload validation."""

    issues: list[ValidationIssue] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)

    def error(self, code: str, message: str, location: str) -> None:
        self.issues.append(ValidationIssue(Severity.ERROR, code, message, location))

    def warning(self, code: str, message: str, location: str) -> None:
        self.issues.append(ValidationIssue(Severity.WARNING, code, message, location))

    def info(self, code: str, message: str, location: str) -> None:
        self.issues.append(ValidationIssue(Severity.INFO, code, message, location))

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    def get_errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def get_warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def get_infos(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.INFO]

    def error_messages(self) -> list[str]:
        """Flat list of error message strings for use in CurriculumImportService."""
        return [str(i) for i in self.get_errors()]

    def warning_messages(self) -> list[str]:
        return [str(i) for i in self.get_warnings()]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def make_topic_key(name: str) -> str:
    """Generate a deterministic URL-safe slug from a topic name."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode()
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"[\s-]+", "-", name)
    return name.strip("-")


def _loc(*parts: str | None) -> str:
    return " > ".join(str(p) for p in parts if p)


def _inspect_text(
    value: Any,
    location: str,
    report: ValidationReport,
    *,
    is_name_field: bool = False,
    max_name_len: int = 200,
) -> None:
    if not isinstance(value, str) or not value:
        return
    stripped = value.strip()
    if "\ufffd" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        report.error("BROKEN_UNICODE", "Broken Unicode character detected.", location)
    if value != " ".join(value.split()):
        report.warning("MALFORMED_WHITESPACE", "Malformed whitespace in value.", location)
    if _HEADER_FOOTER_RE.search(value):
        report.error("HEADER_FOOTER_BLEED", "Probable header/footer bleed.", location)
    if is_name_field:
        if len(stripped) > max_name_len:
            report.warning("OVERSIZED_NAME", f"Name length {len(stripped)} exceeds {max_name_len}.", location)
        if _MERGED_WORD_RE.search(stripped):
            report.warning("SUSPECTED_MERGED_WORDS", "Suspected merged words (possible PDF artefact).", location)
        if _TRUNCATED_ENDINGS_RE.search(stripped):
            report.warning("PROBABLE_TRUNCATION", "Probable truncated word or phrase.", location)


# ---------------------------------------------------------------------------
# Subject-level sub-validators
# ---------------------------------------------------------------------------

def _validate_topics(
    topics_data: list[Any],
    subject_loc: str,
    report: ValidationReport,
    counts: Counter,
) -> tuple[dict[str, str], dict[str, set[str]], dict[str, set[int]]]:
    """Validate topics for one subject.

    Returns:
        topic_key_map:    topic_key -> topic name
        subtopics_map:    topic_key -> set of casefold subtopic names
        objectives_map:   topic_key -> set of LO order values
    """
    topic_key_map: dict[str, str] = {}
    subtopics_map: dict[str, set[str]] = defaultdict(set)
    objectives_map: dict[str, set[int]] = defaultdict(set)
    seen_topic_keys: dict[str, list[int]] = defaultdict(list)

    for t_idx, topic_item in enumerate(topics_data, 1):
        counts["topics"] += 1
        topic_loc = _loc(subject_loc, f"topic#{t_idx}")

        if not isinstance(topic_item, dict):
            report.error("INVALID_TOPIC", "Topic must be an object.", topic_loc)
            continue

        name = (topic_item.get("name") or "").strip()
        if not name:
            report.error("TOPIC_NAME_EMPTY", "Topic 'name' must not be empty.", f"{topic_loc}.name")
            continue

        _inspect_text(name, f"{topic_loc}.name", report, is_name_field=True, max_name_len=200)

        # topic_key
        explicit_key = (topic_item.get("topic_key") or "").strip()
        derived_key = make_topic_key(name)
        if not explicit_key:
            topic_key = derived_key
            report.warning(
                "MISSING_TOPIC_KEY",
                f"No 'topic_key' on topic '{name}'; derived as '{topic_key}'.",
                f"{topic_loc}.topic_key",
            )
        else:
            topic_key = explicit_key
            if topic_key != derived_key:
                report.info(
                    "CUSTOM_TOPIC_KEY",
                    f"Explicit topic_key '{topic_key}' differs from auto-derived '{derived_key}'.",
                    f"{topic_loc}.topic_key",
                )

        seen_topic_keys[topic_key].append(t_idx)
        topic_key_map[topic_key] = name

        # theme
        theme = (topic_item.get("theme") or "").strip()
        if theme and _TERM_LABEL_RE.match(theme):
            report.error(
                "THEME_IS_TERM",
                (
                    f"'theme' value '{theme}' is a term label. "
                    "Use 'term_number' on published_scheme entries instead."
                ),
                f"{topic_loc}.theme",
            )
        if not theme:
            report.warning("MISSING_THEME", "Topic has no 'theme' (pedagogical strand).", f"{topic_loc}.theme")

        if not (topic_item.get("content_summary") or "").strip():
            report.info("EMPTY_CONTENT_SUMMARY", "Topic 'content_summary' is empty.", f"{topic_loc}.content_summary")

        # _source
        src = topic_item.get("_source") or {}
        if not src:
            report.warning("MISSING_PROVENANCE", "Topic has no '_source' provenance block.", topic_loc)
        else:
            p_start = src.get("page_start")
            p_end = src.get("page_end")
            if p_start is not None and (not isinstance(p_start, int) or p_start < 1):
                report.error("INVALID_PAGE_START", "'_source.page_start' must be a positive integer.", f"{topic_loc}._source")
            if (
                p_end is not None and p_start is not None
                and isinstance(p_end, int) and isinstance(p_start, int)
                and p_end < p_start
            ):
                report.error("INVALID_PAGE_RANGE", "'_source.page_end' < 'page_start'.", f"{topic_loc}._source")

        # subtopics
        subtopics_raw = topic_item.get("subtopics") or []
        if not isinstance(subtopics_raw, list):
            report.error("BAD_SUBTOPICS", "'subtopics' must be a list.", f"{topic_loc}.subtopics")
            subtopics_raw = []

        seen_sub_keys: dict[str, int] = {}
        for sub_idx, sub_item in enumerate(subtopics_raw, 1):
            counts["subtopics"] += 1
            sub_loc = f"{topic_loc}.subtopics[{sub_idx}]"

            if isinstance(sub_item, str):
                sub_name = sub_item.strip()
            elif isinstance(sub_item, dict):
                sub_name = (sub_item.get("name") or "").strip()
                sub_order = sub_item.get("order")
                if sub_order is not None and (not isinstance(sub_order, int) or sub_order < 1):
                    report.error("INVALID_SUBTOPIC_ORDER", "'order' must be a positive integer.", f"{sub_loc}.order")
            else:
                report.error("INVALID_SUBTOPIC", "Subtopic must be a string or object.", sub_loc)
                continue

            if not sub_name:
                report.error("SUBTOPIC_NAME_EMPTY", "Subtopic 'name' must not be empty.", f"{sub_loc}.name")
                continue

            _inspect_text(sub_name, sub_loc, report, is_name_field=True, max_name_len=240)
            key = sub_name.casefold()
            if key in seen_sub_keys:
                report.error(
                    "DUPLICATE_SUBTOPIC",
                    f"Duplicate subtopic '{sub_name}' within topic (first at #{seen_sub_keys[key]}).",
                    sub_loc,
                )
            else:
                seen_sub_keys[key] = sub_idx
                subtopics_map[topic_key].add(key)

        # learning_objectives
        objectives_raw = topic_item.get("learning_objectives") or []
        if not isinstance(objectives_raw, list):
            report.error("BAD_OBJECTIVES", "'learning_objectives' must be a list.", f"{topic_loc}.learning_objectives")
            objectives_raw = []

        seen_lo_orders: set[int] = set()
        for lo_idx, lo_item in enumerate(objectives_raw, 1):
            counts["learning_objectives"] += 1
            lo_loc = f"{topic_loc}.learning_objectives[{lo_idx}]"
            if not isinstance(lo_item, dict):
                report.error("INVALID_LO", "Learning objective must be an object.", lo_loc)
                continue
            desc = (lo_item.get("description") or "").strip()
            if not desc:
                report.error("LO_DESC_EMPTY", "'description' must not be empty.", f"{lo_loc}.description")
            lo_order = lo_item.get("order")
            if not isinstance(lo_order, int) or lo_order < 1:
                report.error("INVALID_LO_ORDER", "'order' must be a positive integer.", f"{lo_loc}.order")
            elif lo_order in seen_lo_orders:
                report.error("DUPLICATE_LO_ORDER", f"Duplicate objective 'order' {lo_order}.", f"{lo_loc}.order")
            else:
                seen_lo_orders.add(lo_order)
                objectives_map[topic_key].add(lo_order)
            subtopic_ref = lo_item.get("subtopic_ref")
            if subtopic_ref and subtopic_ref.casefold() not in subtopics_map[topic_key]:
                report.error(
                    "UNRESOLVED_LO_SUBTOPIC_REF",
                    f"'subtopic_ref' '{subtopic_ref}' not found in topic's 'subtopics'.",
                    f"{lo_loc}.subtopic_ref",
                )

        # guidance
        guidance = topic_item.get("guidance")
        if guidance is not None and not isinstance(guidance, dict):
            report.error("BAD_GUIDANCE", "'guidance' must be an object or null.", f"{topic_loc}.guidance")

    for key, indices in seen_topic_keys.items():
        if len(indices) > 1:
            report.error(
                "DUPLICATE_TOPIC_KEY",
                f"topic_key '{key}' used by {len(indices)} topics (indices {indices}).",
                f"{subject_loc}.topics",
            )

    return topic_key_map, subtopics_map, objectives_map


def _validate_published_schemes(
    schemes_data: list[Any],
    subject_loc: str,
    topic_key_map: dict[str, str],
    subtopics_map: dict[str, set[str]],
    report: ValidationReport,
    counts: Counter,
) -> set[str]:
    """Validate published_schemes for one subject.

    Returns all valid entry_key values across all schemes.
    """
    all_entry_keys: set[str] = set()
    counts["published_schemes"] += len(schemes_data)

    for sc_idx, scheme_item in enumerate(schemes_data, 1):
        scheme_loc = _loc(subject_loc, f"published_scheme#{sc_idx}")
        if not isinstance(scheme_item, dict):
            report.error("INVALID_SCHEME", "Published scheme must be an object.", scheme_loc)
            continue

        scheme_name = (scheme_item.get("name") or "").strip()
        if not scheme_name:
            report.warning("SCHEME_NAME_EMPTY", "Published scheme has no 'name'.", f"{scheme_loc}.name")

        entries_data = scheme_item.get("entries") or []
        if not isinstance(entries_data, list):
            report.error("BAD_ENTRIES", "'entries' must be a list.", f"{scheme_loc}.entries")
            entries_data = []

        counts["published_scheme_entries"] += len(entries_data)
        seen_entry_keys: dict[str, int] = {}
        seen_entry_orders: dict[tuple, int] = {}

        for e_idx, entry_item in enumerate(entries_data, 1):
            entry_loc = _loc(scheme_loc, f"entry#{e_idx}")
            if not isinstance(entry_item, dict):
                report.error("INVALID_ENTRY", "Scheme entry must be an object.", entry_loc)
                continue

            # entry_key
            entry_key = (entry_item.get("entry_key") or "").strip()
            if not entry_key:
                report.error("MISSING_ENTRY_KEY", "Scheme entry must have a non-empty 'entry_key'.", f"{entry_loc}.entry_key")
            elif entry_key in seen_entry_keys:
                report.error(
                    "DUPLICATE_ENTRY_KEY",
                    f"entry_key '{entry_key}' already used by entry #{seen_entry_keys[entry_key]}.",
                    f"{entry_loc}.entry_key",
                )
            else:
                seen_entry_keys[entry_key] = e_idx
                all_entry_keys.add(entry_key)

            # term_number
            term_number = entry_item.get("term_number")
            if term_number not in (1, 2, 3):
                report.error("INVALID_TERM", f"'term_number' must be 1, 2, or 3 (got {term_number!r}).", f"{entry_loc}.term_number")

            # week_start / week_end
            week_start = entry_item.get("week_start")
            week_end = entry_item.get("week_end")
            if week_start is not None:
                if not isinstance(week_start, int) or week_start < 1:
                    report.error("INVALID_WEEK_START", f"'week_start' must be positive (got {week_start!r}).", f"{entry_loc}.week_start")
            if week_end is not None:
                if not isinstance(week_end, int) or week_end < 1:
                    report.error("INVALID_WEEK_END", f"'week_end' must be positive (got {week_end!r}).", f"{entry_loc}.week_end")
                elif week_start is None:
                    report.error(
                        "WEEK_END_WITHOUT_START",
                        "'week_end' requires a non-null 'week_start'.",
                        f"{entry_loc}.week_end",
                    )
                elif week_start is not None and isinstance(week_start, int) and week_end < week_start:
                    report.error("INVALID_WEEK_RANGE", f"'week_end' ({week_end}) < 'week_start' ({week_start}).", f"{entry_loc}.week_end")

            # entry_type
            entry_type = (entry_item.get("entry_type") or "").upper().strip()
            if entry_type not in VALID_ENTRY_TYPES:
                report.error(
                    "INVALID_ENTRY_TYPE",
                    f"'entry_type' '{entry_type}' invalid. Valid: {sorted(VALID_ENTRY_TYPES)}.",
                    f"{entry_loc}.entry_type",
                )

            # topic_ref
            topic_ref = entry_item.get("topic_ref")
            if topic_ref:
                if topic_ref not in topic_key_map:
                    report.error(
                        "UNRESOLVED_TOPIC_REF",
                        f"'topic_ref' '{topic_ref}' not found in this subject's topic_keys.",
                        f"{entry_loc}.topic_ref",
                    )
                else:
                    counts["entries_with_topic"] = counts.get("entries_with_topic", 0) + 1
            else:
                if entry_type == "INSTRUCTION":
                    report.warning("INSTRUCTION_WITHOUT_TOPIC", "INSTRUCTION entry has no 'topic_ref'.", f"{entry_loc}.topic_ref")
                counts["entries_without_topic"] = counts.get("entries_without_topic", 0) + 1

            # subtopic_refs
            subtopic_refs = entry_item.get("subtopic_refs") or []
            if not isinstance(subtopic_refs, list):
                report.error("BAD_SUBTOPIC_REFS", "'subtopic_refs' must be a list.", f"{entry_loc}.subtopic_refs")
                subtopic_refs = []
            if subtopic_refs and topic_ref and topic_ref in topic_key_map:
                valid_subs = subtopics_map.get(topic_ref, set())
                for sub_ref in subtopic_refs:
                    if isinstance(sub_ref, str) and sub_ref.casefold() not in valid_subs:
                        report.warning(
                            "UNRESOLVED_SUBTOPIC_REF",
                            f"subtopic_ref '{sub_ref}' not found in topic '{topic_ref}'.",
                            f"{entry_loc}.subtopic_refs",
                        )

            # order duplicate within (term_number, order)
            order = entry_item.get("order")
            if order is not None and isinstance(term_number, int) and term_number in (1, 2, 3):
                pair = (term_number, order)
                if pair in seen_entry_orders:
                    report.warning(
                        "DUPLICATE_ENTRY_ORDER",
                        f"Duplicate (term_number={term_number}, order={order}) — already at entry #{seen_entry_orders[pair]}.",
                        f"{entry_loc}.order",
                    )
                else:
                    seen_entry_orders[pair] = e_idx

    return all_entry_keys


def _validate_resources(
    resources_data: list[Any],
    subject_loc: str,
    topic_key_map: dict[str, str],
    all_entry_keys: set[str],
    report: ValidationReport,
    counts: Counter,
) -> None:
    """Validate resources for one subject."""
    counts["resources"] += len(resources_data)

    for r_idx, resource_item in enumerate(resources_data, 1):
        res_loc = _loc(subject_loc, f"resource#{r_idx}")
        if not isinstance(resource_item, dict):
            report.error("INVALID_RESOURCE", "Resource must be an object.", res_loc)
            continue

        res_type = (resource_item.get("resource_type") or "").upper().strip()
        if res_type not in VALID_RESOURCE_TYPES:
            report.error(
                "INVALID_RESOURCE_TYPE",
                f"'resource_type' '{res_type}' invalid. Valid: {sorted(VALID_RESOURCE_TYPES)}.",
                f"{res_loc}.resource_type",
            )

        title = (resource_item.get("title") or "").strip()
        if not title:
            report.error("RESOURCE_TITLE_EMPTY", "Resource 'title' must not be empty.", f"{res_loc}.title")
        else:
            _inspect_text(title, f"{res_loc}.title", report, is_name_field=True)

        res_topic_ref = resource_item.get("topic_ref")
        if res_topic_ref and res_topic_ref not in topic_key_map:
            report.error(
                "UNRESOLVED_RESOURCE_TOPIC_REF",
                f"Resource 'topic_ref' '{res_topic_ref}' not found in this subject's topic_keys.",
                f"{res_loc}.topic_ref",
            )

        entry_ref = resource_item.get("published_scheme_entry_ref")
        if entry_ref and entry_ref not in all_entry_keys:
            report.error(
                "UNRESOLVED_ENTRY_REF",
                f"'published_scheme_entry_ref' '{entry_ref}' not found in any scheme entry.",
                f"{res_loc}.published_scheme_entry_ref",
            )

        if not (resource_item.get("_source") or {}):
            report.info("MISSING_RESOURCE_PROVENANCE", "No '_source' block.", res_loc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_v2(data: dict[str, Any]) -> ValidationReport:
    """Validate a Canonical V2 curriculum payload.

    Returns a ValidationReport. Does not require Django or a database.

    For payloads without ``schema_version``, an INFO signals V1 fallback;
    structural V2 checks (topic_key uniqueness, entry_key, theme-is-term) still run.
    """
    report = ValidationReport()
    counts: Counter = Counter()

    if not isinstance(data, dict):
        report.error("BAD_ROOT", "Payload root must be a JSON object.", "root")
        report.metrics = dict(counts)
        return report

    version = data.get("schema_version")
    if version is None:
        report.info(
            "V1_FALLBACK",
            "No 'schema_version' present — treating as V1.",
            "root.schema_version",
        )
    elif version != SCHEMA_VERSION:
        report.error(
            "WRONG_SCHEMA_VERSION",
            f"Expected schema_version '{SCHEMA_VERSION}', got {version!r}.",
            "root.schema_version",
        )

    curriculum_meta = data.get("curriculum")
    if not isinstance(curriculum_meta, dict):
        report.error("MISSING_CURRICULUM", "'curriculum' must be an object.", "root.curriculum")
    elif not (curriculum_meta.get("name") or "").strip():
        report.error("CURRICULUM_NAME_EMPTY", "'curriculum.name' is required.", "root.curriculum.name")

    source_meta = data.get("source")
    if isinstance(source_meta, dict):
        if not (source_meta.get("title") or "").strip():
            report.error("SOURCE_TITLE_EMPTY", "'source.title' must be non-empty.", "root.source.title")
        chk = ((source_meta.get("checksum_sha256") or "")).lower().strip()
        if chk:
            if len(chk) != 64:
                report.error("INVALID_CHECKSUM_LEN", "checksum_sha256 must be 64 hex chars.", "root.source.checksum_sha256")
            else:
                try:
                    int(chk, 16)
                except ValueError:
                    report.error("INVALID_CHECKSUM_CHARS", "checksum_sha256 has non-hex chars.", "root.source.checksum_sha256")

    grades_data = data.get("grades")
    if not isinstance(grades_data, list) or not grades_data:
        report.error("MISSING_GRADES", "'grades' must be a non-empty list.", "root.grades")
        report.metrics = dict(counts)
        return report

    counts["grades"] = len(grades_data)

    for g_idx, grade_item in enumerate(grades_data, 1):
        if not isinstance(grade_item, dict):
            report.error("INVALID_GRADE", f"Grade #{g_idx} must be an object.", f"grades[{g_idx}]")
            continue

        grade_name = (grade_item.get("grade") or "").strip()
        if not grade_name:
            report.error("MISSING_GRADE_ID", f"Grade #{g_idx} missing 'grade' id.", f"grades[{g_idx}].grade")
            continue

        grade_loc = f"grade={grade_name}"
        subjects_data = grade_item.get("subjects")
        if not isinstance(subjects_data, list):
            report.error("MISSING_SUBJECTS", "'subjects' must be a list.", f"{grade_loc}.subjects")
            continue

        for s_idx, subject_item in enumerate(subjects_data, 1):
            if not isinstance(subject_item, dict):
                report.error("INVALID_SUBJECT", f"Subject #{s_idx} must be an object.", f"{grade_loc}.subjects[{s_idx}]")
                continue

            subject_name = (subject_item.get("subject") or "").strip()
            if not subject_name:
                report.error("MISSING_SUBJECT_NAME", f"Subject #{s_idx} has no 'subject' name.", f"{grade_loc}.subjects[{s_idx}].subject")
                continue

            subject_loc = _loc(grade_loc, f"subject={subject_name}")
            counts["grade_subject_mappings"] += 1

            topics_data = subject_item.get("topics") or []
            if not isinstance(topics_data, list):
                report.error("BAD_TOPICS", "'topics' must be a list.", f"{subject_loc}.topics")
                topics_data = []

            topic_key_map, subtopics_map, _objectives_map = _validate_topics(
                topics_data, subject_loc, report, counts
            )

            schemes_data = subject_item.get("published_schemes") or []
            if not isinstance(schemes_data, list):
                report.error("BAD_PUBLISHED_SCHEMES", "'published_schemes' must be a list.", f"{subject_loc}.published_schemes")
                schemes_data = []

            all_entry_keys = _validate_published_schemes(
                schemes_data, subject_loc, topic_key_map, subtopics_map, report, counts
            )

            resources_data = subject_item.get("resources") or []
            if not isinstance(resources_data, list):
                report.error("BAD_RESOURCES", "'resources' must be a list.", f"{subject_loc}.resources")
                resources_data = []

            _validate_resources(
                resources_data, subject_loc, topic_key_map, all_entry_keys, report, counts
            )

    report.metrics = dict(counts)
    return report
