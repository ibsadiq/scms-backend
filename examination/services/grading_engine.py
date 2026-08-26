# examination/services/grading_engine.py
from ..models import GradingScheme


class GradingSchemeResolver:

    @staticmethod
    def get_scheme(classroom, academic_year):
        """
        Resolution order: classroom -> grade_level -> section.
        """
        scheme = GradingScheme.objects.filter(
            classroom=classroom, academic_year=academic_year, is_active=True
        ).first()
        if scheme:
            return scheme

        grade_level = classroom.grade_level

        scheme = GradingScheme.objects.filter(
            grade_level=grade_level, academic_year=academic_year, is_active=True
        ).first()
        if scheme:
            return scheme

        return GradingScheme.objects.filter(
            section=grade_level.section,  # raw SectionType code from GradeLevel, not the display property
            academic_year=academic_year, is_active=True
        ).first()