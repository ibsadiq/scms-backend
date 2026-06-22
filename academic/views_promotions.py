"""
Promotion ViewSets - API endpoints for student promotions

Phase 2.1: Student Promotions & Class Advancement

Provides endpoints for:
- Managing promotion rules
- Previewing promotion recommendations
- Executing bulk promotions
- Viewing promotion history
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import PromotionRule, StudentPromotion, ClassRoom, ClassLevel, Student
from administration.models import AcademicYear
from .serializers import (
    PromotionRuleSerializer,
    StudentPromotionSerializer,
    PromotionPreviewSerializer
)
from .services import PromotionService


class PromotionRuleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing promotion rules.

    Endpoints:
    - GET /api/academic/promotion-rules/ - List all rules
    - POST /api/academic/promotion-rules/ - Create new rule
    - GET /api/academic/promotion-rules/{id}/ - Get specific rule
    - PUT/PATCH /api/academic/promotion-rules/{id}/ - Update rule
    - DELETE /api/academic/promotion-rules/{id}/ - Delete rule
    - GET /api/academic/promotion-rules/active/ - List only active rules
    - GET /api/academic/promotion-rules/by_class_level/?class_level_id=1 - Get rule for class
    """
    queryset = PromotionRule.objects.all()
    serializer_class = PromotionRuleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = PromotionRule.objects.select_related(
            'from_class_level',
            'to_class_level'
        ).order_by('from_class_level__id')

        # Filter by active status
        active_only = self.request.query_params.get('active_only')
        if active_only and active_only.lower() == 'true':
            queryset = queryset.filter(is_active=True)

        return queryset

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active promotion rules"""
        rules = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(rules, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_grade(self, request):
        """
        Get rule for a specific Grade Level ID (e.g., ID for JSS 1).
        Usage: /api/academic/promotion-rules/by_grade/?grade_id=5
        """
        grade_id = request.query_params.get('grade_id')
        if not grade_id:
            return Response({'error': 'grade_id is required'}, status=400)

        rule = PromotionRule.objects.filter(from_grade_id=grade_id, is_active=True).first()
        if not rule:
             return Response({'error': 'No promotion rule found for this grade'}, status=404)
             
        serializer = self.get_serializer(rule)
        return Response(serializer.data)

class StudentPromotionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing student promotions.

    Endpoints:
    - GET /api/academic/promotions/ - List all promotions
    - GET /api/academic/promotions/{id}/ - Get specific promotion
    - GET /api/academic/promotions/by_student/?student_id=1 - Student's promotion history
    - GET /api/academic/promotions/by_academic_year/?year_id=1 - Promotions for a year
    - POST /api/academic/promotions/preview/ - Preview promotion recommendations
    - POST /api/academic/promotions/execute/ - Execute bulk promotions
    - GET /api/academic/promotions/statistics/ - Promotion statistics
    """
    queryset = StudentPromotion.objects.all()
    serializer_class = StudentPromotionSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        """Filter queryset based on query parameters"""
        queryset = StudentPromotion.objects.select_related(
            'student',
            'academic_year',
            'from_class',
            'to_class',
            'promotion_rule',
            'approved_by'
        ).order_by('-promotion_date', '-created_at')

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by academic year
        year_id = self.request.query_params.get('academic_year_id')
        if year_id:
            queryset = queryset.filter(academic_year_id=year_id)

        return queryset

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """
        Get promotion history for a specific student.

        Query params:
        - student_id: Student ID (required)
        """
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        promotions = self.get_queryset().filter(student_id=student_id)
        serializer = self.get_serializer(promotions, many=True)

        return Response({
            'student_id': student_id,
            'total_promotions': promotions.count(),
            'promotions': serializer.data
        })

    @action(detail=False, methods=['get'])
    def by_academic_year(self, request):
        """
        Get all promotions for a specific academic year.

        Query params:
        - year_id: AcademicYear ID (required)
        """
        year_id = request.query_params.get('year_id')
        if not year_id:
            return Response(
                {'error': 'year_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        promotions = self.get_queryset().filter(academic_year_id=year_id)
        serializer = self.get_serializer(promotions, many=True)

        # Calculate statistics
        stats = {
            'total': promotions.count(),
            'promoted': promotions.filter(status='promoted').count(),
            'repeated': promotions.filter(status='repeated').count(),
            'conditional': promotions.filter(status='conditional').count(),
            'graduated': promotions.filter(status='graduated').count(),
        }

        return Response({
            'academic_year_id': year_id,
            'statistics': stats,
            'promotions': serializer.data
        })

    @action(detail=False, methods=['post'])
    def preview(self, request):
        """
        Preview promotion recommendations based on Grade Level rules.
        """
        classroom_id = request.data.get('classroom_id')
        academic_year_id = request.data.get('academic_year_id')

        if not classroom_id or not academic_year_id:
            return Response(
                {'error': 'classroom_id and academic_year_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            classroom = ClassRoom.objects.get(id=classroom_id)
            academic_year = AcademicYear.objects.get(id=academic_year_id)
        except ClassRoom.DoesNotExist:
            return Response({'error': f'Classroom {classroom_id} not found'}, status=404)
        except AcademicYear.DoesNotExist:
            return Response({'error': f'Academic year {academic_year_id} not found'}, status=404)

        # 1. NEW: Identify the Grade Level (e.g., JSS 1) from the Class (e.g., JSS 1 Gold)
        # Path: ClassRoom -> ClassLevel (name) -> GradeLevel
        current_grade = classroom.name.grade_level

        # 2. NEW: Fail fast if no rule exists for this Grade
        rule = PromotionRule.objects.filter(from_grade=current_grade, is_active=True).first()
        if not rule:
            return Response(
                {'error': f'No active promotion rule configured for {current_grade}. Please contact admin.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get promotion service
        service = PromotionService()

        try:
            # Service logic should now use 'rule' to evaluate students
            evaluations = service.bulk_evaluate_classroom(classroom, academic_year)
        except DjangoValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Serialize evaluations
        preview_data = []
        for evaluation in evaluations:
            # Handle destination: It might be a Grade (JSS 2) or a Status (Graduated)
            recommended_grade = "N/A"
            if evaluation.get('to_grade'):
                recommended_grade = str(evaluation['to_grade'])
            elif evaluation.get('recommended_status') == 'graduated':
                recommended_grade = "Graduated"

            preview_data.append({
                'student_id': evaluation['student'].id,
                'student_name': evaluation['student'].full_name,
                'admission_number': evaluation['student'].admission_number,
                
                # Context info
                'current_class': str(classroom.name),  # e.g., "JSS 1 Gold"
                'current_grade': str(current_grade),   # e.g., "JSS 1"
                
                # Recommendation (Changed from 'recommended_class' to 'recommended_grade')
                'recommended_grade': recommended_grade,
                'recommended_status': evaluation['recommended_status'],
                
                # Stats
                'annual_average': float(evaluation['annual_average']) if evaluation.get('annual_average') else 0.0,
                'subjects_passed': evaluation.get('subjects_passed', 0),
                'total_subjects': evaluation.get('total_subjects', 0),
                'english_passed': evaluation.get('english_passed', False),
                'mathematics_passed': evaluation.get('mathematics_passed', False),
                'attendance_percentage': float(evaluation['attendance_percentage']) if evaluation.get('attendance_percentage') else 0.0,
                
                # Debug info
                'meets_criteria': evaluation.get('meets_criteria', False),
                'criteria_failed': evaluation.get('criteria_failed', []),
            })

        # Calculate summary statistics
        summary = {
            'total_students': len(preview_data),
            'promoted': sum(1 for p in preview_data if p['recommended_status'] == 'promoted'),
            'repeated': sum(1 for p in preview_data if p['recommended_status'] == 'repeated'),
            'conditional': sum(1 for p in preview_data if p['recommended_status'] == 'conditional'),
            'graduated': sum(1 for p in preview_data if p['recommended_status'] == 'graduated'),
        }

        return Response({
            'classroom': str(classroom),
            'grade_level': str(current_grade),
            'academic_year': str(academic_year),
            'promotion_rule_used': str(rule),
            'summary': summary,
            'students': preview_data
        })
    
    @action(detail=False, methods=['post'])
    def execute(self, request):
        """
        Execute bulk promotions for a classroom.

        Request body:
        {
            "classroom_id": 1,
            "academic_year_id": 1,
            "auto_approve_passed": true,  // Optional, default false
            "overrides": [  // Optional manual overrides
                {
                    "student_id": 123,
                    "status": "promoted",
                    "reason": "Exceptional circumstances..."
                }
            ]
        }

        Returns:
        List of created promotion records.
        """
        classroom_id = request.data.get('classroom_id')
        academic_year_id = request.data.get('academic_year_id')
        auto_approve_passed = request.data.get('auto_approve_passed', False)
        overrides = request.data.get('overrides', [])

        if not classroom_id or not academic_year_id:
            return Response(
                {'error': 'classroom_id and academic_year_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            classroom = ClassRoom.objects.get(id=classroom_id)
            academic_year = AcademicYear.objects.get(id=academic_year_id)
        except (ClassRoom.DoesNotExist, AcademicYear.DoesNotExist) as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get promotion service
        service = PromotionService()

        try:
            # Evaluate all students
            evaluations = service.bulk_evaluate_classroom(classroom, academic_year)

            # Apply manual overrides
            override_map = {o['student_id']: o for o in overrides}
            for evaluation in evaluations:
                student_id = evaluation['student'].id
                if student_id in override_map:
                    override = override_map[student_id]
                    evaluation['override_status'] = override.get('status')
                    evaluation['override_reason'] = override.get('reason', '')

            # Create promotion records
            promotions = []
            for evaluation in evaluations:
                # Skip if auto-approve is off and student didn't meet criteria
                if not auto_approve_passed:
                    if not evaluation['meets_criteria'] and evaluation['student'].id not in override_map:
                        continue

                override_status = evaluation.get('override_status')
                override_reason = evaluation.get('override_reason', '')

                promotion = service.create_promotion_record(
                    evaluation=evaluation,
                    approved_by=request.user,
                    override_status=override_status,
                    reason=override_reason
                )
                promotions.append(promotion)

            # Serialize results
            serializer = self.get_serializer(promotions, many=True)

            return Response({
                'message': f'Successfully created {len(promotions)} promotion records',
                'total_processed': len(evaluations),
                'total_created': len(promotions),
                'promotions': serializer.data
            }, status=status.HTTP_201_CREATED)

        except DjangoValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get promotion statistics across all years.

        Query params:
        - academic_year_id: Filter by specific year (optional)
        """
        queryset = self.get_queryset()

        year_id = request.query_params.get('academic_year_id')
        if year_id:
            queryset = queryset.filter(academic_year_id=year_id)

        # Overall statistics
        total = queryset.count()
        promoted = queryset.filter(status='promoted').count()
        repeated = queryset.filter(status='repeated').count()
        conditional = queryset.filter(status='conditional').count()
        graduated = queryset.filter(status='graduated').count()

        # Average annual average
        promotions_with_avg = queryset.exclude(annual_average__isnull=True)
        avg_annual_average = None
        if promotions_with_avg.exists():
            total_avg = sum(
                float(p.annual_average)
                for p in promotions_with_avg
                if p.annual_average
            )
            avg_annual_average = round(total_avg / promotions_with_avg.count(), 2)

        # Average attendance
        promotions_with_attendance = queryset.exclude(attendance_percentage__isnull=True)
        avg_attendance = None
        if promotions_with_attendance.exists():
            total_attendance = sum(
                float(p.attendance_percentage)
                for p in promotions_with_attendance
                if p.attendance_percentage
            )
            avg_attendance = round(total_attendance / promotions_with_attendance.count(), 2)

        return Response({
            'total_promotions': total,
            'status_breakdown': {
                'promoted': promoted,
                'repeated': repeated,
                'conditional': conditional,
                'graduated': graduated,
            },
            'percentages': {
                'promoted': round((promoted / total * 100), 2) if total > 0 else 0,
                'repeated': round((repeated / total * 100), 2) if total > 0 else 0,
                'conditional': round((conditional / total * 100), 2) if total > 0 else 0,
                'graduated': round((graduated / total * 100), 2) if total > 0 else 0,
            },
            'average_annual_average': avg_annual_average,
            'average_attendance': avg_attendance,
        })
