from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from examination.models import BehavioralTrait, TermResult, BehavioralDomain, StudentBehavioralRating
from examination.serializers.behavioral import (
    BehavioralTraitSerializer, BulkBehavioralRatingSerializer
)
from examination.services.behavioral_rating_service import BehavioralRatingService
from academic.models import ClassRoom

class IsAdminOrManager(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or request.user.groups.filter(name__in=["admin", "management"]).exists()

def _is_authorized_for_classroom(user, classroom):
    """
    Returns True if user is the homeroom teacher for the classroom,
    or if the user has an explicit admin/management permission.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, 'is_admin', False) or user.groups.filter(name__in=["admin", "management"]).exists():
        return True
    if not classroom:
        return False

    if classroom.class_teacher_id:
        from academic.models import Teacher
        if Teacher.objects.filter(id=classroom.class_teacher_id, user=user).exists():
            return True
        if hasattr(classroom, "class_teacher") and classroom.class_teacher and classroom.class_teacher.user_id == user.id:
            return True

    teacher = getattr(user, 'teacher', None)
    if not teacher:
        from academic.models import Teacher
        teacher = Teacher.objects.filter(user=user).first()

    if teacher and classroom.class_teacher_id == teacher.id:
        return True
    return False

class BehavioralTraitViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows behavioral traits to be managed.
    """
    queryset = BehavioralTrait.objects.all().order_by('domain', 'order', 'name')
    serializer_class = BehavioralTraitSerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ['domain', 'section', 'is_active']

class BehavioralRatingViewSet(viewsets.ViewSet):
    """
    API endpoint for retrieving and recording behavioral ratings for a TermResult.
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'], url_path=r'(?P<term_result_id>\d+)')
    def retrieve_ratings(self, request, term_result_id=None):
        term_result = get_object_or_404(
            TermResult.objects.select_related('student', 'classroom', 'classroom__grade_level'),
            pk=term_result_id
        )

        if not _is_authorized_for_classroom(request.user, term_result.classroom):
            raise PermissionDenied("You do not have permission to view or record ratings for this classroom.")

        student_section = None
        if term_result.classroom and term_result.classroom.grade_level:
            student_section = term_result.classroom.grade_level.section

        traits = BehavioralRatingService.get_applicable_traits(student_section=student_section)
        existing_ratings = StudentBehavioralRating.objects.filter(term_result=term_result).select_related('trait')
        ratings_map = {r.trait_id: r.rating for r in existing_ratings}

        affective = []
        psychomotor = []

        for trait in traits:
            item = {
                "trait_id": trait.id,
                "name": trait.name,
                "rating": ratings_map.get(trait.id, None)
            }
            if trait.domain == BehavioralDomain.AFFECTIVE:
                affective.append(item)
            elif trait.domain == BehavioralDomain.PSYCHOMOTOR:
                psychomotor.append(item)

        return Response({
            "term_result": term_result.id,
            "student": {
                "id": term_result.student.id,
                "name": term_result.student.full_name
            },
            "affective": affective,
            "psychomotor": psychomotor
        })

    @action(detail=False, methods=['get'], url_path='class_ratings')
    def class_ratings(self, request):
        term_id = request.query_params.get('term_id')
        classroom_id = request.query_params.get('classroom_id')

        if not term_id or not classroom_id:
            return Response({"detail": "term_id and classroom_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        classroom = get_object_or_404(ClassRoom.objects.select_related('grade_level'), pk=classroom_id)

        if not _is_authorized_for_classroom(request.user, classroom):
            raise PermissionDenied("You do not have permission to view or record ratings for this classroom.")

        student_section = classroom.grade_level.section if classroom.grade_level else None

        traits = BehavioralRatingService.get_applicable_traits(student_section=student_section)

        term_results = TermResult.objects.filter(
            term_id=term_id,
            classroom_id=classroom_id
        ).select_related('student')

        term_result_ids = [tr.id for tr in term_results]

        all_ratings = StudentBehavioralRating.objects.filter(
            term_result_id__in=term_result_ids
        ).select_related('trait')

        ratings_by_result = {}
        for r in all_ratings:
            if r.term_result_id not in ratings_by_result:
                ratings_by_result[r.term_result_id] = []
            ratings_by_result[r.term_result_id].append({
                "trait_id": r.trait_id,
                "rating": r.rating
            })

        students_data = []
        for tr in term_results:
            students_data.append({
                "student_id": tr.student.id,
                "admission_number": tr.student.admission_number,
                "full_name": tr.student.full_name,
                "term_result_id": tr.id,
                "lifecycle_state": tr.lifecycle_state,
                "ratings": ratings_by_result.get(tr.id, [])
            })

        return Response({
            "traits": [{"id": t.id, "name": t.name, "domain": t.domain, "order": t.order} for t in traits],
            "rating_index": BehavioralRatingService.RATING_INDEX,
            "students": students_data
        })

    @action(detail=False, methods=['post'], url_path='bulk-record')
    def bulk_record(self, request):
        serializer = BulkBehavioralRatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        term_result_id = serializer.validated_data.get('term_result') or serializer.validated_data.get('term_result_id')
        ratings_data = serializer.validated_data['ratings']

        term_result = get_object_or_404(TermResult.objects.select_related('classroom'), pk=term_result_id)

        if not _is_authorized_for_classroom(request.user, term_result.classroom):
            raise PermissionDenied("You do not have permission to record ratings for this classroom.")

        try:
            BehavioralRatingService.bulk_record_ratings(
                term_result=term_result,
                ratings_data=ratings_data,
                user=request.user
            )
            return Response({"detail": "Ratings successfully recorded."}, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"detail": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
