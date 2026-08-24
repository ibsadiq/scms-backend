from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework.permissions import SAFE_METHODS

from finance.permissions import FinanceManagerWriteOwnRead, IsFinanceManager


def user(**roles):
    values = dict(is_authenticated=True, is_admin=False, is_staff=False, is_superuser=False, is_accountant=False, is_student=False, is_parent=False)
    values.update(roles)
    return SimpleNamespace(**values)


class FinancePermissionUnitTests(SimpleTestCase):
    def request(self, method, actor):
        return SimpleNamespace(method=method, user=actor)

    def test_only_admin_and_accountant_can_write(self):
        permission = FinanceManagerWriteOwnRead()
        for actor in (user(is_student=True), user(is_parent=True), user(is_teacher=True)):
            self.assertFalse(permission.has_permission(self.request('POST', actor), None))
        self.assertTrue(permission.has_permission(self.request('POST', user(is_admin=True)), None))
        self.assertTrue(permission.has_permission(self.request('POST', user(is_accountant=True)), None))

    def test_finance_manager_only_routes_reject_teacher(self):
        self.assertFalse(IsFinanceManager().has_permission(self.request('GET', user(is_teacher=True)), None))

    def test_student_and_parent_may_enter_own_read_scope(self):
        permission = FinanceManagerWriteOwnRead()
        self.assertTrue(permission.has_permission(self.request('GET', user(is_student=True)), None))
        self.assertTrue(permission.has_permission(self.request('GET', user(is_parent=True)), None))
