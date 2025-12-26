"""
Promotion Service - Business Logic for Student Promotions

Phase 2.1: Student Promotions & Class Advancement

Handles Nigerian-style annual average calculations, promotion criteria evaluation,
and student advancement decisions.
"""
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from academic.models import (
    Student,
    ClassRoom,
    ClassLevel,
    PromotionRule,
    StudentPromotion,
    Subject
)
from examination.models import TermResult, SubjectResult
from attendance.models import StudentAttendance
from administration.models import AcademicYear, Term


class PromotionService:
    """
    Service for calculating and processing student promotions.

    Supports Nigerian-style annual average calculation:
    - Simple Average: (Term1 + Term2 + Term3) / 3
    - Weighted Average: (Term1 * 0.3) + (Term2 * 0.3) + (Term3 * 0.4)

    Enforces promotion criteria:
    - Minimum annual average (default 50%)
    - English and Mathematics pass requirements
    - Minimum number of subjects passed
    - Attendance thresholds
    """

    def __init__(self):
        """Initialize the promotion service"""
        self.english_subject_names = ['English', 'English Language', 'English Studies']
        self.math_subject_names = ['Mathematics', 'Math', 'Maths']

    def calculate_annual_average(
        self,
        term1_avg: Optional[Decimal],
        term2_avg: Optional[Decimal],
        term3_avg: Optional[Decimal],
        use_weighted: bool = False,
        term1_weight: Decimal = Decimal('0.33'),
        term2_weight: Decimal = Decimal('0.33'),
        term3_weight: Decimal = Decimal('0.34')
    ) -> Optional[Decimal]:
        """
        Calculate annual average from term averages.

        Args:
            term1_avg: First term average percentage
            term2_avg: Second term average percentage
            term3_avg: Third term average percentage
            use_weighted: Whether to use weighted calculation
            term1_weight: Weight for term 1 (default 0.33)
            term2_weight: Weight for term 2 (default 0.33)
            term3_weight: Weight for term 3 (default 0.34)

        Returns:
            Annual average percentage or None if insufficient data
        """
        # Collect available term averages
        term_averages = []
        if term1_avg is not None:
            term_averages.append(term1_avg)
        if term2_avg is not None:
            term_averages.append(term2_avg)
        if term3_avg is not None:
            term_averages.append(term3_avg)

        # Need at least one term to calculate
        if not term_averages:
            return None

        if use_weighted:
            # Weighted average calculation
            total = Decimal('0.0')
            total_weight = Decimal('0.0')

            if term1_avg is not None:
                total += term1_avg * term1_weight
                total_weight += term1_weight
            if term2_avg is not None:
                total += term2_avg * term2_weight
                total_weight += term2_weight
            if term3_avg is not None:
                total += term3_avg * term3_weight
                total_weight += term3_weight

            if total_weight == Decimal('0.0'):
                return None

            return round(total / total_weight, 2)
        else:
            # Simple average
            return round(sum(term_averages) / len(term_averages), 2)

    def get_student_term_results(
        self,
        student: Student,
        academic_year: AcademicYear
    ) -> Dict[str, Optional[TermResult]]:
        """
        Get all term results for a student in an academic year.

        Args:
            student: Student instance
            academic_year: AcademicYear instance

        Returns:
            Dictionary with term1, term2, term3 keys mapping to TermResult or None
        """
        results = {
            'term1': None,
            'term2': None,
            'term3': None
        }

        # Get all terms for the academic year
        terms = Term.objects.filter(academic_year=academic_year).order_by('start_date')

        for i, term in enumerate(terms[:3], start=1):
            try:
                term_result = TermResult.objects.get(
                    student=student,
                    term=term,
                    academic_year=academic_year
                )
                results[f'term{i}'] = term_result
            except TermResult.DoesNotExist:
                results[f'term{i}'] = None

        return results

    def check_subject_pass(
        self,
        subject_name: str,
        subject_results: List[SubjectResult],
        minimum_pass_percentage: Decimal
    ) -> bool:
        """
        Check if student passed a specific subject (e.g., English or Math).

        Args:
            subject_name: Name of subject to check
            subject_results: List of all SubjectResult instances for the year
            minimum_pass_percentage: Minimum percentage to pass (e.g., 40%)

        Returns:
            True if student passed the subject in at least one term
        """
        for subject_result in subject_results:
            if subject_result.subject.name in self._get_subject_name_variants(subject_name):
                if subject_result.percentage >= minimum_pass_percentage:
                    return True
        return False

    def _get_subject_name_variants(self, base_name: str) -> List[str]:
        """Get all possible name variants for a subject."""
        if 'english' in base_name.lower():
            return self.english_subject_names
        elif 'math' in base_name.lower():
            return self.math_subject_names
        return [base_name]

    def count_passed_subjects(
        self,
        subject_results: List[SubjectResult],
        minimum_pass_percentage: Decimal
    ) -> Tuple[int, int]:
        """
        Count how many subjects the student passed.

        Args:
            subject_results: List of SubjectResult instances
            minimum_pass_percentage: Minimum percentage to pass

        Returns:
            Tuple of (subjects_passed, total_subjects)
        """
        if not subject_results:
            return (0, 0)

        # Group by subject to avoid counting same subject multiple times
        subject_pass_status = {}

        for result in subject_results:
            subject_id = result.subject.id
            if subject_id not in subject_pass_status:
                subject_pass_status[subject_id] = False

            # If passed in any term, mark as passed
            if result.percentage >= minimum_pass_percentage:
                subject_pass_status[subject_id] = True

        passed = sum(1 for passed_status in subject_pass_status.values() if passed_status)
        total = len(subject_pass_status)

        return (passed, total)

    def calculate_attendance_percentage(
        self,
        student: Student,
        academic_year: AcademicYear
    ) -> Tuple[Optional[Decimal], int, int, int]:
        """
        Calculate student's attendance percentage for the academic year.

        Args:
            student: Student instance
            academic_year: AcademicYear instance

        Returns:
            Tuple of (attendance_percentage, total_days, days_present, days_absent)
        """
        attendance_records = StudentAttendance.objects.filter(
            student=student,
            date__gte=academic_year.start_date,
            date__lte=academic_year.end_date
        )

        total_days = attendance_records.count()
        if total_days == 0:
            return (None, 0, 0, 0)

        days_absent = attendance_records.filter(status__absent=True).count()
        days_present = total_days - days_absent

        attendance_percentage = round(Decimal(days_present) / Decimal(total_days) * 100, 2)

        return (attendance_percentage, total_days, days_present, days_absent)

    def evaluate_promotion_criteria(
        self,
        student: Student,
        academic_year: AcademicYear,
        promotion_rule: PromotionRule
    ) -> Dict:
        """
        Evaluate whether a student meets promotion criteria.

        Args:
            student: Student instance
            academic_year: AcademicYear instance
            promotion_rule: PromotionRule to apply

        Returns:
            Dictionary with evaluation results and recommendation
        """
        # Get term results
        term_results_dict = self.get_student_term_results(student, academic_year)

        # Extract term averages
        term1_avg = term_results_dict['term1'].average_percentage if term_results_dict['term1'] else None
        term2_avg = term_results_dict['term2'].average_percentage if term_results_dict['term2'] else None
        term3_avg = term_results_dict['term3'].average_percentage if term_results_dict['term3'] else None

        # Calculate annual average
        rule_config = promotion_rule.get_config_dict()
        annual_average = self.calculate_annual_average(
            term1_avg,
            term2_avg,
            term3_avg,
            use_weighted=rule_config['use_weighted_terms'],
            term1_weight=Decimal(str(rule_config['term1_weight'])),
            term2_weight=Decimal(str(rule_config['term2_weight'])),
            term3_weight=Decimal(str(rule_config['term3_weight']))
        )

        # Get all subject results for the year
        all_subject_results = []
        for term_key, term_result in term_results_dict.items():
            if term_result:
                subject_results = SubjectResult.objects.filter(term_result=term_result)
                all_subject_results.extend(subject_results)

        # Check English and Math pass status
        min_subject_pass = Decimal(str(rule_config['minimum_subject_pass_percentage']))
        english_passed = self.check_subject_pass('English', all_subject_results, min_subject_pass)
        mathematics_passed = self.check_subject_pass('Mathematics', all_subject_results, min_subject_pass)

        # Count passed subjects
        subjects_passed, total_subjects = self.count_passed_subjects(
            all_subject_results,
            min_subject_pass
        )
        subjects_failed = total_subjects - subjects_passed

        # Calculate attendance
        attendance_percentage, total_days, days_present, days_absent = \
            self.calculate_attendance_percentage(student, academic_year)

        # Get class position (from most recent term result)
        class_position = None
        total_students_in_class = None
        for term_key in ['term3', 'term2', 'term1']:
            if term_results_dict[term_key]:
                class_position = term_results_dict[term_key].position_in_class
                total_students_in_class = term_results_dict[term_key].total_students
                break

        # Evaluate criteria
        criteria_met = []
        criteria_failed = []

        # 1. Annual Average Check
        if annual_average is not None:
            if annual_average >= rule_config['minimum_annual_average']:
                criteria_met.append(f"Annual average {annual_average}% ≥ {rule_config['minimum_annual_average']}%")
            else:
                criteria_failed.append(f"Annual average {annual_average}% < {rule_config['minimum_annual_average']}%")
        else:
            criteria_failed.append("Insufficient term results to calculate annual average")

        # 2. English Pass Check
        if rule_config['require_english_pass']:
            if english_passed:
                criteria_met.append("Passed English")
            else:
                criteria_failed.append("Failed to pass English")

        # 3. Mathematics Pass Check
        if rule_config['require_mathematics_pass']:
            if mathematics_passed:
                criteria_met.append("Passed Mathematics")
            else:
                criteria_failed.append("Failed to pass Mathematics")

        # 4. Minimum Passed Subjects Check
        if subjects_passed >= rule_config['minimum_passed_subjects']:
            criteria_met.append(f"Passed {subjects_passed}/{total_subjects} subjects (required: {rule_config['minimum_passed_subjects']})")
        else:
            criteria_failed.append(f"Only passed {subjects_passed}/{total_subjects} subjects (required: {rule_config['minimum_passed_subjects']})")

        # 5. Attendance Check
        if attendance_percentage is not None:
            if attendance_percentage >= rule_config['minimum_attendance_percentage']:
                criteria_met.append(f"Attendance {attendance_percentage}% ≥ {rule_config['minimum_attendance_percentage']}%")
            else:
                criteria_failed.append(f"Attendance {attendance_percentage}% < {rule_config['minimum_attendance_percentage']}%")

        # Determine recommendation
        meets_criteria = len(criteria_failed) == 0

        if meets_criteria:
            # Check if graduating (moving from highest class level)
            if promotion_rule.to_class_level is None:
                recommended_status = 'graduated'
            else:
                recommended_status = 'promoted'
        else:
            # Check if close enough for conditional promotion
            if len(criteria_failed) <= 2 and annual_average and annual_average >= (rule_config['minimum_annual_average'] - 5):
                recommended_status = 'conditional'
            else:
                recommended_status = 'repeated'

        return {
            'student': student,
            'academic_year': academic_year,
            'promotion_rule': promotion_rule,
            'term1_average': term1_avg,
            'term2_average': term2_avg,
            'term3_average': term3_avg,
            'annual_average': annual_average,
            'total_subjects': total_subjects,
            'subjects_passed': subjects_passed,
            'subjects_failed': subjects_failed,
            'english_passed': english_passed,
            'mathematics_passed': mathematics_passed,
            'attendance_percentage': attendance_percentage,
            'total_school_days': total_days,
            'days_present': days_present,
            'days_absent': days_absent,
            'class_position': class_position,
            'total_students_in_class': total_students_in_class,
            'meets_criteria': meets_criteria,
            'criteria_met': criteria_met,
            'criteria_failed': criteria_failed,
            'recommended_status': recommended_status,
            'from_class': student.classroom,
            'to_class': promotion_rule.to_class_level,
        }

    @transaction.atomic
    def create_promotion_record(
        self,
        evaluation: Dict,
        approved_by,
        override_status: Optional[str] = None,
        reason: str = ""
    ) -> StudentPromotion:
        """
        Create a StudentPromotion record based on evaluation.

        Args:
            evaluation: Dictionary from evaluate_promotion_criteria()
            approved_by: CustomUser who approved the promotion
            override_status: Optional status override (e.g., admin forcing promotion)
            reason: Additional explanation for the decision

        Returns:
            Created StudentPromotion instance
        """
        status = override_status if override_status else evaluation['recommended_status']

        # Build reason text
        if not reason:
            if evaluation['meets_criteria']:
                reason = "Student met all promotion criteria. " + "; ".join(evaluation['criteria_met'])
            else:
                reason = "Criteria not met: " + "; ".join(evaluation['criteria_failed'])

        # Determine destination classroom
        to_classroom = None
        if status == 'promoted' and evaluation['to_class']:
            # Find a classroom in the target class level
            # Note: This might need more sophisticated logic for stream assignment
            to_classroom = ClassRoom.objects.filter(
                name=evaluation['to_class']
            ).first()
        elif status == 'repeated':
            to_classroom = evaluation['from_class']

        promotion = StudentPromotion.objects.create(
            student=evaluation['student'],
            academic_year=evaluation['academic_year'],
            from_class=evaluation['from_class'],
            to_class=to_classroom,
            status=status,
            promotion_rule=evaluation['promotion_rule'],

            # Term averages
            term1_average=evaluation['term1_average'],
            term2_average=evaluation['term2_average'],
            term3_average=evaluation['term3_average'],
            annual_average=evaluation['annual_average'],

            # Subject performance
            total_subjects=evaluation['total_subjects'],
            subjects_passed=evaluation['subjects_passed'],
            subjects_failed=evaluation['subjects_failed'],
            english_passed=evaluation['english_passed'],
            mathematics_passed=evaluation['mathematics_passed'],

            # Attendance
            attendance_percentage=evaluation['attendance_percentage'],
            total_school_days=evaluation['total_school_days'],
            days_present=evaluation['days_present'],
            days_absent=evaluation['days_absent'],

            # Position
            class_position=evaluation['class_position'],
            total_students_in_class=evaluation['total_students_in_class'],

            # Decision
            meets_criteria=evaluation['meets_criteria'],
            reason=reason,
            approved_by=approved_by
        )

        return promotion

    def bulk_evaluate_classroom(
        self,
        classroom: ClassRoom,
        academic_year: AcademicYear
    ) -> List[Dict]:
        """
        Evaluate promotions for all students in a classroom.

        Args:
            classroom: ClassRoom instance
            academic_year: AcademicYear instance

        Returns:
            List of evaluation dictionaries
        """
        # Get promotion rule for this classroom's class level
        try:
            promotion_rule = PromotionRule.objects.get(
                from_class_level=classroom.name,
                is_active=True
            )
        except PromotionRule.DoesNotExist:
            raise ValidationError(
                f"No active promotion rule found for class level: {classroom.name}"
            )

        # Get all students in the classroom
        students = Student.objects.filter(classroom=classroom, is_active=True)

        evaluations = []
        for student in students:
            evaluation = self.evaluate_promotion_criteria(
                student,
                academic_year,
                promotion_rule
            )
            evaluations.append(evaluation)

        return evaluations

    @transaction.atomic
    def bulk_create_promotions(
        self,
        evaluations: List[Dict],
        approved_by,
        auto_approve_passed: bool = False
    ) -> List[StudentPromotion]:
        """
        Bulk create promotion records from evaluations.

        Args:
            evaluations: List of evaluation dictionaries
            approved_by: CustomUser approving the promotions
            auto_approve_passed: If True, auto-create records for students who met criteria

        Returns:
            List of created StudentPromotion instances
        """
        promotions = []

        for evaluation in evaluations:
            # Skip if requires manual approval
            if not auto_approve_passed and evaluation['promotion_rule'].requires_approval:
                if not evaluation['meets_criteria']:
                    continue  # Skip failed students that need manual review

            promotion = self.create_promotion_record(
                evaluation=evaluation,
                approved_by=approved_by
            )
            promotions.append(promotion)

        return promotions
