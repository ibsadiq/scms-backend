"""
Class Advancement Service - Handles student class movements after promotions

Phase 2.2: Class Advancement Automation

This service manages the actual movement of students to new classrooms based on
promotion decisions made in Phase 2.1. It handles:
- Stream assignment (especially SS1 Science/Commercial/Arts)
- Classroom capacity management
- Balanced distribution across streams
- Auto-creation of new classrooms when needed
- Graduation processing
- Academic year enrollment tracking
"""
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from academic.models import (
    Student,
    ClassRoom,
    ClassLevel,
    Stream,
    StudentPromotion,
    StudentClassEnrollment,
    Teacher
)
from administration.models import AcademicYear


class ClassAdvancementService:
    """
    Service for managing student class advancement after promotions.

    Workflow:
    1. Preview class movements (show where students will go)
    2. Verify capacity (check if classrooms can accommodate)
    3. Execute movements (actually update student records)
    4. Handle graduations (mark students as alumni)
    """

    # Define which class levels require stream assignment
    SS_LEVELS = ['SS1', 'SS2', 'SS3']  # Senior Secondary
    JSS_LEVELS = ['JSS1', 'JSS2', 'JSS3']  # Junior Secondary
    PRIMARY_LEVELS = ['Primary 1', 'Primary 2', 'Primary 3', 'Primary 4', 'Primary 5', 'Primary 6']

    def __init__(self):
        """Initialize the class advancement service"""
        self.default_classroom_capacity = 40

    def preview_class_movements(
        self,
        academic_year: AcademicYear,
        promotion_ids: Optional[List[int]] = None
    ) -> Dict:
        """
        Preview where students will be moved based on promotions.

        Args:
            academic_year: Academic year for which promotions were done
            promotion_ids: Optional list of specific promotion IDs to preview

        Returns:
            Dictionary with movement preview data
        """
        # Get promotions
        promotions = StudentPromotion.objects.filter(academic_year=academic_year)
        if promotion_ids:
            promotions = promotions.filter(id__in=promotion_ids)

        promotions = promotions.select_related(
            'student',
            'from_class',
            'to_class',
            'promotion_rule'
        )

        # Group by status
        movements = {
            'promoted': [],
            'repeated': [],
            'graduated': [],
            'conditional': [],
        }

        capacity_warnings = []
        missing_streams = []

        for promotion in promotions:
            student = promotion.student
            status = promotion.status

            movement = {
                'student_id': student.id,
                'student_name': student.full_name,
                'admission_number': student.admission_number,
                'from_class': str(promotion.from_class) if promotion.from_class else None,
                'to_class': None,
                'assigned_stream': student.assigned_stream,
                'preferred_stream': student.preferred_stream,
                'needs_stream_assignment': False,
            }

            if status == 'promoted':
                # Determine target classroom
                target_class_level = promotion.to_class.name if promotion.to_class else None

                if target_class_level:
                    # Check if this is SS1 and needs stream assignment
                    if str(target_class_level) == 'SS1':
                        if not student.assigned_stream:
                            movement['needs_stream_assignment'] = True
                            movement['to_class'] = f"SS1 {student.preferred_stream or 'Unassigned'}"
                            missing_streams.append(movement)
                        else:
                            # Find appropriate classroom
                            target_classroom = self._find_best_classroom(
                                target_class_level,
                                student.assigned_stream
                            )
                            movement['to_class'] = str(target_classroom) if target_classroom else f"SS1 {student.assigned_stream} (New classroom needed)"

                            # Check capacity
                            if target_classroom:
                                capacity_check = self._check_classroom_capacity(target_classroom)
                                if not capacity_check['has_space']:
                                    capacity_warnings.append({
                                        'classroom': str(target_classroom),
                                        'current': capacity_check['current_count'],
                                        'capacity': capacity_check['capacity'],
                                        'message': f"Classroom {target_classroom} is at capacity"
                                    })
                    else:
                        # Non-SS1 promotion
                        target_classroom = self._find_best_classroom(
                            target_class_level,
                            None  # No stream for primary/JSS
                        )
                        movement['to_class'] = str(target_classroom) if target_classroom else f"{target_class_level} (New classroom needed)"

                        if target_classroom:
                            capacity_check = self._check_classroom_capacity(target_classroom)
                            if not capacity_check['has_space']:
                                capacity_warnings.append({
                                    'classroom': str(target_classroom),
                                    'current': capacity_check['current_count'],
                                    'capacity': capacity_check['capacity'],
                                    'message': f"Classroom {target_classroom} is at capacity"
                                })

            elif status == 'repeated':
                movement['to_class'] = str(promotion.from_class)

            elif status == 'graduated':
                movement['to_class'] = 'Graduated'

            elif status == 'conditional':
                # Conditional promotions still move forward
                target_class_level = promotion.to_class.name if promotion.to_class else None
                if target_class_level:
                    target_classroom = self._find_best_classroom(target_class_level, student.assigned_stream)
                    movement['to_class'] = str(target_classroom) if target_classroom else f"{target_class_level} (New classroom needed)"

            movements[status].append(movement)

        # Calculate statistics
        summary = {
            'total_students': promotions.count(),
            'promoted_count': len(movements['promoted']),
            'repeated_count': len(movements['repeated']),
            'graduated_count': len(movements['graduated']),
            'conditional_count': len(movements['conditional']),
            'needs_stream_assignment_count': len(missing_streams),
        }

        return {
            'summary': summary,
            'movements': movements,
            'capacity_warnings': capacity_warnings,
            'missing_streams': missing_streams,
            'new_classrooms_needed': self._identify_new_classrooms_needed(movements),
        }

    def _find_best_classroom(
        self,
        class_level: ClassLevel,
        stream_type: Optional[str] = None
    ) -> Optional[ClassRoom]:
        """
        Find the best classroom for a student.

        For SS levels, considers assigned_stream.
        For other levels, finds classroom with most space.

        Args:
            class_level: Target class level
            stream_type: Stream type (science/commercial/arts) for SS levels

        Returns:
            Best matching classroom or None
        """
        classrooms = ClassRoom.objects.filter(name=class_level)

        # For SS levels, filter by stream
        if stream_type and str(class_level) in self.SS_LEVELS:
            stream_obj = Stream.objects.filter(name__icontains=stream_type).first()
            if stream_obj:
                classrooms = classrooms.filter(stream=stream_obj)

        # Find classroom with most available space
        classrooms = classrooms.annotate(
            student_count=Count('students')
        ).order_by('student_count')

        for classroom in classrooms:
            if classroom.available_sits > 0:
                return classroom

        return None

    def _check_classroom_capacity(self, classroom: ClassRoom) -> Dict:
        """Check if classroom has space for more students"""
        current_count = classroom.students.count()
        return {
            'classroom_id': classroom.id,
            'capacity': classroom.capacity,
            'current_count': current_count,
            'available': classroom.capacity - current_count,
            'has_space': current_count < classroom.capacity
        }

    def _identify_new_classrooms_needed(self, movements: Dict) -> List[Dict]:
        """
        Identify which new classrooms need to be created.

        Args:
            movements: Dictionary of movements by status

        Returns:
            List of classrooms that need to be created
        """
        needed_classrooms = []

        # Count students needing each classroom
        classroom_demand = defaultdict(int)

        for status in ['promoted', 'conditional']:
            for movement in movements.get(status, []):
                to_class = movement.get('to_class', '')
                if 'New classroom needed' in to_class:
                    # Extract class level and stream
                    parts = to_class.replace(' (New classroom needed)', '').split()
                    class_level_name = ' '.join(parts[:-1]) if len(parts) > 1 else parts[0]
                    stream = parts[-1] if len(parts) > 1 and parts[-1] in ['science', 'commercial', 'arts'] else None

                    key = f"{class_level_name}_{stream}" if stream else class_level_name
                    classroom_demand[key] += 1

        # Calculate how many classrooms of each type needed
        for key, student_count in classroom_demand.items():
            classrooms_needed = (student_count // self.default_classroom_capacity) + 1

            if '_' in key:
                class_level_name, stream = key.rsplit('_', 1)
                for i in range(classrooms_needed):
                    needed_classrooms.append({
                        'class_level': class_level_name,
                        'stream': stream,
                        'section': chr(65 + i),  # A, B, C...
                        'student_count': min(student_count, self.default_classroom_capacity),
                        'capacity': self.default_classroom_capacity
                    })
                    student_count -= self.default_classroom_capacity
            else:
                for i in range(classrooms_needed):
                    needed_classrooms.append({
                        'class_level': key,
                        'stream': None,
                        'section': chr(65 + i),
                        'student_count': min(student_count, self.default_classroom_capacity),
                        'capacity': self.default_classroom_capacity
                    })
                    student_count -= self.default_classroom_capacity

        return needed_classrooms

    @transaction.atomic
    def execute_class_movements(
        self,
        academic_year: AcademicYear,
        new_academic_year: AcademicYear,
        promotion_ids: Optional[List[int]] = None,
        auto_create_classrooms: bool = True,
        default_teacher_id: Optional[int] = None
    ) -> Dict:
        """
        Execute class movements based on promotions.

        Args:
            academic_year: Academic year promotions were done for
            new_academic_year: New academic year students are moving to
            promotion_ids: Optional specific promotions to execute
            auto_create_classrooms: Whether to auto-create classrooms if needed
            default_teacher_id: Default teacher for new classrooms

        Returns:
            Dictionary with execution results
        """
        # Get promotions
        promotions = StudentPromotion.objects.filter(academic_year=academic_year)
        if promotion_ids:
            promotions = promotions.filter(id__in=promotion_ids)

        promotions = promotions.select_related('student', 'from_class', 'to_class')

        results = {
            'promoted': 0,
            'repeated': 0,
            'graduated': 0,
            'conditional': 0,
            'errors': [],
            'classrooms_created': [],
            'enrollments_created': 0,
        }

        default_teacher = None
        if default_teacher_id:
            default_teacher = Teacher.objects.get(id=default_teacher_id)

        for promotion in promotions:
            try:
                student = promotion.student
                status = promotion.status

                if status == 'promoted' or status == 'conditional':
                    # Move to new class
                    target_class_level = promotion.to_class.name if promotion.to_class else None

                    if target_class_level:
                        # Find or create appropriate classroom
                        target_classroom = self._find_best_classroom(
                            target_class_level,
                            student.assigned_stream
                        )

                        if not target_classroom and auto_create_classrooms:
                            # Create new classroom
                            target_classroom = self._create_classroom(
                                target_class_level,
                                student.assigned_stream,
                                default_teacher
                            )
                            results['classrooms_created'].append(str(target_classroom))

                        if target_classroom:
                            # Update student classroom
                            student.classroom = target_classroom
                            student.class_level = target_class_level
                            student.save()

                            # Create enrollment record
                            StudentClassEnrollment.objects.create(
                                student=student,
                                classroom=target_classroom,
                                academic_year=new_academic_year,
                                notes=f"Promoted from {promotion.from_class}"
                            )
                            results['enrollments_created'] += 1
                            results[status] += 1
                        else:
                            results['errors'].append(f"No classroom available for {student.full_name}")

                elif status == 'repeated':
                    # Stay in same class
                    student.classroom = promotion.from_class
                    student.save()

                    # Create enrollment record
                    StudentClassEnrollment.objects.create(
                        student=student,
                        classroom=promotion.from_class,
                        academic_year=new_academic_year,
                        notes="Repeated year"
                    )
                    results['enrollments_created'] += 1
                    results['repeated'] += 1

                elif status == 'graduated':
                    # Mark as graduated
                    student.is_active = False
                    student.graduation_date = timezone.now().date()
                    student.save()

                    results['graduated'] += 1

            except Exception as e:
                results['errors'].append(f"Error processing {promotion.student.full_name}: {str(e)}")

        return results

    def _create_classroom(
        self,
        class_level: ClassLevel,
        stream_type: Optional[str],
        teacher: Optional[Teacher] = None
    ) -> ClassRoom:
        """
        Create a new classroom.

        Args:
            class_level: Class level for the classroom
            stream_type: Stream type (for SS levels)
            teacher: Class teacher (optional)

        Returns:
            Created classroom
        """
        stream_obj = None
        if stream_type and str(class_level) in self.SS_LEVELS:
            stream_obj = Stream.objects.filter(name__icontains=stream_type).first()
            if not stream_obj:
                # Create stream if it doesn't exist
                stream_obj = Stream.objects.create(name=stream_type.capitalize())

        # Find next available section letter
        existing_classrooms = ClassRoom.objects.filter(name=class_level)
        if stream_obj:
            existing_classrooms = existing_classrooms.filter(stream=stream_obj)

        section_count = existing_classrooms.count()

        # Create classroom
        classroom = ClassRoom.objects.create(
            name=class_level,
            stream=stream_obj,
            class_teacher=teacher,
            capacity=self.default_classroom_capacity
        )

        return classroom

    def assign_ss1_streams(
        self,
        student_ids: List[int],
        stream_assignments: Dict[int, str]
    ) -> Dict:
        """
        Assign streams to SS1 students (admin decision).

        Args:
            student_ids: List of student IDs
            stream_assignments: Dict mapping student_id to stream (science/commercial/arts)

        Returns:
            Dictionary with assignment results
        """
        results = {
            'assigned': 0,
            'errors': [],
        }

        students = Student.objects.filter(id__in=student_ids)

        for student in students:
            if student.id in stream_assignments:
                stream = stream_assignments[student.id]

                if stream not in ['science', 'commercial', 'arts']:
                    results['errors'].append(
                        f"{student.full_name}: Invalid stream '{stream}'. Must be science/commercial/arts."
                    )
                    continue

                student.assigned_stream = stream
                student.save()
                results['assigned'] += 1
            else:
                results['errors'].append(f"{student.full_name}: No stream assignment provided")

        return results

    def verify_capacity(self, academic_year: AcademicYear) -> Dict:
        """
        Verify that all classrooms have sufficient capacity for movements.

        Args:
            academic_year: Academic year to verify

        Returns:
            Dictionary with capacity verification results
        """
        preview = self.preview_class_movements(academic_year)

        verification = {
            'all_classrooms_sufficient': len(preview['capacity_warnings']) == 0,
            'capacity_warnings': preview['capacity_warnings'],
            'new_classrooms_needed': preview['new_classrooms_needed'],
            'missing_stream_assignments': preview['missing_streams'],
            'can_proceed': len(preview['capacity_warnings']) == 0 and len(preview['missing_streams']) == 0,
        }

        return verification
