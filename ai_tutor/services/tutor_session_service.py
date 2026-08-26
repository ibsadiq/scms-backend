from typing import Optional, Iterable
from django.core.exceptions import ValidationError
from django.db import transaction
from academic.models import (
    Student,
    Teacher,
    Subject,
    LessonPlan,
    LessonDelivery,
    CurriculumTopic,
    LearningObjective,
    AllocatedSubject,
    StudentClassEnrollment,
)
from ..models import TutorSession, TeacherAvatarSetting


class TutorSessionService:
    """
    Core domain service managing the lifecycle, validation, and teacher assignment
    of AI Tutor sessions.
    """

    @classmethod
    def resolve_student_enrollment(
        cls,
        student: Student,
    ) -> StudentClassEnrollment:
        """
        Resolves the student's authoritative active enrollment.
        """
        enrollment = (
            StudentClassEnrollment.objects
            .filter(student=student, is_active=True)
            .select_related("classroom", "classroom__grade_level", "academic_year")
            .order_by("-academic_year__start_date")
            .first()
        )
        if not enrollment or not enrollment.classroom:
            raise ValidationError("Student does not have an active classroom enrollment.")
        return enrollment

    @classmethod
    def resolve_assigned_teacher(
        cls,
        *,
        student: Student,
        subject: Subject,
        enrollment: Optional[StudentClassEnrollment] = None,
    ) -> Teacher:
        """
        Deterministically resolves the teacher assigned to the student's classroom for the subject.
        Prevents arbitrary teacher selection and rejects random fallbacks.
        """
        if not enrollment:
            enrollment = cls.resolve_student_enrollment(student)

        allocation = (
            AllocatedSubject.objects
            .filter(
                class_room=enrollment.classroom,
                subject=subject,
            )
            .select_related("teacher_name")
            .first()
        )

        if not allocation or not allocation.teacher_name:
            raise ValidationError(
                f"No teacher is assigned to teach {subject.name} in {enrollment.classroom}."
            )

        return allocation.teacher_name

    @classmethod
    def validate_session_context(
        cls,
        *,
        student: Student,
        teacher: Teacher,
        subject: Subject,
        enrollment: StudentClassEnrollment,
        lesson_plan: Optional[LessonPlan] = None,
        lesson_delivery: Optional[LessonDelivery] = None,
        curriculum_topic: Optional[CurriculumTopic] = None,
        learning_objectives: Optional[Iterable[LearningObjective]] = None,
    ):
        """
        Validates academic scopes and consistency among all context models.
        """
        # 1. Validate teacher AI enablement
        avatar_setting = getattr(teacher, "ai_avatar_setting", None)
        if avatar_setting and not avatar_setting.is_ai_tutor_enabled:
            raise ValidationError("AI Tutor is currently disabled for this teacher.")

        # 2. Validate lesson plan
        if lesson_plan:
            if lesson_plan.allocation.subject_id != subject.id:
                raise ValidationError("The selected lesson plan does not belong to this subject.")
            if lesson_plan.allocation.class_room_id != enrollment.classroom_id:
                raise ValidationError("The selected lesson plan was not planned for your classroom.")

        # 3. Validate lesson delivery
        if lesson_delivery:
            if not lesson_plan:
                lesson_plan = lesson_delivery.lesson_plan
            elif lesson_delivery.lesson_plan_id != lesson_plan.id:
                raise ValidationError("The selected lesson delivery does not match the lesson plan.")

        # 4. Validate curriculum topic
        grade_level = (
            enrollment.classroom.grade_level
            if enrollment.classroom and enrollment.classroom.grade_level
            else None
        )
        if curriculum_topic:
            curr_sub = curriculum_topic.curriculum_subject
            if curr_sub.subject_id != subject.id:
                raise ValidationError("The curriculum topic does not belong to this subject.")
            if grade_level and curr_sub.grade_level_id != grade_level.id:
                raise ValidationError("The curriculum topic does not match your current grade level.")

        # 5. Validate learning objectives
        if learning_objectives:
            for lo in learning_objectives:
                if curriculum_topic and lo.curriculum_topic_id != curriculum_topic.id:
                    raise ValidationError(
                        f"Learning objective '{lo.description[:30]}' does not belong to the selected topic."
                    )

    @classmethod
    @transaction.atomic
    def start_or_get_session(
        cls,
        *,
        student: Student,
        subject: Subject,
        lesson_plan: Optional[LessonPlan] = None,
        lesson_delivery: Optional[LessonDelivery] = None,
        curriculum_topic: Optional[CurriculumTopic] = None,
        learning_objectives: Optional[Iterable[LearningObjective]] = None,
    ) -> TutorSession:
        """
        Creates or retrieves an active tutoring session for the student with their allocated teacher.
        """
        enrollment = cls.resolve_student_enrollment(student)
        teacher = cls.resolve_assigned_teacher(student=student, subject=subject, enrollment=enrollment)

        cls.validate_session_context(
            student=student,
            teacher=teacher,
            subject=subject,
            enrollment=enrollment,
            lesson_plan=lesson_plan,
            lesson_delivery=lesson_delivery,
            curriculum_topic=curriculum_topic,
            learning_objectives=learning_objectives,
        )

        # Derive auto title
        topic_name = ""
        if curriculum_topic and curriculum_topic.topic:
            topic_name = curriculum_topic.topic.name
        elif lesson_plan and lesson_plan.title:
            topic_name = lesson_plan.title
        title = f"{subject.name} - {topic_name}" if topic_name else f"{subject.name} Tutoring"

        # Look up existing recent session with matching primary context
        session = (
            TutorSession.objects
            .filter(
                student=student,
                teacher=teacher,
                subject=subject,
                lesson_plan=lesson_plan,
                curriculum_topic=curriculum_topic,
            )
            .order_by("-updated_at")
            .first()
        )

        if not session:
            session = TutorSession.objects.create(
                student=student,
                teacher=teacher,
                subject=subject,
                lesson_plan=lesson_plan,
                lesson_delivery=lesson_delivery,
                curriculum_topic=curriculum_topic,
                title=title,
            )
            if learning_objectives:
                session.learning_objectives.set(learning_objectives)
            elif lesson_plan:
                session.learning_objectives.set(lesson_plan.learning_objectives.all())
        else:
            if lesson_delivery and session.lesson_delivery != lesson_delivery:
                session.lesson_delivery = lesson_delivery
                session.save(update_fields=["lesson_delivery", "updated_at"])

        return session
