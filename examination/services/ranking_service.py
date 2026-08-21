from django.db.models import Window, F
from django.db.models.functions import Rank
from ..models import TermResult, SubjectResult, AnnualResult, AnnualSubjectResult


class RankingService:
    @staticmethod
    def _apply_ranking(results, value_attr, rank_attr, total_students=None):
        current_rank = 0
        previous_val = None
        for position, result in enumerate(results, start=1):
            val = getattr(result, value_attr)
            if val == previous_val:
                setattr(result, rank_attr, current_rank)
            else:
                current_rank = position
                setattr(result, rank_attr, current_rank)
                previous_val = val
            
            if total_students is not None:
                result.total_students = total_students

    @staticmethod
    def rank_class(classroom, term, academic_year):
        results = list(
            TermResult.objects.filter(
                classroom=classroom, term=term, academic_year=academic_year
            ).order_by("-average_percentage", "student__id")
        )
        total = len(results)
        RankingService._apply_ranking(results, "average_percentage", "position_in_class", total)
        TermResult.objects.bulk_update(results, ["position_in_class", "total_students"])
        return results

    @staticmethod
    def rank_subject(classroom, term, academic_year, subject):
        subject_results = list(
            SubjectResult.objects.filter(
                term_result__classroom=classroom,
                term_result__term=term,
                term_result__academic_year=academic_year,
                subject=subject,
            ).order_by("-percentage", "term_result__student__id")
        )
        total = len(subject_results)
        if not subject_results:
            return []

        highest = subject_results[0].percentage
        lowest = subject_results[-1].percentage
        average = sum(r.percentage for r in subject_results) / total

        RankingService._apply_ranking(subject_results, "percentage", "position_in_subject", total)

        for result in subject_results:
            result.highest_score = highest
            result.lowest_score = lowest
            result.class_average = round(average, 2)

        SubjectResult.objects.bulk_update(
            subject_results,
            ["position_in_subject", "total_students", "highest_score", "lowest_score", "class_average"],
        )
        return subject_results

    @staticmethod
    def rank_annual_class(classroom, academic_year):
        results = list(
            AnnualResult.objects.filter(
                classroom=classroom, academic_year=academic_year
            ).order_by("-average_percentage", "student__id")
        )
        total = len(results)
        RankingService._apply_ranking(results, "average_percentage", "position_in_class", total)
        AnnualResult.objects.bulk_update(results, ["position_in_class", "total_students"])
        return results

    @staticmethod
    def rank_annual_subject(classroom, academic_year, subject):
        subject_results = list(
            AnnualSubjectResult.objects.filter(
                annual_result__classroom=classroom,
                annual_result__academic_year=academic_year,
                subject=subject,
            ).order_by("-annual_average", "annual_result__student__id")
        )
        total = len(subject_results)
        if not subject_results:
            return []

        RankingService._apply_ranking(subject_results, "annual_average", "position_in_subject")
        AnnualSubjectResult.objects.bulk_update(subject_results, ["position_in_subject"])
        return subject_results