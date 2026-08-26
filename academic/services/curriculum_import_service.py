"""Curriculum Content Import Service.

Handles ingestion, validation, preview, provenance resolution, and persistence of
structured curriculum content:
    CurriculumSubject
        -> Topic
        -> CurriculumTopic
            -> SubTopic
            -> LearningObjective
            -> CurriculumGuidance

Supports provenance tracking via CurriculumSource and CurriculumImportBatch.
"""

import json
import logging
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
    CurriculumSource,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    ImportBatchStatus,
    LearningObjective,
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
        }
    )

    def record(self, entity: str, status: str, count: int = 1):
        self.counts[entity][status] += count

    def get_summary(self) -> dict[str, dict[str, int]]:
        return {entity: dict(counter) for entity, counter in self.counts.items()}

    def total(self, status: str) -> int:
        return sum(counter[status] for counter in self.counts.values())


class CurriculumImportService:
    """Service for parsing, validating, previewing, and importing curriculum content with provenance."""

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

    @classmethod
    def resolve_grade(cls, grade_spec: str) -> GradeLevel | None:
        """Resolves a GradeLevel by system_code, default_name, or alias."""
        clean = normalize_text(grade_spec)
        return GradeLevel.objects.filter(
            Q(system_code__iexact=clean)
            | Q(default_name__iexact=clean)
            | Q(alias__iexact=clean)
        ).first()

    @classmethod
    def resolve_subject(cls, subject_spec: str) -> Subject | None:
        """Resolves a Subject by name or subject_code."""
        clean = normalize_text(subject_spec)
        return Subject.objects.filter(
            Q(name__iexact=clean) | Q(subject_code__iexact=clean)
        ).first()

    @classmethod
    def is_grade_selected(cls, grade_spec: str, grade_filter: str | None) -> bool:
        if not grade_filter:
            return True
        f = normalize_text(grade_filter).lower()
        spec = normalize_text(grade_spec).lower()
        if spec == f:
            return True
        gl = cls.resolve_grade(grade_spec)
        if gl and (
            gl.system_code.lower() == f
            or gl.default_name.lower() == f
            or (gl.alias and gl.alias.lower() == f)
        ):
            return True
        return False

    @classmethod
    def is_subject_selected(cls, subject_spec: str, subject_filter: str | None) -> bool:
        if not subject_filter:
            return True
        f = normalize_text(subject_filter).lower()
        spec = normalize_text(subject_spec).lower()
        if spec == f:
            return True
        subj = cls.resolve_subject(subject_spec)
        if subj and (
            subj.name.lower() == f
            or subj.subject_code.lower() == f
        ):
            return True
        return False

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
        """
        Performs full structural, relational, and provenance preflight validation.
        Returns a list of error strings (empty list if 100% valid).
        """
        errors = []

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
                if not subject_obj:
                    errors.append(
                        f"Subject '{subject_str}' in Grade '{grade_str}' does not exist in canonical catalog."
                    )
                    continue

                cs_mapping = CurriculumSubject.objects.filter(
                    curriculum=curriculum_obj,
                    subject=subject_obj,
                    grade_level=grade_obj,
                ).first()
                if not cs_mapping:
                    errors.append(
                        f"CurriculumSubject mapping missing for {subject_obj.name} -> {grade_obj.system_code} "
                        f"in curriculum '{curriculum_obj}'. Run Phase 1 setup first."
                    )
                    continue

                topics_data = subject_item.get("topics")
                if not isinstance(topics_data, list) or len(topics_data) == 0:
                    errors.append(
                        f"{grade_str} > {subject_str}: must contain a non-empty 'topics' list."
                    )
                    continue

                seen_topic_names = set()
                seen_topic_orders = set()

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
                    if name_lower in seen_topic_names:
                        errors.append(f"{ctx}: Duplicate topic name '{name}' in same subject/grade import.")
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
                cs_mapping = CurriculumSubject.objects.get(
                    curriculum=curriculum,
                    subject=subject_obj,
                    grade_level=grade_obj,
                )

                topics_data = subject_item.get("topics", [])

                # ── Phase A: Record original state and shift existing orders to avoid unique collisions
                existing_cts = list(
                    CurriculumTopic.objects.filter(curriculum_subject=cs_mapping)
                )
                orig_ct_data = {
                    ct.topic_id: {
                        "order": ct.order,
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
                        sub_name = normalize_text(sub_raw)
                        if not sub_name:
                            continue
                        sub_obj = SubTopic.objects.filter(
                            topic=topic_obj,
                            name__iexact=sub_name,
                        ).first()

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
                        topic=topic_obj,
                    ).first()

                    target_source = source if source is not None else (ct_obj.source if ct_obj else None)

                    if ct_obj:
                        orig = orig_ct_data.get(topic_obj.id, {})
                        changed = (
                            orig.get("order") != target_order
                            or orig.get("theme") != theme
                            or orig.get("content_summary") != content_summary
                            or not orig.get("is_active", True)
                            or orig.get("source_id") != (target_source.id if target_source else None)
                            or orig.get("source_page_start") != p_start
                            or orig.get("source_page_end") != p_end
                            or orig.get("source_reference") != src_ref
                        )
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
                            ct.order = orig_ct_data[ct.topic_id]["order"]
                            ct.save(update_fields=["order"])
