import os
import logging
from typing import Generator, List, Dict, Any, Optional
from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger(__name__)


class GeminiTutorService:
    """
    Service integrating Google Gemini via modern google-genai SDK for SSync AI Tutor.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', '')
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("GEMINI_API_KEY not configured. AI Tutor will run in mock mode if called.")

    def build_system_instruction(
        self,
        teacher_name: str,
        subject_name: str,
        classroom_name: str,
        student_name: str,
        teaching_tone: str = 'socratic',
        custom_instructions: str = '',
        lesson_topic_title: str = '',
        lesson_summary: str = '',
        lesson_materials_text: str = ''
    ) -> str:
        """
        Builds the structured pedagogical teacher persona prompt.
        """
        tone_guidelines = {
            'socratic': "Use the Socratic method. Guide the student by asking thoughtful questions, encouraging their reasoning before giving the final answer.",
            'encouraging': "Be warm, praise the student's effort, build confidence, and explain concepts with relatable, uplifting examples.",
            'step_by_step': "Provide structured, numbered step-by-step explanations. Break difficult formulas down into digestible micro-steps.",
            'simplified': "Use clear, vivid real-world analogies suitable for young learners. Avoid unnecessary technical jargon.",
        }.get(teaching_tone, "Be a helpful, structured, and encouraging teacher.")

        prompt = f"""You are {teacher_name}, the {subject_name} teacher for {classroom_name} at SSync Academy.
You are currently speaking 1-on-1 with your student, {student_name}.

YOUR ROLE & PERSONA:
- Embody {teacher_name}'s teaching persona for {subject_name}.
- Teaching style: {tone_guidelines}
- Always maintain an encouraging, respectful, safe, and academically focused environment.
- Format equations clearly using standard Markdown or LaTeX ($...$ or $$...$$).

CURRENT LESSON CONTEXT:
- Active Topic: {lesson_topic_title or 'General ' + subject_name + ' Concepts'}
- Lesson Summary: {lesson_summary or 'Standard curriculum guidance'}

TEACHER'S LESSON STUDY NOTES & MATERIALS:
\"\"\"
{lesson_materials_text or 'Refer to standard school curriculum for ' + subject_name}
\"\"\"

ADDITIONAL TEACHER INSTRUCTIONS:
{custom_instructions or 'Focus on concept mastery and foundational understanding.'}

GUIDELINES FOR YOUR RESPONSE:
1. Address the student by name naturally when appropriate.
2. Directly address what the student asked, referencing the lesson notes above.
3. If the student asks for direct homework/test answers, guide them through the concept and method rather than simply giving away the final answer.
4. Keep explanations concise, clear, and easy to read on mobile or web interfaces.
"""
        return prompt

    def generate_reply_stream(
        self,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: str = 'gemini-2.5-flash'
    ) -> Generator[str, None, None]:
        """
        Streams AI tutor response tokens using the google-genai SDK.
        """
        if not self.client:
            yield "Hello! I am your AI Teacher Tutor. Please configure GEMINI_API_KEY in your settings or environment to enable live AI responses."
            return

        try:
            # Format contents for Gemini
            contents = []
            for msg in conversation_history:
                role = 'user' if msg.get('role') in ['student', 'user'] else 'model'
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg.get('content', ''))]
                    )
                )

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=1500,
            )

            # Stream generation
            response = self.client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )

            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            logger.error(f"Error generating AI tutor response: {e}")
            yield f"\n\n[Teacher Tutor Notice: Unable to complete response: {str(e)}]"

    def generate_reply_sync(
        self,
        system_instruction: str,
        conversation_history: List[Dict[str, str]],
        model: str = 'gemini-2.5-flash'
    ) -> str:
        """
        Synchronous reply generation for standard JSON endpoints.
        """
        tokens = list(self.generate_reply_stream(system_instruction, conversation_history, model=model))
        return "".join(tokens)
