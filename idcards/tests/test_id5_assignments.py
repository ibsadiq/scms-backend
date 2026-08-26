from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import ClassRoom, Department, GradeLevel, SchoolSection, Staff, Student, StudentClassEnrollment
from administration.models import AcademicYear
from idcards.models import AssignmentScope, HolderType, IDCardTemplateAssignment
from idcards.services import CardService, IDCardTemplateLifecycleService, IDCardTemplateResolver
from idcards.views import IDCardTemplateAssignmentViewSet
from school.testcases import TenantTestCase

from .test_id1_versioning import v1


class ID5TemplateAssignmentTests(TenantTestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(email="id5@example.com", password="x", is_admin=True)
        self.year = AcademicYear.objects.create(name="2026/27", start_date="2026-09-01", end_date="2027-07-31", active_year=True)
        self.section = SchoolSection.objects.create(system_code="JSS", default_name="Junior Secondary", sequence_order=1)
        self.grade = GradeLevel.objects.create(system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1)
        self.room = ClassRoom.objects.create(name="Gold", grade_level=self.grade)
        self.student = Student.objects.create(first_name="Ibrahim", last_name="Musa", admission_number="ID5-1", parent_contact="08030000001")
        StudentClassEnrollment.objects.create(student=self.student, classroom=self.room, academic_year=self.year, is_active=True)
        self.department = Department.objects.create(name="science")
        self.staff = Staff.objects.create(role=Staff.Role.TEACHER, department=self.department)
        self.factory = APIRequestFactory()

    def template(self, name, holder_type):
        field = "student.full_name" if holder_type == HolderType.STUDENT else "staff.full_name"
        template = IDCardTemplateLifecycleService.create_template(
            name=name, holder_type=holder_type, actor=self.admin, front_layout=v1(field),
            back_layout={"schema_version": 1, "elements": []},
        )
        IDCardTemplateLifecycleService.publish(template.current_draft_version, actor=self.admin)
        template.refresh_from_db()
        return template

    def assign(self, template, scope, **target):
        return IDCardTemplateAssignment.objects.create(
            holder_type=template.holder_type, scope_type=scope, template=template, created_by=self.admin, **target,
        )

    def test_student_precedence_and_active_enrollment(self):
        default = self.template("Default", HolderType.STUDENT)
        section = self.template("Section", HolderType.STUDENT)
        grade = self.template("Grade", HolderType.STUDENT)
        room = self.template("Room", HolderType.STUDENT)
        self.assign(default, AssignmentScope.DEFAULT)
        self.assign(section, AssignmentScope.SECTION, section=self.section)
        self.assign(grade, AssignmentScope.GRADE_LEVEL, grade_level=self.grade)
        self.assign(room, AssignmentScope.CLASSROOM, classroom=self.room)
        resolved = IDCardTemplateResolver.resolve_for_student(self.student)
        self.assertEqual(resolved.template, room)
        self.assertEqual(resolved.matched_scope, AssignmentScope.CLASSROOM)

    def test_student_falls_back_grade_section_then_default(self):
        default = self.template("Default Chain", HolderType.STUDENT)
        section = self.template("Section Chain", HolderType.STUDENT)
        grade = self.template("Grade Chain", HolderType.STUDENT)
        default_assignment = self.assign(default, AssignmentScope.DEFAULT)
        section_assignment = self.assign(section, AssignmentScope.SECTION, section=self.section)
        grade_assignment = self.assign(grade, AssignmentScope.GRADE_LEVEL, grade_level=self.grade)
        self.assertEqual(IDCardTemplateResolver.resolve_for_student(self.student).template, grade)
        grade_assignment.is_active = False; grade_assignment.save()
        self.assertEqual(IDCardTemplateResolver.resolve_for_student(self.student).template, section)
        section_assignment.is_active = False; section_assignment.save()
        self.assertEqual(IDCardTemplateResolver.resolve_for_student(self.student).template, default)
        default_assignment.is_active = False; default_assignment.save()
        with self.assertRaisesMessage(ValidationError, "No active ID card template assignment"):
            IDCardTemplateResolver.resolve_for_student(self.student)

    def test_stale_student_snapshot_does_not_override_active_enrollment(self):
        other_grade = GradeLevel.objects.create(system_code="JSS_2", section="JSS", default_name="JSS 2", sequence_order=2)
        stale_room = ClassRoom.objects.create(name="Blue", grade_level=other_grade)
        self.student.classroom = stale_room; self.student.save()
        active_template = self.template("Active Enrollment", HolderType.STUDENT)
        stale_template = self.template("Stale Snapshot", HolderType.STUDENT)
        self.assign(active_template, AssignmentScope.CLASSROOM, classroom=self.room)
        self.assign(stale_template, AssignmentScope.CLASSROOM, classroom=stale_room)
        self.assertEqual(IDCardTemplateResolver.resolve_for_student(self.student).template, active_template)

    def test_inactive_enrollment_cannot_supply_specific_context(self):
        StudentClassEnrollment.objects.filter(student=self.student).update(is_active=False)
        default = self.template("No Enrollment Default", HolderType.STUDENT)
        specific = self.template("Inactive Enrollment Room", HolderType.STUDENT)
        self.assign(default, AssignmentScope.DEFAULT)
        self.assign(specific, AssignmentScope.CLASSROOM, classroom=self.room)
        self.assertEqual(IDCardTemplateResolver.resolve_for_student(self.student).template, default)

    def test_staff_role_wins_over_department_then_default(self):
        default = self.template("Staff Default", HolderType.STAFF)
        department = self.template("Science", HolderType.STAFF)
        role = self.template("Teacher", HolderType.STAFF)
        self.assign(default, AssignmentScope.DEFAULT)
        self.assign(department, AssignmentScope.DEPARTMENT, department=self.department)
        self.assign(role, AssignmentScope.STAFF_ROLE, staff_role=Staff.Role.TEACHER)
        self.assertEqual(IDCardTemplateResolver.resolve_for_staff(self.staff).template, role)

    def test_invalid_and_duplicate_assignments_are_rejected(self):
        student_template = self.template("Student", HolderType.STUDENT)
        staff_template = self.template("Staff", HolderType.STAFF)
        self.assign(student_template, AssignmentScope.DEFAULT)
        with self.assertRaises(ValidationError):
            IDCardTemplateAssignment.objects.create(holder_type=HolderType.STUDENT, scope_type=AssignmentScope.DEFAULT, template=student_template)
        with self.assertRaises(ValidationError):
            IDCardTemplateAssignment.objects.create(holder_type=HolderType.STUDENT, scope_type=AssignmentScope.CLASSROOM, template=staff_template, classroom=self.room)

    def test_invalid_target_combinations_and_unpublished_templates_are_rejected(self):
        published = self.template("Target Validation", HolderType.STUDENT)
        with self.assertRaises(ValidationError):
            self.assign(published, AssignmentScope.DEFAULT, classroom=self.room)
        unpublished = IDCardTemplateLifecycleService.create_template(
            name="Unpublished", holder_type=HolderType.STUDENT, actor=self.admin,
            front_layout=v1(), back_layout={"schema_version": 1, "elements": []},
        )
        with self.assertRaises(ValidationError):
            self.assign(unpublished, AssignmentScope.DEFAULT)

    def test_archived_template_cannot_be_newly_assigned(self):
        template = self.template("Archived Assignment", HolderType.STUDENT)
        IDCardTemplateLifecycleService.archive(template)
        template.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.assign(template, AssignmentScope.DEFAULT)

    def test_new_issuance_pins_resolution_but_replacement_keeps_history(self):
        template = self.template("Assigned", HolderType.STUDENT)
        self.assign(template, AssignmentScope.DEFAULT)
        first = template.current_published_version
        card = CardService.issue_student_card(student=self.student, issued_by=self.admin)
        draft = IDCardTemplateLifecycleService.create_draft(template, actor=self.admin)
        IDCardTemplateLifecycleService.publish(draft, actor=self.admin)
        replacement = CardService.replace_card(card, actor=self.admin)
        self.assertEqual(card.template_version_id, first.id)
        self.assertEqual(replacement.template_version_id, first.id)

    def test_new_card_uses_new_published_version_and_changed_assignment(self):
        original = self.template("Original Assignment", HolderType.STUDENT)
        assignment = self.assign(original, AssignmentScope.DEFAULT)
        first_card = CardService.issue_student_card(student=self.student, issued_by=self.admin)
        CardService.deactivate_card(first_card)
        next_version = IDCardTemplateLifecycleService.create_draft(original, actor=self.admin)
        IDCardTemplateLifecycleService.publish(next_version, actor=self.admin)
        second_card = CardService.issue_student_card(student=self.student, issued_by=self.admin)
        self.assertEqual(second_card.template_version_id, next_version.id)
        self.assertEqual(first_card.template_version.template_id, original.id)
        CardService.deactivate_card(second_card)
        assignment.is_active = False; assignment.save()
        replacement_template = self.template("Changed Assignment", HolderType.STUDENT)
        self.assign(replacement_template, AssignmentScope.DEFAULT)
        third_card = CardService.issue_student_card(student=self.student, issued_by=self.admin)
        self.assertEqual(third_card.template, replacement_template)
        self.assertEqual(first_card.template_version_id, original.versions.order_by("version_number").first().id)

    def test_assignment_api_requires_canonical_school_admin(self):
        teacher = get_user_model().objects.create_user(email="id5-teacher@example.com", password="x", is_teacher=True, is_staff=True)
        view = IDCardTemplateAssignmentViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/idcards/template-assignments/")
        force_authenticate(request, user=teacher)
        self.assertEqual(view(request).status_code, 403)
        request = self.factory.get("/api/idcards/template-assignments/")
        force_authenticate(request, user=self.admin)
        self.assertEqual(view(request).status_code, 200)

    def test_resolution_preview_reports_scope_version_and_path(self):
        template = self.template("Preview Assignment", HolderType.STUDENT)
        assignment = self.assign(template, AssignmentScope.CLASSROOM, classroom=self.room)
        request = self.factory.post("/api/idcards/template-assignments/resolve/", {"holder_type": "STUDENT", "holder_id": self.student.id}, format="json")
        force_authenticate(request, user=self.admin)
        response = IDCardTemplateAssignmentViewSet.as_view({"post": "resolve"})(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["assignment"]["id"], assignment.id)
        self.assertEqual(response.data["matched_scope"], AssignmentScope.CLASSROOM)
        self.assertEqual(response.data["template_version"]["id"], template.current_published_version_id)
        self.assertTrue(response.data["path"][0]["matched"])
