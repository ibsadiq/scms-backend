from typing import Dict, Any, List, Optional
from academic.models import (
    Student,
    Teacher,
    Subject,
    LessonPlan,
    LessonDelivery,
    CurriculumTopic,
    LearningObjective,
    StudentClassEnrollment,
)
from ..models import TutorSession, TeacherAvatarSetting
from .tutor_material_service import TutorMaterialService


class TutorContextService:
    """
    Assembles structured, pedagogically prioritized grounding context
    from authoritative curriculum, lesson plan, and delivery records.
    """

    @classmethod
    def get_student_active_enrollment(
        cls,
        student: Student,
    ) -> Optional[StudentClassEnrollment]:
        return (
            StudentClassEnrollment.objects
            .filter(student=student, is_active=True)
            .select_related("classroom", "classroom__grade_level", "academic_year")
            .order_by("-academic_year__start_date")
            .first()
        )

    @classmethod
    def assemble_structured_context(
        cls,
        session: TutorSession,
    ) -> Dict[str, Any]:
        """
        Gathers complete structured context for a tutor session.
        """
        student = session.student
        teacher = session.teacher
        subject = session.subject
        lesson_plan = session.lesson_plan
        lesson_delivery = session.lesson_delivery
        curriculum_topic = session.curriculum_topic

        # If session has lesson_plan but no delivery, check if delivery exists
        if lesson_plan and not lesson_delivery:
            lesson_delivery = getattr(lesson_plan, "delivery", None)

        # If session has lesson_plan but no curriculum_topic, resolve from scheme_item
        if lesson_plan and not curriculum_topic and lesson_plan.scheme_item_id:
            curriculum_topic = lesson_plan.scheme_item.curriculum_topic

        # Student context
        enrollment = cls.get_student_active_enrollment(student)
        classroom_str = str(enrollment.classroom) if enrollment else str(getattr(student, "classroom", "Classroom"))
        grade_str = (
            str(enrollment.classroom.grade_level)
            if enrollment and enrollment.classroom and enrollment.classroom.grade_level
            else "Standard Grade Level"
        )
        student_name = getattr(student, "full_name", f"{student.first_name} {student.last_name}").strip()

        # Teacher context & avatar settings
        avatar_setting = getattr(teacher, "ai_avatar_setting", None)
        tone = avatar_setting.teaching_tone if avatar_setting else "socratic"
        custom_instructions = avatar_setting.custom_system_instructions if avatar_setting else ""
        allow_direct_answers = avatar_setting.allow_direct_answers if avatar_setting else False
        teacher_name = getattr(teacher, "full_name", str(teacher))

        # Curriculum & Objectives prioritization
        delivered_objectives: List[str] = []
        planned_undelivered_objectives: List[str] = []
        broader_topic_objectives: List[str] = []

        if lesson_delivery and lesson_delivery.pk:
            delivered_objectives = [
                obj.description
                for obj in lesson_delivery.objectives_covered.all()
            ]

        if lesson_plan:
            delivered_pks = set(lesson_delivery.objectives_covered.values_list("pk", flat=True)) if lesson_delivery else set()
            planned_undelivered_objectives = [
                obj.description
                for obj in lesson_plan.learning_objectives.exclude(pk__in=delivered_pks)
            ]

        if curriculum_topic:
            all_topic_objs = curriculum_topic.learning_objectives.filter(is_active=True)
            handled_descriptions = set(delivered_objectives + planned_undelivered_objectives)
            broader_topic_objectives = [
                obj.description
                for obj in all_topic_objs
                if obj.description not in handled_descriptions
            ]

        # Lesson plan details
        lesson_plan_data: Dict[str, Any] = {}
        if lesson_plan:
            lesson_plan_data = {
                "title": lesson_plan.title,
                "lesson_date": str(lesson_plan.lesson_date),
                "lesson_content": lesson_plan.lesson_content,
                "previous_knowledge": lesson_plan.previous_knowledge,
                "introduction": lesson_plan.introduction,
                "teacher_activities": lesson_plan.teacher_activities,
                "learner_activities": lesson_plan.learner_activities,
                "teaching_materials": lesson_plan.teaching_materials,
                "evaluation": lesson_plan.evaluation,
                "assignment_notes": lesson_plan.assignment_notes,
                "references": lesson_plan.references,
            }

        # Lesson delivery notes
        lesson_delivery_data: Dict[str, Any] = {}
        if lesson_delivery:
            lesson_delivery_data = {
                "status": lesson_delivery.status,
                "taught_at": str(lesson_delivery.taught_at),
                "teacher_notes": lesson_delivery.teacher_notes,
                "learner_response": lesson_delivery.learner_response,
                "follow_up_required": lesson_delivery.follow_up_required,
                "follow_up_notes": lesson_delivery.follow_up_notes,
            }

        # Materials text
        materials_text = TutorMaterialService.get_grounding_materials_text(lesson_plan=lesson_plan)

        return {
            "student": {
                "name": student_name,
                "admission_number": student.admission_number,
                "classroom": classroom_str,
                "grade_level": grade_str,
            },
            "teacher": {
                "name": teacher_name,
                "tone": tone,
                "custom_instructions": custom_instructions,
                "allow_direct_answers": allow_direct_answers,
            },
            "subject": {
                "name": subject.name,
                "code": getattr(subject, "code", ""),
            },
            "curriculum": {
                "topic_name": curriculum_topic.topic.name if curriculum_topic and curriculum_topic.topic else "",
                "delivered_objectives": delivered_objectives,
                "planned_undelivered_objectives": planned_undelivered_objectives,
                "broader_topic_objectives": broader_topic_objectives,
            },
            "lesson_plan": lesson_plan_data,
            "lesson_delivery": lesson_delivery_data,
            "materials_text": materials_text,
        }

    @classmethod
    def build_system_instruction(
        cls,
        session: TutorSession,
    ) -> str:
        """
        Builds the comprehensive pedagogical teacher persona prompt.
        """
        ctx = cls.assemble_structured_context(session)

        student = ctx["student"]
        teacher = ctx["teacher"]
        subject = ctx["subject"]
        curriculum = ctx["curriculum"]
        plan = ctx["lesson_plan"]
        delivery = ctx["lesson_delivery"]
        materials = ctx["materials_text"]

        tone_guidelines = {
            "socratic": "Use the Socratic method. Guide the student by asking thoughtful questions, encouraging their reasoning before giving the final answer.",
            "encouraging": "Be warm, praise the student's effort, build confidence, and explain concepts with relatable, uplifting examples.",
            "step_by_step": "Provide structured, numbered step-by-step explanations. Break difficult formulas down into digestible micro-steps.",
            "simplified": "Use clear, vivid real-world analogies suitable for young learners. Avoid unnecessary technical jargon.",
        }.get(teacher["tone"], "Be a helpful, structured, and encouraging teacher.")

        # Pedagogical rules for direct answer permission
        answer_guideline = (
            "You MAY provide direct answers when requested, but ensure the conceptual derivation is clearly explained."
            if teacher["allow_direct_answers"]
            else "DO NOT give away direct solutions or final answers to homework/exam questions. Guide the student through the method and concept."
        )

        delivered_str = (
            "\n".join(f"- {o}" for o in curriculum["delivered_objectives"])
            if curriculum["delivered_objectives"]
            else "None formally recorded as delivered yet."
        )

        planned_str = (
            "\n".join(f"- {o}" for o in curriculum["planned_undelivered_objectives"])
            if curriculum["planned_undelivered_objectives"]
            else "None pending."
        )

        prompt = f"""You are {teacher['name']}, the {subject['name']} teacher for {student['classroom']} ({student['grade_level']}) at SSync Academy.
You are currently speaking 1-on-1 with your student, {student['name']}.

YOUR ROLE & PERSONA:
- Embody {teacher['name']}'s teaching persona for {subject['name']}.
- Teaching style: {tone_guidelines}
- Homework & Assessment Policy: {answer_guideline}
- Always maintain an encouraging, respectful, safe, and academically focused environment.
- Format equations clearly using standard Markdown or LaTeX ($...$ or $$...$$).

CURRICULUM & LESSON CONTEXT:
- Active Topic: {curriculum['topic_name'] or plan.get('title') or subject['name'] + ' Fundamentals'}
- Grade Level: {student['grade_level']}

TEACHING STATUS (PEDAGOGICAL GROUNDING):
1. ACTUALLY TAUGHT IN CLASS (Prioritize & Reinforce First):
{delivered_str}

2. PLANNED / UPCOMING CONCEPTS (Not yet confirmed delivered in class):
{planned_str}

TEACHER'S LESSON NOTES & CONTENT:
{plan.get('lesson_content') or 'Standard school curriculum guidance for ' + subject['name']}
{f"Teacher Delivery Notes: {delivery.get('teacher_notes')}" if delivery.get('teacher_notes') else ""}

APPROVED STUDY MATERIALS:
\"\"\"
{materials or 'Refer to standard approved textbooks and curriculum guidelines.'}
\"\"\"

ADDITIONAL TEACHER INSTRUCTIONS:
{teacher['custom_instructions'] or 'Focus on concept mastery and foundational understanding.'}

GUIDELINES FOR YOUR RESPONSE:
1. Address the student by name naturally when appropriate.
2. Clearly distinguish between concepts already taught in class versus upcoming topics.
3. If explaining planned but undelivered content, frame it gently as an introduction or preview.
4. Use the teacher's vocabulary, analogies, and lesson content where available.
5. Never invent or hallucinate materials that do not exist.
6. Keep responses clear, concise, and structured for student learning.
"""
        return prompt
