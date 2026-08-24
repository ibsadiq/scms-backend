from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connections
from django_tenants.utils import schema_context

from academic.models import Student
from idcards.models import HolderType, IDCardTemplate, RFIDCredential
from idcards.services import CardService, RFIDCredentialService
from school.testcases import TenantTransactionTestCase


User = get_user_model()


def layout():
    return {"schema_version": 1, "elements": []}


class IDCardConcurrencyTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Concurrency Academy"

    def setUp(self):
        self.student = Student.objects.create(
            first_name="Race", last_name="Holder", parent_contact="08081110001",
            admission_number="ADM-RACE-1",
        )
        self.other_student = Student.objects.create(
            first_name="Other", last_name="Holder", parent_contact="08081110002",
            admission_number="ADM-RACE-2",
        )
        self.template = IDCardTemplate.objects.create(
            name="Race Template", holder_type=HolderType.STUDENT,
            front_layout=layout(), back_layout=layout(),
        )

    def _run(self, function):
        barrier = Barrier(2)

        def worker(index):
            connections.close_all()
            try:
                with schema_context(self.tenant.schema_name):
                    barrier.wait()
                    return function(index)
            except ValidationError as exc:
                return exc.message_dict.get("code", ["UNKNOWN"])[0]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(worker, range(2)))

    def test_concurrent_card_issue_has_one_deterministic_loser(self):
        def issue(_):
            student = Student.objects.get(pk=self.student.pk)
            template = IDCardTemplate.objects.get(pk=self.template.pk)
            return CardService.issue_student_card(student=student, template=template).pk

        results = self._run(issue)
        self.assertEqual(sum(isinstance(value, int) for value in results), 1)
        self.assertIn("ACTIVE_CARD_EXISTS", results)

    def test_concurrent_uid_assignment_has_one_deterministic_loser(self):
        cards = [
            CardService.issue_student_card(student=self.student, template=self.template),
            CardService.issue_student_card(student=self.other_student, template=self.template),
        ]

        def assign(index):
            return RFIDCredentialService.assign(
                id_card=cards[index], uid="AABBCCDD"
            ).pk

        results = self._run(assign)
        self.assertEqual(sum(isinstance(value, int) for value in results), 1)
        self.assertIn("UID_ALREADY_ASSIGNED", results)
        self.assertEqual(RFIDCredential.objects.filter(status=RFIDCredential.Status.ACTIVE).count(), 1)

    def test_concurrent_credentials_on_one_card_have_one_deterministic_loser(self):
        card = CardService.issue_student_card(student=self.student, template=self.template)

        def assign(index):
            return RFIDCredentialService.assign(
                id_card=card, uid=("AABBCCDD", "11223344")[index]
            ).pk

        results = self._run(assign)
        self.assertEqual(sum(isinstance(value, int) for value in results), 1)
        self.assertIn("ACTIVE_CREDENTIAL_EXISTS", results)
