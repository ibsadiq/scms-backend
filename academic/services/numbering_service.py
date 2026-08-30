from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import (
    AdmissionApplicationNumberPolicy,
    NumberResetPolicy,
    NumberSequence,
    NumberSequenceType,
    SchoolSection,
    StudentAdmissionNumberPolicy,
)
from ..models.numbering import NUMBER_PATTERN_TOKEN_RE


class NumberingService:
    """
    Generates student admission numbers and admission application
    numbers from configured numbering policies.

    Supported tokens:

        {PREFIX}
        {YYYY}
        {YY}
        {SECTION}
        {SEQ}

    Important design rules:

    - {SECTION} affects the rendered number only.
    - Section NEVER affects sequence scope.
    - Student admission numbers and application numbers use
      independent sequences.
    - Generated number year comes from AcademicYear.start_date.
    - Callers do not independently supply a year when generating
      real numbers.
    - Preview does not consume a sequence.
    """

    # ------------------------------------------------------------------
    # Public generation methods
    # ------------------------------------------------------------------

    @classmethod
    def generate_application_number(
        cls,
        *,
        academic_year,
        grade_level=None,
    ):
        """
        Generate the next admission application number.

        Example:

            APP/JS/26/001
        """

        policy = cls._get_active_policy(
            AdmissionApplicationNumberPolicy
        )

        return cls._generate(
            policy=policy,
            sequence_type=(
                NumberSequenceType.ADMISSION_APPLICATION
            ),
            academic_year=academic_year,
            grade_level=grade_level,
        )

    @classmethod
    def generate_student_admission_number(
        cls,
        *,
        academic_year,
        grade_level=None,
    ):
        """
        Generate the next student admission number.

        Example:

            ADM/PRI/26/0001
        """

        policy = cls._get_active_policy(
            StudentAdmissionNumberPolicy
        )

        return cls._generate(
            policy=policy,
            sequence_type=(
                NumberSequenceType.STUDENT_ADMISSION
            ),
            academic_year=academic_year,
            grade_level=grade_level,
        )

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    @classmethod
    def preview(
        cls,
        *,
        policy,
        grade_level=None,
        year=None,
        academic_year=None,
        sequence=1,
    ):
        """
        Render a sample number without consuming a sequence.

        Either:

            year=2026

        or:

            academic_year=<AcademicYear>

        may be supplied.

        If academic_year is supplied, its start_date determines
        the displayed year.
        """

        if academic_year is not None:
            year = cls._resolve_year(
                academic_year=academic_year
            )
        else:
            year = cls._normalize_year(year)

        sequence = cls._normalize_preview_sequence(
            sequence
        )

        cls._validate_render_context(
            policy=policy,
            grade_level=grade_level,
        )

        return cls._render(
            policy=policy,
            sequence=sequence,
            grade_level=grade_level,
            year=year,
        )

    # ------------------------------------------------------------------
    # Policy resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _get_active_policy(model):
        """
        Return the one active policy for the requested policy model.
        """

        try:
            return model.objects.get(
                is_active=True
            )

        except model.DoesNotExist as exc:
            raise ValidationError(
                f"No active {model._meta.verbose_name} "
                "is configured."
            ) from exc

        except model.MultipleObjectsReturned as exc:
            raise ValidationError(
                f"Multiple active "
                f"{model._meta.verbose_name_plural} "
                "were found."
            ) from exc

    # ------------------------------------------------------------------
    # Main generation
    # ------------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def _generate(
        cls,
        *,
        policy,
        sequence_type,
        academic_year,
        grade_level,
    ):
        """
        Generate a real number and consume the next sequence.

        The displayed year is always derived from the supplied
        AcademicYear. This prevents callers from accidentally
        supplying a year that disagrees with the sequence scope.
        """

        cls._validate_generation_context(
            policy=policy,
            academic_year=academic_year,
            grade_level=grade_level,
        )

        year = cls._resolve_year(
            academic_year=academic_year
        )

        scope_key = cls._build_scope_key(
            policy=policy,
            academic_year=academic_year,
        )

        sequence = cls._next_sequence(
            sequence_type=sequence_type,
            reset_policy=policy.reset_policy,
            scope_key=scope_key,
        )

        return cls._render(
            policy=policy,
            sequence=sequence,
            grade_level=grade_level,
            year=year,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @classmethod
    def _validate_generation_context(
        cls,
        *,
        policy,
        academic_year,
        grade_level,
    ):
        """
        Validate the context required for real number generation.
        """

        if not policy:
            raise ValidationError(
                "A numbering policy is required."
            )

        # Real generation always uses AcademicYear as the
        # authoritative year source, regardless of reset policy.
        if academic_year is None:
            raise ValidationError(
                "Academic year is required for "
                "number generation."
            )

        if not getattr(
            academic_year,
            "pk",
            None,
        ):
            raise ValidationError(
                "The academic year must be saved before "
                "a number can be generated."
            )

        cls._resolve_year(
            academic_year=academic_year
        )

        cls._validate_render_context(
            policy=policy,
            grade_level=grade_level,
        )

    @staticmethod
    def _validate_render_context(
        *,
        policy,
        grade_level,
    ):
        """
        Validate data needed to render policy tokens.
        """

        if not policy:
            raise ValidationError(
                "A numbering policy is required."
            )

        if policy.uses_section:
            if grade_level is None:
                raise ValidationError(
                    "Grade level is required because "
                    "the number pattern contains {SECTION}."
                )

            section = getattr(
                grade_level,
                "section",
                None,
            )

            if not section:
                raise ValidationError(
                    "The selected grade level has no "
                    "section configured."
                )

    # ------------------------------------------------------------------
    # Year resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_year(
        *,
        academic_year,
    ):
        """
        Resolve the display year from AcademicYear.start_date.

        Example:

            AcademicYear:
                start_date = 2026-09-01

            Result:
                2026
        """

        if academic_year is None:
            raise ValidationError(
                "Academic year is required."
            )

        start_date = getattr(
            academic_year,
            "start_date",
            None,
        )

        if start_date is None:
            raise ValidationError(
                "The academic year has no start date."
            )

        return start_date.year

    @staticmethod
    def _normalize_year(year):
        """
        Validate an explicitly supplied preview year.
        """

        if year is None:
            raise ValidationError(
                "Year is required for number preview."
            )

        try:
            year = int(year)

        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Year must be a valid four-digit year."
            ) from exc

        if year < 1000 or year > 9999:
            raise ValidationError(
                "Year must be a valid four-digit year."
            )

        return year

    @staticmethod
    def _normalize_preview_sequence(
        sequence,
    ):
        """
        Validate a sequence used only for preview rendering.
        """

        try:
            sequence = int(sequence)

        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Preview sequence must be "
                "a positive integer."
            ) from exc

        if sequence < 1:
            raise ValidationError(
                "Preview sequence must be at least 1."
            )

        return sequence

    # ------------------------------------------------------------------
    # Sequence scope
    # ------------------------------------------------------------------

    @staticmethod
    def _build_scope_key(
        *,
        policy,
        academic_year,
    ):
        """
        Determine which counter is used.

        IMPORTANT:

        Grade level and section deliberately do NOT participate
        in the sequence scope.

        Examples:

            NEVER
                -> global

            ACADEMIC_YEAR
                -> academic_year:12
        """

        if (
            policy.reset_policy
            == NumberResetPolicy.NEVER
        ):
            return "global"

        if (
            policy.reset_policy
            == NumberResetPolicy.ACADEMIC_YEAR
        ):
            if academic_year is None:
                raise ValidationError(
                    "Academic year is required."
                )

            if not getattr(
                academic_year,
                "pk",
                None,
            ):
                raise ValidationError(
                    "The academic year must be saved before "
                    "a sequence can be generated."
                )

            return (
                f"academic_year:{academic_year.pk}"
            )

        raise ValidationError(
            "Unsupported number reset policy: "
            f"{policy.reset_policy}"
        )

    # ------------------------------------------------------------------
    # Section resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_section_code(
        *,
        grade_level,
    ):
        """
        Resolve GradeLevel.section to the school's configured
        number representation.

        Example:

            GradeLevel.section:
                junior_secondary

            SchoolSection:
                system_code = junior_secondary
                number_code = JSS

            Result:
                JSS
        """

        if grade_level is None:
            raise ValidationError(
                "Grade level is required to "
                "resolve section."
            )

        section_system_code = getattr(
            grade_level,
            "section",
            None,
        )

        if not section_system_code:
            raise ValidationError(
                "The selected grade level has no "
                "section configured."
            )

        try:
            school_section = (
                SchoolSection.objects.get(
                    system_code=section_system_code
                )
            )

        except SchoolSection.DoesNotExist as exc:
            raise ValidationError(
                "No school section configuration exists "
                f"for section '{section_system_code}'."
            ) from exc

        number_code = (
            school_section.number_code or ""
        ).strip()

        if not number_code:
            raise ValidationError(
                "No number code has been configured "
                f"for section '{school_section}'."
            )

        return number_code

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    @classmethod
    def _render(
        cls,
        *,
        policy,
        sequence,
        grade_level,
        year,
    ):
        """
        Render a configured pattern into the final number.
        """

        replacements = {
            "{PREFIX}": policy.prefix,
            "{YYYY}": f"{year:04d}",
            "{YY}": f"{year % 100:02d}",
            "{SEQ}": str(sequence).zfill(
                policy.sequence_width
            ),
        }

        if policy.uses_section:
            replacements["{SECTION}"] = (
                cls._resolve_section_code(
                    grade_level=grade_level
                )
            )

        rendered = policy.pattern

        for token, value in replacements.items():
            rendered = rendered.replace(
                token,
                value,
            )

        unresolved = (
            NUMBER_PATTERN_TOKEN_RE.findall(
                rendered
            )
        )

        if unresolved:
            raise ValidationError(
                "Number could not be generated because "
                "these tokens were not resolved: "
                + ", ".join(
                    sorted(
                        set(unresolved)
                    )
                )
            )

        return rendered

    # ------------------------------------------------------------------
    # Atomic sequence increment
    # ------------------------------------------------------------------

    @staticmethod
    def _next_sequence(
        *,
        sequence_type,
        reset_policy,
        scope_key,
    ):
        """
        Atomically obtain and increment a sequence.

        Sequence identity consists of:

            sequence_type
            reset_policy
            scope_key

        This means student admission numbers and application
        numbers never share the same counter.
        """

        sequence, _ = (
            NumberSequence.objects.get_or_create(
                sequence_type=sequence_type,
                reset_policy=reset_policy,
                scope_key=scope_key,
                defaults={
                    "last_value": 0,
                },
            )
        )

        sequence = (
            NumberSequence.objects
            .select_for_update()
            .get(
                pk=sequence.pk
            )
        )

        sequence.last_value += 1

        sequence.save(
            update_fields=[
                "last_value",
                "updated_at",
            ]
        )

        return sequence.last_value