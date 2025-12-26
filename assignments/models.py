"""
Assignment Models - Phase 1.7: Assignment & Homework Management

Handles:
- Assignment creation and management
- Student submissions
- Grading and feedback
- File attachments
- Late submission tracking
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.utils import timezone
from django.core.exceptions import ValidationError

from academic.models import Teacher, Student, ClassRoom, Subject
from administration.models import AcademicYear, Term


class Assignment(models.Model):
    """
    Assignment created by teacher for a classroom.
    """
    
    ASSIGNMENT_TYPES = [
        ('homework', 'Homework'),
        ('project', 'Project'),
        ('quiz', 'Quiz'),
        ('research', 'Research Paper'),
        ('essay', 'Essay'),
        ('lab_report', 'Lab Report'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('closed', 'Closed'),
    ]
    
    title = models.CharField(max_length=200, help_text="Assignment title")
    description = models.TextField(help_text="Detailed instructions")
    assignment_type = models.CharField(
        max_length=20,
        choices=ASSIGNMENT_TYPES,
        default='homework'
    )
    
    # Assignment belongs to
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name='assignments',
        help_text="Classroom this assignment is for"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='assignments',
        null=True,
        blank=True
    )
    
    # Dates
    assigned_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(help_text="When assignment is due")
    
    # Grading
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        validators=[MinValueValidator(0)],
        help_text="Maximum possible score"
    )
    
    # Options
    allow_late_submission = models.BooleanField(
        default=True,
        help_text="Allow submissions after due date"
    )
    late_penalty_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage penalty for late submission"
    )
    
    # Status
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft'
    )
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['classroom', 'status', '-due_date']),
            models.Index(fields=['teacher', '-assigned_date']),
        ]
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"
    
    def __str__(self):
        return f"{self.title} - {self.classroom} ({self.subject.name})"
    
    def clean(self):
        """Validate assignment data"""
        if self.due_date and self.due_date < timezone.now():
            if self.status == 'draft':
                raise ValidationError("Due date cannot be in the past for new assignments")
    
    @property
    def is_overdue(self):
        """Check if assignment is past due date"""
        return timezone.now() > self.due_date
    
    @property
    def total_students(self):
        """Get total number of students in classroom"""
        return self.classroom.students.filter(is_active=True).count()
    
    @property
    def submission_count(self):
        """Get number of submissions"""
        return self.submissions.count()
    
    @property
    def graded_count(self):
        """Get number of graded submissions"""
        return self.submissions.filter(grade__isnull=False).count()
    
    @property
    def submission_rate(self):
        """Get submission percentage"""
        total = self.total_students
        if total == 0:
            return 0
        return round((self.submission_count / total) * 100, 1)


class AssignmentAttachment(models.Model):
    """
    Files attached to an assignment by the teacher.
    """
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(
        upload_to='assignments/teacher_attachments/%Y/%m/',
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'jpg', 'png']
        )]
    )
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(help_text="File size in bytes", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Assignment Attachment"
        verbose_name_plural = "Assignment Attachments"
    
    def __str__(self):
        return f"{self.file_name} ({self.assignment.title})"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_name:
            self.file_name = self.file.name
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)


class AssignmentSubmission(models.Model):
    """
    Student submission for an assignment.
    """
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='assignment_submissions'
    )
    
    # Submission content
    submission_text = models.TextField(
        blank=True,
        help_text="Text submission (optional)"
    )
    
    # Dates
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status
    is_late = models.BooleanField(
        default=False,
        help_text="Submitted after due date"
    )
    
    class Meta:
        ordering = ['-submitted_at']
        unique_together = ['assignment', 'student']
        indexes = [
            models.Index(fields=['assignment', 'student']),
            models.Index(fields=['student', '-submitted_at']),
        ]
        verbose_name = "Assignment Submission"
        verbose_name_plural = "Assignment Submissions"
    
    def __str__(self):
        return f"{self.student.full_name} - {self.assignment.title}"
    
    def save(self, *args, **kwargs):
        """Auto-detect if submission is late"""
        if not self.pk:  # Only on creation
            self.is_late = timezone.now() > self.assignment.due_date
        super().save(*args, **kwargs)
    
    @property
    def is_graded(self):
        """Check if submission has been graded"""
        return hasattr(self, 'grade')


class SubmissionAttachment(models.Model):
    """
    Files attached to a student submission.
    """
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(
        upload_to='assignments/student_submissions/%Y/%m/',
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'jpg', 'png', 'zip']
        )]
    )
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(help_text="File size in bytes", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Submission Attachment"
        verbose_name_plural = "Submission Attachments"
    
    def __str__(self):
        return f"{self.file_name} ({self.submission.student.full_name})"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_name:
            self.file_name = self.file.name
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)


class AssignmentGrade(models.Model):
    """
    Grade and feedback for a student submission.
    """
    submission = models.OneToOneField(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='grade'
    )
    
    # Grading
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Score achieved"
    )
    late_penalty_applied = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
        help_text="Points deducted for late submission"
    )
    
    # Feedback
    feedback = models.TextField(
        blank=True,
        help_text="Teacher feedback/comments"
    )
    
    # Grader
    graded_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name='graded_assignments'
    )
    graded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Assignment Grade"
        verbose_name_plural = "Assignment Grades"
    
    def __str__(self):
        return f"{self.submission.student.full_name} - {self.final_score}/{self.submission.assignment.max_score}"
    
    def clean(self):
        """Validate grade"""
        if self.score > self.submission.assignment.max_score:
            raise ValidationError(f"Score cannot exceed maximum score of {self.submission.assignment.max_score}")
    
    @property
    def final_score(self):
        """Calculate final score after late penalty"""
        return max(0, self.score - self.late_penalty_applied)
    
    @property
    def percentage(self):
        """Calculate percentage score"""
        max_score = self.submission.assignment.max_score
        if max_score == 0:
            return 0
        return round((self.final_score / max_score) * 100, 1)
    
    @property
    def grade_letter(self):
        """Get letter grade based on percentage"""
        pct = self.percentage
        if pct >= 90:
            return 'A'
        elif pct >= 80:
            return 'B'
        elif pct >= 70:
            return 'C'
        elif pct >= 60:
            return 'D'
        else:
            return 'F'
