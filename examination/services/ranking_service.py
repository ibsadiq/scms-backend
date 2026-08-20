from django.db.models import Window, F
from django.db.models.functions import Rank
from ..models import TermResult, SubjectResult, AnnualResult, AnnualSubjectResult


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

    @staticmethod
    def rank_annual_class(classroom, academic_year):
        results = list(
            AnnualResult.objects.filter(
                classroom=classroom, academic_year=academic_year
            ).order_by("-average_percentage")
        )
        total = len(results)
        # Handle ties: identical averages should get same rank
        current_rank = 0
        previous_avg = None
        for position, result in enumerate(results, start=1):
            if result.average_percentage == previous_avg:
                result.position_in_class = current_rank
            else:
                current_rank = position
                result.position_in_class = current_rank
                previous_avg = result.average_percentage
            result.total_students = total
        AnnualResult.objects.bulk_update(results, ["position_in_class", "total_students"])
        return results

    @staticmethod
    def rank_annual_subject(classroom, academic_year, subject):
        subject_results = list(
            AnnualSubjectResult.objects.filter(
                annual_result__classroom=classroom,
                annual_result__academic_year=academic_year,
                subject=subject,
            ).order_by("-annual_average")
        )
        total = len(subject_results)
        if not subject_results:
            return []

        # Handle ties
        current_rank = 0
        previous_avg = None
        for position, result in enumerate(subject_results, start=1):
            if result.annual_average == previous_avg:
                result.position_in_subject = current_rank
            else:
                current_rank = position
                result.position_in_subject = current_rank
                previous_avg = result.annual_average
        
        # Note: Ensure AnnualSubjectResult has position_in_subject field
        AnnualSubjectResult.objects.bulk_update(subject_results, ["position_in_subject"])
        return subject_results