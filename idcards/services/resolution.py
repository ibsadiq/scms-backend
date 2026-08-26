from dataclasses import dataclass

from django.core.exceptions import ValidationError

from academic.models import StudentClassEnrollment
from administration.models import AcademicYear
from idcards.models import AssignmentScope, HolderType, IDCardTemplateAssignment


@dataclass(frozen=True)
class TemplateResolution:
    template: object
    template_version: object
    matched_scope: str
    assignment: IDCardTemplateAssignment
    path: tuple


class IDCardTemplateResolver:
    @classmethod
    def _resolve(cls, holder_type, candidates):
        path = []
        for scope, filters, label in candidates:
            assignment = IDCardTemplateAssignment.objects.select_related(
                "template__current_published_version"
            ).filter(holder_type=holder_type, scope_type=scope, is_active=True, **filters).first()
            path.append({"scope": scope, "label": label, "matched": bool(assignment)})
            if assignment:
                version = assignment.template.current_published_version
                if assignment.template.is_active and not assignment.template.is_archived and version:
                    return TemplateResolution(assignment.template, version, scope, assignment, tuple(path))
        raise ValidationError(f"No active ID card template assignment could be resolved for this {holder_type.lower()}.")

    @classmethod
    def resolve_for_student(cls, student, *, academic_year=None):
        academic_year = academic_year or AcademicYear.objects.filter(active_year=True).first()
        enrollment = None
        if academic_year:
            enrollment = StudentClassEnrollment.objects.select_related(
                "classroom__grade_level"
            ).filter(student=student, academic_year=academic_year, is_active=True).first()
        candidates = []
        if enrollment and enrollment.classroom:
            classroom = enrollment.classroom
            grade = classroom.grade_level
            candidates.extend([
                (AssignmentScope.CLASSROOM, {"classroom": classroom}, str(classroom)),
                (AssignmentScope.GRADE_LEVEL, {"grade_level": grade}, str(grade) if grade else ""),
                (AssignmentScope.SECTION, {"section__system_code": grade.section} if grade else {}, grade.get_section_display() if grade else ""),
            ])
        candidates.append((AssignmentScope.DEFAULT, {}, "All students"))
        return cls._resolve(HolderType.STUDENT, candidates)

    @classmethod
    def resolve_for_staff(cls, staff):
        candidates = [(AssignmentScope.STAFF_ROLE, {"staff_role": staff.role}, staff.get_role_display())]
        if staff.department_id:
            candidates.append((AssignmentScope.DEPARTMENT, {"department": staff.department}, str(staff.department)))
        candidates.append((AssignmentScope.DEFAULT, {}, "All staff"))
        return cls._resolve(HolderType.STAFF, candidates)

    @classmethod
    def resolve_for_holder(cls, holder_type, holder, **kwargs):
        return cls.resolve_for_student(holder, **kwargs) if holder_type == HolderType.STUDENT else cls.resolve_for_staff(holder)
