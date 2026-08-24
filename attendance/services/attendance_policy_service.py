from attendance.models import AttendancePolicy


class AttendancePolicyService:
    @staticmethod
    def get_current():
        policy, _ = AttendancePolicy.objects.get_or_create(singleton_key=True)
        return policy
