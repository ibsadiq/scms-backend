from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connections
from django_tenants.utils import schema_context

from academic.models import Student
from school.testcases import TenantTransactionTestCase


class AdmissionNumberConcurrencyTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Admission Race Academy"

    def test_concurrent_first_students_receive_distinct_formatted_numbers(self):
        barrier = Barrier(2)

        def create_student(index):
            connections.close_all()
            try:
                with schema_context(self.tenant.schema_name):
                    barrier.wait()
                    student = Student.objects.create(
                        first_name="Concurrent", last_name=str(index),
                        parent_contact=f"0808222000{index}",
                    )
                    return student.admission_number
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            numbers = list(executor.map(create_student, range(2)))
        self.assertEqual(len(set(numbers)), 2)
        for number in numbers:
            self.assertRegex(number, r"^ADM-\d{4}-\d{4,}$")

