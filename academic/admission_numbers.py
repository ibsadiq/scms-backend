import re

from django.db import connection, transaction
from django.utils import timezone

from academic.models.numbering import NumberResetPolicy


def render_number(*, pattern, prefix, year, sequence, width):
    result = pattern
    for token, value in {
        "{PREFIX}": prefix, "{YEAR}": str(year), "{YEAR2}": str(year)[-2:],
        "{SEQ}": str(sequence).zfill(width),
    }.items():
        result = result.replace(token, value)
    return result


def pattern_regex(*, pattern, prefix, year):
    escaped = re.escape(pattern)
    for token, value in {
        re.escape("{PREFIX}"): re.escape(prefix),
        re.escape("{YEAR}"): re.escape(str(year)),
        re.escape("{YEAR2}"): re.escape(str(year)[-2:]),
        re.escape("{SEQ}"): r"(\d+)",
    }.items():
        escaped = escaped.replace(token, value)
    return re.compile(rf"^{escaped}$")


class AdmissionNumberService:
    @classmethod
    @transaction.atomic
    def allocate(cls, year=None):
        from academic.models import AdmissionNumberSequence, Student, StudentAdmissionNumberPolicy

        year = year or timezone.localdate().year
        policy = StudentAdmissionNumberPolicy.objects.filter(is_active=True).first()
        pattern = policy.pattern if policy else "{PREFIX}-{YEAR}-{SEQ}"
        prefix = policy.prefix if policy else "ADM"
        width = policy.sequence_width if policy else 4
        reset = policy.reset_policy if policy else NumberResetPolicy.ACADEMIC_YEAR
        scope = "global" if reset == NumberResetPolicy.NEVER else str(year)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [
                f"{connection.schema_name}:academic:student-number:{reset}:{scope}"
            ])
        sequence, _ = AdmissionNumberSequence.objects.get_or_create(
            reset_policy=reset, scope_key=scope,
            defaults={"year": year if reset == NumberResetPolicy.ACADEMIC_YEAR else None},
        )
        sequence = AdmissionNumberSequence.objects.select_for_update().get(pk=sequence.pk)
        if sequence.last_value == 0:
            matcher = pattern_regex(pattern=pattern, prefix=prefix, year=year)
            sequence.last_value = max((
                int(match.group(1)) for value in
                Student.objects.exclude(admission_number="").values_list("admission_number", flat=True)
                if (match := matcher.fullmatch(value or ""))
            ), default=0)
        while True:
            sequence.last_value += 1
            candidate = render_number(pattern=pattern, prefix=prefix, year=year,
                                      sequence=sequence.last_value, width=width)
            if not Student.objects.filter(admission_number=candidate).exists():
                break
        sequence.save(update_fields=("last_value", "updated_at"))
        return candidate

    @classmethod
    def preview(cls, year=None):
        from academic.models import AdmissionNumberSequence, Student, StudentAdmissionNumberPolicy
        year = year or timezone.localdate().year
        policy = StudentAdmissionNumberPolicy.objects.filter(is_active=True).first()
        pattern = policy.pattern if policy else "{PREFIX}-{YEAR}-{SEQ}"
        prefix = policy.prefix if policy else "ADM"
        width = policy.sequence_width if policy else 4
        reset = policy.reset_policy if policy else NumberResetPolicy.ACADEMIC_YEAR
        scope = "global" if reset == NumberResetPolicy.NEVER else str(year)
        current = AdmissionNumberSequence.objects.filter(
            reset_policy=reset, scope_key=scope
        ).values_list("last_value", flat=True).first() or 0
        matcher = pattern_regex(pattern=pattern, prefix=prefix, year=year)
        current = max(current, max((
            int(match.group(1)) for value in
            Student.objects.exclude(admission_number="").values_list("admission_number", flat=True)
            if (match := matcher.fullmatch(value or ""))
        ), default=0))
        while True:
            current += 1
            candidate = render_number(
                pattern=pattern, prefix=prefix, year=year,
                sequence=current, width=width,
            )
            if not Student.objects.filter(admission_number=candidate).exists():
                return candidate


class ApplicationNumberService:
    @classmethod
    @transaction.atomic
    def allocate(cls, admission_session):
        from academic.models import (
            AdmissionApplication, AdmissionApplicationNumberPolicy,
            AdmissionApplicationNumberSequence,
        )
        year = admission_session.academic_year.start_date.year
        policy = AdmissionApplicationNumberPolicy.objects.filter(is_active=True).first()
        pattern = policy.pattern if policy else "{PREFIX}/{YEAR}/{SEQ}"
        prefix = policy.prefix if policy else admission_session.application_number_prefix
        width = policy.sequence_width if policy else 3
        reset = policy.reset_policy if policy else NumberResetPolicy.ACADEMIC_YEAR
        scope = "global" if reset == NumberResetPolicy.NEVER else str(year)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [
                f"{connection.schema_name}:academic:application-number:{reset}:{scope}"
            ])
        sequence, _ = AdmissionApplicationNumberSequence.objects.get_or_create(
            reset_policy=reset, scope_key=scope,
        )
        sequence = AdmissionApplicationNumberSequence.objects.select_for_update().get(pk=sequence.pk)
        if sequence.last_value == 0:
            matcher = pattern_regex(pattern=pattern, prefix=prefix, year=year)
            sequence.last_value = max((
                int(match.group(1)) for value in
                AdmissionApplication.objects.exclude(application_number="").values_list("application_number", flat=True)
                if (match := matcher.fullmatch(value or ""))
            ), default=0)
        while True:
            sequence.last_value += 1
            candidate = render_number(pattern=pattern, prefix=prefix, year=year,
                                      sequence=sequence.last_value, width=width)
            if not AdmissionApplication.objects.filter(application_number=candidate).exists():
                break
        sequence.save(update_fields=("last_value", "updated_at"))
        return candidate

    @classmethod
    def preview(cls, admission_session):
        from academic.models import (
            AdmissionApplication, AdmissionApplicationNumberPolicy,
            AdmissionApplicationNumberSequence,
        )
        year = admission_session.academic_year.start_date.year
        policy = AdmissionApplicationNumberPolicy.objects.filter(is_active=True).first()
        pattern = policy.pattern if policy else "{PREFIX}/{YEAR}/{SEQ}"
        prefix = policy.prefix if policy else admission_session.application_number_prefix
        width = policy.sequence_width if policy else 3
        reset = policy.reset_policy if policy else NumberResetPolicy.ACADEMIC_YEAR
        scope = "global" if reset == NumberResetPolicy.NEVER else str(year)
        current = AdmissionApplicationNumberSequence.objects.filter(
            reset_policy=reset, scope_key=scope
        ).values_list("last_value", flat=True).first() or 0
        matcher = pattern_regex(pattern=pattern, prefix=prefix, year=year)
        current = max(current, max((
            int(match.group(1)) for value in
            AdmissionApplication.objects.exclude(application_number="").values_list("application_number", flat=True)
            if (match := matcher.fullmatch(value or ""))
        ), default=0))
        while True:
            current += 1
            candidate = render_number(
                pattern=pattern, prefix=prefix, year=year,
                sequence=current, width=width,
            )
            if not AdmissionApplication.objects.filter(application_number=candidate).exists():
                return candidate
