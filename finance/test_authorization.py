from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from school.testcases import TenantTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import ClassLevel, ClassRoom, GradeLevel, Parent, Student
from administration.models import AcademicYear, Term
from finance.models import FeeStructure, Receipt, StudentFeeAssignment
from finance.views import ReceiptViewSet, StudentFeeAssignmentViewSet


User = get_user_model()


class FinanceAuthorizationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = User.objects.create_user(email='admin@finance.test', password='x', is_admin=True)
        self.accountant = User.objects.create_user(email='accountant@finance.test', password='x', is_accountant=True)
        self.teacher = User.objects.create_user(email='teacher@finance.test', password='x', is_teacher=True)
        self.student_user = User.objects.create_user(email='student@finance.test', password='x', is_student=True)
        self.parent_user = User.objects.create_user(email='parent@finance.test', password='x', is_parent=True)
        parent = Parent.objects.create(user=self.parent_user, phone_number='08000000101')
        year = AcademicYear.objects.create(name='2026/2027', start_date=date(2026, 9, 1), end_date=date(2027, 7, 1), active_year=True)
        term = Term.objects.create(name='First', academic_year=year, start_date=date(2026, 9, 1), end_date=date(2026, 12, 1))
        grade = GradeLevel.objects.create(system_code='JSS_1', section='JSS', default_name='JSS 1', sequence_order=1)
        level = ClassLevel.objects.create(name='JSS 1 A', grade_level=grade)
        classroom = ClassRoom.objects.create(name=level)
        self.own_student = Student.objects.create(user=self.student_user, first_name='Own', last_name='Student', parent_contact=parent.phone_number, classroom=classroom)
        self.other_student = Student.objects.create(first_name='Other', last_name='Student', parent_contact='08000000103', classroom=classroom)
        fee = FeeStructure.objects.create(name='Tuition', amount=Decimal('1000'), academic_year=year, term=term, created_by=self.admin)
        fee.auto_assign_to_students(term=term)
        self.own_assignment = StudentFeeAssignment.objects.get(student=self.own_student, fee_structure=fee, term=term)
        self.other_assignment = StudentFeeAssignment.objects.get(student=self.other_student, fee_structure=fee, term=term)
        Receipt.objects.create(student=self.own_student, amount=Decimal('100'), term=term, received_by=self.admin)
        Receipt.objects.create(student=self.other_student, amount=Decimal('100'), term=term, received_by=self.admin)

    def _assignment_ids(self, user):
        request = self.factory.get('/')
        force_authenticate(request, user=user)
        response = StudentFeeAssignmentViewSet.as_view({'get': 'list'})(request)
        rows = response.data.get('results', response.data)
        return response.status_code, {row['id'] for row in rows}

    def test_student_and_parent_reads_are_own_scoped(self):
        self.assertEqual(self._assignment_ids(self.student_user)[1], {self.own_assignment.id})
        self.assertEqual(self._assignment_ids(self.parent_user)[1], {self.own_assignment.id})

    def test_non_finance_roles_cannot_mutate(self):
        for user in (self.student_user, self.parent_user, self.teacher):
            request = self.factory.delete('/')
            force_authenticate(request, user=user)
            response = StudentFeeAssignmentViewSet.as_view({'delete': 'destroy'})(request, pk=self.own_assignment.pk)
            self.assertEqual(response.status_code, 403)

    def test_accountant_and_admin_can_mutate(self):
        for user in (self.accountant, self.admin):
            request = self.factory.patch('/', {'amount_owed': '1100.00'}, format='json')
            force_authenticate(request, user=user)
            response = StudentFeeAssignmentViewSet.as_view({'patch': 'partial_update'})(request, pk=self.own_assignment.pk)
            self.assertEqual(response.status_code, 200)

    def test_receipts_are_own_scoped_and_anonymous_rejected(self):
        request = self.factory.get('/')
        force_authenticate(request, user=self.parent_user)
        response = ReceiptViewSet.as_view({'get': 'list'})(request)
        rows = response.data.get('results', response.data)
        self.assertEqual(len(rows), 1)
        anonymous = ReceiptViewSet.as_view({'get': 'list'})(self.factory.get('/'))
        self.assertIn(anonymous.status_code, (401, 403))
