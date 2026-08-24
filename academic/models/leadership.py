from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from administration.models import AcademicYear
from .choices import AcademicLeadershipRole, AcademicWorkflow, ApprovalRoute, SectionType
from .structure import Department
from .staff import Teacher


class AcademicLeadershipAssignment(models.Model):
    """
    Authoritative assignment of a Teacher to an academic leadership role.
    Scoped by academic year, department (for secondary HOD), or section (for primary/nursery).
    """
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="leadership_assignments",
    )
    role = models.CharField(
        max_length=20,
        choices=AcademicLeadershipRole.choices,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="leadership_assignments",
        help_text="Required if role is HOD.",
    )
    section = models.CharField(
        max_length=20,
        choices=SectionType.choices,
        null=True,
        blank=True,
        help_text="Required if role is HEAD_TEACHER.",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="leadership_assignments",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-academic_year__start_date", "role", "department", "section"]
        constraints = [
            models.UniqueConstraint(
                fields=["department", "academic_year"],
                condition=models.Q(is_active=True, role="HOD"),
                name="unique_active_hod_per_department_year",
            ),
            models.UniqueConstraint(
                fields=["section", "academic_year"],
                condition=models.Q(is_active=True, role="HEAD_TEACHER"),
                name="unique_active_head_teacher_per_section_year",
            ),
        ]

    def clean(self):
        errors = {}
        if self.role == AcademicLeadershipRole.HOD:
            if not self.department:
                errors["department"] = "Department is required for HOD assignment."
            if self.section:
                errors["section"] = "Section should be empty for HOD assignment."
        elif self.role == AcademicLeadershipRole.HEAD_TEACHER:
            if not self.section:
                errors["section"] = "Section is required for Head Teacher assignment."
            if self.department:
                errors["department"] = "Department should be empty for Head Teacher assignment."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        scope = self.department.name if self.department else self.get_section_display()
        return f"{self.get_role_display()}: {self.teacher} ({scope} - {self.academic_year})"


class AcademicApprovalPolicy(models.Model):
    """
    Per-school/tenant configuration defining required approval routes per academic workflow.
    Defaults to ADMIN_ONLY to preserve seamless operation without requiring HOD configuration.
    """
    workflow = models.CharField(
        max_length=30,
        choices=AcademicWorkflow.choices,
        unique=True,
    )
    approval_route = models.CharField(
        max_length=30,
        choices=ApprovalRoute.choices,
        default=ApprovalRoute.ADMIN_ONLY,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workflow"]
        verbose_name_plural = "Academic Approval Policies"

    def __str__(self):
        return f"{self.get_workflow_display()}: {self.get_approval_route_display()}"
