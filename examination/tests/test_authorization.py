from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from examination.permissions import CanViewMarkedScript, IsAdmin
from examination.views.assessment import AssessmentSessionViewSet
from examination.views.result import _term_results_for_user


class ExaminationAuthorizationUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_anonymous_assessment_session_read_is_rejected(self):
        request = self.factory.get('/')
        request.user = AnonymousUser()
        response = AssessmentSessionViewSet.as_view({'get': 'list'})(request)
        self.assertIn(response.status_code, (401, 403))

    def test_marked_script_permission_is_explicit_and_visibility_scoped(self):
        student = SimpleNamespace(id=10, parent_guardian_id=20)
        script = SimpleNamespace(student_id=10, student=student, uploaded_by_id=30, visible_to_student=True, visible_to_parent=False)
        student_user = SimpleNamespace(is_authenticated=True, is_admin=False, is_superuser=False, is_staff=False, is_student=True, is_parent=False, active_role='student', student_profile=SimpleNamespace(id=10))
        request = SimpleNamespace(user=student_user)
        self.assertTrue(CanViewMarkedScript().has_object_permission(request, None, script))

        other_user = SimpleNamespace(is_authenticated=True, is_admin=False, is_superuser=False, is_staff=False, is_student=True, is_parent=False, active_role='student', student_profile=SimpleNamespace(id=11))
        self.assertFalse(CanViewMarkedScript().has_object_permission(SimpleNamespace(user=other_user), None, script))

    def test_result_audit_admin_permission_fails_closed(self):
        user = SimpleNamespace(is_authenticated=True, is_admin=False, is_staff=False, is_superuser=False)
        self.assertFalse(IsAdmin().has_permission(SimpleNamespace(user=user), None))

    def test_teacher_without_profile_result_scope_fails_closed(self):
        user = SimpleNamespace(
            is_authenticated=True, is_admin=False, is_staff=False,
            is_superuser=False, is_teacher=True, is_parent=False,
            is_student=False, is_accountant=False, active_role='teacher',
        )
        self.assertTrue(_term_results_for_user(user).query.is_empty())

    def test_admin_result_scope_remains_tenant_wide(self):
        user = SimpleNamespace(is_authenticated=True, is_admin=True, is_staff=False, is_superuser=False)
        self.assertFalse(_term_results_for_user(user).query.is_empty())
