from decimal import Decimal
from django.utils import timezone
from rest_framework import status

from academic.models import (
    Subject,
    ClassRoom,
    GradeLevel,
    AllocatedSubject,
    AcademicLeadershipRole,
    AcademicLeadershipAssignment,
    AcademicWorkflow,
    SectionType,
    StandardClassCode,
)
from cbt.models import (
    QuestionBank,
    Question,
    QuestionType,
    QuestionDifficulty,
    CBTExam,
    CBTExamStatus,
)
from cbt.tests.base import CBTAPITestBase


class CBTAcademicScopeAPITests(CBTAPITestBase):
    def setUp(self):
        super().setUp()

        # Grade levels
        self.grade_jss2, _ = GradeLevel.objects.get_or_create(
            system_code=StandardClassCode.JSS_2,
            defaults={"section": SectionType.JUNIOR_SECONDARY, "default_name": "JSS 2", "sequence_order": 12},
        )

        # Classrooms
        self.class_jss1a = self.classroom_jss1
        self.class_jss1b = self.classroom_jss2
        self.class_jss2a, _ = ClassRoom.objects.get_or_create(
            name="C",
            grade_level=self.grade_jss2,
            defaults={"capacity": 30},
        )

        # Subjects
        # self.subj_math and self.subj_physics are already created by CBTAPITestBase
        self.subj_science = self.subj_physics
        self.subj_chemistry, _ = Subject.objects.get_or_create(
            name="Chemistry",
            defaults={"subject_code": "CHM101", "department": self.dept_science},
        )

        # Teacher 1 Allocations:
        # Mathematics -> JSS 1 (A)
        # Mathematics -> JSS 1 (B)
        # Physics -> JSS 2 (C)
        AllocatedSubject.objects.create(
            teacher_name=self.teacher_1,
            subject=self.subj_math,
            class_room=self.class_jss1a,
            academic_year=self.academic_year,
            weekly_periods=4,
        )
        AllocatedSubject.objects.create(
            teacher_name=self.teacher_1,
            subject=self.subj_math,
            class_room=self.class_jss1b,
            academic_year=self.academic_year,
            weekly_periods=4,
        )
        AllocatedSubject.objects.create(
            teacher_name=self.teacher_1,
            subject=self.subj_science,
            class_room=self.class_jss2a,
            academic_year=self.academic_year,
            weekly_periods=4,
        )

    # -------------------------------------------------------------
    # 1-7: Authoring Scope API Scenarios
    # -------------------------------------------------------------
    def test_teacher_subject_scope_and_deduplication(self):
        """1-3: Teacher sees assigned subjects (Math, Physics), deduplicated, not Chemistry."""
        self.client.force_authenticate(user=self.teacher_user_1)
        response = self.client.get("/api/cbt/authoring-scope/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertFalse(data["is_admin"])
        subject_names = [s["name"] for s in data["subjects"]]

        self.assertIn("Mathematics", subject_names)
        self.assertIn("Physics", subject_names)
        self.assertNotIn("Chemistry", subject_names)
        self.assertEqual(subject_names.count("Mathematics"), 1)

    def test_teacher_classroom_scope_depends_on_subject(self):
        """4-5: Math returns JSS 1 (A/B); Physics returns JSS 2 (C) only."""
        self.client.force_authenticate(user=self.teacher_user_1)
        response = self.client.get("/api/cbt/authoring-scope/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        subject_classrooms = data["subject_classrooms"]

        # Math -> A & B
        math_classrooms = [c["name"] for c in subject_classrooms.get(str(self.subj_math.id), [])]
        self.assertIn("A", math_classrooms)
        self.assertIn("B", math_classrooms)
        self.assertNotIn("C", math_classrooms)

        # Physics -> C
        sci_classrooms = [c["name"] for c in subject_classrooms.get(str(self.subj_science.id), [])]
        self.assertIn("C", sci_classrooms)
        self.assertNotIn("A", sci_classrooms)
        self.assertNotIn("B", sci_classrooms)

    def test_admin_scope_returns_all_school_subjects_and_classrooms(self):
        """6-7: School admin sees all tenant subjects and all classrooms."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/api/cbt/authoring-scope/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertTrue(data["is_admin"])
        subject_names = [s["name"] for s in data["subjects"]]
        classroom_names = [c["name"] for c in data["classrooms"]]

        self.assertIn("Mathematics", subject_names)
        self.assertIn("Physics", subject_names)
        self.assertIn("Chemistry", subject_names)

        self.assertIn("A", classroom_names)
        self.assertIn("B", classroom_names)
        self.assertIn("C", classroom_names)

    # -------------------------------------------------------------
    # 8-11: Question Bank Security
    # -------------------------------------------------------------
    def test_teacher_can_create_bank_for_assigned_subject(self):
        """8: Teacher can create bank for assigned subject."""
        self.client.force_authenticate(user=self.teacher_user_1)
        response = self.client.post("/api/cbt/question-banks/", {
            "name": "Teacher Math Bank",
            "subject": self.subj_math.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_teacher_cannot_create_bank_for_unassigned_subject(self):
        """9: Teacher cannot create bank for Chemistry (unassigned)."""
        self.client.force_authenticate(user=self.teacher_user_1)
        response = self.client.post("/api/cbt/question-banks/", {
            "name": "Malicious Chemistry Bank",
            "subject": self.subj_chemistry.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = response.json().get("detail", response.json())
        self.assertIn("subject", error_data)

    def test_teacher_cannot_patch_bank_to_unassigned_subject(self):
        """10: Teacher cannot update bank subject to unassigned Chemistry."""
        bank = QuestionBank.objects.create(
            name="Original Math Bank",
            subject=self.subj_math,
            created_by=self.teacher_1,
        )
        self.client.force_authenticate(user=self.teacher_user_1)
        response = self.client.patch(f"/api/cbt/question-banks/{bank.id}/", {
            "subject": self.subj_chemistry.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_create_bank_for_any_school_subject(self):
        """11: Admin can create bank for Chemistry."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post("/api/cbt/question-banks/", {
            "name": "Admin Chemistry Bank",
            "subject": self.subj_chemistry.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_teacher_grade_level_scope_depends_on_subject(self):
        """Teacher grade level scope is subject-dependent: Math -> JSS 1; Physics -> JSS 2."""
        self.client.force_authenticate(user=self.teacher_user_1)
        response = self.client.get("/api/cbt/authoring-scope/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        subject_grade_levels = data.get("subject_grade_levels", {})

        math_grades = [g["name"] for g in subject_grade_levels.get(str(self.subj_math.id), [])]
        self.assertIn("JSS 1", math_grades)
        self.assertNotIn("JSS 2", math_grades)

        phy_grades = [g["name"] for g in subject_grade_levels.get(str(self.subj_science.id), [])]
        self.assertIn("JSS 2", phy_grades)
        self.assertNotIn("JSS 1", phy_grades)

    def test_teacher_cannot_author_question_for_unallocated_grade_level(self):
        """Teacher teaches Math at JSS 1, but NOT at JSS 2. Creating Math + JSS 2 Question must fail."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss2.id],
            "question_type": "SINGLE_CHOICE",
            "text": "Math question for JSS 2",
            "options": [{"text": "A", "is_correct": True}],
        }
        response = self.client.post("/api/cbt/questions/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = response.json().get("detail", response.json())
        self.assertIn("grade_levels", error_data)

    def test_topic_must_match_subject_and_grade_level(self):
        """Topic must belong to the question subject and selected grade level."""
        from academic.models import Topic, SubTopic
        topic_math_jss1 = Topic.objects.create(
            name="Fractions", subject=self.subj_math, grade_level=self.grade_jss1
        )
        topic_math_jss2 = Topic.objects.create(
            name="Linear Equations", subject=self.subj_math, grade_level=self.grade_jss2
        )
        topic_chem = Topic.objects.create(
            name="Acids and Bases", subject=self.subj_chemistry, grade_level=self.grade_jss1
        )

        self.client.force_authenticate(user=self.teacher_user_1)

        # 1. Valid: Math + JSS 1 + Fractions
        payload_valid = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "topic": topic_math_jss1.id,
            "question_type": "SINGLE_CHOICE",
            "text": "What is 1/2 + 1/2?",
            "options": [{"text": "1", "is_correct": True}],
        }
        res_valid = self.client.post("/api/cbt/questions/", payload_valid, format="json")
        self.assertEqual(res_valid.status_code, status.HTTP_201_CREATED)

        # 2. Invalid: Math + JSS 1 + Chemistry Topic
        payload_wrong_subject = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "topic": topic_chem.id,
            "question_type": "SINGLE_CHOICE",
            "text": "Invalid topic question",
            "options": [{"text": "1", "is_correct": True}],
        }
        res_wrong_subj = self.client.post("/api/cbt/questions/", payload_wrong_subject, format="json")
        self.assertEqual(res_wrong_subj.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Invalid: Math + JSS 1 + Math JSS 2 Topic
        payload_wrong_grade = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "topic": topic_math_jss2.id,
            "question_type": "SINGLE_CHOICE",
            "text": "Invalid grade topic question",
            "options": [{"text": "1", "is_correct": True}],
        }
        res_wrong_grade = self.client.post("/api/cbt/questions/", payload_wrong_grade, format="json")
        self.assertEqual(res_wrong_grade.status_code, status.HTTP_400_BAD_REQUEST)

    def test_subtopic_must_belong_to_selected_topic(self):
        """SubTopic must belong to the selected Topic."""
        from academic.models import Topic, SubTopic
        topic_a = Topic.objects.create(name="Topic A", subject=self.subj_math, grade_level=self.grade_jss1)
        topic_b = Topic.objects.create(name="Topic B", subject=self.subj_math, grade_level=self.grade_jss1)

        subtopic_a = SubTopic.objects.create(name="SubTopic A1", topic=topic_a)
        subtopic_b = SubTopic.objects.create(name="SubTopic B1", topic=topic_b)

        self.client.force_authenticate(user=self.teacher_user_1)

        # Valid: Topic A + SubTopic A1
        payload_valid = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "topic": topic_a.id,
            "subtopic": subtopic_a.id,
            "question_type": "SINGLE_CHOICE",
            "text": "Valid subtopic question",
            "options": [{"text": "1", "is_correct": True}],
        }
        res_valid = self.client.post("/api/cbt/questions/", payload_valid, format="json")
        self.assertEqual(res_valid.status_code, status.HTTP_201_CREATED)

        # Invalid: Topic A + SubTopic B1
        payload_mismatch = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "topic": topic_a.id,
            "subtopic": subtopic_b.id,
            "question_type": "SINGLE_CHOICE",
            "text": "Mismatch subtopic question",
            "options": [{"text": "1", "is_correct": True}],
        }
        res_mismatch = self.client.post("/api/cbt/questions/", payload_mismatch, format="json")
        self.assertEqual(res_mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = res_mismatch.json().get("detail", res_mismatch.json())
        self.assertIn("subtopic", error_data)

    def test_learning_objective_alignment_curriculum_scope(self):
        """Learning objective alignment must belong to the question's curriculum scope."""
        from academic.models import (
            Curriculum, CurriculumSubject, CurriculumTopic, Topic, LearningObjective
        )
        curriculum, _ = Curriculum.objects.get_or_create(
            name="CBT Test Curriculum",
            defaults={"version": "1.0"}
        )
        cur_subj, _ = CurriculumSubject.objects.get_or_create(
            curriculum=curriculum,
            name="Mathematics",
            grade_level=self.grade_jss1,
            defaults={"subject": self.subj_math},
        )
        topic, _ = Topic.objects.get_or_create(
            name="Number Bases", subject=self.subj_math, grade_level=self.grade_jss1
        )
        cur_topic, _ = CurriculumTopic.objects.get_or_create(
            curriculum_subject=cur_subj, name="Number Bases", topic=topic
        )
        obj_valid = LearningObjective.objects.create(
            curriculum_topic=cur_topic, description="Convert base 10 to base 2", order=1
        )

        other_subj, _ = CurriculumSubject.objects.get_or_create(
            curriculum=curriculum,
            name="Chemistry",
            grade_level=self.grade_jss1,
            defaults={"subject": self.subj_chemistry},
        )
        other_cur_topic, _ = CurriculumTopic.objects.get_or_create(
            curriculum_subject=other_subj, name="Chemical Reactions"
        )
        obj_unrelated = LearningObjective.objects.create(
            curriculum_topic=other_cur_topic, description="Balance chemical equation", order=1
        )

        self.client.force_authenticate(user=self.teacher_user_1)
        q_res = self.client.post("/api/cbt/questions/", {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "topic": topic.id,
            "question_type": "SINGLE_CHOICE",
            "text": "Convert 5 to binary",
            "options": [{"text": "101", "is_correct": True}],
        }, format="json")
        self.assertEqual(q_res.status_code, status.HTTP_201_CREATED)
        q_id = q_res.json()["id"]

        # Valid objective alignment
        align_res = self.client.post(f"/api/cbt/questions/{q_id}/learning-objectives/", {
            "learning_objective": obj_valid.id,
            "is_primary": True,
        })
        self.assertEqual(align_res.status_code, status.HTTP_201_CREATED)

        # Unrelated objective alignment must fail
        bad_align = self.client.post(f"/api/cbt/questions/{q_id}/learning-objectives/", {
            "learning_objective": obj_unrelated.id,
        })
        self.assertEqual(bad_align.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_question_grade_levels_validates_topic_compatibility(self):
        """PATCH grade_levels on Question validates compatibility with existing Topic."""
        from academic.models import Topic
        topic_jss1 = Topic.objects.create(
            name="Arithmetic JSS1", subject=self.subj_science, grade_level=self.grade_jss1
        )
        topic_jss2 = Topic.objects.create(
            name="Mechanics JSS2", subject=self.subj_science, grade_level=self.grade_jss2
        )

        self.client.force_authenticate(user=self.teacher_user_1)
        # Create Physics Question at JSS 2 with Mechanics JSS2 Topic
        q_res = self.client.post("/api/cbt/questions/", {
            "subject": self.subj_science.id,
            "grade_levels": [self.grade_jss2.id],
            "topic": topic_jss2.id,
            "question_type": "SINGLE_CHOICE",
            "text": "What is velocity?",
            "options": [{"text": "Speed in direction", "is_correct": True}],
        }, format="json")
        self.assertEqual(q_res.status_code, status.HTTP_201_CREATED)
        q_id = q_res.json()["id"]

        # Attempt to PATCH grade_levels to [JSS 1] (teacher is not allocated Physics at JSS 1, plus topic is JSS 2)
        patch_res = self.client.patch(f"/api/cbt/questions/{q_id}/", {
            "grade_levels": [self.grade_jss1.id],
        }, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------
    # Exam Security & Subject-Classroom Pairs
    # -------------------------------------------------------------
    def test_teacher_can_create_exam_for_valid_subject_and_classroom(self):
        """15: Teacher can create exam for Math in JSS 1A."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "title": "JSS 1A Math Exam",
            "session": self.session.id,
            "component": self.component.id,
            "subject": self.subj_math.id,
            "classroom": self.class_jss1a.id,
            "duration_minutes": 60,
        }
        response = self.client.post("/api/cbt/exams/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_teacher_cannot_create_exam_for_unassigned_classroom_for_subject(self):
        """16: Teacher teaches Math in JSS 1A/1B, but NOT in JSS 2A."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "title": "Invalid Math Exam in JSS 2A",
            "session": self.session.id,
            "component": self.component.id,
            "subject": self.subj_math.id,
            "classroom": self.class_jss2a.id,
            "duration_minutes": 60,
        }
        response = self.client.post("/api/cbt/exams/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = response.json().get("detail", response.json())
        self.assertIn("classroom", error_data)

    def test_teacher_cannot_create_exam_for_unassigned_subject(self):
        """17: Teacher cannot create exam for Chemistry in any classroom."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "title": "Invalid Chemistry Exam",
            "session": self.session.id,
            "component": self.component.id,
            "subject": self.subj_chemistry.id,
            "classroom": self.class_jss1a.id,
            "duration_minutes": 60,
        }
        response = self.client.post("/api/cbt/exams/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_data = response.json().get("detail", response.json())
        self.assertIn("subject", error_data)

    def test_patch_exam_subject_validates_resulting_pair(self):
        """18: Changing subject via PATCH validates against existing classroom."""
        exam = CBTExam.objects.create(
            title="Math Exam in JSS 1A",
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.class_jss1a,
            duration_minutes=60,
            created_by=self.teacher_1,
        )
        self.client.force_authenticate(user=self.teacher_user_1)
        # Attempt PATCH subject to Basic Science (which teacher only teaches in JSS 2A, not JSS 1A)
        response = self.client.patch(f"/api/cbt/exams/{exam.id}/", {
            "subject": self.subj_science.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_exam_classroom_validates_resulting_pair(self):
        """19: Changing classroom via PATCH validates against existing subject."""
        exam = CBTExam.objects.create(
            title="Science Exam in JSS 2A",
            session=self.session,
            component=self.component,
            subject=self.subj_science,
            classroom=self.class_jss2a,
            duration_minutes=60,
            created_by=self.teacher_1,
        )
        self.client.force_authenticate(user=self.teacher_user_1)
        # Attempt PATCH classroom to JSS 1A (where teacher teaches Math, not Science)
        response = self.client.patch(f"/api/cbt/exams/{exam.id}/", {
            "classroom": self.class_jss1a.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_create_valid_school_wide_exam_combinations(self):
        """20: Admin can create exam for any school subject and classroom."""
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "title": "Admin Chemistry Exam",
            "session": self.session.id,
            "component": self.component.id,
            "subject": self.subj_chemistry.id,
            "classroom": self.class_jss2a.id,
            "duration_minutes": 60,
        }
        response = self.client.post("/api/cbt/exams/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # -------------------------------------------------------------
    # 21-23: Authority Regression & Safety
    # -------------------------------------------------------------
    def test_hod_review_authority_remains_functional(self):
        """21: HOD of Science department can see science subjects in scope."""
        # Make Teacher 2 HOD of Science Department
        AcademicLeadershipAssignment.objects.create(
            teacher=self.teacher_2,
            role=AcademicLeadershipRole.HOD,
            department=self.dept_science,
            academic_year=self.academic_year,
            is_active=True,
        )
        self.client.force_authenticate(user=self.teacher_user_2)
        response = self.client.get("/api/cbt/authoring-scope/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        subject_names = [s["name"] for s in data["subjects"]]
        # HOD can review/author across department subjects
        self.assertIn("Mathematics", subject_names)
        self.assertIn("Physics", subject_names)
        self.assertIn("Chemistry", subject_names)

    def test_student_cannot_access_authoring_scope(self):
        """22: Student is forbidden from accessing CBT authoring scope endpoint."""
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/cbt/authoring-scope/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unrelated_teacher_cannot_gain_unauthorized_exam_access(self):
        """23: Teacher 2 cannot author or modify Teacher 1's Math exam."""
        exam = CBTExam.objects.create(
            title="Teacher 1 Math Exam",
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.class_jss1a,
            duration_minutes=60,
            created_by=self.teacher_1,
        )
        self.client.force_authenticate(user=self.teacher_user_2)
        # Teacher 2 has no allocations
        response = self.client.patch(f"/api/cbt/exams/{exam.id}/", {
            "title": "Tampered Title",
        })
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
