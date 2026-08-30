#!/usr/bin/env python3
"""Validate an SSync curriculum JSON file without database access.

Supports both Canonical V1 (no schema_version) and V2 (schema_version == "2.0").
V2 payloads are validated using the dedicated curriculum_v2_validator module.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any


SHORT_ALLOWED = {
    "art", "ict", "map", "music", "qur'an", "salat", "wudu",
}
TRUNCATED_ENDINGS = re.compile(
    r"\b(?:activi|assess|histo|learni|muham|niger|peopl|pharao|prono|"
    r"revie|simpl|stori|writ)\b$",
    re.IGNORECASE,
)
HEADER_FOOTER = re.compile(
    r"(?:scheme\s+of\s+wor?k|back\s+to\s+table|get\s+access|\d+\s*\|\s*985)",
    re.IGNORECASE,
)
MERGED_MARKERS = re.compile(
    r"(?:[•▪]|\s+-\s+(?:Activity|Discussion|Lesson|Practice|Young)\b)",
    re.IGNORECASE,
)


def display_location(location: dict[str, Any]) -> str:
    bits = [
        f"grade={location.get('grade')!r}",
        f"subject={location.get('subject')!r}",
        f"term={location.get('term')!r}",
        f"week/order={location.get('order')!r}",
        f"field={location.get('field')!r}",
    ]
    return ", ".join(bits)


def validate(data: Any) -> tuple[Counter[str], list[dict[str, Any]], list[dict[str, Any]]]:
    counts: Counter[str] = Counter()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def issue(bucket: list[dict[str, Any]], reason: str, location: dict[str, Any], value: Any) -> None:
        bucket.append({"reason": reason, "location": location, "value": value})

    if not isinstance(data, dict) or not isinstance(data.get("grades"), list):
        issue(errors, "root must be an object containing a grades list", {"field": "grades"}, data)
        return counts, errors, warnings

    for grade in data["grades"]:
        if not isinstance(grade, dict):
            issue(errors, "grade record is not an object", {"field": "grade"}, grade)
            continue
        counts["grades"] += 1
        grade_name = grade.get("grade")
        subjects = grade.get("subjects")
        if not isinstance(subjects, list):
            issue(errors, "subjects must be a list", {"grade": grade_name, "field": "subjects"}, subjects)
            continue
        for subject in subjects:
            if not isinstance(subject, dict):
                issue(errors, "subject record is not an object", {"grade": grade_name, "field": "subject"}, subject)
                continue
            counts["grade_subject_mappings"] += 1
            subject_name = subject.get("subject")
            topics = subject.get("topics")
            if not isinstance(topics, list):
                issue(errors, "topics must be a list", {"grade": grade_name, "subject": subject_name, "field": "topics"}, topics)
                continue

            topic_names: dict[tuple[str, str], list[int]] = defaultdict(list)
            for topic_index, topic in enumerate(topics):
                if not isinstance(topic, dict):
                    issue(errors, "topic record is not an object", {"grade": grade_name, "subject": subject_name, "field": "topic"}, topic)
                    continue
                counts["topics"] += 1
                name = topic.get("name")
                term = topic.get("theme")
                order = topic.get("order", topic_index + 1)
                base = {"grade": grade_name, "subject": subject_name, "term": term, "order": order}
                if isinstance(name, str) and name.strip():
                    topic_names[(str(term), " ".join(name.split()).casefold())].append(order)
                else:
                    issue(errors, "empty topic name", {**base, "field": "topic.name"}, name)
                inspect_value(name, "topic.name", base, errors, warnings)

                subtopics = topic.get("subtopics", [])
                if not isinstance(subtopics, list):
                    issue(errors, "subtopics must be a list", {**base, "field": "subtopics"}, subtopics)
                    subtopics = []
                counts["subtopics"] += len(subtopics)
                seen_subtopics: dict[str, list[int]] = defaultdict(list)
                for sub_index, subtopic in enumerate(subtopics):
                    # V2: subtopics can be objects; V1: strings
                    if isinstance(subtopic, dict):
                        value = subtopic.get("name")
                    elif isinstance(subtopic, str):
                        value = subtopic
                    else:
                        value = None
                    field = f"subtopics[{sub_index}]"
                    if not isinstance(value, str) or not value.strip():
                        issue(errors, "empty subtopic value", {**base, "field": field}, value)
                    else:
                        seen_subtopics[" ".join(value.split()).casefold()].append(sub_index)
                    inspect_value(value, field, base, errors, warnings)
                for normalized, positions in seen_subtopics.items():
                    if normalized and len(positions) > 1:
                        issue(errors, "duplicate subtopic within topic", {**base, "field": "subtopics"}, {"positions": positions, "value": subtopics[positions[0]]})

                objectives = topic.get("learning_objectives", [])
                if isinstance(objectives, list):
                    counts["learning_objectives"] += len(objectives)
                    for objective_index, objective in enumerate(objectives):
                        inspect_value(objective, f"learning_objectives[{objective_index}]", base, errors, warnings)
                else:
                    issue(errors, "learning_objectives must be a list", {**base, "field": "learning_objectives"}, objectives)

                guidance = topic.get("guidance")
                if guidance not in (None, "", [], {}):
                    counts["guidance_records"] += 1
                    values = guidance.values() if isinstance(guidance, dict) else [guidance]
                    for guidance_index, value in enumerate(values):
                        inspect_value(value, f"guidance[{guidance_index}]", base, errors, warnings)

            for (term, normalized), orders in topic_names.items():
                if len(orders) > 1:
                    issue(warnings, "duplicate topic name within the same term (week/order disambiguates it)", {"grade": grade_name, "subject": subject_name, "term": term, "order": orders, "field": "topic.name"}, normalized)

    counts["duplicate_topics"] = sum(i["reason"].startswith("duplicate topic") for i in errors + warnings)
    counts["duplicate_subtopics"] = sum(i["reason"].startswith("duplicate subtopic") for i in errors)
    counts["empty_values"] = sum(i["reason"].startswith("empty ") for i in errors)
    counts["oversized_names"] = sum(i["reason"].startswith("oversized ") for i in errors)
    counts["suspiciously_short_values"] = sum(i["reason"] == "suspiciously short value" for i in warnings)
    counts["probable_truncated_words"] = sum(i["reason"] == "probable truncated word or phrase" for i in warnings)
    counts["malformed_merged_content"] = sum(i["reason"] in {"probable merged bullet content", "probable repeated header/footer", "malformed whitespace", "broken Unicode"} for i in errors + warnings)
    counts["unresolved_suspicious_records"] = len(errors) + len(warnings)
    return counts, errors, warnings


def inspect_value(value: Any, field: str, base: dict[str, Any], errors: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    if not isinstance(value, str) or not value:
        return
    location = {**base, "field": field}
    stripped = value.strip()
    name_field = field == "topic.name" or field.startswith("subtopics[")
    limit = 160 if field == "topic.name" else 240
    if name_field and len(stripped) > limit:
        errors.append({"reason": f"oversized {'topic' if field == 'topic.name' else 'subtopic'} name", "location": location, "value": value})
    if "\ufffd" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        errors.append({"reason": "broken Unicode", "location": location, "value": value})
    if value != " ".join(value.split()):
        warnings.append({"reason": "malformed whitespace", "location": location, "value": value})
    if HEADER_FOOTER.search(value):
        errors.append({"reason": "probable repeated header/footer", "location": location, "value": value})
    if name_field and MERGED_MARKERS.search(value):
        errors.append({"reason": "probable merged bullet content", "location": location, "value": value})
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", stripped)
    if field.startswith("subtopics[") and stripped.casefold() not in SHORT_ALLOWED:
        if len(stripped) == 1 or (len(words) == 1 and len(words[0]) <= 5):
            warnings.append({"reason": "suspiciously short value", "location": location, "value": value})
        if TRUNCATED_ENDINGS.search(stripped):
            warnings.append({"reason": "probable truncated word or phrase", "location": location, "value": value})


def _run_v2_validation(data: dict[str, Any], max_issues: int) -> tuple[bool, list[str]]:
    """Run the V2 semantic validator and print results.

    Returns (has_errors, error_strings).
    """
    try:
        import os
        import sys
        # Ensure project root is on path so academic.services is importable.
        project_root = str(Path(__file__).resolve().parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")

        try:
            import django
            django.setup()
        except Exception:
            pass  # validator itself has no Django dependency

        from academic.services.curriculum_v2_validator import validate_v2, Severity
    except ImportError as exc:
        print(f"[WARNING] V2 validator not importable ({exc}); skipping V2 semantic checks.", file=sys.stderr)
        return False, []

    report = validate_v2(data)
    print(f"\nCanonical V2 Semantic Validation")
    print(f"  Errors   : {len(report.get_errors())}")
    print(f"  Warnings : {len(report.get_warnings())}")
    print(f"  Infos    : {len(report.get_infos())}")

    limit = None if max_issues == 0 else max_issues
    for label, issues in (("ERRORS", report.get_errors()), ("WARNINGS", report.get_warnings())):
        if not issues:
            continue
        print(f"\nV2 {label} ({len(issues)}):")
        for item in issues[:limit]:
            print(f"- {item}")
        if limit and len(issues) > limit:
            print(f"- ... {len(issues) - limit} additional {label.lower()} omitted")

    return report.has_errors, report.error_messages()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path, help="Curriculum JSON file")
    parser.add_argument("--max-issues", type=int, default=200, help="Maximum detailed issues to print per severity (0 means all)")
    args = parser.parse_args()
    try:
        with args.file.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read valid JSON: {exc}", file=sys.stderr)
        return 2

    schema_version = data.get("schema_version") if isinstance(data, dict) else None
    is_v2 = schema_version == "2.0"

    print(f"Schema Version : {schema_version or 'V1 (not set)'}")
    print(f"Mode           : {'Canonical V2' if is_v2 else 'V1 (legacy)'}")

    # V1 structural checks (always run)
    counts, errors, warnings = validate(data)
    print("\nStructural Validation Summary")
    for key in (
        "grades", "grade_subject_mappings", "topics", "subtopics",
        "learning_objectives", "guidance_records", "duplicate_topics",
        "duplicate_subtopics", "empty_values", "oversized_names",
        "suspiciously_short_values", "probable_truncated_words",
        "malformed_merged_content", "unresolved_suspicious_records",
    ):
        print(f"  {key.replace('_', ' ').title()}: {counts[key]}")

    limit = None if args.max_issues == 0 else args.max_issues
    for label, issues in (("ERRORS", errors), ("WARNINGS", warnings)):
        print(f"\n{label} ({len(issues)}):")
        for item in issues[:limit]:
            print(f"- {item['reason']}: {display_location(item['location'])}; value={item['value']!r}")
        if limit is not None and len(issues) > limit:
            print(f"- ... {len(issues) - limit} additional {label.lower()} omitted (use --max-issues 0 for all)")

    # V2 semantic checks
    v2_has_errors = False
    if is_v2:
        v2_has_errors, _v2_errors = _run_v2_validation(data, args.max_issues)

    if errors or v2_has_errors:
        print("\nFAIL: structural or semantic errors remain.")
        return 1
    print("\nPASS with warnings." if (warnings) else "\nPASS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
