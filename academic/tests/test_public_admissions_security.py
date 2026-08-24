from datetime import date, timedelta
from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import FileSystemStorage
from django.urls import NoReverseMatch, resolve, reverse
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from academic.models import (
    AdmissionApplication,
    AdmissionDocument,
    AdmissionFeeStructure,
    AdmissionSession,
    GradeLevel,
)
from administration.models import AcademicYear
from tenants.models import Client as SchoolTenant, Domain, TenantStatus
from school.testcases import TenantTestCase


class PublicAdmissionsSecurityTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Public Admissions Test School"
        tenant.status = TenantStatus.ACTIVE
        return super().setup_tenant(tenant)

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_directory = TemporaryDirectory()
        cls._document_file_field = AdmissionDocument._meta.get_field("file")
        cls._production_document_storage = cls._document_file_field.storage
        cls._document_file_field.storage = FileSystemStorage(
            location=cls._media_directory.name,
            base_url="/test-admission-media/",
        )
        with schema_context("public"):
            cls.other_tenant = SchoolTenant(
                schema_name="public_admissions_other",
                name="Other Admissions School",
                status=TenantStatus.ACTIVE,
            )
            cls.other_tenant.auto_create_schema = True
            cls.other_tenant.save(verbosity=0)
            cls.other_domain = Domain.objects.create(
                tenant=cls.other_tenant,
                domain="public-admissions-other.test.com",
                is_primary=True,
            )

    @classmethod
    def tearDownClass(cls):
        try:
            with schema_context("public"):
                cls.other_domain.delete()
                cls.other_tenant.delete(force_drop=True)
        finally:
            cls._document_file_field.storage = cls._production_document_storage
            cls._media_directory.cleanup()
            super().tearDownClass()

    def setUp(self):
        cache.clear()
        today = timezone.localdate()
        self.year = AcademicYear.objects.create(
            name="2030/2031",
            start_date=date(2030, 9, 1),
            end_date=date(2031, 7, 31),
            active_year=True,
        )
        self.grade = GradeLevel.objects.update_or_create(
            system_code="JSS_1",
            defaults={
                "section": "JSS",
                "default_name": "JSS 1",
                "sequence_order": 11,
            },
        )[0]
        self.session = AdmissionSession.objects.create(
            academic_year=self.year,
            name="2030 Admissions",
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=30),
            is_active=True,
            allow_public_applications=True,
        )
        self.fees = AdmissionFeeStructure.objects.create(
            admission_session=self.session,
            application_fee=1000,
            application_fee_required=False,
            acceptance_fee=5000,
            acceptance_fee_required=False,
        )
        self.fees.grade_levels.add(self.grade)
        self.client = APIClient(HTTP_HOST=self.domain.domain)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def make_application(self, suffix="one", **overrides):
        values = {
            "admission_session": self.session,
            "applying_for_class": self.grade,
            "first_name": "Applicant",
            "middle_name": "",
            "last_name": suffix,
            "gender": "Male",
            "date_of_birth": date(2018, 1, 1),
            "state_of_origin": "Lagos",
            "lga": "Ikeja",
            "address": "1 Test Street",
            "city": "Lagos",
            "parent_first_name": "Parent",
            "parent_last_name": suffix,
            "parent_email": f"parent-{suffix}@example.test",
            "parent_phone": f"0801000{len(suffix):04d}",
        }
        values.update(overrides)
        return AdmissionApplication.objects.create(**values)

    def application_payload(self, suffix="created"):
        return {
            "admission_session": self.session.pk,
            "applying_for_class": self.grade.pk,
            "first_name": "Created",
            "middle_name": "",
            "last_name": suffix,
            "gender": "Male",
            "date_of_birth": "2018-01-01",
            "state_of_origin": "Lagos",
            "lga": "Ikeja",
            "address": "1 Test Street",
            "city": "Lagos",
            "parent_first_name": "Parent",
            "parent_last_name": suffix,
            "parent_email": f"created-{suffix}@example.test",
            "parent_phone": "08012345678",
        }

    def test_public_application_collection_has_create_but_no_list(self):
        url = reverse("public-admission-application-list")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertIn("post", resolve(url).func.actions)
        self.assertNotIn("get", resolve(url).func.actions)

    def test_public_application_has_no_put_or_delete(self):
        application = self.make_application()
        url = reverse(
            "public-admission-application-detail",
            kwargs={"tracking_token": application.tracking_token},
        )
        self.assertEqual(self.client.put(url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_create_returns_tracking_token_and_safe_application_shape(self):
        response = self.client.post(
            reverse("public-admission-application-list"),
            self.application_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("tracking_token", response.data)
        self.assertRegex(
            response.data["application_number"],
            rf"^ADM/{self.year.start_date.year}/\d{{3,}}$",
        )
        self.assertNotIn("tracking_token", response.data["application"])
        for internal in (
            "admin_notes", "reviewed_by", "application_fee_receipt",
            "exam_fee_receipt", "acceptance_fee_receipt", "enrolled_student",
        ):
            self.assertNotIn(internal, response.data["application"])

    def test_valid_token_retrieves_only_its_application_with_safe_fields(self):
        application = self.make_application()
        other = self.make_application("other")
        response = self.client.get(reverse(
            "public-admission-application-detail",
            kwargs={"tracking_token": application.tracking_token},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["application_number"], application.application_number)
        self.assertNotEqual(response.data["application_number"], other.application_number)
        for internal in (
            "tracking_token", "admin_notes", "reviewed_by", "reviewed_by_name",
            "application_fee_receipt", "exam_fee_receipt", "acceptance_fee_receipt",
            "enrolled_student",
        ):
            self.assertNotIn(internal, response.data)

    def test_token_a_cannot_mutate_application_b(self):
        application_a = self.make_application("alpha")
        application_b = self.make_application("beta")
        url_a = reverse(
            "public-admission-application-detail",
            kwargs={"tracking_token": application_a.tracking_token},
        )
        response = self.client.patch(url_a, {"last_name": "changed"}, format="json")
        self.assertEqual(response.status_code, 200)
        application_a.refresh_from_db()
        application_b.refresh_from_db()
        self.assertEqual(application_a.last_name, "changed")
        self.assertEqual(application_b.last_name, "beta")

    def test_invalid_token_gets_not_found(self):
        response = self.client.get(
            "/api/public/admissions/applications/not-a-valid-token/"
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_tenant_tracking_token_cannot_be_used(self):
        today = timezone.localdate()
        with schema_context(self.other_tenant.schema_name):
            other_year = AcademicYear.objects.create(
                name="2040/2041", start_date=today,
                end_date=today + timedelta(days=365), active_year=True,
            )
            other_grade = GradeLevel.objects.update_or_create(
                system_code="JSS_1",
                defaults={
                    "section": "JSS", "default_name": "JSS 1",
                    "sequence_order": 11,
                },
            )[0]
            other_session = AdmissionSession.objects.create(
                academic_year=other_year, name="Other Admissions",
                start_date=today, end_date=today + timedelta(days=30),
            )
            other_application = AdmissionApplication.objects.create(
                admission_session=other_session,
                applying_for_class=other_grade,
                first_name="Other", last_name="Tenant", gender="Male",
                date_of_birth=date(2018, 1, 1), state_of_origin="Lagos",
                lga="Ikeja", address="Other", city="Lagos",
                parent_first_name="Other", parent_last_name="Parent",
                parent_email="other-parent@example.test",
                parent_phone="08099990000",
            )
            other_token = other_application.tracking_token

        response = self.client.get(
            f"/api/public/admissions/applications/{other_token}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_document_upload_uses_url_application_and_rejects_application_field(self):
        application = self.make_application()
        url = reverse("public-admission-documents", kwargs={
            "tracking_token": application.tracking_token,
        })
        upload = SimpleUploadedFile("birth.pdf", b"%PDF-1.4 test", "application/pdf")
        response = self.client.post(url, {
            "document_type": "birth_certificate",
            "file": upload,
            "description": "Birth certificate",
        }, format="multipart")
        self.assertEqual(response.status_code, 201)
        document = AdmissionDocument.objects.get()
        self.assertEqual(document.application, application)
        for internal in ("application", "verified", "verified_by", "verified_at", "verification_notes"):
            self.assertNotIn(internal, response.data["document"])

        upload = SimpleUploadedFile("result.pdf", b"%PDF-1.4 test", "application/pdf")
        response = self.client.post(url, {
            "application": application.pk,
            "document_type": "previous_results",
            "file": upload,
        }, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_document_delete_is_token_scoped_and_uses_public_id(self):
        application = self.make_application()
        other = self.make_application("other")
        document = AdmissionDocument.objects.create(
            application=application,
            document_type="other",
            file=SimpleUploadedFile("one.pdf", b"%PDF-1.4", "application/pdf"),
        )
        wrong_url = reverse("public-admission-document-detail", kwargs={
            "tracking_token": other.tracking_token,
            "document_public_id": document.public_id,
        })
        self.assertEqual(self.client.delete(wrong_url).status_code, 404)
        self.assertTrue(AdmissionDocument.objects.filter(pk=document.pk).exists())

        right_url = reverse("public-admission-document-detail", kwargs={
            "tracking_token": application.tracking_token,
            "document_public_id": document.public_id,
        })
        self.assertEqual(self.client.delete(right_url).status_code, 204)
        self.assertFalse(AdmissionDocument.objects.filter(pk=document.pk).exists())

    def test_integer_only_document_delete_route_is_unavailable(self):
        self.assertEqual(
            self.client.delete("/api/public/admissions/documents/1/").status_code,
            404,
        )

    def test_verified_document_cannot_be_deleted(self):
        application = self.make_application()
        document = AdmissionDocument.objects.create(
            application=application,
            document_type="other",
            file=SimpleUploadedFile("one.pdf", b"%PDF-1.4", "application/pdf"),
            verified=True,
        )
        url = reverse("public-admission-document-detail", kwargs={
            "tracking_token": application.tracking_token,
            "document_public_id": document.public_id,
        })
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertTrue(AdmissionDocument.objects.filter(pk=document.pk).exists())

    def test_fee_classes_and_payment_info_use_grade_levels(self):
        fees_response = self.client.get(reverse("public-admission-fee-structure-list"))
        self.assertEqual(fees_response.status_code, 200)
        self.assertEqual(fees_response.data["results"][0]["grade_levels"], [self.grade.pk])

        classes_response = self.client.get(reverse("public-admission-class-list"))
        self.assertEqual(classes_response.status_code, 200)
        self.assertEqual(classes_response.data["classes"][0]["id"], self.grade.pk)
        self.assertNotIn("min_age", classes_response.data["classes"][0])

        application = self.make_application()
        payment_response = self.client.get(reverse(
            "public-admission-application-payment-info",
            kwargs={"tracking_token": application.tracking_token},
        ))
        self.assertEqual(payment_response.status_code, 200)
        self.assertEqual(payment_response.data["class"], str(self.grade))

    def test_track_failure_is_uniform(self):
        url = reverse("public-admission-application-track")
        missing = self.client.post(url, {
            "application_number": "ADM/2030/999",
            "email": "none@example.test",
        }, format="json")
        wrong_contact = self.client.post(url, {
            "application_number": self.make_application().application_number,
            "email": "wrong@example.test",
        }, format="json")
        self.assertEqual((missing.status_code, missing.data), (wrong_contact.status_code, wrong_contact.data))

    def test_track_returns_only_the_matching_application_token(self):
        application = self.make_application("match")
        other = self.make_application("other")
        response = self.client.post(
            reverse("public-admission-application-track"),
            {
                "application_number": application.application_number,
                "email": application.parent_email,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tracking_token"], application.tracking_token)
        self.assertNotEqual(response.data["tracking_token"], other.tracking_token)

    def test_track_endpoint_is_throttled(self):
        cache.clear()
        url = reverse("public-admission-application-track")
        payload = {"application_number": "missing", "email": "none@example.test"}
        for _ in range(10):
            self.assertEqual(self.client.post(url, payload, format="json").status_code, 404)
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 429)
