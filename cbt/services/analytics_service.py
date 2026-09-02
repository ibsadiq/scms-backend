from decimal import Decimal
from statistics import median
from django.db.models import Avg, Count, Max, Min, Q

from academic.models import StudentClassEnrollment
from cbt.models import (
    CBTExam,
    ExamAttempt,
    ExamAttemptStatus,
    AttemptGrade,
    AttemptGradingStatus,
    AttemptQuestion,
    AttemptQuestionGrade,
    StudentAnswer,
    StudentChoiceAnswer,
    QuestionOption,
)


class CBTAnalyticsService:
    """
    Dedicated Service for CBT Post-Examination Performance Analytics.
    """

    @classmethod
    def get_exam_summary(cls, exam: CBTExam) -> dict:
        total_candidates = 0
        if exam.classroom_id and exam.session_id:
            total_candidates = StudentClassEnrollment.objects.filter(
                classroom_id=exam.classroom_id,
                academic_year_id=exam.session.academic_year_id,
                is_active=True,
            ).count()

        attempts_qs = ExamAttempt.objects.filter(cbt_exam=exam)
        started_count = attempts_qs.count()
        submitted_count = attempts_qs.filter(status=ExamAttemptStatus.SUBMITTED).count()

        grades_qs = AttemptGrade.objects.filter(
            attempt__cbt_exam=exam,
            status__in=[AttemptGradingStatus.GRADED, AttemptGradingStatus.POSTED],
            normalized_score__isnull=False,
        )
        graded_count = grades_qs.count()
        posted_count = grades_qs.filter(status=AttemptGradingStatus.POSTED).count()

        if graded_count > 0:
            agg = grades_qs.aggregate(
                avg_score=Avg("normalized_score"),
                avg_pct=Avg("percentage"),
                min_score=Min("normalized_score"),
                max_score=Max("normalized_score"),
            )
            scores_list = list(
                grades_qs.values_list("normalized_score", flat=True)
            )
            scores_floats = [float(s) for s in scores_list]
            med_score = round(median(scores_floats), 2) if scores_floats else None
            avg_score = round(float(agg["avg_score"]), 2) if agg["avg_score"] is not None else None
            avg_pct = round(float(agg["avg_pct"]), 2) if agg["avg_pct"] is not None else None
            min_score = round(float(agg["min_score"]), 2) if agg["min_score"] is not None else None
            max_score = round(float(agg["max_score"]), 2) if agg["max_score"] is not None else None
        else:
            avg_score = None
            avg_pct = None
            med_score = None
            min_score = None
            max_score = None

        completion_rate = (
            round((submitted_count / started_count) * 100, 1)
            if started_count > 0
            else 0.0
        )

        return {
            "total_candidates": total_candidates,
            "started_count": started_count,
            "submitted_count": submitted_count,
            "graded_count": graded_count,
            "posted_count": posted_count,
            "completion_rate": completion_rate,
            "average_score": avg_score,
            "median_score": med_score,
            "highest_score": max_score,
            "lowest_score": min_score,
            "average_percentage": avg_pct,
        }

    @classmethod
    def get_score_distribution(cls, exam: CBTExam) -> list[dict]:
        grades = list(
            AttemptGrade.objects.filter(
                attempt__cbt_exam=exam,
                status__in=[AttemptGradingStatus.GRADED, AttemptGradingStatus.POSTED],
                percentage__isnull=False,
            ).values_list("percentage", flat=True)
        )

        total_graded = len(grades)
        bands = [
            ("0–9%", 0, 9.99),
            ("10–19%", 10, 19.99),
            ("20–29%", 20, 29.99),
            ("30–39%", 30, 39.99),
            ("40–49%", 40, 49.99),
            ("50–59%", 50, 59.99),
            ("60–69%", 60, 69.99),
            ("70–79%", 70, 79.99),
            ("80–89%", 80, 89.99),
            ("90–100%", 90, 100.0),
        ]

        result = []
        for label, low, high in bands:
            cnt = sum(1 for p in grades if low <= float(p) <= high)
            pct = round((cnt / total_graded) * 100, 1) if total_graded > 0 else 0.0
            result.append({
                "band": label,
                "count": cnt,
                "percentage": pct,
            })
        return result

    @classmethod
    def get_question_performance(cls, exam: CBTExam) -> list[dict]:
        exam_questions = (
            exam.exam_questions.all()
            .select_related(
                "question_version__question__topic",
                "question_version__question__subtopic",
            )
            .order_by("order")
        )

        results = []
        for eq in exam_questions:
            q_version = eq.question_version
            q_base = q_version.question if q_version else None
            max_m = float(eq.marks) if eq.marks else 1.0

            attempt_q_grades = AttemptQuestionGrade.objects.filter(
                attempt_question__attempt__cbt_exam=exam,
                attempt_question__exam_question=eq,
            )
            responses_count = attempt_q_grades.count()

            if responses_count > 0:
                agg = attempt_q_grades.aggregate(
                    avg_awarded=Avg("awarded_marks"),
                    full_credit=Count("id", filter=Q(awarded_marks__gte=eq.marks)),
                    zero_credit=Count("id", filter=Q(awarded_marks__lte=0)),
                )
                avg_awarded = float(agg["avg_awarded"]) if agg["avg_awarded"] is not None else 0.0
                avg_pct = round((avg_awarded / max_m) * 100, 1) if max_m > 0 else 0.0
                full_count = agg["full_credit"] or 0
                zero_count = agg["zero_credit"] or 0
                full_rate = round((full_count / responses_count) * 100, 1)
                zero_rate = round((zero_count / responses_count) * 100, 1)
            else:
                avg_awarded = 0.0
                avg_pct = 0.0
                full_count = 0
                zero_count = 0
                full_rate = 0.0
                zero_rate = 0.0

            unanswered_count = StudentAnswer.objects.filter(
                attempt_question__attempt__cbt_exam=exam,
                attempt_question__exam_question=eq,
                is_answered=False,
            ).count()
            unanswered_rate = (
                round((unanswered_count / responses_count) * 100, 1)
                if responses_count > 0
                else 0.0
            )

            q_type = q_version.question_type if q_version else "SINGLE_CHOICE"

            # Distractor distribution for choice questions
            options_dist = []
            if q_type in ["SINGLE_CHOICE", "MULTIPLE_CHOICE", "TRUE_FALSE"] and q_version:
                for opt in q_version.options.all().order_by("order"):
                    selections = StudentChoiceAnswer.objects.filter(
                        student_answer__attempt_question__attempt__cbt_exam=exam,
                        student_answer__attempt_question__exam_question=eq,
                        question_option=opt,
                    ).count()
                    sel_pct = (
                        round((selections / responses_count) * 100, 1)
                        if responses_count > 0
                        else 0.0
                    )
                    options_dist.append({
                        "option_id": opt.id,
                        "text": opt.text,
                        "is_correct": opt.is_correct,
                        "selections_count": selections,
                        "selection_percentage": sel_pct,
                    })

            results.append({
                "order": eq.order,
                "question_text": q_version.text if q_version else "",
                "question_type": q_type,
                "difficulty": q_base.difficulty if q_base else "MEDIUM",
                "topic_name": q_base.topic.name if (q_base and q_base.topic) else None,
                "max_marks": max_m,
                "responses_count": responses_count,
                "average_awarded_marks": round(avg_awarded, 2),
                "average_percentage": avg_pct,
                "facility_index": round(avg_pct / 100, 2),
                "full_credit_count": full_count,
                "full_credit_rate": full_rate,
                "zero_credit_count": zero_count,
                "zero_credit_rate": zero_rate,
                "unanswered_count": unanswered_count,
                "unanswered_rate": unanswered_rate,
                "options_distribution": options_dist,
            })

        return results

    @classmethod
    def get_type_and_difficulty_performance(cls, exam: CBTExam) -> dict:
        q_perf = cls.get_question_performance(exam)

        type_map: dict[str, list[float]] = {}
        diff_map: dict[str, list[float]] = {}
        topic_map: dict[str, list[float]] = {}

        for item in q_perf:
            q_type = item["question_type"]
            diff = item["difficulty"]
            topic = item["topic_name"] or "General / Uncategorized"
            pct = item["average_percentage"]

            type_map.setdefault(q_type, []).append(pct)
            diff_map.setdefault(diff, []).append(pct)
            topic_map.setdefault(topic, []).append(pct)

        type_results = []
        for t, pcts in type_map.items():
            type_results.append({
                "question_type": t,
                "question_count": len(pcts),
                "average_percentage": round(sum(pcts) / len(pcts), 1) if pcts else 0.0,
            })

        diff_results = []
        for d, pcts in diff_map.items():
            diff_results.append({
                "difficulty": d,
                "question_count": len(pcts),
                "average_percentage": round(sum(pcts) / len(pcts), 1) if pcts else 0.0,
            })

        topic_results = []
        for top, pcts in topic_map.items():
            topic_results.append({
                "topic_name": top,
                "question_count": len(pcts),
                "average_percentage": round(sum(pcts) / len(pcts), 1) if pcts else 0.0,
            })

        return {
            "by_type": type_results,
            "by_difficulty": diff_results,
            "by_topic": topic_results,
        }

    @classmethod
    def get_candidate_performance(cls, exam: CBTExam) -> list[dict]:
        grades = (
            AttemptGrade.objects.filter(attempt__cbt_exam=exam)
            .select_related("attempt__student")
            .order_by("attempt__student__first_name", "attempt__student__last_name")
        )

        results = []
        for g in grades:
            student = g.attempt.student
            results.append({
                "attempt_id": g.attempt_id,
                "public_id": str(g.attempt.public_id),
                "student_name": f"{student.first_name} {student.last_name}".strip(),
                "admission_number": student.admission_number,
                "status": g.status,
                "raw_score": g.raw_score,
                "total_marks": g.total_marks,
                "percentage": g.percentage,
                "normalized_score": g.normalized_score,
                "graded_at": g.graded_at,
                "posted_at": g.posted_at,
            })
        return results
