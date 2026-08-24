import logging
from django.db import transaction
from ..models import TutorSession, TutorSessionInsight, TutorMessage

logger = logging.getLogger(__name__)


class TutorInsightService:
    """
    Generates and updates analytical, teacher-facing insights from tutoring dialogues.
    """

    @classmethod
    @transaction.atomic
    def generate_or_update_session_insight(
        cls,
        session: TutorSession,
    ) -> TutorSessionInsight:
        """
        Derives actionable insights from session messages and updates TutorSessionInsight.
        """
        messages = list(
            session.messages
            .filter(role__in=[TutorMessage.Role.STUDENT, TutorMessage.Role.ASSISTANT])
            .order_by("created_at")
        )

        if not messages:
            insight, _ = TutorSessionInsight.objects.get_or_create(
                session=session,
                defaults={
                    "summary": "Session started; no messages exchanged yet.",
                    "misconceptions": [],
                    "concepts_struggled_with": [],
                    "concepts_mastered": [],
                    "follow_up_recommended": False,
                    "teacher_attention_required": False,
                },
            )
            return insight

        student_msgs = [m.content for m in messages if m.role == TutorMessage.Role.STUDENT]
        assistant_msgs = [m.content for m in messages if m.role == TutorMessage.Role.ASSISTANT]

        # Extract linked learning objective descriptions if available
        lo_descriptions = list(
            session.learning_objectives.values_list("description", flat=True)
        )
        topic_title = (
            session.curriculum_topic.topic.name
            if session.curriculum_topic and session.curriculum_topic.topic
            else (session.lesson_plan.title if session.lesson_plan else session.subject.name)
        )

        struggles = []
        misconceptions = []
        mastered = []
        teacher_attention = False
        follow_up = False

        # Heuristic/Deterministic analysis of conversation dynamics
        total_student_queries = len(student_msgs)
        struggle_keywords = ["confused", "don't understand", "not getting", "why does", "stuck", "help with", "error", "wrong"]
        struggle_count = sum(
            1 for msg in student_msgs if any(k in msg.lower() for k in struggle_keywords)
        )

        if struggle_count >= 2:
            struggles.append(f"Repeated difficulty clarifying concepts in {topic_title}")
            follow_up = True

        if struggle_count >= 4 or total_student_queries >= 8:
            teacher_attention = True
            follow_up = True

        # Summarize session engagement
        summary = (
            f"Student engaged in {total_student_queries} inquiry turn(s) on '{topic_title}'. "
            f"{'Follow-up recommended in class.' if follow_up else 'Student demonstrated progressive understanding.'}"
        )

        insight, _ = TutorSessionInsight.objects.update_or_create(
            session=session,
            defaults={
                "summary": summary,
                "misconceptions": misconceptions,
                "concepts_struggled_with": struggles,
                "concepts_mastered": mastered,
                "follow_up_recommended": follow_up,
                "teacher_attention_required": teacher_attention,
            },
        )

        return insight
