"""
Grading Engine for Result Computation
Handles grade calculation, GPA computation, and grade boundaries.
Uses configurable GradeScale from database.
"""
from decimal import Decimal
from typing import Dict, Tuple, Optional


class GradingEngine:
    """
    Handles all grading-related calculations.
    Uses configurable grade scales from GradeScale and GradeScaleRule models.
    """

    def __init__(self, grade_scale=None):
        """
        Initialize grading engine with a specific grade scale.

        Args:
            grade_scale: GradeScale instance. If None, will use default or first available.
        """
        self.grade_scale = grade_scale
        if self.grade_scale is None:
            self.grade_scale = self._get_default_grade_scale()

    def _get_default_grade_scale(self):
        """Get the default grade scale from database."""
        from examination.models import GradeScale

        # Try to get a grade scale marked as default (you can add this field later)
        # For now, just get the first one or create a default
        grade_scale = GradeScale.objects.first()

        if not grade_scale:
            # Create default Nigerian grading scale if none exists
            grade_scale = self._create_default_nigerian_scale()

        return grade_scale

    def _create_default_nigerian_scale(self):
        """Create default Nigerian WAEC/NECO grading scale."""
        from examination.models import GradeScale, GradeScaleRule

        grade_scale = GradeScale.objects.create(
            name="Nigerian Standard (WAEC/NECO)"
        )

        # Create grade rules
        rules = [
            (75, 100, 'A', 4.00),
            (70, 74, 'B', 3.50),
            (60, 69, 'C', 3.00),
            (50, 59, 'D', 2.00),
            (40, 49, 'E', 1.00),
            (0, 39, 'F', 0.00),
        ]

        for min_grade, max_grade, letter, numeric in rules:
            GradeScaleRule.objects.create(
                grade_scale=grade_scale,
                min_grade=Decimal(str(min_grade)),
                max_grade=Decimal(str(max_grade)),
                letter_grade=letter,
                numeric_scale=Decimal(str(numeric))
            )

        return grade_scale

    def get_grade_from_percentage(self, percentage: Decimal) -> Tuple[str, Decimal, str]:
        """
        Get letter grade, grade point, and remark from percentage using configured grade scale.

        Args:
            percentage: Percentage score (0-100)

        Returns:
            Tuple of (letter_grade, grade_point, remark)
            Example: ('A', Decimal('4.00'), 'Excellent')
        """
        percentage = Decimal(str(percentage))

        if not self.grade_scale:
            # Fallback to F if no grade scale available
            return 'F', Decimal('0.00'), 'Fail'

        # Use the grade scale's get_rule method
        rule = self.grade_scale.get_rule(percentage)

        if rule:
            letter_grade = rule.letter_grade or 'F'
            grade_point = rule.numeric_scale or Decimal('0.00')
            remark = self._get_remark_from_letter(letter_grade)
            return letter_grade, grade_point, remark

        # Default to F if no rule found
        return 'F', Decimal('0.00'), 'Fail'

    def _get_remark_from_letter(self, letter_grade: str) -> str:
        """Get remark text from letter grade."""
        remarks = {
            'A': 'Excellent',
            'B': 'Very Good',
            'C': 'Good',
            'D': 'Pass',
            'E': 'Poor',
            'F': 'Fail'
        }
        return remarks.get(letter_grade, 'N/A')

    @classmethod
    def get_grade_from_score(cls, score: Decimal, max_score: Decimal) -> Tuple[str, Decimal, str]:
        """
        Get grade from raw score and maximum possible score.

        Args:
            score: Score obtained
            max_score: Maximum possible score

        Returns:
            Tuple of (letter_grade, grade_point, remark)
        """
        if max_score == 0:
            return 'F', Decimal('0.00'), 'Fail'

        percentage = (Decimal(str(score)) / Decimal(str(max_score))) * 100
        return cls.get_grade_from_percentage(percentage)

    @classmethod
    def calculate_gpa(cls, grade_points: list) -> Decimal:
        """
        Calculate GPA from list of grade points.

        Args:
            grade_points: List of grade points (e.g., [4.0, 3.5, 3.0])

        Returns:
            Average GPA (0.00 - 4.00)
        """
        if not grade_points:
            return Decimal('0.00')

        total = sum(Decimal(str(gp)) for gp in grade_points)
        count = len(grade_points)
        gpa = total / count

        # Round to 2 decimal places
        return round(gpa, 2)

    @classmethod
    def get_overall_grade_from_gpa(cls, gpa: Decimal) -> str:
        """
        Get overall letter grade from GPA.

        Args:
            gpa: Grade Point Average (0.00 - 4.00)

        Returns:
            Letter grade (A-F)
        """
        gpa = Decimal(str(gpa))

        if gpa >= Decimal('3.50'):
            return 'A'
        elif gpa >= Decimal('3.00'):
            return 'B'
        elif gpa >= Decimal('2.00'):
            return 'C'
        elif gpa >= Decimal('1.00'):
            return 'D'
        elif gpa >= Decimal('0.50'):
            return 'E'
        else:
            return 'F'

    @classmethod
    def get_automated_remark(cls, gpa: Decimal, attendance_percentage: Decimal = None) -> str:
        """
        Generate automated remarks based on GPA and optional attendance.

        Args:
            gpa: Grade Point Average (0.00 - 4.00)
            attendance_percentage: Optional attendance percentage

        Returns:
            Automated remark string
        """
        gpa = Decimal(str(gpa))

        # Base remark on GPA
        if gpa >= Decimal('3.50'):
            base_remark = "Excellent performance! Keep up the outstanding work."
        elif gpa >= Decimal('3.00'):
            base_remark = "Very good performance. Continue with the same effort."
        elif gpa >= Decimal('2.00'):
            base_remark = "Good performance. There is room for improvement."
        elif gpa >= Decimal('1.00'):
            base_remark = "Fair performance. More effort is needed."
        elif gpa >= Decimal('0.50'):
            base_remark = "Poor performance. Requires serious attention and improvement."
        else:
            base_remark = "Unsatisfactory performance. Immediate intervention required."

        # Add attendance remark if provided
        if attendance_percentage is not None:
            attendance_percentage = Decimal(str(attendance_percentage))
            if attendance_percentage < Decimal('75.00'):
                base_remark += " Poor attendance is affecting performance."
            elif attendance_percentage < Decimal('85.00'):
                base_remark += " Attendance should be improved."

        return base_remark

    @classmethod
    def calculate_class_statistics(cls, scores: list) -> Dict:
        """
        Calculate class statistics for a subject.

        Args:
            scores: List of scores (Decimal values)

        Returns:
            Dictionary with highest, lowest, average, and pass_rate
        """
        if not scores:
            return {
                'highest': Decimal('0.00'),
                'lowest': Decimal('0.00'),
                'average': Decimal('0.00'),
                'pass_rate': Decimal('0.00'),
                'total_students': 0
            }

        scores = [Decimal(str(s)) for s in scores]
        highest = max(scores)
        lowest = min(scores)
        average = sum(scores) / len(scores)

        # Count passing scores (>= 40%)
        passing_scores = [s for s in scores if s >= Decimal('40.00')]
        pass_rate = (len(passing_scores) / len(scores)) * 100 if scores else Decimal('0.00')

        return {
            'highest': round(highest, 2),
            'lowest': round(lowest, 2),
            'average': round(average, 2),
            'pass_rate': round(pass_rate, 2),
            'total_students': len(scores)
        }

    @classmethod
    def rank_students(cls, student_scores: Dict[int, Decimal]) -> Dict[int, int]:
        """
        Rank students based on scores.

        Args:
            student_scores: Dictionary mapping student_id to total_score

        Returns:
            Dictionary mapping student_id to rank/position
        """
        if not student_scores:
            return {}

        # Sort students by score (descending)
        sorted_students = sorted(
            student_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Assign ranks (handle ties)
        rankings = {}
        current_rank = 1

        for i, (student_id, score) in enumerate(sorted_students):
            # Check if this score is same as previous (tie)
            if i > 0 and score == sorted_students[i - 1][1]:
                # Same rank as previous student
                rankings[student_id] = rankings[sorted_students[i - 1][0]]
            else:
                rankings[student_id] = current_rank

            current_rank += 1

        return rankings
