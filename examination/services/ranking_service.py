from django.db.models import Window, F
from django.db.models.functions import Rank
from ..models import TermResult, SubjectResult


class RankingService:

    @staticmethod
    def rank_class(classroom, term, academic_year):
        results = list(
            TermResult.objects.filter(
                classroom=classroom, term=term, academic_year=academic_year
            ).order_by("-average_percentage")
        )
        total = len(results)
        for position, result in enumerate(results, start=1):
            result.position_in_class = position
            result.total_students = total
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
            ).order_by("-percentage")
        )
        total = len(subject_results)
        if not subject_results:
            return []

        highest = subject_results[0].percentage
        lowest = subject_results[-1].percentage
        average = sum(r.percentage for r in subject_results) / total

        for position, result in enumerate(subject_results, start=1):
            result.position_in_subject = position
            result.total_students = total
            result.highest_score = highest
            result.lowest_score = lowest
            result.class_average = round(average, 2)

        SubjectResult.objects.bulk_update(
            subject_results,
            ["position_in_subject", "total_students", "highest_score", "lowest_score", "class_average"],
        )
        return subject_results