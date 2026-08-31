from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.db.models import Q
from academic.models import (
    AllocatedSubject,
    CurriculumAssignment,
    CurriculumSubject,
    SchoolSection,
)


class CurriculumAssignmentResolver:
    """
    Deterministic resolution service to determine which Curriculum and
    canonical CurriculumSubject applies to a teacher allocation or academic scope.
    """

    STATUS_RESOLVED = "RESOLVED"
    STATUS_NO_CURRICULUM_ASSIGNED = "NO_CURRICULUM_ASSIGNED"
    STATUS_SUBJECT_UNMAPPED = "SUBJECT_UNMAPPED"
    STATUS_CONFIGURATION_CONFLICT = "CONFIGURATION_CONFLICT"

    @classmethod
    def resolve_for_allocation(cls, allocation: AllocatedSubject) -> Dict[str, Any]:
        """Resolve curriculum context for a single AllocatedSubject."""
        results = cls.resolve_for_allocations([allocation])
        return results.get(allocation.id, cls._empty_result(cls.STATUS_NO_CURRICULUM_ASSIGNED))

    @classmethod
    def resolve_for_allocations(cls, allocations: List[AllocatedSubject]) -> Dict[int, Dict[str, Any]]:
        """
        Batch resolve curriculum context for multiple AllocatedSubject records
        in O(1) database queries.
        """
        if not allocations:
            return {}

        # 1. Collect query parameters
        academic_year_ids = {a.academic_year_id for a in allocations if a.academic_year_id}
        if not academic_year_ids:
            return {a.id: cls._empty_result(cls.STATUS_NO_CURRICULUM_ASSIGNED) for a in allocations}

        # 2. Fetch all active curriculum assignments for relevant academic years
        assignments = list(
            CurriculumAssignment.objects.filter(
                academic_year_id__in=academic_year_ids,
                is_active=True,
                curriculum__is_active=True,
            ).select_related("curriculum", "section", "grade_level", "classroom")
        )

        # Index assignments by academic_year_id
        assignments_by_year: Dict[int, List[CurriculumAssignment]] = defaultdict(list)
        for ca in assignments:
            assignments_by_year[ca.academic_year_id].append(ca)

        # 3. Map SchoolSection system_codes to SchoolSection objects in memory
        school_sections = list(SchoolSection.objects.all())
        section_by_code = {s.system_code: s for s in school_sections}

        # 4. Resolve assigned Curriculum for each allocation in memory
        assigned_curricula: Dict[int, Optional[Any]] = {}
        assigned_assignments: Dict[int, Optional[CurriculumAssignment]] = {}

        candidate_subject_pairs = set()

        for a in allocations:
            year_id = a.academic_year_id
            year_assignments = assignments_by_year.get(year_id, [])

            classroom = a.class_room
            grade_level = classroom.grade_level if classroom else None
            section_code = grade_level.section if grade_level else None
            matching_section = section_by_code.get(section_code) if section_code else None

            assigned_ca = None

            # Specificity 1: Classroom
            if classroom:
                cls_matches = [ca for ca in year_assignments if ca.classroom_id == classroom.id]
                if len(cls_matches) == 1:
                    assigned_ca = cls_matches[0]
                elif len(cls_matches) > 1:
                    # Configuration conflict at classroom level
                    assigned_curricula[a.id] = None
                    assigned_assignments[a.id] = None
                    continue

            # Specificity 2: GradeLevel
            if not assigned_ca and grade_level:
                grade_matches = [ca for ca in year_assignments if ca.grade_level_id == grade_level.id]
                if len(grade_matches) == 1:
                    assigned_ca = grade_matches[0]
                elif len(grade_matches) > 1:
                    assigned_curricula[a.id] = None
                    assigned_assignments[a.id] = None
                    continue

            # Specificity 3: Section
            if not assigned_ca and matching_section:
                sec_matches = [ca for ca in year_assignments if ca.section_id == matching_section.id]
                if len(sec_matches) == 1:
                    assigned_ca = sec_matches[0]
                elif len(sec_matches) > 1:
                    assigned_curricula[a.id] = None
                    assigned_assignments[a.id] = None
                    continue

            # Specificity 4: School-wide
            if not assigned_ca:
                school_matches = [
                    ca for ca in year_assignments
                    if ca.classroom_id is None and ca.grade_level_id is None and ca.section_id is None
                ]
                if len(school_matches) == 1:
                    assigned_ca = school_matches[0]
                elif len(school_matches) > 1:
                    assigned_curricula[a.id] = None
                    assigned_assignments[a.id] = None
                    continue

            if assigned_ca:
                assigned_curricula[a.id] = assigned_ca.curriculum
                assigned_assignments[a.id] = assigned_ca
                if a.subject_id and grade_level:
                    candidate_subject_pairs.add((assigned_ca.curriculum_id, grade_level.id, a.subject_id))
            else:
                assigned_curricula[a.id] = None
                assigned_assignments[a.id] = None

        # 5. Batch fetch matching CurriculumSubject records for (curriculum, grade_level, subject)
        curriculum_subjects_map: Dict[tuple, List[CurriculumSubject]] = defaultdict(list)
        if candidate_subject_pairs:
            q_filter = Q()
            for curr_id, gr_id, subj_id in candidate_subject_pairs:
                q_filter |= Q(curriculum_id=curr_id, grade_level_id=gr_id, subject_id=subj_id)

            cs_records = CurriculumSubject.objects.filter(
                q_filter,
                is_active=True,
                curriculum__is_active=True,
            ).select_related("curriculum")

            for cs in cs_records:
                curriculum_subjects_map[(cs.curriculum_id, cs.grade_level_id, cs.subject_id)].append(cs)

        # 6. Build final resolution dict
        results: Dict[int, Dict[str, Any]] = {}

        for a in allocations:
            ca = assigned_assignments.get(a.id)
            curriculum = assigned_curricula.get(a.id)

            if not ca or not curriculum:
                results[a.id] = cls._empty_result(cls.STATUS_NO_CURRICULUM_ASSIGNED)
                continue

            classroom = a.class_room
            grade_level = classroom.grade_level if classroom else None
            subject_id = a.subject_id

            if not grade_level or not subject_id:
                results[a.id] = {
                    "status": cls.STATUS_SUBJECT_UNMAPPED,
                    "curriculum_assignment_id": ca.id,
                    "assignment_scope": ca.scope_type,
                    "curriculum_id": curriculum.id,
                    "curriculum_name": curriculum.name,
                    "curriculum_subject_id": None,
                    "curriculum_subject_name": None,
                    "candidate_count": 0,
                }
                continue

            candidates = curriculum_subjects_map.get((curriculum.id, grade_level.id, subject_id), [])
            candidate_count = len(candidates)

            if candidate_count == 1:
                cs = candidates[0]
                results[a.id] = {
                    "status": cls.STATUS_RESOLVED,
                    "curriculum_assignment_id": ca.id,
                    "assignment_scope": ca.scope_type,
                    "curriculum_id": curriculum.id,
                    "curriculum_name": curriculum.name,
                    "curriculum_subject_id": cs.id,
                    "curriculum_subject_name": cs.name,
                    "candidate_count": 1,
                }
            elif candidate_count == 0:
                results[a.id] = {
                    "status": cls.STATUS_SUBJECT_UNMAPPED,
                    "curriculum_assignment_id": ca.id,
                    "assignment_scope": ca.scope_type,
                    "curriculum_id": curriculum.id,
                    "curriculum_name": curriculum.name,
                    "curriculum_subject_id": None,
                    "curriculum_subject_name": None,
                    "candidate_count": 0,
                }
            else:
                results[a.id] = {
                    "status": cls.STATUS_CONFIGURATION_CONFLICT,
                    "curriculum_assignment_id": ca.id,
                    "assignment_scope": ca.scope_type,
                    "curriculum_id": curriculum.id,
                    "curriculum_name": curriculum.name,
                    "curriculum_subject_id": None,
                    "curriculum_subject_name": None,
                    "candidate_count": candidate_count,
                }

        return results

    @staticmethod
    def _empty_result(status: str) -> Dict[str, Any]:
        return {
            "status": status,
            "curriculum_assignment_id": None,
            "assignment_scope": None,
            "curriculum_id": None,
            "curriculum_name": None,
            "curriculum_subject_id": None,
            "curriculum_subject_name": None,
            "candidate_count": 0,
        }
