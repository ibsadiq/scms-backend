from django.db import models
from academic.models import (
    Subject,
    Teacher,
    Student,
    CurriculumTopic,
    LearningObjective,
    LessonPlan,
    LessonDelivery,
)


class TeacherAvatarSetting(models.Model):
    """
    Persona & voice settings for a teacher's AI embodiment.
    """
    class AvatarStyle(models.TextChoices):
        PHOTO_ANIMATED = "photo_animated", "Realistic Photo Avatar"
        ILLUSTRATED = "illustrated", "Illustrated Academic Persona"
        MINIMAL_GLOW = "minimal_glow", "Minimalist Soundwave & Glow"

    class TeachingTone(models.TextChoices):
        ENCOURAGING = "encouraging", "Warm & Encouraging (Praise-oriented)"
        SOCRATIC = "socratic", "Socratic & Inquisitive (Asks guiding questions)"
        STEP_BY_STEP = "step_by_step", "Structured & Analytical (Step-by-step breakdowns)"
        SIMPLIFIED = "simplified", "Simple & Intuitive (Rich analogies for younger pupils)"

    teacher = models.OneToOneField(
        Teacher,
        on_delete=models.CASCADE,
        related_name="ai_avatar_setting",
    )
    avatar_style = models.CharField(
        max_length=30,
        choices=AvatarStyle.choices,
        default=AvatarStyle.PHOTO_ANIMATED,
    )
    teaching_tone = models.CharField(
        max_length=30,
        choices=TeachingTone.choices,
        default=TeachingTone.SOCRATIC,
    )
    custom_system_instructions = models.TextField(
        blank=True,
        help_text="Custom behavioral guidelines from the teacher.",
    )
    is_ai_tutor_enabled = models.BooleanField(default=True)
    allow_direct_answers = models.BooleanField(
        default=False,
        help_text="Controls whether the tutor is allowed to provide direct answers versus guiding students through reasoning.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        teacher_name = getattr(self.teacher, "full_name", str(self.teacher))
        return f"AI Avatar Setting: {teacher_name}"


class TutorSession(models.Model):
    """
    An ongoing or past tutoring conversation between a student and their teacher's AI avatar,
    grounded in authoritative academic curriculum and lesson delivery context.
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="ai_tutor_sessions",
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="ai_tutor_sessions",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="ai_tutor_sessions",
    )
    lesson_plan = models.ForeignKey(
        LessonPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_tutor_sessions",
    )
    lesson_delivery = models.ForeignKey(
        LessonDelivery,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_tutor_sessions",
    )
    curriculum_topic = models.ForeignKey(
        CurriculumTopic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_tutor_sessions",
    )
    learning_objectives = models.ManyToManyField(
        LearningObjective,
        blank=True,
        related_name="ai_tutor_sessions",
    )

    title = models.CharField(max_length=255, default="Tutoring Session")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["student", "subject", "-updated_at"]),
            models.Index(fields=["teacher", "-updated_at"]),
        ]

    def __str__(self):
        return f"Session: {self.student} with {self.teacher} ({self.subject.name})"


class TutorMessage(models.Model):
    """
    Individual message in an AI tutor session linked to structured learning objectives.
    """
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        ASSISTANT = "assistant", "Teacher AI"
        SYSTEM = "system", "System Context"

    session = models.ForeignKey(
        TutorSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )
    content = models.TextField()
    tokens_used = models.PositiveIntegerField(default=0)
    learning_objective = models.ForeignKey(
        LearningObjective,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutor_messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.role}] {self.content[:40]}..."


class TutorSessionInsight(models.Model):
    """
    Actionable teacher-facing analytics and pedagogical insights derived from a tutoring session.
    """
    session = models.OneToOneField(
        TutorSession,
        on_delete=models.CASCADE,
        related_name="insight",
    )
    summary = models.TextField(blank=True)
    misconceptions = models.JSONField(default=list, blank=True)
    concepts_struggled_with = models.JSONField(default=list, blank=True)
    concepts_mastered = models.JSONField(default=list, blank=True)
    follow_up_recommended = models.BooleanField(default=False)
    teacher_attention_required = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Insight for {self.session}"
