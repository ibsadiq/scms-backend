"""
Result Computation Service
Handles automated result computation for terms and classrooms.
"""
from decimal import Decimal
from typing import List, Dict, Optional
from django.db import transaction
from django.db.models import Sum, Avg, Count, Q, F
from django.core.exceptions import ValidationError

from examination.models import (
    TermResult,
    SubjectResult,
    MarksManagement,
    ExaminationListHandler
)
from academic.models import Student, ClassRoom, AllocatedSubject
from administration.models import Term, AcademicYear
from .grading_engine import GradingEngine


class ResultComputationService:
    """
    Service class for computing student results.
    Handles CA + Exam aggregation, grading, ranking, and result generation.
    """

    def __init__(self, term: Term, classroom: ClassRoom, computed_by=None, grade_scale=None):
        """
        Initialize the result computation service.

        Args:
            term: Term for which to compute results
            classroom: Classroom for which to compute results
            computed_by: User who triggered the computation
            grade_scale: Optional GradeScale to use. If None, uses default.
        """
        self.term = term
        self.classroom = classroom
        self.academic_year = term.academic_year
        self.computed_by = computed_by
        self.grading_engine = GradingEngine(grade_scale=grade_scale)

    def compute_results_for_classroom(self) -> Dict:
        """
        Compute results for all students in the classroom.

        Returns:
            Dictionary with computation summary
        """
        with transaction.atomic():
            # Get all active students in classroom
            students = Student.objects.filter(
                classroom=self.classroom,
                is_active=True
            )

            if not students.exists():
                raise ValidationError("No active students found in this classroom.")

            results = {
                'total_students': students.count(),
                'computed': 0,
                'failed': 0,
                'errors': []
            }

            # Compute result for each student
            for student in students:
                try:
                    self._compute_student_result(student)
                    results['computed'] += 1
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append({
                        'student': student.full_name,
                        'error': str(e)
                    })

            # After all students computed, rank them
            if results['computed'] > 0:
                self._rank_students_in_class()

            return results

    def compute_result_for_student(self, student: Student) -> TermResult:
        """
        Compute result for a single student.

        Args:
            student: Student instance

        Returns:
            TermResult instance
        """
        with transaction.atomic():
            term_result = self._compute_student_result(student)

            # Rank this student among classmates
            self._rank_students_in_class()

            return term_result

    def _compute_student_result(self, student: Student) -> TermResult:
        """
        Internal method to compute a student's result.

        Args:
            student: Student instance

        Returns:
            TermResult instance
        """
        # Check if result already exists
        term_result, created = TermResult.objects.get_or_create(
            student=student,
            term=self.term,
            academic_year=self.academic_year,
            defaults={
                'classroom': self.classroom,
                'total_marks': Decimal('0.00'),
                'total_possible': Decimal('0.00'),
                'average_percentage': Decimal('0.00'),
                'grade': 'F',
                'gpa': Decimal('0.00'),
                'computed_by': self.computed_by
            }
        )

        # Delete existing subject results if recomputing
        if not created:
            term_result.subject_results.all().delete()

        # Get all subjects allocated to this classroom
        allocated_subjects = AllocatedSubject.objects.filter(
            class_room=self.classroom,
            academic_year=self.academic_year,
            term=self.term
        ).select_related('subject', 'teacher_name')

        if not allocated_subjects.exists():
            raise ValidationError(
                f"No subjects allocated to {self.classroom} for {self.term}"
            )

        subject_results = []
        grade_points = []

        # Process each subject
        for allocation in allocated_subjects:
            subject = allocation.subject
            teacher = allocation.teacher_name

            # Get CA and Exam marks for this student and subject
            ca_score, exam_score = self._get_student_marks(student, subject)

            # Calculate totals and grade
            total_score = ca_score + exam_score
            ca_max = Decimal('40.00')
            exam_max = Decimal('60.00')
            total_max = Decimal('100.00')

            # Calculate percentage
            percentage = (total_score / total_max) * 100 if total_max > 0 else Decimal('0.00')

            # Get grade
            grade, grade_point, _ = self.grading_engine.get_grade_from_percentage(percentage)

            # Create subject result
            subject_result = SubjectResult.objects.create(
                term_result=term_result,
                subject=subject,
                teacher=teacher,
                ca_score=ca_score,
                ca_max=ca_max,
                exam_score=exam_score,
                exam_max=exam_max,
                total_score=total_score,
                total_possible=total_max,
                percentage=percentage,
                grade=grade,
                grade_point=grade_point
            )

            subject_results.append(subject_result)
            grade_points.append(grade_point)

        # Calculate overall statistics
        if subject_results:
            total_marks = sum(sr.total_score for sr in subject_results)
            total_possible = sum(sr.total_possible for sr in subject_results)
            average_percentage = (total_marks / total_possible) * 100 if total_possible > 0 else Decimal('0.00')

            # Calculate GPA
            gpa = self.grading_engine.calculate_gpa(grade_points)

            # Get overall grade
            overall_grade = self.grading_engine.get_overall_grade_from_gpa(gpa)

            # Update term result
            term_result.total_marks = total_marks
            term_result.total_possible = total_possible
            term_result.average_percentage = average_percentage
            term_result.gpa = gpa
            term_result.grade = overall_grade
            term_result.save()

            # Calculate subject-level statistics
            self._calculate_subject_statistics(term_result)

        return term_result

    def _get_student_marks(self, student: Student, subject) -> tuple:
        """
        Get CA and Exam marks for a student in a subject.

        Args:
            student: Student instance
            subject: Subject instance

        Returns:
            Tuple of (ca_score, exam_score)
        """
        # Get student enrollment
        from academic.models import StudentClassEnrollment
        enrollment = StudentClassEnrollment.objects.filter(
            student=student,
            classroom=self.classroom,
            academic_year=self.academic_year
        ).first()

        if not enrollment:
            raise ValidationError(
                f"Student {student.full_name} is not enrolled in {self.classroom}"
            )

        # Get CA marks (exams marked as CA/continuous assessment)
        ca_exams = ExaminationListHandler.objects.filter(
            classrooms=self.classroom,
            name__icontains='CA'  # Assumes CA exams have 'CA' in name
        )

        ca_marks = MarksManagement.objects.filter(
            student=enrollment,
            subject=subject,
            exam_name__in=ca_exams
        )

        # Sum CA marks (convert to 40% scale if needed)
        ca_total = sum(mark.points_scored for mark in ca_marks)
        # Normalize to 40 (assuming marks are already on appropriate scale)
        ca_score = Decimal(str(min(ca_total, 40)))

        # Get Exam marks (exams marked as Exam/Final)
        final_exams = ExaminationListHandler.objects.filter(
            classrooms=self.classroom
        ).exclude(name__icontains='CA')

        exam_marks = MarksManagement.objects.filter(
            student=enrollment,
            subject=subject,
            exam_name__in=final_exams
        ).order_by('-date_time').first()  # Get most recent exam

        exam_score = Decimal(str(exam_marks.points_scored)) if exam_marks else Decimal('0.00')
        # Normalize to 60 (assuming marks are already on appropriate scale)
        exam_score = min(exam_score, Decimal('60.00'))

        return ca_score, exam_score

    def _rank_students_in_class(self):
        """
        Rank all students in the classroom based on total marks.
        """
        # Get all term results for this classroom and term
        term_results = TermResult.objects.filter(
            classroom=self.classroom,
            term=self.term,
            academic_year=self.academic_year
        )

        # Create student_id -> total_marks mapping
        student_scores = {}
        for result in term_results:
            student_scores[result.student.id] = result.total_marks

        # Get rankings
        rankings = self.grading_engine.rank_students(student_scores)

        # Update positions
        total_students = len(rankings)
        for result in term_results:
            result.position_in_class = rankings.get(result.student.id)
            result.total_students = total_students
            result.save(update_fields=['position_in_class', 'total_students'])

    def _calculate_subject_statistics(self, term_result: TermResult):
        """
        Calculate class statistics for each subject (highest, lowest, average, position).

        Args:
            term_result: TermResult instance
        """
        subject_results = term_result.subject_results.all()

        for subject_result in subject_results:
            # Get all results for this subject in the class
            all_subject_results = SubjectResult.objects.filter(
                term_result__classroom=self.classroom,
                term_result__term=self.term,
                subject=subject_result.subject
            )

            # Calculate statistics
            scores = [sr.total_score for sr in all_subject_results]
            stats = self.grading_engine.calculate_class_statistics(scores)

            # Rank students in this subject
            student_scores = {
                sr.term_result.student.id: sr.total_score
                for sr in all_subject_results
            }
            rankings = self.grading_engine.rank_students(student_scores)

            # Update subject result with statistics
            subject_result.highest_score = stats['highest']
            subject_result.lowest_score = stats['lowest']
            subject_result.class_average = stats['average']
            subject_result.position_in_subject = rankings.get(term_result.student.id)
            subject_result.total_students = stats['total_students']
            subject_result.save()

    def recompute_results(self) -> Dict:
        """
        Recompute all results for the classroom (e.g., if marks were updated).

        Returns:
            Computation summary
        """
        # Delete existing results
        TermResult.objects.filter(
            classroom=self.classroom,
            term=self.term,
            academic_year=self.academic_year
        ).delete()

        # Recompute
        return self.compute_results_for_classroom()

    @staticmethod
    def publish_results(term: Term, classroom: ClassRoom):
        """
        Publish all results for a classroom and term.

        Args:
            term: Term instance
            classroom: ClassRoom instance
        """
        results = TermResult.objects.filter(
            term=term,
            classroom=classroom
        )

        results.update(
            is_published=True,
            published_date=timezone.now()
        )

    @staticmethod
    def unpublish_results(term: Term, classroom: ClassRoom):
        """
        Unpublish all results for a classroom and term.

        Args:
            term: Term instance
            classroom: ClassRoom instance
        """
        results = TermResult.objects.filter(
            term=term,
            classroom=classroom
        )

        results.update(
            is_published=False,
            published_date=None
        )
