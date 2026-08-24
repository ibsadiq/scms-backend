from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Count
from django.core.exceptions import ValidationError, PermissionDenied
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import TeacherAvatarSetting, TutorSession, TutorMessage, TutorSessionInsight
from .serializers import (
    TeacherAvatarSettingSerializer,
    TutorSessionSerializer,
    TutorMessageSerializer,
    TutorSessionInsightSerializer,
)
from .services import (
    TutorSessionService,
    TutorResponseService,
    TutorInsightService,
)
from academic.models import (
    Student,
    Teacher,
    Subject,
    LessonPlan,
    LessonDelivery,
    CurriculumTopic,
    LearningObjective,
    Parent,
)


class TutorSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for student-teacher AI tutor sessions grounded in authoritative curriculum context.
    """
    queryset = (
        TutorSession.objects.all()
        .select_related("student", "teacher", "subject", "lesson_plan", "lesson_delivery", "curriculum_topic", "insight")
        .prefetch_related("messages", "learning_objectives")
    )
    serializer_class = TutorSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if getattr(user, "is_student", False):
            student = Student.objects.filter(user=user).first()
            if student:
                return qs.filter(student=student)
            return qs.none()

        if getattr(user, "is_teacher", False):
            teacher = getattr(user, "teacher", None) or Teacher.objects.filter(user=user).first()
            if teacher:
                return qs.filter(teacher=teacher)
            return qs.none()

        if getattr(user, "is_staff", False) or getattr(user, "is_admin", False) or getattr(user, "is_superuser", False):
            return qs

        return qs.none()

    @action(detail=False, methods=["post"], url_path="start-or-get")
    def start_or_get_session(self, request):
        """
        Starts or retrieves an active tutoring session for the student with their allocated teacher.
        """
        user = request.user
        student = None

        if getattr(user, "is_student", False):
            student = Student.objects.filter(user=user).first()
        else:
            student_id = request.data.get("student_id")
            if student_id and (getattr(user, "is_staff", False) or getattr(user, "is_admin", False)):
                student = Student.objects.filter(id=student_id).first()

        if not student:
            return Response({"error": "Student profile not found"}, status=status.HTTP_400_BAD_REQUEST)

        subject_id = request.data.get("subject_id")
        if not subject_id:
            return Response({"error": "subject_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        subject = get_object_or_404(Subject, id=subject_id)

        lesson_plan_id = request.data.get("lesson_plan_id")
        lesson_delivery_id = request.data.get("lesson_delivery_id")
        curriculum_topic_id = request.data.get("curriculum_topic_id")
        learning_objective_ids = request.data.get("learning_objective_ids", [])

        lesson_plan = LessonPlan.objects.filter(id=lesson_plan_id).first() if lesson_plan_id else None
        lesson_delivery = LessonDelivery.objects.filter(id=lesson_delivery_id).first() if lesson_delivery_id else None
        curriculum_topic = CurriculumTopic.objects.filter(id=curriculum_topic_id).first() if curriculum_topic_id else None
        learning_objectives = (
            list(LearningObjective.objects.filter(id__in=learning_objective_ids))
            if learning_objective_ids
            else None
        )

        try:
            session = TutorSessionService.start_or_get_session(
                student=student,
                subject=subject,
                lesson_plan=lesson_plan,
                lesson_delivery=lesson_delivery,
                curriculum_topic=curriculum_topic,
                learning_objectives=learning_objectives,
            )
        except ValidationError as e:
            return Response({"error": e.messages if hasattr(e, "messages") else str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="send-message")
    def send_message(self, request, pk=None):
        """
        Sends a question to the AI tutor and returns the teacher's AI response (Streaming SSE or JSON).
        """
        session = self.get_object()
        message_text = request.data.get("message", "").strip()
        stream_response = request.data.get("stream", True)

        if not message_text:
            return Response({"error": "Message text is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if stream_response:
                response = StreamingHttpResponse(
                    TutorResponseService.send_message_stream(
                        session=session,
                        user=request.user,
                        message_text=message_text,
                    ),
                    content_type="text/event-stream",
                )
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Buffering"] = "no"
                return response
            else:
                assistant_msg = TutorResponseService.send_message_sync(
                    session=session,
                    user=request.user,
                    message_text=message_text,
                )
                return Response(TutorMessageSerializer(assistant_msg).data, status=status.HTTP_200_OK)

        except (ValidationError, PermissionDenied) as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({"error": f"Unable to process message: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"], url_path="parent-digest")
    def parent_digest(self, request):
        """
        Provides parent view of their authorized children's AI Tutor study and inquiry activity.
        """
        parent = Parent.objects.filter(user=request.user).first()
        is_admin = getattr(request.user, "is_staff", False) or getattr(request.user, "is_admin", False)

        if not parent and not is_admin:
            return Response({"error": "Parent profile not found"}, status=status.HTTP_403_FORBIDDEN)

        children = Student.objects.filter(parent_guardian=parent) if parent else Student.objects.filter(is_active=True)[:5]
        digest = []

        for child in children:
            child_sessions = TutorSession.objects.filter(student=child)
            total_sessions = child_sessions.count()
            total_questions = TutorMessage.objects.filter(session__in=child_sessions, role=TutorMessage.Role.STUDENT).count()
            subjects_explored = list(child_sessions.values_list("subject__name", flat=True).distinct())

            recent_queries = []
            for msg in (
                TutorMessage.objects.filter(session__in=child_sessions, role=TutorMessage.Role.STUDENT)
                .select_related("session", "session__subject", "session__curriculum_topic", "session__curriculum_topic__topic")
                .order_by("-created_at")[:8]
            ):
                topic_title = (
                    msg.session.curriculum_topic.topic.name
                    if msg.session.curriculum_topic and msg.session.curriculum_topic.topic
                    else "General Support"
                )
                recent_queries.append({
                    "id": msg.id,
                    "subject": msg.session.subject.name,
                    "topic": topic_title,
                    "question": msg.content,
                    "created_at": msg.created_at,
                })

            digest.append({
                "student_id": child.id,
                "student_name": getattr(child, "full_name", f"{child.first_name} {child.last_name}"),
                "admission_number": child.admission_number,
                "classroom": str(getattr(child, "classroom", "N/A")),
                "total_sessions": total_sessions,
                "total_questions": total_questions,
                "subjects_explored": subjects_explored,
                "recent_queries": recent_queries,
            })

        return Response(digest, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="admin-overview")
    def admin_overview(self, request):
        """
        Provides school-wide analytics on AI Tutor usage using efficient ORM aggregations.
        """
        if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_admin", False) or getattr(request.user, "is_superuser", False)):
            return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

        total_sessions = TutorSession.objects.count()
        total_questions = TutorMessage.objects.filter(role=TutorMessage.Role.STUDENT).count()
        total_active_teachers = TutorSession.objects.values("teacher").distinct().count()
        total_active_students = TutorSession.objects.values("student").distinct().count()

        top_subjects = list(
            TutorSession.objects.values("subject__name")
            .annotate(sessions=Count("id"))
            .order_by("-sessions")[:6]
        )

        return Response({
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "total_active_teachers": total_active_teachers,
            "total_active_students": total_active_students,
            "top_subjects": [{"subject": item["subject__name"], "sessions": item["sessions"]} for item in top_subjects],
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="teacher-insights")
    def teacher_insights(self, request):
        """
        Provides aggregated statistics and insights on student inquiries for the logged-in teacher.
        """
        teacher = getattr(request.user, "teacher", None) or Teacher.objects.filter(user=request.user).first()
        is_admin = getattr(request.user, "is_admin", False) or getattr(request.user, "is_staff", False)

        if not teacher and not is_admin:
            return Response({"error": "Teacher profile not found"}, status=status.HTTP_403_FORBIDDEN)

        sessions = TutorSession.objects.all()
        if teacher:
            sessions = sessions.filter(teacher=teacher)

        total_sessions = sessions.count()
        total_questions = TutorMessage.objects.filter(session__in=sessions, role=TutorMessage.Role.STUDENT).count()

        # Follow-up flags
        insights_requiring_attention = list(
            TutorSessionInsight.objects.filter(
                session__in=sessions,
                teacher_attention_required=True,
            ).select_related("session", "session__student", "session__subject")[:10]
        )

        attention_list = [
            {
                "session_id": ins.session_id,
                "student_name": getattr(ins.session.student, "full_name", str(ins.session.student)),
                "subject": ins.session.subject.name,
                "summary": ins.summary,
                "struggles": ins.concepts_struggled_with,
            }
            for ins in insights_requiring_attention
        ]

        return Response({
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "attention_required_sessions": attention_list,
        }, status=status.HTTP_200_OK)


class TeacherAvatarSettingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for teachers to configure their AI Avatar Persona.
    """
    queryset = TeacherAvatarSetting.objects.all().select_related("teacher")
    serializer_class = TeacherAvatarSettingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "is_teacher", False):
            teacher = getattr(user, "teacher", None) or Teacher.objects.filter(user=user).first()
            if teacher:
                return self.queryset.filter(teacher=teacher)
        return self.queryset

    @action(detail=False, methods=["get", "post", "patch"], url_path="my-setting")
    def my_setting(self, request):
        teacher = getattr(request.user, "teacher", None) or Teacher.objects.filter(user=request.user).first()
        if not teacher:
            return Response({"error": "Teacher profile not found"}, status=status.HTTP_404_NOT_FOUND)

        setting, _ = TeacherAvatarSetting.objects.get_or_create(
            teacher=teacher,
            defaults={
                "avatar_style": TeacherAvatarSetting.AvatarStyle.PHOTO_ANIMATED,
                "teaching_tone": TeacherAvatarSetting.TeachingTone.SOCRATIC,
                "custom_system_instructions": "",
            },
        )

        if request.method in ["POST", "PATCH"]:
            serializer = self.get_serializer(setting, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)
