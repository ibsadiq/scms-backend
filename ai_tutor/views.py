import json
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import LessonTopic, LessonMaterial, TeacherAvatarSetting, TutorSession, TutorMessage
from .serializers import (
    LessonTopicSerializer, LessonMaterialSerializer,
    TeacherAvatarSettingSerializer, TutorSessionSerializer, TutorMessageSerializer
)
from .services.llm_service import GeminiTutorService
from academic.models import Student, Teacher, Subject, ClassRoom, AllocatedSubject


class LessonTopicViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing and browsing lesson topics.
    """
    queryset = LessonTopic.objects.all().select_related('classroom', 'subject', 'teacher', 'academic_year', 'term').prefetch_related('materials')
    serializer_class = LessonTopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        classroom_id = self.request.query_params.get('classroom')
        subject_id = self.request.query_params.get('subject')
        week = self.request.query_params.get('week')

        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if week:
            qs = qs.filter(week_number=week)

        # If student, limit to published topics
        if getattr(self.request.user, 'is_student', False):
            qs = qs.filter(is_published=True)

        return qs

    def perform_create(self, serializer):
        teacher = getattr(self.request.user, 'teacher', None) or Teacher.objects.filter(user=self.request.user).first()
        if teacher and not serializer.validated_data.get('teacher'):
            serializer.save(teacher=teacher)
        else:
            serializer.save()

    @action(detail=True, methods=['post'], url_path='add-material')
    def add_material(self, request, pk=None):
        topic = self.get_object()
        title = request.data.get('title', 'Study Note')
        material_type = request.data.get('material_type', 'text')
        content_text = request.data.get('content_text', '')
        document_file = request.FILES.get('document_file')

        # Auto-extract text from uploaded PDF if provided
        if document_file and document_file.name.lower().endswith('.pdf'):
            try:
                import pypdf
                reader = pypdf.PdfReader(document_file)
                extracted_pages = []
                for page in reader.pages[:30]:  # extract up to 30 pages
                    text = page.extract_text()
                    if text:
                        extracted_pages.append(text)
                if extracted_pages:
                    pdf_text = "\n".join(extracted_pages)
                    content_text = f"{content_text}\n{pdf_text}".strip() if content_text else pdf_text
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Error extracting PDF text: {e}")

        material = LessonMaterial.objects.create(
            lesson_topic=topic,
            title=title,
            material_type=material_type,
            content_text=content_text,
            document_file=document_file
        )
        return Response(LessonMaterialSerializer(material).data, status=status.HTTP_201_CREATED)


class TutorSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for student-teacher AI tutor sessions.
    """
    queryset = TutorSession.objects.all().select_related('student', 'teacher', 'subject', 'lesson_topic').prefetch_related('messages')
    serializer_class = TutorSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        # If student, show own sessions
        if getattr(user, 'is_student', False):
            student = Student.objects.filter(user=user).first()
            if student:
                return qs.filter(student=student)
            return qs.none()

        # If teacher, show sessions conducted with their AI embodiment
        if getattr(user, 'is_teacher', False):
            teacher = Teacher.objects.filter(user=user).first()
            if teacher:
                return qs.filter(teacher=teacher)
            return qs.none()

        return qs

    @action(detail=False, methods=['get'], url_path='parent-digest')
    def parent_digest(self, request):
        """
        Provides parent view of their children's AI Tutor study and inquiry activity.
        """
        from academic.models import Parent
        parent = Parent.objects.filter(user=request.user).first()
        if not parent and not (getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_admin', False)):
            return Response({"error": "Parent profile not found"}, status=status.HTTP_403_FORBIDDEN)

        children = Student.objects.filter(parent_guardian=parent) if parent else Student.objects.filter(is_active=True)[:5]
        digest = []

        for child in children:
            child_sessions = TutorSession.objects.filter(student=child)
            total_sessions = child_sessions.count()
            total_questions = TutorMessage.objects.filter(session__in=child_sessions, role='student').count()

            # Active subjects
            subjects_explored = list(child_sessions.values_list('subject__name', flat=True).distinct())

            # Recent questions asked by child
            recent_queries = []
            for msg in TutorMessage.objects.filter(session__in=child_sessions, role='student').select_related('session', 'session__subject', 'session__lesson_topic').order_by('-created_at')[:8]:
                recent_queries.append({
                    'id': msg.id,
                    'subject': msg.session.subject.name,
                    'topic': msg.session.lesson_topic.title if msg.session.lesson_topic else 'General Support',
                    'question': msg.content,
                    'created_at': msg.created_at
                })

            digest.append({
                'student_id': child.id,
                'student_name': child.full_name if hasattr(child, 'full_name') else f"{child.first_name} {child.last_name}",
                'admission_number': child.admission_number,
                'classroom': str(child.classroom) if child.classroom else 'N/A',
                'total_sessions': total_sessions,
                'total_questions': total_questions,
                'subjects_explored': subjects_explored,
                'recent_queries': recent_queries
            })

        return Response(digest, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='admin-overview')
    def admin_overview(self, request):
        """
        Provides school-wide analytics on AI Tutor usage.
        """
        if not (getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_superuser', False)):
            return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

        total_sessions = TutorSession.objects.count()
        total_questions = TutorMessage.objects.filter(role='student').count()
        total_active_teachers = TutorSession.objects.values('teacher').distinct().count()
        total_active_students = TutorSession.objects.values('student').distinct().count()

        # Subject breakdown
        subject_counts = {}
        for s in TutorSession.objects.select_related('subject'):
            name = s.subject.name
            subject_counts[name] = subject_counts.get(name, 0) + 1

        top_subjects = sorted([{'subject': k, 'sessions': v} for k, v in subject_counts.items()], key=lambda x: x['sessions'], reverse=True)[:6]

        return Response({
            'total_sessions': total_sessions,
            'total_questions': total_questions,
            'total_active_teachers': total_active_teachers,
            'total_active_students': total_active_students,
            'top_subjects': top_subjects,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='teacher-insights')
    def teacher_insights(self, request):
        """
        Provides aggregated statistics on student inquiries for the logged-in teacher.
        """
        teacher = getattr(request.user, 'teacher', None) or Teacher.objects.filter(user=request.user).first()
        is_admin = getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_staff', False)

        if not teacher and not is_admin:
            return Response({"error": "Teacher profile not found"}, status=status.HTTP_403_FORBIDDEN)

        sessions = TutorSession.objects.all()
        if teacher:
            sessions = sessions.filter(teacher=teacher)

        total_sessions = sessions.count()
        total_questions = TutorMessage.objects.filter(session__in=sessions, role='student').count()

        # Recent questions asked by students
        recent_student_messages = TutorMessage.objects.filter(
            session__in=sessions,
            role='student'
        ).select_related('session', 'session__student', 'session__subject', 'session__lesson_topic').order_by('-created_at')[:15]

        queries_data = []
        for msg in recent_student_messages:
            student = msg.session.student
            queries_data.append({
                'id': msg.id,
                'student_name': student.full_name if hasattr(student, 'full_name') else str(student),
                'subject_name': msg.session.subject.name,
                'topic_title': msg.session.lesson_topic.title if msg.session.lesson_topic else 'General Support',
                'question': msg.content,
                'created_at': msg.created_at
            })

        # Most queried topics
        topic_counts = {}
        for s in sessions.filter(lesson_topic__isnull=False).select_related('lesson_topic', 'subject'):
            top_title = f"{s.subject.name}: {s.lesson_topic.title}"
            topic_counts[top_title] = topic_counts.get(top_title, 0) + 1

        top_topics = sorted([{'topic': k, 'inquiries': v} for k, v in topic_counts.items()], key=lambda x: x['inquiries'], reverse=True)[:5]

        return Response({
            'total_sessions': total_sessions,
            'total_questions': total_questions,
            'top_topics': top_topics,
            'recent_queries': queries_data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='start-or-get')
    def start_or_get_session(self, request):
        """
        Creates or retrieves an active tutoring session for a student with a specific teacher & subject.
        """
        student = None
        if getattr(request.user, 'is_student', False):
            student = Student.objects.filter(user=request.user).first()
        else:
            student_id = request.data.get('student_id')
            if student_id:
                student = Student.objects.filter(id=student_id).first()

        if not student:
            return Response({"error": "Student profile not found"}, status=status.HTTP_400_BAD_REQUEST)

        subject_id = request.data.get('subject_id')
        teacher_id = request.data.get('teacher_id')
        lesson_topic_id = request.data.get('lesson_topic_id')

        subject = get_object_or_404(Subject, id=subject_id)
        
        # If teacher_id is not provided, look up teacher assigned to student's classroom for this subject
        teacher = None
        if teacher_id:
            teacher = get_object_or_404(Teacher, id=teacher_id)
        elif student.classroom:
            allocation = AllocatedSubject.objects.filter(
                class_room=student.classroom,
                subject=subject
            ).first()
            if allocation and allocation.teacher_name:
                teacher = allocation.teacher_name

        if not teacher:
            # Fallback to any teacher specializing in this subject
            teacher = Teacher.objects.filter(subject_specialization=subject).first() or Teacher.objects.first()

        lesson_topic = None
        if lesson_topic_id:
            lesson_topic = LessonTopic.objects.filter(id=lesson_topic_id).first()

        # Find existing active session or create new (resilient to race conditions)
        session = TutorSession.objects.filter(
            student=student,
            teacher=teacher,
            subject=subject,
            lesson_topic=lesson_topic,
        ).order_by('-updated_at').first()

        created = False
        if not session:
            session = TutorSession.objects.create(
                student=student,
                teacher=teacher,
                subject=subject,
                lesson_topic=lesson_topic,
                title=f"{subject.name} - {lesson_topic.title if lesson_topic else 'Tutoring'}"
            )
            created = True

        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='send-message')
    def send_message(self, request, pk=None):
        """
        Sends a question to the AI tutor and returns the teacher's AI response (Streaming SSE or JSON).
        """
        session = self.get_object()
        student_message_text = request.data.get('message', '').strip()
        stream_response = request.data.get('stream', True)

        if not student_message_text:
            return Response({"error": "Message text is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Save student message
        TutorMessage.objects.create(
            session=session,
            role='student',
            content=student_message_text
        )

        # 2. Assemble context
        teacher = session.teacher
        student = session.student
        subject = session.subject
        topic = session.lesson_topic

        # Fetch Avatar settings
        avatar_setting = getattr(teacher, 'ai_avatar_setting', None)
        tone = avatar_setting.teaching_tone if avatar_setting else 'socratic'
        custom_instructions = avatar_setting.custom_system_instructions if avatar_setting else ''

        # Fetch lesson materials text
        materials_text = ""
        if topic:
            for mat in topic.materials.all():
                if mat.content_text:
                    materials_text += f"\n--- Material: {mat.title} ---\n{mat.content_text}\n"

        # Teacher name
        teacher_name = teacher.full_name if hasattr(teacher, 'full_name') else f"Teacher {teacher.user.last_name if teacher.user else ''}"
        student_name = student.full_name if hasattr(student, 'full_name') else f"{student.first_name}"
        classroom_name = str(student.classroom) if student.classroom else "Classroom"

        llm_service = GeminiTutorService()
        system_instruction = llm_service.build_system_instruction(
            teacher_name=teacher_name,
            subject_name=subject.name,
            classroom_name=classroom_name,
            student_name=student_name,
            teaching_tone=tone,
            custom_instructions=custom_instructions,
            lesson_topic_title=topic.title if topic else '',
            lesson_summary=topic.summary if topic else '',
            lesson_materials_text=materials_text
        )

        # Build history
        recent_messages = session.messages.order_by('created_at')[:20]
        history = [{'role': m.role, 'content': m.content} for m in recent_messages]

        # 3. If streaming requested:
        if stream_response:
            def event_stream():
                full_reply = []
                try:
                    for token in llm_service.generate_reply_stream(system_instruction, history):
                        full_reply.append(token)
                        yield f"data: {json.dumps({'token': token})}\n\n"
                    
                    complete_text = "".join(full_reply)
                    # Save assistant message
                    TutorMessage.objects.create(
                        session=session,
                        role='assistant',
                        content=complete_text
                    )
                    yield f"data: {json.dumps({'done': True, 'full_content': complete_text})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

            response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
        else:
            # Sync JSON
            reply_text = llm_service.generate_reply_sync(system_instruction, history)
            assistant_msg = TutorMessage.objects.create(
                session=session,
                role='assistant',
                content=reply_text
            )
            return Response(TutorMessageSerializer(assistant_msg).data, status=status.HTTP_200_OK)


class TeacherAvatarSettingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for teachers to configure their AI Avatar Persona.
    """
    queryset = TeacherAvatarSetting.objects.all().select_related('teacher')
    serializer_class = TeacherAvatarSettingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_teacher', False):
            teacher = Teacher.objects.filter(user=user).first()
            if teacher:
                return self.queryset.filter(teacher=teacher)
        return self.queryset

    @action(detail=False, methods=['get', 'post', 'patch'], url_path='my-setting')
    def my_setting(self, request):
        teacher = getattr(request.user, 'teacher', None) or Teacher.objects.filter(user=request.user).first()
        if not teacher:
            return Response({"error": "Teacher profile not found"}, status=status.HTTP_404_NOT_FOUND)

        setting, _ = TeacherAvatarSetting.objects.get_or_create(
            teacher=teacher,
            defaults={
                'avatar_style': 'photo_animated',
                'teaching_tone': 'socratic',
                'custom_system_instructions': ''
            }
        )

        if request.method in ['POST', 'PATCH']:
            serializer = self.get_serializer(setting, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)

