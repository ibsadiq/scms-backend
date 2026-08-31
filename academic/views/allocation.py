from django.db.models import Prefetch
from django_filters import CharFilter, FilterSet, NumberFilter
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academic.models import (
    AllocatedSubject,
    CurriculumResource,
    CurriculumSubject,
    CurriculumTopic,
    LearningObjective,
    PublishedScheme,
    SubTopic,
)
from academic.permissions import IsAcademicAdminOrReadOnly
from academic.serializers import AllocatedSubjectListSerializer, AllocatedSubjectSerializer
from academic.serializers.schema_contracts import TeacherCurriculumWorkspaceResponseSerializer
from academic.services import CurriculumAssignmentResolver
from academic.services.academic_authority_service import AcademicAuthorityService


class AllocatedSubjectFilter(FilterSet):
    """Filter for AllocatedSubject"""
    teacher = NumberFilter(field_name='teacher_name')
    subject = NumberFilter(field_name='subject')
    class_room = NumberFilter(field_name='class_room')
    academic_year = NumberFilter(field_name='academic_year')
    term = NumberFilter(field_name='term')

    class Meta:
        model = AllocatedSubject
        fields = ['teacher', 'subject', 'class_room', 'academic_year', 'term']



class AllocatedSubjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing teacher class allocations (AllocatedSubject).
    
    Endpoints:
    - GET /api/academic/allocated-subjects/ - List all allocations
    - POST /api/academic/allocated-subjects/ - Create new allocation
    - GET /api/academic/allocated-subjects/{id}/ - Get allocation details
    - PUT/PATCH /api/academic/allocated-subjects/{id}/ - Update allocation
    - DELETE /api/academic/allocated-subjects/{id}/ - Delete allocation
    """
    permission_classes = [IsAcademicAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AllocatedSubjectFilter

    def get_queryset(self):
        """Filter allocations based on user role"""
        queryset = AllocatedSubject.objects.select_related(
            'teacher_name',
            'teacher_name__user',
            'subject',
            'class_room',
            'class_room__grade_level',
            'academic_year',
            'term'
        ).order_by('-academic_year', 'class_room', 'subject')

        if AcademicAuthorityService.is_school_admin(self.request.user):
            return queryset

        teacher = AcademicAuthorityService.get_teacher(self.request.user)
        if teacher:
            return queryset.filter(teacher_name=teacher)

        return queryset.none()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        from schedule.models import TimetableEntry
        TimetableEntry.objects.filter(subject=instance).delete()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_class(self):
        """Use list serializer for list actions"""
        if self.action == 'list':
            return AllocatedSubjectListSerializer
        return AllocatedSubjectSerializer

    @action(detail=False, methods=['get'])
    def by_teacher(self, request):
        """
        Get allocations for a specific teacher
        ?teacher_id=<teacher_id>
        """
        teacher_id = request.query_params.get('teacher_id')
        if not teacher_id:
            return Response(
                {'error': 'teacher_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        allocations = self.get_queryset().filter(teacher_name_id=teacher_id)
        serializer = AllocatedSubjectListSerializer(allocations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        """
        Get allocations for a specific classroom
        ?classroom_id=<classroom_id>
        """
        classroom_id = request.query_params.get('classroom_id')
        if not classroom_id:
            return Response(
                {'error': 'classroom_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        allocations = self.get_queryset().filter(class_room_id=classroom_id)
        serializer = AllocatedSubjectListSerializer(allocations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_subject(self, request):
        """
        Get allocations for a specific subject
        ?subject_id=<subject_id>
        """
        subject_id = request.query_params.get('subject_id')
        if not subject_id:
            return Response(
                {'error': 'subject_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        allocations = self.get_queryset().filter(subject_id=subject_id)
        serializer = AllocatedSubjectListSerializer(allocations, many=True)
        return Response(serializer.data)

    @extend_schema(responses={200: TeacherCurriculumWorkspaceResponseSerializer})
    @action(detail=True, methods=['get'], url_path='curriculum')
    def curriculum(self, request, pk=None):
        """
        GET /api/academic/allocated-subjects/{id}/curriculum/
        Returns the resolved canonical curriculum content for this allocation.
        """
        allocation = self.get_object()

        # Build allocation summary
        classroom = allocation.class_room
        grade_level = classroom.grade_level if classroom else None
        allocation_summary = {
            'id': allocation.id,
            'subject_id': allocation.subject_id,
            'subject_name': allocation.subject.name if allocation.subject else '',
            'classroom_id': classroom.id if classroom else None,
            'classroom_name': str(classroom) if classroom else '',
            'grade_level_id': grade_level.id if grade_level else None,
            'grade_level_name': str(grade_level) if grade_level else '',
            'academic_year_id': allocation.academic_year_id,
            'academic_year_name': allocation.academic_year.name if allocation.academic_year else None,
            'term_id': allocation.term_id,
            'term_name': allocation.term.name if allocation.term else None,
        }

        # Resolve context deterministically
        resolution = CurriculumAssignmentResolver.resolve_for_allocation(allocation)
        status_code_str = resolution['status']

        if status_code_str != CurriculumAssignmentResolver.STATUS_RESOLVED:
            curriculum_info = None
            if resolution.get('curriculum_id') and resolution.get('curriculum_name'):
                curriculum_info = {
                    'id': resolution['curriculum_id'],
                    'name': resolution['curriculum_name'],
                    'version': '',
                    'authority_name': None,
                    'authority_type': None,
                    'description': '',
                }

            message_map = {
                CurriculumAssignmentResolver.STATUS_NO_CURRICULUM_ASSIGNED: (
                    "Your school has not assigned a curriculum framework to this class for this academic year."
                ),
                CurriculumAssignmentResolver.STATUS_SUBJECT_UNMAPPED: (
                    f"{resolution.get('curriculum_name') or 'Curriculum'} applies to this class, "
                    "but this school subject has not been mapped to a canonical curriculum subject."
                ),
                CurriculumAssignmentResolver.STATUS_CONFIGURATION_CONFLICT: (
                    "The curriculum for this teaching allocation cannot currently be resolved safely. "
                    "Contact an administrator."
                ),
            }

            return Response({
                'status': status_code_str,
                'message': message_map.get(status_code_str, "Curriculum context is unresolved."),
                'allocation': allocation_summary,
                'curriculum': curriculum_info,
                'curriculum_subject': None,
                'topics': [],
                'published_schemes': [],
                'resources': [],
            }, status=status.HTTP_200_OK)

        # Status is RESOLVED
        resolved_subject_id = resolution['curriculum_subject_id']
        curriculum_subject = CurriculumSubject.objects.select_related(
            'curriculum', 'grade_level'
        ).filter(pk=resolved_subject_id, is_active=True).first()

        if not curriculum_subject:
            return Response({
                'status': CurriculumAssignmentResolver.STATUS_NO_CURRICULUM_ASSIGNED,
                'message': "Resolved curriculum subject is no longer active or available.",
                'allocation': allocation_summary,
                'curriculum': None,
                'curriculum_subject': None,
                'topics': [],
                'published_schemes': [],
                'resources': [],
            }, status=status.HTTP_200_OK)

        curriculum_model = curriculum_subject.curriculum
        curriculum_info = {
            'id': curriculum_model.id,
            'name': curriculum_model.name,
            'version': curriculum_model.version or '',
            'authority_name': curriculum_model.authority_name or '',
            'authority_type': curriculum_model.authority_type or '',
            'description': curriculum_model.description or '',
        }

        curriculum_subject_info = {
            'id': curriculum_subject.id,
            'name': curriculum_subject.name,
            'code': curriculum_subject.code or '',
            'grade_level_id': curriculum_subject.grade_level_id,
            'grade_level_name': str(curriculum_subject.grade_level),
        }

        # 1. Topics with M2M subtopics, learning_objectives, guidance, and resource counts
        subtopics_prefetch = Prefetch(
            'subtopics',
            queryset=SubTopic.objects.filter(is_active=True).order_by('name'),
        )
        objectives_prefetch = Prefetch(
            'learning_objectives',
            queryset=LearningObjective.objects.filter(is_active=True).select_related('subtopic').order_by('order', 'id'),
        )

        topics_qs = CurriculumTopic.objects.filter(
            curriculum_subject=curriculum_subject,
            is_active=True,
        ).select_related('guidance').prefetch_related(
            subtopics_prefetch,
            objectives_prefetch,
        ).order_by('order', 'name')

        # 2. Resources for subject / topics
        resources_qs = CurriculumResource.objects.filter(
            curriculum_subject=curriculum_subject,
            is_active=True,
        ).select_related('curriculum_topic').order_by('order', 'title', 'id')

        resource_topic_counts = {}
        resources_data = []
        for res in resources_qs:
            topic_id = res.curriculum_topic_id
            if topic_id:
                resource_topic_counts[topic_id] = resource_topic_counts.get(topic_id, 0) + 1

            resources_data.append({
                'id': res.id,
                'title': res.title,
                'resource_type': res.resource_type,
                'resource_type_display': res.get_resource_type_display(),
                'content': res.content or '',
                'topic_id': topic_id,
                'topic_name': res.curriculum_topic.name if res.curriculum_topic else None,
                'published_scheme_entry_id': res.published_scheme_entry_id,
                'metadata': res.metadata or {},
            })

        topics_data = []
        for t in topics_qs:
            subtopics_list = [
                {'id': st.id, 'name': st.name}
                for st in t.subtopics.all()
            ]

            objectives_list = [
                {
                    'id': obj.id,
                    'description': obj.description,
                    'order': obj.order,
                    'subtopic_id': obj.subtopic_id,
                    'subtopic_name': obj.subtopic.name if obj.subtopic else None,
                }
                for obj in t.learning_objectives.all()
            ]

            guidance_data = None
            if hasattr(t, 'guidance') and t.guidance:
                guidance_data = {
                    'teacher_activities': t.guidance.teacher_activities or '',
                    'learner_activities': t.guidance.learner_activities or '',
                    'teaching_learning_materials': t.guidance.teaching_learning_materials or '',
                    'evaluation_guide': t.guidance.evaluation_guide or '',
                    'notes': t.guidance.notes or '',
                }

            topics_data.append({
                'id': t.id,
                'name': t.name,
                'theme': t.theme or '',
                'content_summary': t.content_summary or '',
                'order': t.order,
                'subtopics': subtopics_list,
                'learning_objectives': objectives_list,
                'guidance': guidance_data,
                'resource_count': resource_topic_counts.get(t.id, 0),
            })

        # 3. Published Schemes
        schemes_qs = PublishedScheme.objects.filter(
            curriculum_subject=curriculum_subject,
            is_active=True,
        ).prefetch_related('entries').order_by('name', 'version')

        schemes_data = []
        for s in schemes_qs:
            entries = [e for e in s.entries.all() if e.is_active]
            terms = sorted({e.term_number for e in entries if e.term_number is not None})
            schemes_data.append({
                'id': s.id,
                'name': s.name,
                'version': s.version or '',
                'description': s.description or '',
                'term_coverage': terms,
                'entry_count': len(entries),
            })

        return Response({
            'status': CurriculumAssignmentResolver.STATUS_RESOLVED,
            'message': None,
            'allocation': allocation_summary,
            'curriculum': curriculum_info,
            'curriculum_subject': curriculum_subject_info,
            'topics': topics_data,
            'published_schemes': schemes_data,
            'resources': resources_data,
        }, status=status.HTTP_200_OK)
