from django.db import models
from django.conf import settings
from academic.models import Subject, ClassRoom, Teacher, Student
from administration.models import AcademicYear, Term


class LessonTopic(models.Model):
    """
    Represents a specific lesson taught in a classroom for a subject.
    E.g., Week 3: Quadratic Equations, or Photosynthesis in Plants.
    """
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name='lesson_topics')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='lesson_topics')
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='lesson_topics')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='lesson_topics')
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True, related_name='lesson_topics')
    
    title = models.CharField(max_length=255)
    week_number = models.PositiveIntegerField(default=1, help_text="Curriculum week number (e.g. 1, 2, 3...)")
    summary = models.TextField(blank=True, help_text="Brief summary of the lesson concepts")
    learning_objectives = models.TextField(blank=True, help_text="Key takeaways students should understand")
    
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year', 'week_number', 'title']
        indexes = [
            models.Index(fields=['classroom', 'subject', 'week_number']),
        ]

    def __str__(self):
        return f"{self.subject.name} - W{self.week_number}: {self.title} ({self.classroom})"


class LessonMaterial(models.Model):
    """
    Teacher-provided study notes, syllabus chunks, documents, or textbook excerpts
    grounding the AI tutor for this specific lesson.
    """
    MATERIAL_TYPES = (
        ('text', 'Typed Note / Lecture Text'),
        ('document', 'Document (PDF / Word)'),
        ('link', 'External Reference URL'),
    )

    lesson_topic = models.ForeignKey(LessonTopic, on_delete=models.CASCADE, related_name='materials')
    title = models.CharField(max_length=255)
    material_type = models.CharField(max_length=20, choices=MATERIAL_TYPES, default='text')
    
    content_text = models.TextField(blank=True, help_text="Extracted text content used for AI context")
    document_file = models.FileField(upload_to='ai_tutor/materials/', blank=True, null=True)
    external_url = models.URLField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.lesson_topic.title})"


class TeacherAvatarSetting(models.Model):
    """
    Persona & voice settings for a teacher's AI embodiment.
    """
    AVATAR_STYLES = (
        ('photo_animated', 'Realistic Photo Avatar'),
        ('illustrated', 'Illustrated Academic Persona'),
        ('minimal_glow', 'Minimalist Soundwave & Glow'),
    )
    
    TEACHING_TONES = (
        ('encouraging', 'Warm & Encouraging (Praise-oriented)'),
        ('socratic', 'Socratic & Inquisitive (Asks guiding questions)'),
        ('step_by_step', 'Structured & Analytical (Step-by-step breakdowns)'),
        ('simplified', 'Simple & Intuitive (Rich analogies for younger pupils)'),
    )

    teacher = models.OneToOneField(Teacher, on_delete=models.CASCADE, related_name='ai_avatar_setting')
    avatar_style = models.CharField(max_length=30, choices=AVATAR_STYLES, default='photo_animated')
    teaching_tone = models.CharField(max_length=30, choices=TEACHING_TONES, default='socratic')
    custom_system_instructions = models.TextField(
        blank=True,
        help_text="Custom behavioral guidelines from the teacher (e.g., 'Never give direct solutions to algebra problems, guide them through factoring first.')"
    )
    is_ai_tutor_enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI Avatar Setting: {self.teacher.full_name if hasattr(self.teacher, 'full_name') else self.teacher}"


class TutorSession(models.Model):
    """
    An ongoing or past tutoring conversation between a student and their teacher's AI avatar.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='ai_tutor_sessions')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='ai_tutor_sessions')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='ai_tutor_sessions')
    lesson_topic = models.ForeignKey(LessonTopic, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_tutor_sessions')
    
    title = models.CharField(max_length=255, default='Tutoring Session')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Session: {self.student} with {self.teacher} ({self.subject.name})"


class TutorMessage(models.Model):
    """
    Individual message in an AI tutor session.
    """
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('assistant', 'Teacher AI'),
        ('system', 'System Context'),
    )

    session = models.ForeignKey(TutorSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    
    # Metadata for analytics & teacher insights
    tokens_used = models.PositiveIntegerField(default=0)
    topic_referenced = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:40]}..."
