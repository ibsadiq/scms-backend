import json
import logging
from typing import Generator, Optional, Dict, Any
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from ..models import TutorSession, TutorMessage
from .tutor_context_service import TutorContextService
from .tutor_llm_service import TutorLLMService
from .tutor_insight_service import TutorInsightService

logger = logging.getLogger(__name__)


class TutorResponseService:
    """
    Coordinates session message exchange, context assembly, LLM generation,
    message persistence, and analytical insight updates.
    """

    MAX_HISTORY_MESSAGES = 20

    @classmethod
    def authorize_session_access(
        cls,
        *,
        session: TutorSession,
        user,
    ):
        """
        Validates that the user is the student owning the session, the assigned teacher, or staff.
        """
        if getattr(user, "is_staff", False) or getattr(user, "is_admin", False) or getattr(user, "is_superuser", False):
            return

        if session.student and session.student.user_id == user.id:
            return

        if session.teacher and session.teacher.user_id == user.id:
            return

        raise PermissionDenied("You do not have access to this tutoring session.")

    @classmethod
    def _build_history_payload(
        cls,
        session: TutorSession,
    ):
        recent_messages = (
            session.messages
            .filter(role__in=[TutorMessage.Role.STUDENT, TutorMessage.Role.ASSISTANT])
            .order_by("-created_at")[:cls.MAX_HISTORY_MESSAGES]
        )
        # Reverse to chronological order
        chronological = list(reversed(recent_messages))
        return [
            {
                "role": "user" if m.role == TutorMessage.Role.STUDENT else "assistant",
                "content": m.content,
            }
            for m in chronological
        ]

    @classmethod
    def send_message_stream(
        cls,
        *,
        session: TutorSession,
        user,
        message_text: str,
    ) -> Generator[str, None, None]:
        """
        Processes student query and yields SSE tokens, saving messages atomically.
        """
        message_text = message_text.strip()
        if not message_text:
            raise ValidationError("Message text cannot be empty.")

        cls.authorize_session_access(session=session, user=user)

        # 1. Save student message
        TutorMessage.objects.create(
            session=session,
            role=TutorMessage.Role.STUDENT,
            content=message_text,
        )

        # 2. Build system instruction and history
        system_instruction = TutorContextService.build_system_instruction(session)
        history = cls._build_history_payload(session)

        # 3. Stream from LLM provider
        full_reply = []
        try:
            for token in TutorLLMService.generate_reply_stream(
                system_instruction=system_instruction,
                conversation_history=history,
            ):
                full_reply.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"

            complete_text = "".join(full_reply).strip()
            if complete_text:
                # 4. Save assistant message
                TutorMessage.objects.create(
                    session=session,
                    role=TutorMessage.Role.ASSISTANT,
                    content=complete_text,
                )

                # 5. Trigger/Update session insight
                try:
                    TutorInsightService.generate_or_update_session_insight(session)
                except Exception as e:
                    logger.warning("Failed to update session insight: %s", e)

            yield f"data: {json.dumps({'done': True, 'full_content': complete_text})}\n\n"

        except Exception as e:
            logger.error("Error during streaming tutor response: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    @classmethod
    @transaction.atomic
    def send_message_sync(
        cls,
        *,
        session: TutorSession,
        user,
        message_text: str,
    ) -> TutorMessage:
        """
        Synchronous JSON handler for message exchange.
        """
        message_text = message_text.strip()
        if not message_text:
            raise ValidationError("Message text cannot be empty.")

        cls.authorize_session_access(session=session, user=user)

        # 1. Save student message
        TutorMessage.objects.create(
            session=session,
            role=TutorMessage.Role.STUDENT,
            content=message_text,
        )

        # 2. Build prompt context and history
        system_instruction = TutorContextService.build_system_instruction(session)
        history = cls._build_history_payload(session)

        # 3. Generate response
        reply_text = TutorLLMService.generate_reply_sync(
            system_instruction=system_instruction,
            conversation_history=history,
        )

        # 4. Save assistant message
        assistant_msg = TutorMessage.objects.create(
            session=session,
            role=TutorMessage.Role.ASSISTANT,
            content=reply_text,
        )

        # 5. Update session insight
        try:
            TutorInsightService.generate_or_update_session_insight(session)
        except Exception as e:
            logger.warning("Failed to update session insight: %s", e)

        return assistant_msg
