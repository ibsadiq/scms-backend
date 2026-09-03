from django.core.exceptions import ValidationError
from django.db.models import Q

from academic.models import (
    Subject,
    GradeLevel,
    ClassRoom,
    Teacher,
    AllocatedSubject,
    AcademicWorkflow,
    Topic,
    SubTopic,
    LearningObjective,
)
from academic.models.choices import PublishedSchemeEntryType
from academic.services.academic_authority_service import AcademicAuthorityService
from administration.models import AcademicYear
from cbt.services.cbt_actor_service import CBTActorService


class CBTAcademicScopeService:
    """
    Authoritative service for resolving academic authoring scope across CBT.
    Distinguishes ordinary teacher authoring scope (AllocatedSubject assignments),
    academic leadership oversight (AcademicAuthorityService), and school-wide admin authority.
    """

    @classmethod
    def is_admin_scope(cls, user) -> bool:
        """
        Determines if the user has institutional school-wide scope.
        """
        if not user or not user.is_authenticated:
            return False
        return bool(
            getattr(user, "is_admin", False)
            or getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )

    @classmethod
    def get_current_academic_year(cls, session=None, academic_year=None):
        """
        Resolves the contextual academic year from parameters or active academic year.
        """
        if academic_year:
            return academic_year
        if session and hasattr(session, "academic_year") and session.academic_year:
            return session.academic_year
        return AcademicYear.objects.filter(active_year=True).first()

    @classmethod
    def get_allowed_subjects(cls, user, session=None, academic_year=None):
        """
        Returns QuerySet of Subjects the user is authorized to author or manage CBT content for.
        """
        if cls.is_admin_scope(user):
            return Subject.objects.all().order_by("name")

        try:
            teacher = CBTActorService.resolve_teacher(user)
        except ValidationError:
            return Subject.objects.none()

        target_year = cls.get_current_academic_year(session=session, academic_year=academic_year)

        alloc_qs = AllocatedSubject.objects.filter(teacher_name=teacher)
        if target_year:
            # Match current academic year allocations if available; if none exist, check across all active allocations
            year_alloc = alloc_qs.filter(academic_year=target_year)
            if year_alloc.exists():
                alloc_qs = year_alloc

        assigned_subject_ids = set(alloc_qs.values_list("subject_id", flat=True).distinct())

        # Include subjects where teacher has leadership authority (e.g. HOD)
        from academic.models import AcademicLeadershipAssignment, AcademicLeadershipRole

        hod_assignments = AcademicLeadershipAssignment.objects.filter(
            teacher=teacher,
            role=AcademicLeadershipRole.HOD,
            is_active=True,
        )
        if target_year:
            year_hod = hod_assignments.filter(academic_year=target_year)
            if year_hod.exists():
                hod_assignments = year_hod
        hod_dept_ids = set(hod_assignments.values_list("department_id", flat=True))

        all_tenant_subjects = Subject.objects.select_related("department").all()
        leadership_subject_ids = {
            s.id for s in all_tenant_subjects
            if (s.department_id and s.department_id in hod_dept_ids)
            or AcademicAuthorityService.can_approve(
                actor=user,
                workflow=AcademicWorkflow.QUESTION_BANK,
                subject=s,
                academic_year=target_year,
            )
        }

        allowed_ids = assigned_subject_ids.union(leadership_subject_ids)
        return Subject.objects.filter(id__in=allowed_ids).order_by("name")

    @classmethod
    def get_allowed_grade_levels(cls, user, subject=None, session=None, academic_year=None):
        """
        Returns QuerySet of GradeLevels the user is authorized to use for the selected subject.
        For teachers, grade levels are derived strictly from classrooms where they teach THAT subject.
        """
        if cls.is_admin_scope(user):
            return GradeLevel.objects.all().order_by("sequence_order")

        try:
            teacher = CBTActorService.resolve_teacher(user)
        except ValidationError:
            return GradeLevel.objects.none()

        target_year = cls.get_current_academic_year(session=session, academic_year=academic_year)

        alloc_qs = AllocatedSubject.objects.filter(teacher_name=teacher)
        if target_year:
            year_alloc = alloc_qs.filter(academic_year=target_year)
            if year_alloc.exists():
                alloc_qs = year_alloc

        if subject is not None:
            subject_id = getattr(subject, "pk", subject)
            alloc_qs = alloc_qs.filter(subject_id=subject_id)

        grade_level_ids = alloc_qs.values_list("class_room__grade_level_id", flat=True).distinct()
        return GradeLevel.objects.filter(id__in=grade_level_ids).order_by("sequence_order")

    @classmethod
    def get_allowed_classrooms(cls, user, subject=None, grade_level=None, session=None, academic_year=None):
        """
        Returns QuerySet of ClassRooms the user is authorized to use for an exam.
        For teachers, classroom access strictly depends on the selected subject (and grade level if specified).
        """
        if cls.is_admin_scope(user):
            qs = ClassRoom.objects.all().select_related("grade_level", "stream")
            if grade_level is not None:
                gl_id = getattr(grade_level, "pk", grade_level)
                qs = qs.filter(grade_level_id=gl_id)
            return qs.order_by("grade_level__sequence_order", "name")

        try:
            teacher = CBTActorService.resolve_teacher(user)
        except ValidationError:
            return ClassRoom.objects.none()

        target_year = cls.get_current_academic_year(session=session, academic_year=academic_year)

        alloc_qs = AllocatedSubject.objects.filter(teacher_name=teacher)
        if target_year:
            year_alloc = alloc_qs.filter(academic_year=target_year)
            if year_alloc.exists():
                alloc_qs = year_alloc

        if subject is not None:
            subject_id = getattr(subject, "pk", subject)
            alloc_qs = alloc_qs.filter(subject_id=subject_id)

        if grade_level is not None:
            gl_id = getattr(grade_level, "pk", grade_level)
            alloc_qs = alloc_qs.filter(class_room__grade_level_id=gl_id)

        classroom_ids = alloc_qs.values_list("class_room_id", flat=True).distinct()
        return ClassRoom.objects.filter(id__in=classroom_ids).select_related(
            "grade_level", "stream"
        ).order_by("grade_level__sequence_order", "name")

    @classmethod
    def can_use_subject(cls, user, subject, session=None, academic_year=None) -> bool:
        """
        Validates whether user has authority to author CBT items for the subject.
        """
        if not subject:
            return False
        if cls.is_admin_scope(user):
            subject_id = getattr(subject, "pk", subject)
            return Subject.objects.filter(pk=subject_id).exists()

        subject_id = getattr(subject, "pk", subject)
        allowed_ids = set(cls.get_allowed_subjects(
            user, session=session, academic_year=academic_year
        ).values_list("id", flat=True))
        return subject_id in allowed_ids

    @classmethod
    def can_use_grade_level_for_subject(
        cls, user, grade_level, subject, session=None, academic_year=None
    ) -> bool:
        """
        Validates whether the user is authorized to use the grade level for the selected subject.
        """
        if not grade_level or not subject:
            return False

        if cls.is_admin_scope(user):
            gl_id = getattr(grade_level, "pk", grade_level)
            return GradeLevel.objects.filter(pk=gl_id).exists()

        gl_id = getattr(grade_level, "pk", grade_level)
        allowed_gl_ids = set(cls.get_allowed_grade_levels(
            user, subject=subject, session=session, academic_year=academic_year
        ).values_list("id", flat=True))
        return gl_id in allowed_gl_ids

    @classmethod
    def can_use_classroom_for_subject(
        cls, user, classroom, subject, session=None, academic_year=None
    ) -> bool:
        """
        Validates whether user can create/manage an exam for the subject + classroom pair.
        """
        if not classroom or not subject:
            return False

        if cls.is_admin_scope(user):
            classroom_id = getattr(classroom, "pk", classroom)
            return ClassRoom.objects.filter(pk=classroom_id).exists()

        classroom_id = getattr(classroom, "pk", classroom)
        allowed_classroom_ids = set(cls.get_allowed_classrooms(
            user, subject=subject, session=session, academic_year=academic_year
        ).values_list("id", flat=True))
        return classroom_id in allowed_classroom_ids

    @classmethod
    def get_allowed_topics(cls, user, subject, grade_levels=None):
        """
        Returns QuerySet of eligible instructional Topics for the subject and grade levels.
        """
        if not subject:
            return Topic.objects.none()

        subject_id = getattr(subject, "pk", subject)
        qs = Topic.objects.filter(subject_id=subject_id, is_active=True).select_related(
            "grade_level", "subject"
        )

        if grade_levels:
            if hasattr(grade_levels, "all"):
                grade_ids = list(grade_levels.values_list("id", flat=True))
            elif isinstance(grade_levels, (list, tuple, set)):
                grade_ids = [getattr(g, "pk", g) for g in grade_levels]
            else:
                grade_ids = [getattr(grade_levels, "pk", grade_levels)]
            qs = qs.filter(grade_level_id__in=grade_ids)

        # Exclude topics that are strictly non-instructional published scheme entries
        # If a curriculum topic has entries, ensure at least one active entry is INSTRUCTION
        non_instruction_only_topics = Topic.objects.filter(
            curriculum_mappings__published_scheme_entries__isnull=False
        ).exclude(
            curriculum_mappings__published_scheme_entries__entry_type=PublishedSchemeEntryType.INSTRUCTION
        ).filter(
            curriculum_mappings__published_scheme_entries__is_active=True
        ).values_list("id", flat=True)

        qs = qs.exclude(id__in=non_instruction_only_topics)
        return qs.order_by("grade_level__sequence_order", "name")

    @classmethod
    def can_use_topic(cls, user, topic, subject, grade_levels=None) -> bool:
        """
        Validates whether the topic belongs to the subject, intersects selected grade levels,
        and represents instructional curriculum content.
        """
        if not topic or not subject:
            return False

        topic_id = getattr(topic, "pk", topic)
        return cls.get_allowed_topics(
            user, subject=subject, grade_levels=grade_levels
        ).filter(pk=topic_id).exists()

    @classmethod
    def can_use_subtopic(cls, user, subtopic, topic) -> bool:
        """
        Validates whether the subtopic belongs directly to the selected topic.
        """
        if not subtopic or not topic:
            return False

        subtopic_id = getattr(subtopic, "pk", subtopic)
        topic_id = getattr(topic, "pk", topic)
        return SubTopic.objects.filter(pk=subtopic_id, topic_id=topic_id, is_active=True).exists()

    @classmethod
    def get_authoring_scope_payload(cls, user, session=None, academic_year=None) -> dict:
        """
        Constructs the authoring scope metadata payload for frontend selectors.
        """
        is_admin = cls.is_admin_scope(user)
        subjects = list(cls.get_allowed_subjects(user, session=session, academic_year=academic_year))
        target_year = cls.get_current_academic_year(session=session, academic_year=academic_year)

        subject_data = [
            {
                "id": s.id,
                "name": s.name,
                "subject_code": s.subject_code,
            }
            for s in subjects
        ]

        if is_admin:
            all_grade_levels = list(GradeLevel.objects.all().order_by("sequence_order"))
            grade_level_data = [
                {
                    "id": gl.id,
                    "name": str(gl),
                    "sequence_order": gl.sequence_order,
                }
                for gl in all_grade_levels
            ]

            all_classrooms = list(
                ClassRoom.objects.select_related("grade_level", "stream")
                .all()
                .order_by("grade_level__sequence_order", "name")
            )
            classroom_data = [
                {
                    "id": c.id,
                    "name": c.name,
                    "display_name": c.display_name,
                    "grade_level": c.grade_level_id,
                    "grade_level_name": str(c.grade_level) if c.grade_level else "",
                }
                for c in all_classrooms
            ]

            # Admin gets all grade levels & classrooms across all subjects
            subject_grade_levels = {
                str(s["id"]): grade_level_data for s in subject_data
            }
            subject_classrooms = {
                str(s["id"]): classroom_data for s in subject_data
            }
            return {
                "is_admin": True,
                "subjects": subject_data,
                "grade_levels": grade_level_data,
                "classrooms": classroom_data,
                "subject_grade_levels": subject_grade_levels,
                "subject_classrooms": subject_classrooms,
            }

        # Teacher scope construction
        try:
            teacher = CBTActorService.resolve_teacher(user)
        except ValidationError:
            return {
                "is_admin": False,
                "subjects": [],
                "grade_levels": [],
                "classrooms": [],
                "subject_grade_levels": {},
                "subject_classrooms": {},
            }

        alloc_qs = AllocatedSubject.objects.filter(teacher_name=teacher).select_related(
            "class_room__grade_level", "class_room__stream"
        )
        if target_year:
            year_alloc = alloc_qs.filter(academic_year=target_year)
            if year_alloc.exists():
                alloc_qs = year_alloc

        subject_grade_levels_map = {}
        subject_classrooms_map = {}
        distinct_grade_levels = {}
        distinct_classrooms = {}

        for alloc in alloc_qs:
            sid = str(alloc.subject_id)
            c = alloc.class_room
            if not c:
                continue

            c_dict = {
                "id": c.id,
                "name": c.name,
                "display_name": c.display_name,
                "grade_level": c.grade_level_id,
                "grade_level_name": str(c.grade_level) if c.grade_level else "",
            }
            distinct_classrooms[c.id] = c_dict

            if sid not in subject_classrooms_map:
                subject_classrooms_map[sid] = []
            if not any(item["id"] == c.id for item in subject_classrooms_map[sid]):
                subject_classrooms_map[sid].append(c_dict)

            gl = c.grade_level
            if gl:
                gl_dict = {
                    "id": gl.id,
                    "name": str(gl),
                    "sequence_order": gl.sequence_order,
                }
                distinct_grade_levels[gl.id] = gl_dict

                if sid not in subject_grade_levels_map:
                    subject_grade_levels_map[sid] = []
                if not any(item["id"] == gl.id for item in subject_grade_levels_map[sid]):
                    subject_grade_levels_map[sid].append(gl_dict)

        # Sort grade levels by sequence order
        sorted_grade_levels = sorted(distinct_grade_levels.values(), key=lambda g: g["sequence_order"])
        for sid in subject_grade_levels_map:
            subject_grade_levels_map[sid].sort(key=lambda g: g["sequence_order"])

        return {
            "is_admin": False,
            "subjects": subject_data,
            "grade_levels": sorted_grade_levels,
            "classrooms": list(distinct_classrooms.values()),
            "subject_grade_levels": subject_grade_levels_map,
            "subject_classrooms": subject_classrooms_map,
        }

