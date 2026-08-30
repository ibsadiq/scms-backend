"""Curriculum Content Import Service.

Handles ingestion, validation, preview, provenance resolution, and persistence of
structured curriculum content (V1 and Canonical V2):
    CurriculumSubject
        -> Topic
        -> CurriculumTopic
            -> SubTopic
            -> LearningObjective
            -> CurriculumGuidance
        -> PublishedScheme
            -> PublishedSchemeEntry
        -> CurriculumResource

Supports provenance tracking via CurriculumSource and CurriculumImportBatch.
V2 payloads are identified by ``schema_version == "2.0"``.
"""

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from academic.models import (
    Curriculum,
    CurriculumGuidance,
    CurriculumImportBatch,
    CurriculumResource,
    CurriculumResourceType,
    CurriculumSource,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    ImportBatchStatus,
    LearningObjective,
    PublishedScheme,
    PublishedSchemeEntry,
    PublishedSchemeEntryType,
    SourceType,
    SubTopic,
    Subject,
    Topic,
)
from academic.models.choices import CurriculumAuthority, StandardClassCode

logger = logging.getLogger(__name__)


class CurriculumImportError(Exception):
    """Raised when curriculum content import validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


class DryRunRollback(Exception):
    """Internal sentinel exception used to force transaction rollback during dry-runs."""
    pass


def normalize_text(text: str | None) -> str:
    """Strip leading/trailing whitespace and collapse internal consecutive whitespace."""
    if not text:
        return ""
    return " ".join(str(text).strip().split())


@dataclass
class ImportMetrics:
    """Structured counters for all entities during import."""
    counts: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "CurriculumSource": Counter(),
            "Topic": Counter(),
            "CurriculumTopic": Counter(),
            "SubTopic": Counter(),
            "LearningObjective": Counter(),
            "CurriculumGuidance": Counter(),
            # V2 entities
            "PublishedScheme": Counter(),
            "PublishedSchemeEntry": Counter(),
            "CurriculumResource": Counter(),
        }
    )

    def record(self, entity: str, status: str, count: int = 1):
        self.counts[entity][status] += count

    def get_summary(self) -> dict[str, dict[str, int]]:
        return {entity: dict(counter) for entity, counter in self.counts.items()}

    def total(self, status: str) -> int:
        return sum(counter[status] for counter in self.counts.values())


class CurriculumImportService:
    """Service for parsing, validating, previewing, and importing curriculum content with provenance.

    Supports both V1 (no schema_version) and Canonical V2 (schema_version == "2.0") payloads.
    """

    # ── Schema detection ───────────────────────────────────────────────────

    @staticmethod
    def _is_v2(data: dict[str, Any]) -> bool:
        """Return True when the payload declares Canonical V2 schema."""
        return data.get("schema_version") == "2.0"

    # ── Text normalization ─────────────────────────────────────────────────

    @staticmethod
    def normalize_multiline_text(text: str | None) -> str:
        """Normalize multiline text, preserving paragraph breaks.

        Each line is individually stripped and internal whitespace runs are
        collapsed, but line separators are kept so that block content (teacher
        activities, content summaries, resource content) retains structure.
        """
        if not text:
            return ""
        lines = str(text).splitlines()
        normalized = "\n".join(" ".join(line.split()) for line in lines)
        # Collapse three or more consecutive blank lines into two.
        import re as _re
        normalized = _re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def make_topic_key(name: str) -> str:
        """Derive a canonical URL-safe slug from a topic name.

        Used to build the in-memory topic_key → CurriculumTopic lookup map
        when a V2 payload omits explicit topic_key values.

        Examples::

            make_topic_key("Number Base System") -> "number-base-system"
            make_topic_key("HCF (Highest Common Factor)") -> "hcf-highest-common-factor"
        """
        import unicodedata as _ud
        import re as _re
        name = _ud.normalize("NFKD", name)
        name = name.encode("ascii", "ignore").decode()
        name = name.lower().strip()
        name = _re.sub(r"[^a-z0-9\s-]", "", name)
        name = _re.sub(r"[\s-]+", "-", name)
        return name.strip("-")

    # ── JSON subtopic normalization ────────────────────────────────────────

    @staticmethod
    def _normalize_subtopics_to_v2(
        subtopics_raw: list[Any],
    ) -> list[dict[str, Any]]:
        """Normalise a subtopic list to V2 object form ``{name, order}``.

        V1 payloads supply plain strings; V2 payloads supply objects.
        Both are normalised to ``{"name": str, "order": int}``.
        String items have their order assigned from their 1-based position.
        """
        result: list[dict[str, Any]] = []
        for idx, item in enumerate(subtopics_raw, 1):
            if isinstance(item, str):
                name = normalize_text(item)
                if name:
                    result.append({"name": name, "order": idx})
            elif isinstance(item, dict):
                name = normalize_text(item.get("name"))
                if name:
                    result.append({"name": name, "order": item.get("order", idx)})
        return result

    @staticmethod
    def load_json(file_path: str | Path) -> dict[str, Any]:
        """Loads and parses a curriculum JSON file."""
        path = Path(file_path)
        if not path.exists():
            raise CurriculumImportError(f"Curriculum file not found: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise CurriculumImportError(f"Invalid JSON in {path}: {exc}") from exc
        except Exception as exc:
            raise CurriculumImportError(f"Failed to read {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise CurriculumImportError("Curriculum JSON root must be an object/dict.")
        return data

    @classmethod
    def resolve_curriculum(
        cls,
        *,
        data: dict[str, Any],
        curriculum: Curriculum | str | None = None,
    ) -> Curriculum:
        """
        Resolves and verifies the target Curriculum model instance.
        Never creates a Curriculum record.
        """
        if isinstance(curriculum, Curriculum):
            target = curriculum
        elif isinstance(curriculum, str) and curriculum.strip():
            sel = curriculum.strip()
            if sel.isdigit():
                target = Curriculum.objects.filter(pk=int(sel)).first()
            else:
                target = Curriculum.objects.filter(
                    Q(name__iexact=sel) | Q(version__iexact=sel)
                ).first()
            if not target:
                raise CurriculumImportError(
                    f"Specified curriculum '{sel}' does not exist in this tenant."
                )
        else:
            curr_meta = data.get("curriculum", {})
            name = normalize_text(curr_meta.get("name"))
            version = normalize_text(curr_meta.get("version"))
            qs = Curriculum.objects.filter(is_active=True)
            if name:
                qs = qs.filter(name__iexact=name)
            if version:
                qs = qs.filter(version__iexact=version)
            matches = list(qs)
            if len(matches) == 1:
                target = matches[0]
            elif len(matches) > 1:
                options = ", ".join(f"{c.id}: {c}" for c in matches)
                raise CurriculumImportError(
                    f"Ambiguous curriculum metadata in payload. Matches: {options}"
                )
            else:
                raise CurriculumImportError(
                    "No active Curriculum matching payload metadata found. "
                    "Ensure Phase 1 academic setup has been run."
                )

        curr_meta = data.get("curriculum")
        if isinstance(curr_meta, dict) and curr_meta.get("name"):
            expected_name = normalize_text(curr_meta.get("name"))
            if target.name.lower() != expected_name.lower():
                raise CurriculumImportError(
                    f"Payload curriculum name '{expected_name}' does not match target curriculum '{target.name}'."
                )
        if isinstance(curr_meta, dict) and curr_meta.get("version"):
            expected_version = normalize_text(curr_meta.get("version"))
            if target.version.lower() != expected_version.lower():
                raise CurriculumImportError(
                    f"Payload curriculum version '{expected_version}' does not match target curriculum version '{target.version}'."
                )

        return target

    @classmethod
    def resolve_source(
        cls,
        *,
        data: dict[str, Any],
        curriculum: Curriculum,
        source: CurriculumSource | None = None,
        created_by: Any | None = None,
        metrics: ImportMetrics | None = None,
    ) -> CurriculumSource | None:
        """
        Resolves or creates a CurriculumSource instance.
        Validates cross-curriculum integrity and deduplicates by checksum.
        """
        if source is not None:
            if source.curriculum_id != curriculum.id:
                raise CurriculumImportError(
                    f"Supplied source '{source.title}' belongs to curriculum '{source.curriculum}' "
                    f"which does not match target curriculum '{curriculum}'."
                )
            if metrics:
                metrics.record("CurriculumSource", "REUSED")
            return source

        src_data = data.get("source")
        if not src_data or not isinstance(src_data, dict):
            return None

        title = normalize_text(src_data.get("title"))
        if not title:
            raise CurriculumImportError("Source metadata must contain a non-empty 'title'.")

        raw_checksum = normalize_text(src_data.get("checksum_sha256") or src_data.get("checksum"))
        clean_checksum = raw_checksum.lower()

        if clean_checksum:
            if len(clean_checksum) != 64:
                raise CurriculumImportError("Source checksum_sha256 must be exactly 64 hexadecimal characters.")
            try:
                int(clean_checksum, 16)
            except ValueError:
                raise CurriculumImportError("Source checksum_sha256 contains invalid hexadecimal characters.")

            # Search by unique curriculum + checksum
            existing_source = CurriculumSource.objects.filter(
                curriculum=curriculum,
                checksum_sha256=clean_checksum,
            ).first()

            if existing_source:
                if metrics:
                    metrics.record("CurriculumSource", "REUSED")
                return existing_source

        # Parse optional fields
        authority = normalize_text(src_data.get("authority"))
        version = normalize_text(src_data.get("version"))
        filename = normalize_text(src_data.get("original_filename") or src_data.get("filename"))
        source_ref = normalize_text(src_data.get("source_reference") or src_data.get("reference"))
        pub_year = src_data.get("publication_year")
        if pub_year is not None:
            try:
                pub_year = int(pub_year)
            except (ValueError, TypeError):
                pub_year = None

        src_type_str = normalize_text(src_data.get("source_type") or "PDF").upper()
        if src_type_str in SourceType.values:
            source_type = src_type_str
        else:
            source_type = SourceType.OTHER

        source_obj = CurriculumSource(
            curriculum=curriculum,
            title=title,
            authority=authority,
            publication_year=pub_year,
            version=version,
            original_filename=filename,
            source_type=source_type,
            source_reference=source_ref,
            checksum_sha256=clean_checksum,
            metadata=src_data.get("metadata", {}),
            created_by=created_by,
        )
        source_obj.full_clean()
        source_obj.save()

        if metrics:
            metrics.record("CurriculumSource", "CREATED")

        return source_obj

    @staticmethod
    def normalize_grade_key(value: str | None) -> str:
        """Normalize external grade labels to SSync system codes."""

        if not value:
            return ""

        value = normalize_text(value).upper()
        value = re.sub(r"[\s\-]+", "_", value)
        value = re.sub(r"_+", "_", value).strip("_")

        aliases = {
            "PRENURSERY": "PRE_NURSERY",
            "PRE_NURSERY": "PRE_NURSERY",

            "NURSERY1": "NURSERY_1",
            "NURSERY_1": "NURSERY_1",

            "NURSERY2": "NURSERY_2",
            "NURSERY_2": "NURSERY_2",

            "NURSERY3": "NURSERY_3",
            "NURSERY_3": "NURSERY_3",

            "PRIMARY1": "BASIC_1",
            "PRIMARY_1": "BASIC_1",
            "BASIC1": "BASIC_1",
            "BASIC_1": "BASIC_1",
            "YEAR1": "BASIC_1",
            "YEAR_1": "BASIC_1",

            "PRIMARY2": "BASIC_2",
            "PRIMARY_2": "BASIC_2",
            "BASIC2": "BASIC_2",
            "BASIC_2": "BASIC_2",
            "YEAR2": "BASIC_2",
            "YEAR_2": "BASIC_2",

            "PRIMARY3": "BASIC_3",
            "PRIMARY_3": "BASIC_3",
            "BASIC3": "BASIC_3",
            "BASIC_3": "BASIC_3",
            "YEAR3": "BASIC_3",
            "YEAR_3": "BASIC_3",

            "PRIMARY4": "BASIC_4",
            "PRIMARY_4": "BASIC_4",
            "BASIC4": "BASIC_4",
            "BASIC_4": "BASIC_4",
            "YEAR4": "BASIC_4",
            "YEAR_4": "BASIC_4",

            "PRIMARY5": "BASIC_5",
            "PRIMARY_5": "BASIC_5",
            "BASIC5": "BASIC_5",
            "BASIC_5": "BASIC_5",
            "YEAR5": "BASIC_5",
            "YEAR_5": "BASIC_5",

            "PRIMARY6": "BASIC_6",
            "PRIMARY_6": "BASIC_6",
            "BASIC6": "BASIC_6",
            "BASIC_6": "BASIC_6",
            "YEAR6": "BASIC_6",
            "YEAR_6": "BASIC_6",

            "JSS1": "JSS_1",
            "JSS_1": "JSS_1",
            "JSS2": "JSS_2",
            "JSS_2": "JSS_2",
            "JSS3": "JSS_3",
            "JSS_3": "JSS_3",

            "SSS1": "SS_1",
            "SSS_1": "SS_1",
            "SS1": "SS_1",
            "SS_1": "SS_1",

            "SSS2": "SS_2",
            "SSS_2": "SS_2",
            "SS2": "SS_2",
            "SS_2": "SS_2",

            "SSS3": "SS_3",
            "SSS_3": "SS_3",
            "SS3": "SS_3",
            "SS_3": "SS_3",
        }

        compact = value.replace("_", "")

        return aliases.get(
            value,
            aliases.get(compact, value),
        )

    @classmethod
    def resolve_grade(
        cls,
        grade_spec: str,
    ) -> GradeLevel | None:
        """Resolve GradeLevel using normalized SSync system codes."""

        wanted = cls.normalize_grade_key(
            grade_spec
        )

        grade = GradeLevel.objects.filter(
            system_code__iexact=wanted
        ).first()

        if grade:
            return grade

        for candidate in GradeLevel.objects.all():
            candidate_keys = {
                cls.normalize_grade_key(
                    candidate.system_code
                ),
                cls.normalize_grade_key(
                    candidate.default_name
                ),
            }

            if candidate.alias:
                candidate_keys.add(
                    cls.normalize_grade_key(
                        candidate.alias
                    )
                )

            if wanted in candidate_keys:
                return candidate

        return None

    @staticmethod
    def normalize_subject_key(value: str | None) -> str:
        """Return a comparison key for tolerant subject-name matching.

        Treats "&" and the word "and" as equivalent while preserving the
        canonical Subject.name stored in the database.

        Examples:
            "Physical & Health Education"
            "Physical and Health Education"
            "Physical And Health Education"

        all normalize to the same comparison key.
        """
        clean = normalize_text(value).casefold()
        clean = re.sub(r"\s*&\s*", " and ", clean)
        clean = re.sub(r"\band\b", " and ", clean)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    @classmethod
    def resolve_subject(cls, subject_spec: str) -> Subject | None:
        clean = normalize_text(subject_spec)

        if not clean:
            return None

        alias_key = cls.normalize_subject_key(clean)

        aliases = {
            "catering and craft practice": "Catering and Craft Practice",
            "computer hardware and gsm repairs": "Computer Hardware",
            "financial accounting": "Financial Accounting",
            "food and nutrition": "Foods & Nutrition",
            "english studies": "English Language",
            "fashion design and garment making": "Fashion",
            "islamic religious studies": "Islamic Studies",
            "solar photovoltaic (pv) installation and maintenance": "Solar",

            #pre-primary aliases
            "literacy": "Letter Work",
            "literacy (letter work)": "Letter Work",
            "literacy (language domain)": "Language Domain",
            "numeracy": "Number Work",
            "pre-science": "Science",
            "social habits": "Social Habits",
            "personal development": "Personal Development",
            "civic education": "Citizenship and Heritage Studies",
            "creativity": "Creative Art",
            "songs and rhymes": "Rhymes",
            "songs & rhymes": "Rhymes",
            "prevocational studies": "Pre-Vocational Studies",
            "french language": "French",
        }

        canonical_alias = aliases.get(alias_key)

        if canonical_alias:
            return Subject.objects.filter(
                name__iexact=canonical_alias
            ).first()

        exact = Subject.objects.filter(
            Q(subject_code__iexact=clean)
            | Q(name__iexact=clean)
        ).first()

        if exact:
            return exact

        wanted = cls.normalize_subject_key(clean)

        matches = [
            subject
            for subject in Subject.objects.all()
            if cls.normalize_subject_key(subject.name) == wanted
        ]

        if len(matches) == 1:
            return matches[0]

        return None

    @classmethod
    def is_grade_selected(
        cls,
        grade_spec: str,
        grade_filter: str | None,
    ) -> bool:
        if not grade_filter:
            return True

        return (
            cls.normalize_grade_key(
                grade_spec
            )
            ==
            cls.normalize_grade_key(
                grade_filter
            )
        )

    @classmethod
    def is_subject_selected(cls, subject_spec: str, subject_filter: str | None) -> bool:
        """Return whether a payload subject matches the requested filter.

        Subject codes are matched case-insensitively. Subject names use the
        same tolerant canonical comparison as resolve_subject(), so "&" and
        "and" do not cause filters to miss otherwise identical subjects.
        """
        if not subject_filter:
            return True

        filter_text = normalize_text(subject_filter)
        spec_text = normalize_text(subject_spec)

        if spec_text.casefold() == filter_text.casefold():
            return True

        if (
            cls.normalize_subject_key(spec_text)
            == cls.normalize_subject_key(filter_text)
        ):
            return True

        subject_obj = cls.resolve_subject(subject_spec)
        if not subject_obj:
            return False

        return (
            subject_obj.subject_code.casefold() == filter_text.casefold()
            or cls.normalize_subject_key(subject_obj.name)
            == cls.normalize_subject_key(filter_text)
        )

    @classmethod
    def validate(
        cls,
        *,
        data: dict[str, Any],
        curriculum: Curriculum | str | None = None,
        source: CurriculumSource | None = None,
        grade_filter: str | None = None,
        subject_filter: str | None = None,
        strict: bool = False,
    ) -> list[str]:
        """Perform full structural, relational, and provenance preflight validation.

        For V2 payloads (schema_version == "2.0") the Canonical V2 validator runs
        first; its ERRORs are returned immediately before any DB round-trips.
        WARNINGs are included when ``strict=True``.

        For V1 payloads the existing traversal is used unchanged.

        Returns a list of error strings (empty list means valid).
        """
        errors = []

        # ── V2 semantic validation (no DB) ──────────────────────────────────
        if cls._is_v2(data):
            from academic.services.curriculum_v2_validator import validate_v2
            v2_report = validate_v2(data)
            errors.extend(v2_report.error_messages())
            if strict:
                errors.extend(v2_report.warning_messages())
            if errors:
                return errors
            
        is_v2 = cls._is_v2(data)
        

        # 1. Resolve Curriculum
        try:
            curriculum_obj = cls.resolve_curriculum(data=data, curriculum=curriculum)
        except CurriculumImportError as exc:
            return [str(exc)]

        # 2. Validate Source if present
        if source is not None and source.curriculum_id != curriculum_obj.id:
            errors.append(
                f"Supplied source belongs to curriculum '{source.curriculum}' "
                f"which does not match target curriculum '{curriculum_obj}'."
            )

        src_data = data.get("source")
        if src_data and isinstance(src_data, dict):
            if not normalize_text(src_data.get("title")):
                errors.append("Source metadata must contain a non-empty 'title'.")
            chk = normalize_text(src_data.get("checksum_sha256") or src_data.get("checksum")).lower()
            if chk:
                if len(chk) != 64:
                    errors.append("Source checksum_sha256 must be exactly 64 hexadecimal characters.")
                else:
                    try:
                        int(chk, 16)
                    except ValueError:
                        errors.append("Source checksum_sha256 contains invalid hexadecimal characters.")

        grades_data = data.get("grades")
        if not isinstance(grades_data, list) or len(grades_data) == 0:
            errors.append("Payload must contain a non-empty 'grades' list.")
            return errors

        # 3. Traverse Grades -> Subjects -> Topics -> SubTopics / Objectives / Guidance
        for g_idx, grade_item in enumerate(grades_data, 1):
            if not isinstance(grade_item, dict):
                errors.append(f"Grade entry #{g_idx} must be an object.")
                continue

            raw_grade = grade_item.get("grade")
            if not raw_grade or not str(raw_grade).strip():
                errors.append(f"Grade entry #{g_idx} is missing 'grade' identifier.")
                continue

            grade_str = str(raw_grade).strip()
            if not cls.is_grade_selected(grade_str, grade_filter):
                continue

            grade_obj = cls.resolve_grade(grade_str)
            if not grade_obj:
                errors.append(
                    f"Grade '{grade_str}' (entry #{g_idx}) does not exist in this school. "
                    "Ensure GradeLevels are configured."
                )
                continue

            subjects_data = grade_item.get("subjects")
            if not isinstance(subjects_data, list) or len(subjects_data) == 0:
                errors.append(f"Grade '{grade_str}' must contain a non-empty 'subjects' list.")
                continue

            for s_idx, subject_item in enumerate(subjects_data, 1):
                if not isinstance(subject_item, dict):
                    errors.append(f"Grade '{grade_str}' > Subject entry #{s_idx} must be an object.")
                    continue

                raw_subject = subject_item.get("subject")
                if not raw_subject or not str(raw_subject).strip():
                    errors.append(f"Grade '{grade_str}' > Subject entry #{s_idx} is missing 'subject' identifier.")
                    continue

                subject_str = str(raw_subject).strip()
                if not cls.is_subject_selected(subject_str, subject_filter):
                    continue

                subject_obj = cls.resolve_subject(subject_str)
                if not subject_obj and not cls._is_v2(data):
                    errors.append(
                        f"Subject '{subject_str}' in Grade '{grade_str}' does not exist in canonical catalog."
                    )
                    continue

                cs_mapping = CurriculumSubject.objects.filter(
                    curriculum=curriculum_obj,
                    grade_level=grade_obj,
                ).filter(
                    Q(name__iexact=subject_str)
                    | (Q(subject=subject_obj) if subject_obj else Q(pk__isnull=True))
                ).first()
                if not cs_mapping and not cls._is_v2(data):
                    errors.append(
                        f"CurriculumSubject mapping missing for {subject_str} -> {grade_obj.system_code} "
                        f"in curriculum '{curriculum_obj}'. Run Phase 1 setup first."
                    )
                    continue

                topics_data = subject_item.get("topics")
                if not isinstance(topics_data, list):
                    errors.append(
                        f"{grade_str} > {subject_str}: 'topics' must be a list."
                    )
                    continue
                if not topics_data and not cls._is_v2(data):
                    errors.append(
                        f"{grade_str} > {subject_str}: must contain a non-empty 'topics' list."
                    )
                    continue

                seen_topic_names: set[str] = set()
                seen_topic_keys: set[str] = set()
                seen_topic_orders: set[int] = set()


                for t_idx, topic_item in enumerate(topics_data, 1):
                    ctx = f"{grade_str} > {subject_str} > Topic #{t_idx}"
                    if not isinstance(topic_item, dict):
                        errors.append(f"{ctx} must be an object.")
                        continue

                    raw_name = topic_item.get("name")
                    name = normalize_text(raw_name)
                    if not name:
                        errors.append(f"{ctx}: Topic 'name' cannot be blank.")
                        continue

                    name_lower = name.lower()

                    if is_v2:
                        topic_key = normalize_text(
                            topic_item.get("topic_key")
                        )

                        if not topic_key:
                            errors.append(
                                f"{ctx}: V2 topic 'topic_key' cannot be blank."
                            )
                        else:
                            topic_key_lower = topic_key.lower()

                            if topic_key_lower in seen_topic_keys:
                                errors.append(
                                    f"{ctx}: Duplicate topic_key "
                                    f"'{topic_key}' in same subject/grade import."
                                )

                            seen_topic_keys.add(topic_key_lower)

                    else:
                        if name_lower in seen_topic_names:
                            errors.append(
                                f"{ctx}: Duplicate topic name "
                                f"'{name}' in same subject/grade import."
                            )

                        seen_topic_names.add(name_lower)

                    order = topic_item.get("order")
                    if order is None or not isinstance(order, int) or order <= 0:
                        errors.append(f"{ctx} ('{name}'): 'order' must be a positive integer.")
                    elif order in seen_topic_orders:
                        errors.append(f"{ctx} ('{name}'): Duplicate topic order '{order}' in same subject/grade import.")
                    else:
                        seen_topic_orders.add(order)

                    # Topic-level provenance validation
                    topic_src = topic_item.get("_source") or topic_item.get("source")
                    if topic_src and isinstance(topic_src, dict):
                        p_start = topic_src.get("page_start")
                        p_end = topic_src.get("page_end")
                        if p_start is not None and (not isinstance(p_start, int) or p_start <= 0):
                            errors.append(f"{ctx} ('{name}'): 'page_start' must be a positive integer.")
                        if p_end is not None and (not isinstance(p_end, int) or p_end <= 0):
                            errors.append(f"{ctx} ('{name}'): 'page_end' must be a positive integer.")
                        if (
                            isinstance(p_start, int)
                            and isinstance(p_end, int)
                            and p_start > 0
                            and p_end > 0
                            and p_end < p_start
                        ):
                            errors.append(f"{ctx} ('{name}'): 'page_end' cannot be less than 'page_start'.")

                    # SubTopics validation
                    subtopics_raw = topic_item.get("subtopics", [])
                    defined_subtopics = set()
                    if subtopics_raw:
                        if not isinstance(subtopics_raw, list):
                            errors.append(f"{ctx} ('{name}'): 'subtopics' must be a list of strings.")
                        else:
                            for sub_idx, sub_item in enumerate(subtopics_raw, 1):
                                sub_name = normalize_text(sub_item)
                                max_subtopic_length = (
                                    SubTopic._meta
                                    .get_field("name")
                                    .max_length
                                    or 255
                                )

                                if len(sub_name) > max_subtopic_length:
                                    # Allowed: persistence will shorten the display name
                                    # while preserving the full text in content_summary.
                                    logger.debug(
                                        "Subtopic exceeds %s characters and will "
                                        "be shortened during import: %s",
                                        max_subtopic_length,
                                        sub_name,
                                    )
                                if not sub_name:
                                    errors.append(f"{ctx} ('{name}') > SubTopic #{sub_idx} cannot be blank.")
                                    continue
                                sub_lower = sub_name.lower()
                                if sub_lower in defined_subtopics:
                                    errors.append(
                                        f"{ctx} ('{name}'): Duplicate subtopic name '{sub_name}' within topic."
                                    )
                                defined_subtopics.add(sub_lower)

                    # LearningObjectives validation
                    objectives_raw = topic_item.get("learning_objectives", [])
                    if objectives_raw:
                        if not isinstance(objectives_raw, list):
                            errors.append(f"{ctx} ('{name}'): 'learning_objectives' must be a list.")
                        else:
                            seen_lo_orders = set()
                            for lo_idx, lo_item in enumerate(objectives_raw, 1):
                                lo_ctx = f"{ctx} ('{name}') > Objective #{lo_idx}"
                                if not isinstance(lo_item, dict):
                                    errors.append(f"{lo_ctx} must be an object.")
                                    continue

                                desc = normalize_text(lo_item.get("description"))
                                if not desc:
                                    errors.append(f"{lo_ctx}: 'description' cannot be blank.")

                                lo_order = lo_item.get("order")
                                if lo_order is None or not isinstance(lo_order, int) or lo_order <= 0:
                                    errors.append(f"{lo_ctx}: 'order' must be a positive integer.")
                                elif lo_order in seen_lo_orders:
                                    errors.append(f"{lo_ctx}: Duplicate objective order '{lo_order}' in topic.")
                                else:
                                    seen_lo_orders.add(lo_order)

                                lo_subtopic = lo_item.get("subtopic")
                                if lo_subtopic:
                                    clean_sub = normalize_text(lo_subtopic).lower()
                                    if clean_sub not in defined_subtopics:
                                        errors.append(
                                            f"{lo_ctx}: Referenced subtopic '{lo_subtopic}' is not defined in topic's 'subtopics' list."
                                        )

                                lo_src = lo_item.get("_source") or lo_item.get("source")
                                if lo_src and isinstance(lo_src, dict):
                                    lo_page = lo_src.get("page") if "page" in lo_src else lo_src.get("source_page")
                                    if lo_page is not None and (not isinstance(lo_page, int) or lo_page <= 0):
                                        errors.append(f"{lo_ctx}: 'page' must be a positive integer.")

                    # Guidance validation
                    guidance_raw = topic_item.get("guidance")
                    if guidance_raw is not None and not isinstance(guidance_raw, dict):
                        errors.append(f"{ctx} ('{name}'): 'guidance' must be an object/dict.")

        return errors

    @classmethod
    def preview(
        cls,
        *,
        data: dict[str, Any],
        curriculum: Curriculum | str | None = None,
        source: CurriculumSource | None = None,
        grade_filter: str | None = None,
        subject_filter: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyzes payload against current database state and returns planned actions summary.
        Does not write to DB.
        """
        errors = cls.validate(
            data=data,
            curriculum=curriculum,
            source=source,
            grade_filter=grade_filter,
            subject_filter=subject_filter,
        )
        if errors:
            raise CurriculumImportError("Preflight validation failed.", errors=errors)

        curriculum_obj = cls.resolve_curriculum(data=data, curriculum=curriculum)
        metrics = ImportMetrics()

        for grade_item in data.get("grades", []):
            grade_str = str(grade_item.get("grade", "")).strip()
            if not cls.is_grade_selected(grade_str, grade_filter):
                for s in grade_item.get("subjects", []):
                    for t in s.get("topics", []):
                        metrics.record("Topic", "SKIPPED")
                        metrics.record("CurriculumTopic", "SKIPPED")
                continue

            grade_obj = cls.resolve_grade(grade_str)
            for subject_item in grade_item.get("subjects", []):
                subject_str = str(subject_item.get("subject", "")).strip()
                if not cls.is_subject_selected(subject_str, subject_filter):
                    for t in subject_item.get("topics", []):
                        metrics.record("Topic", "SKIPPED")
                        metrics.record("CurriculumTopic", "SKIPPED")
                    continue

                subject_obj = cls.resolve_subject(subject_str)
                cs_mapping = CurriculumSubject.objects.filter(
                    curriculum=curriculum_obj,
                    subject=subject_obj,
                    grade_level=grade_obj,
                ).first()

                for topic_item in subject_item.get("topics", []):
                    topic_name = normalize_text(topic_item.get("name"))
                    existing_topic = Topic.objects.filter(
                        grade_level=grade_obj,
                        subject=subject_obj,
                        name__iexact=topic_name,
                    ).first()

                    if existing_topic:
                        metrics.record("Topic", "REUSED")
                    else:
                        metrics.record("Topic", "CREATED")

                    for sub_name_raw in topic_item.get("subtopics", []):
                        sub_name = normalize_text(sub_name_raw)
                        if existing_topic and SubTopic.objects.filter(
                            topic=existing_topic, name__iexact=sub_name
                        ).exists():
                            metrics.record("SubTopic", "REUSED")
                        else:
                            metrics.record("SubTopic", "CREATED")

                    existing_ct = None
                    if existing_topic and cs_mapping:
                        existing_ct = CurriculumTopic.objects.filter(
                            curriculum_subject=cs_mapping,
                            topic=existing_topic,
                        ).first()

                    order = topic_item.get("order", 1)
                    theme = normalize_text(topic_item.get("theme", ""))
                    content_summary = normalize_text(topic_item.get("content_summary", ""))

                    topic_src = topic_item.get("_source") or topic_item.get("source") or {}
                    p_start = topic_src.get("page_start")
                    p_end = topic_src.get("page_end")
                    src_ref = normalize_text(topic_src.get("reference") or topic_src.get("source_reference"))

                    if existing_ct:
                        changed = (
                            existing_ct.order != order
                            or existing_ct.theme != theme
                            or existing_ct.content_summary != content_summary
                            or not existing_ct.is_active
                            or existing_ct.source_page_start != p_start
                            or existing_ct.source_page_end != p_end
                            or existing_ct.source_reference != src_ref
                        )
                        metrics.record("CurriculumTopic", "UPDATED" if changed else "UNCHANGED")
                    else:
                        metrics.record("CurriculumTopic", "CREATED")

                    for lo_item in topic_item.get("learning_objectives", []):
                        lo_order = lo_item.get("order", 1)
                        lo_desc = normalize_text(lo_item.get("description", ""))
                        lo_sub_name = normalize_text(lo_item.get("subtopic", ""))

                        lo_src = lo_item.get("_source") or lo_item.get("source") or {}
                        lo_page = lo_src.get("page") if "page" in lo_src else lo_src.get("source_page")
                        lo_ref = normalize_text(lo_src.get("reference") or lo_src.get("source_reference"))

                        existing_lo = None
                        if existing_ct:
                            existing_lo = LearningObjective.objects.filter(
                                curriculum_topic=existing_ct,
                                order=lo_order,
                            ).first()

                        if existing_lo:
                            sub_match = (
                                existing_lo.subtopic.name.lower() == lo_sub_name.lower()
                                if existing_lo.subtopic and lo_sub_name
                                else (existing_lo.subtopic is None and not lo_sub_name)
                            )
                            changed = (
                                existing_lo.description != lo_desc
                                or not sub_match
                                or not existing_lo.is_active
                                or existing_lo.source_page != lo_page
                                or existing_lo.source_reference != lo_ref
                            )
                            metrics.record("LearningObjective", "UPDATED" if changed else "UNCHANGED")
                        else:
                            metrics.record("LearningObjective", "CREATED")

                    guidance_dict = topic_item.get("guidance")
                    if guidance_dict and any(str(v).strip() for v in guidance_dict.values()):
                        existing_cg = None
                        if existing_ct:
                            existing_cg = CurriculumGuidance.objects.filter(
                                curriculum_topic=existing_ct
                            ).first()
                        if existing_cg:
                            t_act = normalize_text(guidance_dict.get("teacher_activities", ""))
                            l_act = normalize_text(guidance_dict.get("learner_activities", ""))
                            mat = normalize_text(guidance_dict.get("teaching_learning_materials", ""))
                            eval_g = normalize_text(guidance_dict.get("evaluation_guide", ""))
                            notes = normalize_text(guidance_dict.get("notes", ""))
                            changed = (
                                existing_cg.teacher_activities != t_act
                                or existing_cg.learner_activities != l_act
                                or existing_cg.teaching_learning_materials != mat
                                or existing_cg.evaluation_guide != eval_g
                                or existing_cg.notes != notes
                            )
                            metrics.record("CurriculumGuidance", "UPDATED" if changed else "UNCHANGED")
                        else:
                            metrics.record("CurriculumGuidance", "CREATED")

        return metrics.get_summary()

    @classmethod
    def import_content(
        cls,
        *,
        data: dict[str, Any],
        curriculum: Curriculum | str | None = None,
        source: CurriculumSource | None = None,
        imported_by: Any | None = None,
        grade_filter: str | None = None,
        subject_filter: str | None = None,
        dry_run: bool = False,
        strict: bool = False,
    ) -> tuple[ImportMetrics, CurriculumSource | None, CurriculumImportBatch | None]:
        """
        Executes structural validation and persists curriculum content with provenance.
        When dry_run=True, executes the real ORM path and rolls back without persisting batch.
        """
        errors = cls.validate(
            data=data,
            curriculum=curriculum,
            source=source,
            grade_filter=grade_filter,
            subject_filter=subject_filter,
            strict=strict,
        )
        if errors:
            raise CurriculumImportError("Preflight validation failed.", errors=errors)

        curriculum_obj = cls.resolve_curriculum(data=data, curriculum=curriculum)
        metrics = ImportMetrics()
        batch_obj = None
        source_obj = None

        try:
            with transaction.atomic():
                source_obj = cls.resolve_source(
                    data=data,
                    curriculum=curriculum_obj,
                    source=source,
                    created_by=imported_by,
                    metrics=metrics,
                )

                if not dry_run:
                    batch_obj = CurriculumImportBatch.objects.create(
                        curriculum=curriculum_obj,
                        source=source_obj,
                        imported_by=imported_by,
                        status=ImportBatchStatus.STARTED,
                        source_checksum=source_obj.checksum_sha256 if source_obj else "",
                        grade_filter=grade_filter or "",
                        subject_filter=subject_filter or "",
                        started_at=timezone.now(),
                    )

                if cls._is_v2(data):
                    cls._persist_data_v2(
                        data=data,
                        curriculum=curriculum_obj,
                        source=source_obj,
                        batch=batch_obj,
                        grade_filter=grade_filter,
                        subject_filter=subject_filter,
                        metrics=metrics,
                    )
                else:
                    cls._persist_data(
                        data=data,
                        curriculum=curriculum_obj,
                        source=source_obj,
                        batch=batch_obj,
                        grade_filter=grade_filter,
                        subject_filter=subject_filter,
                        metrics=metrics,
                    )


                if not dry_run and batch_obj:
                    batch_obj.summary = metrics.get_summary()
                    batch_obj.status = ImportBatchStatus.COMPLETED
                    batch_obj.completed_at = timezone.now()
                    batch_obj.save(update_fields=["summary", "status", "completed_at"])

                if dry_run:
                    raise DryRunRollback()

        except DryRunRollback:
            logger.info("Dry-run execution completed; transaction rolled back.")

        return metrics, source_obj, batch_obj

    @classmethod
    def _persist_data(
        cls,
        *,
        data: dict[str, Any],
        curriculum: Curriculum,
        source: CurriculumSource | None,
        batch: CurriculumImportBatch | None,
        grade_filter: str | None,
        subject_filter: str | None,
        metrics: ImportMetrics,
    ):
        """Internal persistence engine."""
        for grade_item in data.get("grades", []):
            grade_str = str(grade_item.get("grade", "")).strip()
            if not cls.is_grade_selected(grade_str, grade_filter):
                for s in grade_item.get("subjects", []):
                    for t in s.get("topics", []):
                        metrics.record("Topic", "SKIPPED")
                        metrics.record("CurriculumTopic", "SKIPPED")
                continue

            grade_obj = cls.resolve_grade(grade_str)
            for subject_item in grade_item.get("subjects", []):
                subject_str = str(subject_item.get("subject", "")).strip()
                if not cls.is_subject_selected(subject_str, subject_filter):
                    for t in subject_item.get("topics", []):
                        metrics.record("Topic", "SKIPPED")
                        metrics.record("CurriculumTopic", "SKIPPED")
                    continue

                subject_obj = cls.resolve_subject(subject_str)
                cs_mapping = CurriculumSubject.objects.filter(
                    curriculum=curriculum,
                    grade_level=grade_obj,
                ).filter(
                    Q(name__iexact=subject_str)
                    | (Q(subject=subject_obj) if subject_obj else Q(pk__isnull=True))
                ).first()
                if not cs_mapping:
                    cs_name = subject_obj.name if subject_obj else subject_str
                    cs_code = subject_obj.subject_code if subject_obj else ""
                    cs_mapping = CurriculumSubject.objects.create(
                        curriculum=curriculum,
                        grade_level=grade_obj,
                        name=cs_name,
                        code=cs_code,
                        subject=subject_obj,
                        is_active=True,
                    )

                topics_data = subject_item.get("topics", [])

                # ── Phase A: Record original state and shift existing orders to avoid unique collisions
                existing_cts = list(
                    CurriculumTopic.objects.filter(curriculum_subject=cs_mapping)
                )
                orig_ct_data = {
                    ct.id: {
                        "order": ct.order,
                        "name": ct.name,
                        "theme": ct.theme,
                        "content_summary": ct.content_summary,
                        "source_id": ct.source_id,
                        "source_page_start": ct.source_page_start,
                        "source_page_end": ct.source_page_end,
                        "source_reference": ct.source_reference,
                        "is_active": ct.is_active,
                    }
                    for ct in existing_cts
                }
                if existing_cts:
                    CurriculumTopic.objects.filter(curriculum_subject=cs_mapping).update(
                        order=models.F("order") + 100000
                    )

                # ── Phase B: Process Topics, SubTopics, CurriculumTopics, Objectives, Guidance
                processed_topic_ids = set()
                for topic_item in topics_data:
                    topic_name = normalize_text(topic_item.get("name"))
                    target_order = topic_item.get("order", 1)
                    theme = normalize_text(topic_item.get("theme", ""))
                    content_summary = normalize_text(topic_item.get("content_summary", ""))

                    topic_src = topic_item.get("_source") or topic_item.get("source") or {}
                    p_start = topic_src.get("page_start")
                    p_end = topic_src.get("page_end")
                    src_ref = normalize_text(topic_src.get("reference") or topic_src.get("source_reference"))

                    # 1. Topic
                    topic_obj = None
                    if subject_obj:
                        topic_obj = Topic.objects.filter(
                            grade_level=grade_obj,
                            subject=subject_obj,
                            name__iexact=topic_name,
                        ).first()

                        if topic_obj:
                            metrics.record("Topic", "REUSED")
                        else:
                            topic_obj = Topic(
                                grade_level=grade_obj,
                                subject=subject_obj,
                                name=topic_name,
                                is_active=True,
                            )
                            topic_obj.full_clean()
                            topic_obj.save()
                            metrics.record("Topic", "CREATED")

                        processed_topic_ids.add(topic_obj.id)

                    # 2. SubTopics
                    subtopic_map = {}
                    for sub_raw in topic_item.get("subtopics", []):
                        full_sub_name = normalize_text(sub_raw)

                        if not full_sub_name:
                            continue

                        max_subtopic_length = (
                            SubTopic._meta
                            .get_field("name")
                            .max_length
                            or 255
                        )

                        if len(full_sub_name) > max_subtopic_length:
                            suffix = "…"
                            sub_name = (
                                full_sub_name[
                                    : max_subtopic_length - len(suffix)
                                ].rstrip()
                                + suffix
                            )

                            if full_sub_name not in content_summary:
                                content_summary = (
                                    f"{content_summary}\n\n"
                                    f"Subtopic detail: {full_sub_name}"
                                ).strip()
                        else:
                            sub_name = full_sub_name
                        if not sub_name:
                            continue

                        sub_obj = None
                        if topic_obj:
                            sub_obj = SubTopic.objects.filter(
                                topic=topic_obj,
                                name__iexact=sub_name,
                            ).first()
                        if not sub_obj:
                            sub_obj = SubTopic.objects.filter(
                                curriculum_topics__curriculum_subject=cs_mapping,
                                curriculum_topics__name__iexact=topic_name,
                                name__iexact=sub_name,
                            ).distinct().first()

                        if sub_obj:
                            metrics.record("SubTopic", "REUSED")
                        else:
                            sub_obj = SubTopic(
                                topic=topic_obj,
                                name=sub_name,
                                is_active=True,
                            )
                            sub_obj.full_clean()
                            sub_obj.save()
                            metrics.record("SubTopic", "CREATED")
                        subtopic_map[sub_name.lower()] = sub_obj

                    # 3. CurriculumTopic
                    ct_obj = CurriculumTopic.objects.filter(
                        curriculum_subject=cs_mapping,
                        name__iexact=topic_name,
                    ).first()
                    if not ct_obj and topic_obj:
                        ct_obj = CurriculumTopic.objects.filter(
                            curriculum_subject=cs_mapping,
                            topic=topic_obj,
                        ).first()

                    target_source = source if source is not None else (ct_obj.source if ct_obj else None)

                    if ct_obj:
                        orig = orig_ct_data.get(ct_obj.id, {})
                        changed = (
                            orig.get("order") != target_order
                            or orig.get("name") != topic_name
                            or orig.get("theme") != theme
                            or orig.get("content_summary") != content_summary
                            or not orig.get("is_active", True)
                            or orig.get("source_id") != (target_source.id if target_source else None)
                            or orig.get("source_page_start") != p_start
                            or orig.get("source_page_end") != p_end
                            or orig.get("source_reference") != src_ref
                        )
                        ct_obj.name = topic_name
                        if topic_obj:
                            ct_obj.topic = topic_obj
                        ct_obj.order = target_order
                        ct_obj.theme = theme
                        ct_obj.content_summary = content_summary
                        ct_obj.source = target_source
                        ct_obj.source_page_start = p_start
                        ct_obj.source_page_end = p_end
                        ct_obj.source_reference = src_ref
                        ct_obj.is_active = True
                        if changed and batch:
                            ct_obj.last_import_batch = batch
                        ct_obj.full_clean()
                        ct_obj.save()
                        metrics.record("CurriculumTopic", "UPDATED" if changed else "UNCHANGED")
                    else:
                        ct_obj = CurriculumTopic(
                            curriculum_subject=cs_mapping,
                            name=topic_name,
                            topic=topic_obj,
                            order=target_order,
                            theme=theme,
                            content_summary=content_summary,
                            source=target_source,
                            source_page_start=p_start,
                            source_page_end=p_end,
                            source_reference=src_ref,
                            last_import_batch=batch,
                            is_active=True,
                        )
                        ct_obj.full_clean()
                        ct_obj.save()
                        metrics.record("CurriculumTopic", "CREATED")

                    if subtopic_map:
                        ct_obj.subtopics.add(*subtopic_map.values())

                    # 4. LearningObjectives
                    for lo_item in topic_item.get("learning_objectives", []):
                        lo_order = lo_item.get("order", 1)
                        lo_desc = normalize_text(lo_item.get("description", ""))
                        lo_sub_name = normalize_text(lo_item.get("subtopic", ""))
                        sub_obj = subtopic_map.get(lo_sub_name.lower()) if lo_sub_name else None

                        lo_src = lo_item.get("_source") or lo_item.get("source") or {}
                        lo_page = lo_src.get("page") if "page" in lo_src else lo_src.get("source_page")
                        lo_ref = normalize_text(lo_src.get("reference") or lo_src.get("source_reference"))

                        lo_obj = LearningObjective.objects.filter(
                            curriculum_topic=ct_obj,
                            order=lo_order,
                        ).first()

                        if lo_obj:
                            changed = (
                                lo_obj.description != lo_desc
                                or lo_obj.subtopic_id != (sub_obj.id if sub_obj else None)
                                or not lo_obj.is_active
                                or lo_obj.source_page != lo_page
                                or lo_obj.source_reference != lo_ref
                            )
                            lo_obj.description = lo_desc
                            lo_obj.subtopic = sub_obj
                            lo_obj.source_page = lo_page
                            lo_obj.source_reference = lo_ref
                            lo_obj.is_active = True
                            if changed and batch:
                                lo_obj.last_import_batch = batch
                            lo_obj.full_clean()
                            lo_obj.save()
                            metrics.record("LearningObjective", "UPDATED" if changed else "UNCHANGED")
                        else:
                            lo_obj = LearningObjective(
                                curriculum_topic=ct_obj,
                                subtopic=sub_obj,
                                description=lo_desc,
                                order=lo_order,
                                source_page=lo_page,
                                source_reference=lo_ref,
                                last_import_batch=batch,
                                is_active=True,
                            )
                            lo_obj.full_clean()
                            lo_obj.save()
                            metrics.record("LearningObjective", "CREATED")

                    # 5. CurriculumGuidance
                    guidance_dict = topic_item.get("guidance")
                    if guidance_dict and any(str(v).strip() for v in guidance_dict.values()):
                        t_act = normalize_text(guidance_dict.get("teacher_activities", ""))
                        l_act = normalize_text(guidance_dict.get("learner_activities", ""))
                        mat = normalize_text(guidance_dict.get("teaching_learning_materials", ""))
                        eval_g = normalize_text(guidance_dict.get("evaluation_guide", ""))
                        notes = normalize_text(guidance_dict.get("notes", ""))

                        cg_obj = CurriculumGuidance.objects.filter(
                            curriculum_topic=ct_obj
                        ).first()

                        if cg_obj:
                            changed = (
                                cg_obj.teacher_activities != t_act
                                or cg_obj.learner_activities != l_act
                                or cg_obj.teaching_learning_materials != mat
                                or cg_obj.evaluation_guide != eval_g
                                or cg_obj.notes != notes
                            )
                            cg_obj.teacher_activities = t_act
                            cg_obj.learner_activities = l_act
                            cg_obj.teaching_learning_materials = mat
                            cg_obj.evaluation_guide = eval_g
                            cg_obj.notes = notes
                            cg_obj.full_clean()
                            cg_obj.save()
                            metrics.record("CurriculumGuidance", "UPDATED" if changed else "UNCHANGED")
                        else:
                            cg_obj = CurriculumGuidance(
                                curriculum_topic=ct_obj,
                                teacher_activities=t_act,
                                learner_activities=l_act,
                                teaching_learning_materials=mat,
                                evaluation_guide=eval_g,
                                notes=notes,
                            )
                            cg_obj.full_clean()
                            cg_obj.save()
                            metrics.record("CurriculumGuidance", "CREATED")

                # Restore any unchanged CTs that were shifted if they weren't in the import list
                # (Conservative preservation: do not delete omitted records)
                for ct in existing_cts:
                    if ct.topic_id not in processed_topic_ids:
                        ct.refresh_from_db()
                        if ct.order > 50000:
                            ct.order = orig_ct_data[ct.id]["order"]
                            ct.save(update_fields=["order"])

    # =========================================================================
    # V2 Persistence Engine
    # =========================================================================

    @classmethod
    def _persist_topics_v2(
        cls,
        *,
        subject_item: dict[str, Any],
        cs_mapping: "CurriculumSubject",
        subject_obj: "Subject | None",
        grade_obj: "GradeLevel",
        source: "CurriculumSource | None",
        batch: "CurriculumImportBatch | None",
        metrics: ImportMetrics,
    ) -> dict[str, "CurriculumTopic"]:
        """Persist topics, subtopics, curriculum-topics, objectives, and guidance for one V2 subject.

        Returns a mapping of ``{topic_key: CurriculumTopic}`` for use by
        ``_persist_published_schemes`` and ``_persist_resources_v2``.
        """
        topics_data = subject_item.get("topics") or []
        topic_key_to_ct: dict[str, CurriculumTopic] = {}

        # ── Phase A: Shift existing CurriculumTopic orders to avoid unique collisions ──
        existing_cts = list(CurriculumTopic.objects.filter(curriculum_subject=cs_mapping))
        orig_ct_data = {
            ct.id: {
                "order": ct.order,
                "name": ct.name,
                "theme": ct.theme,
                "content_summary": ct.content_summary,
                "source_id": ct.source_id,
                "source_page_start": ct.source_page_start,
                "source_page_end": ct.source_page_end,
                "source_reference": ct.source_reference,
                "is_active": ct.is_active,
            }
            for ct in existing_cts
        }
        if existing_cts:
            CurriculumTopic.objects.filter(curriculum_subject=cs_mapping).update(
                order=models.F("order") + 100000
            )

        # ── Phase B: Process topics ────────────────────────────────────────
        processed_topic_ids: set[int] = set()

        for topic_item in topics_data:
            topic_name = normalize_text(topic_item.get("name"))
            if not topic_name:
                continue

            explicit_key = (topic_item.get("topic_key") or "").strip()
            topic_key = explicit_key if explicit_key else cls.make_topic_key(topic_name)

            target_order = topic_item.get("order", 1)
            theme = normalize_text(topic_item.get("theme", ""))
            content_summary = normalize_text(topic_item.get("content_summary", ""))

            topic_src = topic_item.get("_source") or {}
            p_start = topic_src.get("page_start")
            p_end = topic_src.get("page_end")
            src_ref = normalize_text(topic_src.get("reference") or topic_src.get("source_reference") or "")

            # 1. Topic (optional operational mapping)
            topic_obj = None
            if subject_obj:
                topic_obj = Topic.objects.filter(
                    grade_level=grade_obj,
                    subject=subject_obj,
                    name__iexact=topic_name,
                ).first()

                if topic_obj:
                    metrics.record("Topic", "REUSED")
                else:
                    topic_obj = Topic(
                        grade_level=grade_obj,
                        subject=subject_obj,
                        name=topic_name,
                        is_active=True,
                    )
                    topic_obj.full_clean()
                    topic_obj.save()
                    metrics.record("Topic", "CREATED")

                processed_topic_ids.add(topic_obj.id)

            # 2. SubTopics (V2: object list; V1 strings normalised to objects)
            subtopics_raw = topic_item.get("subtopics") or []
            normalised_subtopics = cls._normalize_subtopics_to_v2(subtopics_raw)

            subtopic_name_map: dict[str, SubTopic] = {}  # casefold name → SubTopic

            max_subtopic_length = SubTopic._meta.get_field("name").max_length or 255

            for sub_data in normalised_subtopics:
                full_sub_name = sub_data["name"]
                if not full_sub_name:
                    continue

                if len(full_sub_name) > max_subtopic_length:
                    suffix = "…"
                    sub_name = (
                        full_sub_name[: max_subtopic_length - len(suffix)].rstrip() + suffix
                    )
                    if full_sub_name not in content_summary:
                        content_summary = (
                            f"{content_summary}\n\nSubtopic detail: {full_sub_name}"
                        ).strip()
                else:
                    sub_name = full_sub_name

                sub_obj = None
                if topic_obj:
                    sub_obj = SubTopic.objects.filter(
                        topic=topic_obj, name__iexact=sub_name
                    ).first()
                if not sub_obj:
                    sub_obj = SubTopic.objects.filter(
                        curriculum_topics__curriculum_subject=cs_mapping,
                        curriculum_topics__name__iexact=topic_name,
                        name__iexact=sub_name,
                    ).distinct().first()

                if sub_obj:
                    metrics.record("SubTopic", "REUSED")
                else:
                    sub_obj = SubTopic(topic=topic_obj, name=sub_name, is_active=True)
                    sub_obj.full_clean()
                    sub_obj.save()
                    metrics.record("SubTopic", "CREATED")

                subtopic_name_map[sub_name.casefold()] = sub_obj
                subtopic_name_map[full_sub_name.casefold()] = sub_obj  # also index by original

            # 3. CurriculumTopic (canonical curriculum identity)
            ct_obj = CurriculumTopic.objects.filter(
                curriculum_subject=cs_mapping,
                name__iexact=topic_name,
            ).first()
            if not ct_obj and topic_obj:
                ct_obj = CurriculumTopic.objects.filter(
                    curriculum_subject=cs_mapping,
                    topic=topic_obj,
                ).first()

            target_source = source if source is not None else (ct_obj.source if ct_obj else None)

            if ct_obj:
                orig = orig_ct_data.get(ct_obj.id, {})
                changed = (
                    orig.get("order") != target_order
                    or orig.get("name") != topic_name
                    or orig.get("theme") != theme
                    or orig.get("content_summary") != content_summary
                    or not orig.get("is_active", True)
                    or orig.get("source_id") != (target_source.id if target_source else None)
                    or orig.get("source_page_start") != p_start
                    or orig.get("source_page_end") != p_end
                    or orig.get("source_reference") != src_ref
                )
                ct_obj.name = topic_name
                if topic_obj:
                    ct_obj.topic = topic_obj
                ct_obj.order = target_order
                ct_obj.theme = theme
                ct_obj.content_summary = content_summary
                ct_obj.source = target_source
                ct_obj.source_page_start = p_start
                ct_obj.source_page_end = p_end
                ct_obj.source_reference = src_ref
                ct_obj.is_active = True
                if changed and batch:
                    ct_obj.last_import_batch = batch
                ct_obj.full_clean()
                ct_obj.save()
                metrics.record("CurriculumTopic", "UPDATED" if changed else "UNCHANGED")
            else:
                ct_obj = CurriculumTopic(
                    curriculum_subject=cs_mapping,
                    name=topic_name,
                    topic=topic_obj,
                    order=target_order,
                    theme=theme,
                    content_summary=content_summary,
                    source=target_source,
                    source_page_start=p_start,
                    source_page_end=p_end,
                    source_reference=src_ref,
                    last_import_batch=batch,
                    is_active=True,
                )
                ct_obj.full_clean()
                ct_obj.save()
                metrics.record("CurriculumTopic", "CREATED")

            if subtopic_name_map:
                ct_obj.subtopics.add(*subtopic_name_map.values())

            topic_key_to_ct[topic_key] = ct_obj

            # 4. LearningObjectives
            for lo_item in topic_item.get("learning_objectives") or []:
                lo_order = lo_item.get("order", 1)
                lo_desc = normalize_text(lo_item.get("description", ""))
                lo_sub_ref = normalize_text(lo_item.get("subtopic_ref") or lo_item.get("subtopic", ""))
                sub_obj = subtopic_name_map.get(lo_sub_ref.casefold()) if lo_sub_ref else None

                lo_src = lo_item.get("_source") or lo_item.get("source") or {}
                lo_page = lo_src.get("page") if "page" in lo_src else lo_src.get("source_page")
                lo_ref = normalize_text(lo_src.get("reference") or lo_src.get("source_reference") or "")

                lo_obj = LearningObjective.objects.filter(
                    curriculum_topic=ct_obj, order=lo_order
                ).first()

                if lo_obj:
                    changed = (
                        lo_obj.description != lo_desc
                        or lo_obj.subtopic_id != (sub_obj.id if sub_obj else None)
                        or not lo_obj.is_active
                        or lo_obj.source_page != lo_page
                        or lo_obj.source_reference != lo_ref
                    )
                    lo_obj.description = lo_desc
                    lo_obj.subtopic = sub_obj
                    lo_obj.source_page = lo_page
                    lo_obj.source_reference = lo_ref
                    lo_obj.is_active = True
                    if changed and batch:
                        lo_obj.last_import_batch = batch
                    lo_obj.full_clean()
                    lo_obj.save()
                    metrics.record("LearningObjective", "UPDATED" if changed else "UNCHANGED")
                else:
                    lo_obj = LearningObjective(
                        curriculum_topic=ct_obj,
                        subtopic=sub_obj,
                        description=lo_desc,
                        order=lo_order,
                        source_page=lo_page,
                        source_reference=lo_ref,
                        last_import_batch=batch,
                        is_active=True,
                    )
                    lo_obj.full_clean()
                    lo_obj.save()
                    metrics.record("LearningObjective", "CREATED")

            # 5. CurriculumGuidance
            guidance_dict = topic_item.get("guidance")
            if guidance_dict and isinstance(guidance_dict, dict) and any(str(v).strip() for v in guidance_dict.values()):
                t_act = cls.normalize_multiline_text(guidance_dict.get("teacher_activities", ""))
                l_act = cls.normalize_multiline_text(guidance_dict.get("learner_activities", ""))
                mat = cls.normalize_multiline_text(guidance_dict.get("teaching_learning_materials", ""))
                eval_g = cls.normalize_multiline_text(guidance_dict.get("evaluation_guide", ""))
                notes = cls.normalize_multiline_text(guidance_dict.get("notes", ""))

                cg_obj = CurriculumGuidance.objects.filter(curriculum_topic=ct_obj).first()
                if cg_obj:
                    changed = (
                        cg_obj.teacher_activities != t_act
                        or cg_obj.learner_activities != l_act
                        or cg_obj.teaching_learning_materials != mat
                        or cg_obj.evaluation_guide != eval_g
                        or cg_obj.notes != notes
                    )
                    cg_obj.teacher_activities = t_act
                    cg_obj.learner_activities = l_act
                    cg_obj.teaching_learning_materials = mat
                    cg_obj.evaluation_guide = eval_g
                    cg_obj.notes = notes
                    cg_obj.full_clean()
                    cg_obj.save()
                    metrics.record("CurriculumGuidance", "UPDATED" if changed else "UNCHANGED")
                else:
                    cg_obj = CurriculumGuidance(
                        curriculum_topic=ct_obj,
                        teacher_activities=t_act,
                        learner_activities=l_act,
                        teaching_learning_materials=mat,
                        evaluation_guide=eval_g,
                        notes=notes,
                    )
                    cg_obj.full_clean()
                    cg_obj.save()
                    metrics.record("CurriculumGuidance", "CREATED")

        # ── Restore any shifted CTs not in the import list ─────────────────
        for ct in existing_cts:
            if ct.topic_id not in processed_topic_ids:
                ct.refresh_from_db()
                if ct.order > 50000:
                    ct.order = orig_ct_data[ct.topic_id]["order"]
                    ct.save(update_fields=["order"])

        return topic_key_to_ct

    @classmethod
    def _persist_published_schemes(
        cls,
        *,
        subject_item: dict[str, Any],
        cs_mapping: "CurriculumSubject",
        topic_key_to_ct: dict[str, "CurriculumTopic"],
        source: "CurriculumSource | None",
        batch: "CurriculumImportBatch | None",
        metrics: ImportMetrics,
    ) -> dict[str, "PublishedSchemeEntry"]:
        """Persist published schemes and their entries for one V2 subject.

        Builds and returns an in-memory mapping of ``{entry_key: PublishedSchemeEntry}``
        across all schemes in this subject for use by ``_persist_resources_v2``.

        Idempotency key for entries: ``(published_scheme, term_number, order)``.
        The ``entry_key`` from the payload is a stable cross-reference used only
        at import time; it is not stored as a DB field.
        """
        schemes_data = subject_item.get("published_schemes") or []
        entry_key_to_pse: dict[str, PublishedSchemeEntry] = {}

        for scheme_item in schemes_data:
            if not isinstance(scheme_item, dict):
                continue

            scheme_name = normalize_text(scheme_item.get("name") or "Published Scheme of Work")
            scheme_version = normalize_text(scheme_item.get("version") or "")
            scheme_desc = cls.normalize_multiline_text(scheme_item.get("description") or "")

            scheme_src_data = scheme_item.get("_source") or {}
            scheme_src_page_start = scheme_src_data.get("page_start")
            scheme_src_page_end = scheme_src_data.get("page_end")
            scheme_src_ref = normalize_text(scheme_src_data.get("reference") or "")

            ps_obj, ps_created = PublishedScheme.objects.get_or_create(
                curriculum_subject=cs_mapping,
                name=scheme_name,
                version=scheme_version,
                defaults={
                    "description": scheme_desc,
                    "source": source,
                    "is_active": True,
                },
            )
            if ps_created:
                metrics.record("PublishedScheme", "CREATED")
            else:
                metrics.record("PublishedScheme", "REUSED")

            # Build a map of existing entries by (term_number, order) for change detection.
            existing_entries: dict[tuple[int, int], PublishedSchemeEntry] = {
                (e.term_number, e.order): e
                for e in PublishedSchemeEntry.objects.filter(published_scheme=ps_obj)
            }

            for entry_item in scheme_item.get("entries") or []:
                if not isinstance(entry_item, dict):
                    continue

                entry_key = (entry_item.get("entry_key") or "").strip()
                term_number = entry_item.get("term_number", 1)
                week_start = entry_item.get("week_start")
                week_end = entry_item.get("week_end")
                entry_type_str = (entry_item.get("entry_type") or "INSTRUCTION").upper()
                topic_ref = entry_item.get("topic_ref")
                title = normalize_text(entry_item.get("title") or "")
                content_summary = cls.normalize_multiline_text(entry_item.get("content_summary") or "")
                order = entry_item.get("order", 1)
                teacher_activities = cls.normalize_multiline_text(entry_item.get("teacher_activities") or "")
                pupil_activities = cls.normalize_multiline_text(entry_item.get("pupil_activities") or "")
                learning_resources = cls.normalize_multiline_text(entry_item.get("learning_resources") or "")

                entry_src_data = entry_item.get("_source") or {}
                entry_src_page_start = entry_src_data.get("page_start")
                entry_src_page_end = entry_src_data.get("page_end")
                entry_src_ref = normalize_text(entry_src_data.get("reference") or "")

                # Resolve entry_type
                try:
                    entry_type = PublishedSchemeEntryType(entry_type_str)
                except ValueError:
                    entry_type = PublishedSchemeEntryType.OTHER

                # Resolve curriculum_topic from topic_ref
                ct_obj = topic_key_to_ct.get(topic_ref) if topic_ref else None

                # Resolve subtopics (list of names)
                subtopic_refs = entry_item.get("subtopic_refs") or []
                subtopic_objs: list[SubTopic] = []
                if subtopic_refs and ct_obj:
                    for sub_ref in subtopic_refs:
                        if not isinstance(sub_ref, str):
                            continue
                        sub_obj = ct_obj.subtopics.filter(
                            name__iexact=sub_ref
                        ).first()
                        if sub_obj:
                            subtopic_objs.append(sub_obj)

                # Resolve learning_objectives (list of order integers)
                lo_refs = entry_item.get("learning_objective_refs") or []
                lo_objs: list[LearningObjective] = []
                if lo_refs and ct_obj:
                    for lo_ref in lo_refs:
                        if isinstance(lo_ref, int):
                            lo_obj = LearningObjective.objects.filter(
                                curriculum_topic=ct_obj, order=lo_ref
                            ).first()
                            if lo_obj:
                                lo_objs.append(lo_obj)

                # Idempotency: look up by (published_scheme, term_number, order)
                lookup_key = (term_number, order)
                pse_obj = existing_entries.get(lookup_key)

                if pse_obj:
                    changed = (
                        pse_obj.week_start != week_start
                        or pse_obj.week_end != week_end
                        or pse_obj.entry_type != entry_type
                        or pse_obj.curriculum_topic_id != (ct_obj.id if ct_obj else None)
                        or pse_obj.title != title
                        or pse_obj.content_summary != content_summary
                        or pse_obj.teacher_activities != teacher_activities
                        or pse_obj.pupil_activities != pupil_activities
                        or pse_obj.learning_resources != learning_resources
                        or pse_obj.source_page_start != entry_src_page_start
                        or pse_obj.source_page_end != entry_src_page_end
                        or pse_obj.source_reference != entry_src_ref
                        or not pse_obj.is_active
                    )
                    pse_obj.week_start = week_start
                    pse_obj.week_end = week_end
                    pse_obj.entry_type = entry_type
                    pse_obj.curriculum_topic = ct_obj
                    pse_obj.title = title
                    pse_obj.content_summary = content_summary
                    pse_obj.teacher_activities = teacher_activities
                    pse_obj.pupil_activities = pupil_activities
                    pse_obj.learning_resources = learning_resources
                    pse_obj.source_page_start = entry_src_page_start
                    pse_obj.source_page_end = entry_src_page_end
                    pse_obj.source_reference = entry_src_ref
                    pse_obj.is_active = True
                    if changed and batch:
                        pse_obj.import_batch = batch
                    pse_obj.full_clean()
                    pse_obj.save()
                    if subtopic_objs or lo_objs:
                        pse_obj.subtopics.set(subtopic_objs)
                        pse_obj.learning_objectives.set(lo_objs)
                    metrics.record("PublishedSchemeEntry", "UPDATED" if changed else "UNCHANGED")
                else:
                    pse_obj = PublishedSchemeEntry(
                        published_scheme=ps_obj,
                        term_number=term_number,
                        week_start=week_start,
                        week_end=week_end,
                        entry_type=entry_type,
                        curriculum_topic=ct_obj,
                        title=title,
                        content_summary=content_summary,
                        order=order,
                        teacher_activities=teacher_activities,
                        pupil_activities=pupil_activities,
                        learning_resources=learning_resources,
                        source=source,
                        source_page_start=entry_src_page_start,
                        source_page_end=entry_src_page_end,
                        source_reference=entry_src_ref,
                        import_batch=batch,
                        is_active=True,
                    )
                    pse_obj.full_clean()
                    pse_obj.save()
                    if subtopic_objs:
                        pse_obj.subtopics.set(subtopic_objs)
                    if lo_objs:
                        pse_obj.learning_objectives.set(lo_objs)
                    metrics.record("PublishedSchemeEntry", "CREATED")

                if entry_key:
                    entry_key_to_pse[entry_key] = pse_obj

        return entry_key_to_pse

    @classmethod
    def _persist_resources_v2(
        cls,
        *,
        subject_item: dict[str, Any],
        cs_mapping: "CurriculumSubject",
        topic_key_to_ct: dict[str, "CurriculumTopic"],
        entry_key_to_pse: dict[str, "PublishedSchemeEntry"],
        source: "CurriculumSource | None",
        batch: "CurriculumImportBatch | None",
        metrics: ImportMetrics,
    ) -> None:
        """Persist curriculum resources for one V2 subject.

        Idempotency: filter by ``(curriculum_subject, curriculum_topic,
        published_scheme_entry, resource_type, title__iexact)``; update fields
        if changed.  No unique DB constraint exists on this combination so the
        service uses filter-first-then-update-or-create.
        """
        resources_data = subject_item.get("resources") or []

        for resource_item in resources_data:
            if not isinstance(resource_item, dict):
                continue

            res_type_str = (resource_item.get("resource_type") or "OTHER").upper()
            try:
                res_type = CurriculumResourceType(res_type_str)
            except ValueError:
                res_type = CurriculumResourceType.OTHER

            title = normalize_text(resource_item.get("title") or "")
            if not title:
                continue

            content = cls.normalize_multiline_text(resource_item.get("content") or "")
            order = resource_item.get("order", 1)
            metadata = resource_item.get("metadata") or {}

            topic_ref = resource_item.get("topic_ref")
            ct_obj = topic_key_to_ct.get(topic_ref) if topic_ref else None

            entry_ref = resource_item.get("published_scheme_entry_ref")
            pse_obj = entry_key_to_pse.get(entry_ref) if entry_ref else None

            res_src_data = resource_item.get("_source") or {}
            res_src_page_start = res_src_data.get("page_start")
            res_src_page_end = res_src_data.get("page_end")
            res_src_ref = normalize_text(res_src_data.get("reference") or "")

            # Filter-first idempotency
            qs = CurriculumResource.objects.filter(
                curriculum_subject=cs_mapping,
                curriculum_topic=ct_obj,
                published_scheme_entry=pse_obj,
                resource_type=res_type,
                title__iexact=title,
            )
            existing = qs.first()

            if existing:
                changed = (
                    existing.content != content
                    or existing.order != order
                    or existing.metadata != metadata
                    or existing.source_page_start != res_src_page_start
                    or existing.source_page_end != res_src_page_end
                    or existing.source_reference != res_src_ref
                    or not existing.is_active
                )
                existing.content = content
                existing.order = order
                existing.metadata = metadata
                existing.source_page_start = res_src_page_start
                existing.source_page_end = res_src_page_end
                existing.source_reference = res_src_ref
                existing.is_active = True
                if changed and batch:
                    existing.import_batch = batch
                existing.full_clean()
                existing.save()
                metrics.record("CurriculumResource", "UPDATED" if changed else "UNCHANGED")
            else:
                res_obj = CurriculumResource(
                    curriculum_subject=cs_mapping,
                    curriculum_topic=ct_obj,
                    published_scheme_entry=pse_obj,
                    resource_type=res_type,
                    title=title,
                    content=content,
                    order=order,
                    metadata=metadata,
                    source=source,
                    source_page_start=res_src_page_start,
                    source_page_end=res_src_page_end,
                    source_reference=res_src_ref,
                    import_batch=batch,
                    is_active=True,
                )
                res_obj.full_clean()
                res_obj.save()
                metrics.record("CurriculumResource", "CREATED")

    @classmethod
    def _persist_data_v2(
        cls,
        *,
        data: dict[str, Any],
        curriculum: "Curriculum",
        source: "CurriculumSource | None",
        batch: "CurriculumImportBatch | None",
        grade_filter: str | None,
        subject_filter: str | None,
        metrics: ImportMetrics,
    ) -> None:
        """V2 persistence orchestrator: Topics → PublishedSchemes → Resources."""
        for grade_item in data.get("grades", []):
            grade_str = str(grade_item.get("grade", "")).strip()
            if not cls.is_grade_selected(grade_str, grade_filter):
                continue

            grade_obj = cls.resolve_grade(grade_str)
            if not grade_obj:
                raise CurriculumImportError(
                    f"Grade '{grade_str}' could not be resolved. "
                    "Ensure GradeLevels are configured before importing."
                )

            for subject_item in grade_item.get("subjects", []):
                subject_str = str(subject_item.get("subject", "")).strip()
                if not cls.is_subject_selected(subject_str, subject_filter):
                    continue

                subject_obj = cls.resolve_subject(subject_str)
                cs_mapping = CurriculumSubject.objects.filter(
                    curriculum=curriculum,
                    grade_level=grade_obj,
                ).filter(
                    Q(name__iexact=subject_str)
                    | (Q(subject=subject_obj) if subject_obj else Q(pk__isnull=True))
                ).first()
                if not cs_mapping:
                    cs_mapping = CurriculumSubject.objects.create(
                        curriculum=curriculum,
                        subject=subject_obj,
                        grade_level=grade_obj,
                        name=subject_obj.name if subject_obj else subject_str,
                        code=(subject_obj.subject_code or "") if subject_obj else "",
                        is_active=True,
                    )

                # Phase A: Topics + SubTopics + CurriculumTopics + LOs + Guidance
                topic_key_to_ct = cls._persist_topics_v2(
                    subject_item=subject_item,
                    cs_mapping=cs_mapping,
                    subject_obj=subject_obj,
                    grade_obj=grade_obj,
                    source=source,
                    batch=batch,
                    metrics=metrics,
                )

                # Phase B: PublishedSchemes + Entries
                entry_key_to_pse = cls._persist_published_schemes(
                    subject_item=subject_item,
                    cs_mapping=cs_mapping,
                    topic_key_to_ct=topic_key_to_ct,
                    source=source,
                    batch=batch,
                    metrics=metrics,
                )

                # Phase C: Resources
                cls._persist_resources_v2(
                    subject_item=subject_item,
                    cs_mapping=cs_mapping,
                    topic_key_to_ct=topic_key_to_ct,
                    entry_key_to_pse=entry_key_to_pse,
                    source=source,
                    batch=batch,
                    metrics=metrics,
                )
