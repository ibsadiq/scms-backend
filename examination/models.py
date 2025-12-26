import datetime
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from academic.models import Student, Teacher, ClassRoom, StudentClassEnrollment, Subject
from administration.models import AcademicYear, Term
from users.models import CustomUser


class GradeScale(models.Model):
    """Translate a numeric grade to some other scale.
    Example: Letter grade or 4.0 scale."""

    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name

    def get_rule(self, grade):
        if grade is None:
            return None
        rule = self.gradescalerule_set.filter(
            min_grade__lte=grade, max_grade__gte=grade
        ).first()
        if not rule:
            # Optionally log or raise a warning
            print(f"No rule found for grade: {grade}")
        return rule

    def to_letter(self, grade):
        rule = self.get_rule(grade)
        if rule:
            return rule.letter_grade
        return None  # Return None if no rule found

    def to_numeric(self, grade):
        rule = self.get_rule(grade)
        if rule:
            return rule.numeric_scale
        return None  # Return None if no rule found


class GradeScaleRule(models.Model):
    """One rule for a grade scale."""

    min_grade = models.DecimalField(max_digits=5, decimal_places=2)
    max_grade = models.DecimalField(max_digits=5, decimal_places=2)
    letter_grade = models.CharField(max_length=50, blank=True, null=True)
    numeric_scale = models.DecimalField(max_digits=5, decimal_places=2, blank=True)
    grade_scale = models.ForeignKey(GradeScale, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("min_grade", "max_grade", "grade_scale")
        indexes = [
            models.Index(fields=["min_grade", "max_grade", "grade_scale"]),
        ]

    def __str__(self):
        return f"{self.min_grade}-{self.max_grade} {self.letter_grade} {self.numeric_scale}"

    def clean(self):
        """Ensure consistency between letter grade and numeric scale."""
        if not self.letter_grade and not self.numeric_scale:
            raise ValidationError(
                "Either a letter grade or numeric scale must be provided."
            )
        if self.letter_grade and self.numeric_scale is None:
            raise ValidationError(
                "If a letter grade is provided, numeric scale must also be provided."
            )
        if self.numeric_scale and self.letter_grade is None:
            raise ValidationError(
                "If a numeric scale is provided, a letter grade must also be provided."
            )

    def save(self, *args, **kwargs):
        if self.min_grade >= self.max_grade:
            raise ValidationError("min_grade must be less than max_grade.")
        super().save(*args, **kwargs)


class Result(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    gpa = models.FloatField(null=True)
    cat_gpa = models.FloatField(null=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    term = models.OneToOneField(Term, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return str(self.student)

    def clean(self):
        """Validate that GPA is within a valid range (0.0 - 4.0)."""
        if self.gpa is not None and (self.gpa < 0.0 or self.gpa > 4.0):
            raise ValidationError("GPA must be between 0.0 and 4.0.")
        if self.cat_gpa is not None and (self.cat_gpa < 0.0 or self.cat_gpa > 4.0):
            raise ValidationError("CAT GPA must be between 0.0 and 4.0.")


class ExaminationListHandler(models.Model):
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    ends_date = models.DateField()
    out_of = models.IntegerField()
    classrooms = models.ManyToManyField(ClassRoom, related_name="class_exams")
    comments = models.CharField(
        max_length=200, blank=True, null=True, help_text="Comments Regarding Exam"
    )
    created_by = models.ForeignKey(Teacher, on_delete=models.CASCADE, null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    @property
    def status(self):
        today = datetime.now().date()
        if today > self.ends_date:
            return "Done"
        elif self.start_date <= today <= self.ends_date:
            return "Ongoing"
        return "Coming Up"

    def __str__(self):
        return self.name

    def clean(self):
        """Ensure the start date is not later than the end date."""
        if self.start_date > self.ends_date:
            raise ValidationError("Start date cannot be later than end date.")
        super(ExaminationListHandler, self).clean()


class MarksManagement(models.Model):
    exam_name = models.ForeignKey(
        ExaminationListHandler, on_delete=models.CASCADE, related_name="exam_marks"
    )
    points_scored = models.FloatField()
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="subject_marks"
    )
    student = models.ForeignKey(
        StudentClassEnrollment, on_delete=models.CASCADE, related_name="student_marks"
    )
    created_by = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name="marks_entered"
    )
    date_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.exam_name} - {self.student} - {self.points_scored}"

    def clean(self):
        """
        Validate points scored and teacher authorization.
        Phase 1.3: Added teacher authorization check.
        """
        # Validate points scored range
        if self.points_scored < 0 or self.points_scored > self.exam_name.out_of:
            raise ValidationError(
                f"Points scored must be between 0 and {self.exam_name.out_of}."
            )

        # Phase 1.3: Check if teacher is authorized to enter marks for this subject/classroom
        if self.created_by and self.subject and self.student:
            from academic.models import AllocatedSubject

            # Get student's classroom
            student_classroom = self.student.class_room if hasattr(self.student, 'class_room') else None

            if student_classroom:
                # Check if teacher is allocated to this subject and classroom
                is_allocated = AllocatedSubject.objects.filter(
                    teacher_name=self.created_by,
                    subject=self.subject,
                    class_room=student_classroom
                ).exists()

                if not is_allocated:
                    raise ValidationError(
                        f"You are not authorized to enter marks for {self.subject.name} "
                        f"in {student_classroom}. Please check your subject allocations."
                    )

        super(MarksManagement, self).clean()


# ============================================================================
# RESULT COMPUTATION MODELS (Phase 1.1)
# ============================================================================

class TermResult(models.Model):
    """
    Stores computed results for a student in a specific term.
    This is the master result record that aggregates all subject results.
    """
    GRADE_CHOICES = [
        ('A', 'Excellent (A)'),
        ('B', 'Very Good (B)'),
        ('C', 'Good (C)'),
        ('D', 'Pass (D)'),
        ('E', 'Poor (E)'),
        ('F', 'Fail (F)'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='term_results'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Classroom at the time of result computation"
    )

    # Computed scores
    total_marks = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Sum of all subject scores"
    )
    total_possible = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Total possible marks across all subjects"
    )
    average_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Average percentage across all subjects"
    )
    grade = models.CharField(
        max_length=2,
        choices=GRADE_CHOICES,
        help_text="Overall grade for the term"
    )
    gpa = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text="Grade Point Average (0.00 - 4.00)"
    )

    # Ranking
    position_in_class = models.IntegerField(
        help_text="Student's rank in the class",
        null=True,
        blank=True
    )
    total_students = models.IntegerField(
        help_text="Total number of students in class",
        null=True,
        blank=True
    )

    # Remarks
    class_teacher_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Remarks from class teacher"
    )
    principal_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Remarks from principal/head teacher"
    )

    # Metadata
    computed_date = models.DateTimeField(
        default=timezone.now,
        help_text="When the result was computed"
    )
    computed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='computed_results'
    )
    is_published = models.BooleanField(
        default=False,
        help_text="Whether result is visible to parents/students"
    )
    published_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the result was published"
    )

    class Meta:
        unique_together = ('student', 'term', 'academic_year')
        ordering = ['-academic_year__start_date', '-term__start_date', 'position_in_class']
        indexes = [
            models.Index(fields=['student', 'term']),
            models.Index(fields=['classroom', 'term']),
            models.Index(fields=['is_published']),
        ]
        verbose_name = "Term Result"
        verbose_name_plural = "Term Results"

    def __str__(self):
        return f"{self.student.full_name} - {self.term.name} ({self.academic_year.name})"

    @property
    def status(self):
        """Return pass/fail status"""
        return "Pass" if self.grade in ['A', 'B', 'C', 'D'] else "Fail"

    @property
    def percentage_str(self):
        """Return formatted percentage"""
        return f"{self.average_percentage}%"

    def publish(self, published_by=None):
        """Publish result to make it visible to parents/students"""
        self.is_published = True
        self.published_date = timezone.now()
        self.save()

    def unpublish(self):
        """Unpublish result"""
        self.is_published = False
        self.published_date = None
        self.save()


class SubjectResult(models.Model):
    """
    Stores individual subject results for a term.
    Links to TermResult as the parent record.
    """
    GRADE_CHOICES = [
        ('A', 'Excellent (A)'),
        ('B', 'Very Good (B)'),
        ('C', 'Good (C)'),
        ('D', 'Pass (D)'),
        ('E', 'Poor (E)'),
        ('F', 'Fail (F)'),
    ]

    term_result = models.ForeignKey(
        TermResult,
        on_delete=models.CASCADE,
        related_name='subject_results'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Teacher who taught this subject"
    )

    # Score breakdown (following Nigerian system: CA + Exam)
    ca_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Continuous Assessment score (usually 40%)"
    )
    ca_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('40.00'),
        help_text="Maximum CA score possible"
    )
    exam_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Examination score (usually 60%)"
    )
    exam_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('60.00'),
        help_text="Maximum exam score possible"
    )

    # Computed totals
    total_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="CA + Exam score"
    )
    total_possible = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        help_text="Maximum possible score (usually 100)"
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage score"
    )
    grade = models.CharField(
        max_length=2,
        choices=GRADE_CHOICES,
        help_text="Letter grade for this subject"
    )
    grade_point = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text="Grade point (0.00 - 4.00)"
    )

    # Ranking
    position_in_subject = models.IntegerField(
        null=True,
        blank=True,
        help_text="Student's rank in this subject within the class"
    )
    total_students = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total students who took this subject"
    )
    highest_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Highest score in class for this subject"
    )
    lowest_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Lowest score in class for this subject"
    )
    class_average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Class average for this subject"
    )

    # Teacher remarks
    teacher_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Subject teacher's remarks"
    )

    class Meta:
        unique_together = ('term_result', 'subject')
        ordering = ['subject__subject_code', 'subject__name']
        indexes = [
            models.Index(fields=['term_result', 'subject']),
            models.Index(fields=['subject', 'grade']),
        ]
        verbose_name = "Subject Result"
        verbose_name_plural = "Subject Results"

    def __str__(self):
        return f"{self.term_result.student.full_name} - {self.subject.name} ({self.grade})"

    @property
    def status(self):
        """Return pass/fail status"""
        return "Pass" if self.grade in ['A', 'B', 'C', 'D'] else "Fail"

    def save(self, *args, **kwargs):
        """Auto-calculate totals before saving"""
        # Calculate total score
        self.total_score = self.ca_score + self.exam_score

        # Calculate percentage
        if self.total_possible > 0:
            self.percentage = (self.total_score / self.total_possible) * 100
        else:
            self.percentage = Decimal('0.00')

        super().save(*args, **kwargs)


# ============================================================================
# REPORT CARD MODEL (Phase 1.2)
# ============================================================================

class ReportCard(models.Model):
    """
    Stores generated report card PDFs for term results.
    Allows caching of generated PDFs and tracking of downloads.
    """
    term_result = models.OneToOneField(
        TermResult,
        on_delete=models.CASCADE,
        related_name='report_card',
        help_text="Associated term result"
    )
    pdf_file = models.FileField(
        upload_to='report_cards/%Y/%m/',
        null=True,
        blank=True,
        help_text="Generated PDF file"
    )
    generated_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the PDF was generated"
    )
    generated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_report_cards'
    )
    download_count = models.IntegerField(
        default=0,
        help_text="Number of times downloaded"
    )
    last_downloaded = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last download timestamp"
    )

    class Meta:
        ordering = ['-generated_date']
        indexes = [
            models.Index(fields=['term_result']),
            models.Index(fields=['generated_date']),
        ]
        verbose_name = "Report Card"
        verbose_name_plural = "Report Cards"

    def __str__(self):
        return f"Report Card - {self.term_result.student.full_name} ({self.term_result.term.name})"

    def increment_download_count(self):
        """Increment download counter and update timestamp"""
        self.download_count += 1
        self.last_downloaded = timezone.now()
        self.save(update_fields=['download_count', 'last_downloaded'])
