import os
import logging
from abc import ABC, abstractmethod
from typing import Generator, List, Dict, Any, Optional
from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger(__name__)


class BaseTutorLLMProvider(ABC):
    """
    Abstract interface for AI Tutor LLM providers.
    """

    @abstractmethod
    def generate_reply_stream(
        self,
        *,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> Generator[str, None, None]:
        pass

    @abstractmethod
    def generate_reply_sync(
        self,
        *,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        pass


class GeminiTutorProvider(BaseTutorLLMProvider):
    """
    Google Gemini provider implementation via modern google-genai SDK.
    """

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or getattr(settings, "GEMINI_API_KEY", "")
        )
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("GEMINI_API_KEY not configured. AI Tutor will run in fallback notice mode.")

    def generate_reply_stream(
        self,
        *,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> Generator[str, None, None]:
        if not self.client:
            yield "Hello! I am your AI Teacher Tutor. Please configure GEMINI_API_KEY in your environment to enable live AI responses."
            return

        target_model = model or self.DEFAULT_MODEL
        try:
            contents = []
            for msg in conversation_history:
                role = "user" if msg.get("role") in ["student", "user"] else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg.get("content", ""))],
                    )
                )

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=1500,
            )

            response = self.client.models.generate_content_stream(
                model=target_model,
                contents=contents,
                config=config,
            )

            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            logger.error("Error generating AI tutor response via Gemini: %s", e)
            yield f"\n\n[Teacher Tutor Notice: Unable to complete response: {str(e)}]"

    def generate_reply_sync(
        self,
        *,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        tokens = list(
            self.generate_reply_stream(
                system_instruction=system_instruction,
                conversation_history=conversation_history,
                model=model,
            )
        )
        return "".join(tokens)


class TutorLLMService:
    """
    Provider-neutral service facade used by the domain layer.
    """

    _provider: Optional[BaseTutorLLMProvider] = None

    @classmethod
    def get_provider(cls) -> BaseTutorLLMProvider:
        if cls._provider is None:
            cls._provider = GeminiTutorProvider()
        return cls._provider

    @classmethod
    def set_provider(cls, provider: BaseTutorLLMProvider):
        cls._provider = provider

    @classmethod
    def generate_reply_stream(
        cls,
        *,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> Generator[str, None, None]:
        return cls.get_provider().generate_reply_stream(
            system_instruction=system_instruction,
            conversation_history=conversation_history,
            model=model,
        )

    @classmethod
    def generate_reply_sync(
        cls,
        *,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        return cls.get_provider().generate_reply_sync(
            system_instruction=system_instruction,
            conversation_history=conversation_history,
            model=model,
        )
