from django.core.exceptions import ValidationError
from django.db import transaction
from ..models import TermResult, AnnualResult, AnnualSubjectResult, PromotionRule
from academic.models import Subject


class PromotionService:

    @staticmethod
    def _get_third_term_result(term_results):
        with_number = [r for r in term_results if getattr(r.term, "term_number", None) == 3]
        if with_number:
            return with_number[0]
        return max(term_results, key=lambda r: r.term.start_date, default=None)

    @staticmethod
    @transaction.atomic
    def compute_annual_result(student, academic_year, user):
        term_results = list(
            TermResult.objects.filter(student=student, academic_year=academic_year)
            .select_related("term", "grading_scheme", "classroom")
        )
        if not term_results:
            raise ValidationError("No term results found for this academic year.")

        latest = max(term_results, key=lambda r: r.term.start_date)
        scheme = latest.grading_scheme
        rule = getattr(scheme, "promotion_rule", None)
        if not rule:
            raise ValidationError("No promotion rule configured for this grading scheme.")

        if rule.annual_computation_method == PromotionRule.AnnualComputationMethod.FINAL_TERM_ONLY:
            return PromotionService._compute_from_final_term(student, academic_year, term_results, latest, rule, user)
        return PromotionService._compute_from_average(student, academic_year, term_results, latest, rule, user)

    @staticmethod
    def _compute_from_final_term(student, academic_year, term_results, latest, rule, user):
        final = PromotionService._get_third_term_result(term_results)
        if not final:
            raise ValidationError("Final term result not yet computed.")

        annual_result, _ = AnnualResult.objects.update_or_create(
            student=student, academic_year=academic_year,
            defaults={
                "classroom": final.classroom,
                "grading_scheme": final.grading_scheme,
                "total_marks": final.total_marks,
                "average_percentage": final.average_percentage,
                "grade": final.grade,
                "gpa": final.gpa,
                "position_in_class": final.position_in_class,
                "total_students": final.total_students,
                "computed_by": user,
            },
        )
        annual_result.full_clean()
        annual_result.save()
        PromotionService._sync_subject_results(annual_result, term_results, final)
        PromotionService._apply_promotion_decision(annual_result, rule)
        return annual_result

    @staticmethod
    def _compute_from_average(student, academic_year, term_results, latest, rule, user):
        overall_avg = round(sum(r.average_percentage for r in term_results) / len(term_results), 2)

        annual_result, _ = AnnualResult.objects.update_or_create(
            student=student, academic_year=academic_year,
            defaults={
                "classroom": latest.classroom,
                "grading_scheme": latest.grading_scheme,
                "total_marks": sum(r.total_marks for r in term_results),
                "average_percentage": overall_avg,
                "grade": latest.grade,  # or re-resolve via GradeRule against overall_avg
                "gpa": round(sum(r.gpa for r in term_results) / len(term_results), 2),
                "computed_by": user,
            },
        )
        annual_result.full_clean()
        annual_result.save()
        PromotionService._sync_subject_results(annual_result, term_results, None)
        PromotionService._apply_promotion_decision(annual_result, rule)
        return annual_result

    @staticmethod
    def _sync_subject_results(annual_result, term_results, final_only_from):
        by_subject = {}
        for term_result in term_results:
            term_num = getattr(term_result.term, "term_number", None)
            for sr in term_result.subject_results.select_related("subject"):
                bucket = by_subject.setdefault(sr.subject_id, {})
                if term_num == 1:
                    bucket["first_term"] = sr.percentage
                elif term_num == 2:
                    bucket["second_term"] = sr.percentage
                elif term_num == 3:
                    bucket["third_term"] = sr.percentage
                bucket["latest"] = sr

        for subject_id, bucket in by_subject.items():
            if final_only_from:
                final_sr = final_only_from.subject_results.filter(subject_id=subject_id).first()
                annual_avg = final_sr.percentage if final_sr else bucket.get("third_term", 0)
                grade, grade_point, is_pass = (
                    (final_sr.grade, final_sr.grade_point, final_sr.is_pass)
                    if final_sr else (bucket["latest"].grade, bucket["latest"].grade_point, bucket["latest"].is_pass)
                )
            else:
                scores = [v for k, v in bucket.items() if k in ("first_term", "second_term", "third_term")]
                annual_avg = round(sum(scores) / len(scores), 2) if scores else 0
                grade, grade_point, is_pass = (
                    bucket["latest"].grade, bucket["latest"].grade_point, bucket["latest"].is_pass
                )

            subject_result, _ = AnnualSubjectResult.objects.update_or_create(
                annual_result=annual_result, subject_id=subject_id,
                defaults={
                    "first_term": bucket.get("first_term", 0),
                    "second_term": bucket.get("second_term", 0),
                    "third_term": bucket.get("third_term", 0),
                    "annual_average": annual_avg,
                    "grade": grade,
                    "grade_point": grade_point,
                    "is_pass": is_pass,
                },
            )
            subject_result.full_clean()
            subject_result.save()

    @staticmethod
    def _apply_promotion_decision(annual_result, rule):
        failed_subjects = annual_result.subjects.filter(is_pass=False).count()
        meets_average = annual_result.average_percentage >= rule.minimum_average
        within_fail_limit = failed_subjects <= rule.max_failed_subjects

        required_subject_ids = set(rule.required_pass_subjects.values_list("id", flat=True))
        missing_required = set()
        if required_subject_ids:
            passed_required = set(
                annual_result.subjects.filter(
                    subject_id__in=required_subject_ids, is_pass=True
                ).values_list("subject_id", flat=True)
            )
            missing_required = required_subject_ids - passed_required
            within_fail_limit = within_fail_limit and not missing_required

        annual_result.is_promoted = meets_average and within_fail_limit

        if not annual_result.is_promoted:
            reasons = [f"Average {annual_result.average_percentage}% (min {rule.minimum_average}%)"]
            if failed_subjects:
                reasons.append(f"{failed_subjects} subject(s) failed (max allowed {rule.max_failed_subjects})")
            if missing_required:
                names = Subject.objects.filter(id__in=missing_required).values_list("name", flat=True)
                reasons.append(f"Required subject(s) not passed: {', '.join(names)}")
            annual_result.promotion_reason = "; ".join(reasons)

        annual_result.save()