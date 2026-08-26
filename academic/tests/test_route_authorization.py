from django.test import SimpleTestCase

from academic.permissions import IsAcademicAdminOrReadOnly, IsSchoolAdmin
from academic.views.allocation import AllocatedSubjectViewSet
from academic.views.curriculum import (
    CurriculumSubjectViewSet,
    CurriculumTopicViewSet,
    LearningObjectiveViewSet,
    SubTopicViewSet,
    TopicViewSet,
)
from academic.views.class_advancement import StudentEnrollmentViewSet
from academic.views.staff import SubjectListView
from academic.views.structure import ClassRoomView, DepartmentListCreateView
from academic.views.student import BulkUploadStudentClassView, StudentClassListCreateView
from administration.views import AcademicYearListCreateView, TermListCreateView
from sis.views import BulkUploadStudentsView, StudentListView
from sis.permissions import SISStudentPermission


class StructuralRouteAuthorizationTests(SimpleTestCase):
    def test_structural_mutations_use_admin_or_read_only_policy(self):
        views = (
            AllocatedSubjectViewSet, StudentEnrollmentViewSet, SubjectListView,
            ClassRoomView, DepartmentListCreateView, StudentClassListCreateView,
            AcademicYearListCreateView, TermListCreateView,
        )
        for view in views:
            self.assertEqual(view.permission_classes, [IsAcademicAdminOrReadOnly])

    def test_sis_student_routes_use_role_scoped_permission(self):
        self.assertEqual(StudentListView.permission_classes, [SISStudentPermission])

    def test_bulk_student_and_enrollment_uploads_are_admin_only(self):
        self.assertEqual(BulkUploadStudentClassView.permission_classes, [IsSchoolAdmin])
        self.assertEqual(BulkUploadStudentsView.permission_classes, [IsSchoolAdmin])

    def test_curriculum_hierarchy_routes_define_their_supported_filters(self):
        expected_filters = {
            CurriculumSubjectViewSet: ["curriculum"],
            CurriculumTopicViewSet: ["curriculum_subject"],
            TopicViewSet: ["grade_level", "subject"],
            SubTopicViewSet: ["topic"],
            LearningObjectiveViewSet: ["curriculum_topic", "subtopic"],
        }
        for view, fields in expected_filters.items():
            self.assertEqual(view.filterset_fields, fields)
