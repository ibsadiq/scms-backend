import copy
import json
from datetime import timedelta
from tempfile import TemporaryDirectory

from django.core.exceptions import ValidationError
from django.core import signing
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status

from cbt.models import (
    AttemptGrantStatus,
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    ExamQuestion,
    OfflineExamPackage,
    QuestionAttachment,
    QuestionType,
)
from cbt.services import (
    AttemptGrantService,
    ExamAttemptService,
    OfflinePackageError,
    OfflinePackageService,
    PublishedExamRevisionService,
    QuestionBankService,
)
from cbt.tests.base import CBTAPITestBase


class PhaseFiveOfflinePackageTests(CBTAPITestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_directory = TemporaryDirectory()
        cls._attachment_file_field = QuestionAttachment._meta.get_field("file")
        cls._production_attachment_storage = cls._attachment_file_field.storage
        cls._attachment_file_field.storage = FileSystemStorage(
            location=cls._media_directory.name,
            base_url="/test-cbt-media/",
        )

    @classmethod
    def tearDownClass(cls):
        try:
            cls._attachment_file_field.storage = cls._production_attachment_storage
            cls._media_directory.cleanup()
        finally:
            super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)
        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Offline package exam",
            instructions="Work independently.",
            duration_minutes=45,
            available_from=self.now + timedelta(hours=1),
            available_until=self.now + timedelta(hours=3),
            shuffle_questions=True,
            shuffle_options=True,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        definitions = [
            (QuestionType.SINGLE_CHOICE, [{"text": "Alpha", "is_correct": True}, {"text": "Beta", "is_correct": False}], None),
            (QuestionType.MULTIPLE_CHOICE, [{"text": "Gamma", "is_correct": True}, {"text": "Delta", "is_correct": True}], None),
            (QuestionType.TRUE_FALSE, [{"text": "True", "is_correct": True}, {"text": "False", "is_correct": False}], None),
            (QuestionType.SHORT_ANSWER, None, {"accepted_answers": ["hidden-short"]}),
            (QuestionType.NUMERIC, None, {"expected_value": "42", "tolerance": "0.5"}),
            (QuestionType.FILL_BLANK, None, {"blanks": [{"accepted_answers": ["hidden-blank"]}]}),
            (QuestionType.MATCHING, None, {"pairs": [
                {"left_text": "Country A", "right_text": "Capital X"},
                {"left_text": "Country B", "right_text": "Capital Y"},
                {"left_text": "Country C", "right_text": "Capital Z"},
            ]}),
            (QuestionType.ESSAY, None, {
                "model_answer": "hidden model",
                "marking_guide": "hidden guide",
                "minimum_words": 10,
                "maximum_words": 200,
            }),
        ]
        self.questions = []
        for order, (question_type, options, answer_definition) in enumerate(definitions, 1):
            question = QuestionBankService.create_question(
                subject=self.subj_math,
                grade_levels=[self.grade_jss1],
                question_type=question_type,
                text=f"Offline {question_type}",
                created_by=self.teacher_1,
                options=options,
                answer_definition=answer_definition,
            )
            self.questions.append(question)
            if order == 1:
                QuestionAttachment.objects.create(
                    question_version=question.current_version,
                    file=SimpleUploadedFile(
                        "diagram.txt",
                        b"immutable-media-bytes",
                        content_type="text/plain",
                    ),
                    caption="Reference diagram",
                    order=1,
                )
            ExamQuestion.objects.create(
                cbt_exam=self.exam,
                question_version=question.current_version,
                order=order,
                marks=2,
            )
        self.revision = PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        self.client.force_authenticate(user=self.student_user)
        grant_response = self.client.post(
            f"/api/cbt/student/exams/{self.exam.pk}/grant/", {}, format="json"
        )
        self.assertEqual(grant_response.status_code, status.HTTP_200_OK)
        self.grant_token = grant_response.data["grant_token"]
        self.grant = self.exam.attempt_grants.get()

    def download(self, token=None, **body):
        return self.client.post(
            f"/api/cbt/student/exams/{self.exam.pk}/offline-package/",
            {"grant_token": token or self.grant_token, **body},
            format="json",
        )

    def test_preopening_package_is_safe_and_does_not_start_attempt(self):
        response = self.download(student_id=self.other_student.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["schema_version"], 1)
        self.assertEqual(response.data["revision"]["public_id"], str(self.revision.public_id))
        self.assertEqual(response.data["revision"]["content_hash"], self.revision.content_hash)
        self.assertEqual(response.data["grant"]["public_id"], str(self.grant.public_id))
        self.assertIn("server_time", response.data)
        self.assertIn("generated_at", response.data)
        self.assertFalse(ExamAttempt.objects.exists())
        self.grant.refresh_from_db()
        self.assertEqual(self.grant.status, AttemptGrantStatus.ACTIVE)

    def test_all_question_types_render_without_private_grading_data(self):
        response = self.download()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        question_types = {item["question_type"] for item in response.data["questions"]}
        self.assertEqual(question_types, set(QuestionType.values))
        serialized = json.dumps(response.data, sort_keys=True, default=str).casefold()
        forbidden = [
            "correct_choice", "is_correct", "accepted_answers", "expected_value",
            "tolerance", "model_answer", "marking_guide", "grading_definition",
            "source_question", "question_version", "storage_reference",
            "hidden-short", "hidden-blank", "hidden model", "hidden guide",
        ]
        for value in forbidden:
            self.assertNotIn(value, serialized)

        essay = next(item for item in response.data["questions"] if item["question_type"] == QuestionType.ESSAY)
        self.assertEqual(essay["interaction"], {"minimum_words": 10, "maximum_words": 200})
        numeric = next(item for item in response.data["questions"] if item["question_type"] == QuestionType.NUMERIC)
        self.assertNotIn("interaction", numeric)

    def test_matching_has_opaque_independent_ids_and_no_pair_mapping(self):
        package = self.download().data
        matching = next(
            item["matching"] for item in package["questions"]
            if item["question_type"] == QuestionType.MATCHING
        )
        left_ids = {item["public_id"] for item in matching["left"]}
        right_ids = {item["public_id"] for item in matching["right"]}
        self.assertTrue(left_ids.isdisjoint(right_ids))
        self.assertNotIn("key", json.dumps(matching).casefold())
        self.assertNotIn("pair", json.dumps(matching).casefold())
        self.assertEqual(len(left_ids), 3)
        self.assertEqual(len(right_ids), 3)

    def test_repeated_download_is_idempotent_and_volatile_time_not_hashed(self):
        first = self.download()
        second = self.download()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["package_id"], second.data["package_id"])
        self.assertEqual(first.data["package_hash"], second.data["package_hash"])
        self.assertEqual(first.data["presentation_seed"], second.data["presentation_seed"])
        self.assertEqual(first.data["questions"], second.data["questions"])
        self.assertEqual(OfflineExamPackage.objects.count(), 1)
        package = OfflineExamPackage.objects.get()
        package.refresh_from_db()
        self.assertEqual(package.download_count, 2)

        payload_a = OfflinePackageService.response_payload(
            package=package, grant_token=self.grant_token, server_time=self.now
        )
        payload_b = OfflinePackageService.response_payload(
            package=package,
            grant_token=self.grant_token,
            server_time=self.now + timedelta(minutes=5),
        )
        self.assertNotEqual(payload_a["server_time"], payload_b["server_time"])
        self.assertEqual(payload_a["package_hash"], payload_b["package_hash"])

    def test_hash_and_signature_detect_content_or_claim_tampering(self):
        self.download()
        package = OfflineExamPackage.objects.select_related(
            "student", "attempt_grant", "published_revision"
        ).get()
        OfflinePackageService.verify(package=package, student=self.student)
        changed = copy.deepcopy(package.content)
        changed["questions"][0]["question_text"] = "tampered"
        with self.assertRaises(OfflinePackageError):
            OfflinePackageService.verify(
                package=package, student=self.student, content=changed
            )
        with self.assertRaises(OfflinePackageError):
            OfflinePackageService.verify(
                package=package,
                student=self.student,
                signature=package.package_signature + "tampered",
            )
        for changed_claim in (
            {"package_id": "00000000-0000-0000-0000-000000000000"},
            {"revision_hash": "0" * 64},
            {"package_hash": "f" * 64},
        ):
            claims = OfflinePackageService._signature_claims(package) | changed_claim
            changed_signature = signing.dumps(
                claims,
                salt=OfflinePackageService.SIGNATURE_SALT,
                compress=True,
            )
            with self.assertRaises(OfflinePackageError):
                OfflinePackageService.verify(
                    package=package, student=self.student,
                    signature=changed_signature,
                )
        unsupported_claims = OfflinePackageService._signature_claims(package) | {"v": 999}
        unsupported_signature = signing.dumps(
            unsupported_claims,
            salt=OfflinePackageService.SIGNATURE_SALT,
            compress=True,
        )
        with self.assertRaises(OfflinePackageError) as signature_context:
            OfflinePackageService.verify(
                package=package, student=self.student,
                signature=unsupported_signature,
            )
        self.assertEqual(
            signature_context.exception.package_code,
            "UNSUPPORTED_PACKAGE_VERSION",
        )
        original_version = package.schema_version
        package.schema_version = 999
        with self.assertRaises(OfflinePackageError) as context:
            OfflinePackageService.verify(package=package, student=self.student)
        self.assertEqual(context.exception.package_code, "UNSUPPORTED_PACKAGE_VERSION")
        package.schema_version = original_version

        changed_binding = copy.deepcopy(package.content)
        changed_binding["grant"]["public_id"] = "00000000-0000-0000-0000-000000000000"
        self.assertNotEqual(
            OfflinePackageService._hash(changed_binding), package.package_hash
        )

    def test_wrong_student_revision_expiry_and_revocation_are_rejected(self):
        self.client.force_authenticate(user=self.other_student_user)
        wrong_student = self.client.post(
            f"/api/cbt/student/exams/{self.exam.pk}/offline-package/",
            {"grant_token": self.grant_token},
            format="json",
        )
        self.assertIn(wrong_student.status_code, {status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND})

        self.client.force_authenticate(user=self.student_user)
        other_exam = CBTExam.objects.create(
            session=self.session,
            component=self.component.__class__.objects.create(
                scheme=self.grading_scheme, name="Other offline component",
                max_score=100, weight=0, order=88,
            ),
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Other revision",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        mismatch = self.client.post(
            f"/api/cbt/student/exams/{other_exam.pk}/offline-package/",
            {"grant_token": self.grant_token}, format="json",
        )
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(mismatch.data["code"], "REVISION_MISMATCH")

        AttemptGrantService.revoke(
            grant=self.grant, actor=self.teacher_user_1, reason="Withdrawn"
        )
        revoked = self.download()
        self.assertEqual(revoked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(revoked.data["code"], "GRANT_REVOKED")

    def test_expired_grant_cannot_redownload_existing_package(self):
        self.download()
        with self.assertRaises(OfflinePackageError) as context:
            OfflinePackageService.issue(
                student=self.student,
                exam=self.exam,
                grant_token=self.grant_token,
                now=self.grant.valid_until,
            )
        self.assertEqual(context.exception.package_code, "GRANT_EXPIRED")

    def test_answer_protocol_matches_phase2_contract(self):
        protocol = self.download().data["answer_protocol"]
        self.assertEqual(protocol["version"], 1)
        self.assertEqual(protocol["operations"], ["SET", "CLEAR"])
        self.assertEqual(
            set(protocol["payloads"]), set(QuestionType.values)
        )
        self.assertEqual(protocol["payloads"][QuestionType.MATCHING], {
            "matches": "{left_public_id: right_public_id}"
        })
        self.assertNotIn("server_revision", protocol["event_fields"])

    def test_media_manifest_and_authorized_integrity_checked_download(self):
        package_response = self.download()
        manifest = package_response.data["media"]
        self.assertEqual(len(manifest), 1)
        media = manifest[0]
        self.assertEqual(media["byte_size"], len(b"immutable-media-bytes"))
        self.assertEqual(len(media["sha256"]), 64)
        self.assertNotIn("storage", json.dumps(media).casefold())
        response = self.client.get(
            media["download_path"],
            HTTP_X_CBT_GRANT_TOKEN=self.grant_token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.other_student_user)
        unauthorized = self.client.get(
            media["download_path"],
            HTTP_X_CBT_GRANT_TOKEN=self.grant_token,
        )
        self.assertEqual(unauthorized.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(user=self.student_user)
        AttemptGrantService.revoke(
            grant=self.grant, actor=self.teacher_user_1, reason="Media access revoked"
        )
        revoked = self.client.get(
            media["download_path"],
            HTTP_X_CBT_GRANT_TOKEN=self.grant_token,
        )
        self.assertEqual(revoked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(revoked.data["code"], "GRANT_REVOKED")

    def test_tampered_media_blob_fails_safely(self):
        package_response = self.download()
        media = package_response.data["media"][0]
        frozen_media = self.revision.questions.get(
            question_type=QuestionType.SINGLE_CHOICE
        ).media.get()
        frozen_media.__class__.objects.filter(pk=frozen_media.pk).update(
            content_sha256="0" * 64
        )
        response = self.client.get(
            media["download_path"],
            HTTP_X_CBT_GRANT_TOKEN=self.grant_token,
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "MEDIA_INTEGRITY_ERROR")

    def test_online_start_after_download_uses_same_grant_and_revision(self):
        self.download()
        attempt = ExamAttemptService.start_attempt(
            exam=self.exam, student=self.student, now=self.exam.available_from
        )
        self.assertEqual(attempt.attempt_grant_id, self.grant.pk)
        self.assertEqual(attempt.published_revision_id, self.revision.pk)
        self.assertEqual(OfflineExamPackage.objects.get().attempt_grant_id, self.grant.pk)
