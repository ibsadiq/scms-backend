import openpyxl
from django.db.models import Q
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import FilterSet, CharFilter, DjangoFilterBackend
from rest_framework import viewsets, views
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from academic.models import Teacher, Subject, Parent
from .models import CustomUser as User, Accountant, UserInvitation
from .serializers import (
    UserSerializer,
    UserSerializerWithToken,
    AccountantSerializer,
    TeacherSerializer,
    ParentSerializer,
    UserInvitationSerializer,
    AcceptInvitationSerializer,
)


# Custom Token View
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user_data = UserSerializerWithToken(self.user).data
        data.update(user_data)
        return data


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getUserProfile(request):
    user = request.user
    serializer = UserSerializer(user, many=False)
    return Response(serializer.data)


class UserFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")

    class Meta:
        model = User
        fields = [
            "first_name",
            "middle_name",
            "last_name",
        ]


class TeacherFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")

    class Meta:
        model = Teacher
        fields = [
            "first_name",
            "middle_name",
            "last_name",
        ]


class ParentFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")

    class Meta:
        model = Parent
        fields = [
            "first_name",
            "middle_name",
            "last_name",
        ]


class UserListView(generics.ListCreateAPIView):
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = UserFilter

    def get_queryset(self):
        return User.objects.filter(is_parent=False)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(self.get_serializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            raise Http404

    def get(self, request, pk, format=None):
        user = self.get_object(pk)
        print(user)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        user = self.get_object(pk)
        serializer = UserSerializer(user, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        user = self.get_object(pk)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccountantListView(APIView):
    """
    API View for handling single and listing accountants.
    """

    def get(self, request, format=None):
        accountants = Accountant.objects.all()
        serializer = AccountantSerializer(accountants, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, format=None):
        serializer = AccountantSerializer(data=request.data)
        if serializer.is_valid():
            accountant = serializer.save()
            return Response(
                AccountantSerializer(accountant).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AccountantDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Accountant, pk=pk)

    def get(self, request, pk, format=None):
        accountant = self.get_object(pk)
        serializer = AccountantSerializer(accountant)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        accountant = self.get_object(pk)
        serializer = AccountantSerializer(accountant, data=request.data)
        if serializer.is_valid():
            updated_accountant = serializer.save()

            # Update the linked CustomUser when accountant details change
            email = updated_accountant.email
            first_name = updated_accountant.first_name
            last_name = updated_accountant.last_name

            try:
                user = User.objects.get(email=accountant.email)
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.save()
            except User.DoesNotExist:
                pass  # If user does not exist, no update is needed

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        accountant = self.get_object(pk)
        accountant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ParentListView(generics.ListCreateAPIView):
    queryset = Parent.objects.all()
    serializer_class = ParentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ParentFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent = serializer.save()
        return Response(
            self.get_serializer(parent).data, status=status.HTTP_201_CREATED
        )


class ParentDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Parent, pk=pk)

    def get(self, request, pk, format=None):
        parent = self.get_object(pk)
        serializer = ParentSerializer(parent)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        parent = self.get_object(pk)
        serializer = ParentSerializer(parent, data=request.data)
        if serializer.is_valid():
            updated_parent = serializer.save()

            # Update the linked CustomUser when parent details change
            email = updated_parent.email
            first_name = updated_parent.first_name
            last_name = updated_parent.last_name

            try:
                user = User.objects.get(email=parent.email)
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.save()
            except User.DoesNotExist:
                pass  # If user does not exist, no update is needed

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        parent = self.get_object(pk)
        parent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Teacher Views
class TeacherListView(generics.ListCreateAPIView):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = TeacherFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        teacher = serializer.save()
        return Response(
            self.get_serializer(teacher).data, status=status.HTTP_201_CREATED
        )


class TeacherDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Teacher, pk=pk)

    def get(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher, data=request.data)
        if serializer.is_valid():
            updated_teacher = serializer.save()

            # Update the linked CustomUser when teacher details change
            email = updated_teacher.email
            first_name = updated_teacher.first_name
            last_name = updated_teacher.last_name

            try:
                user = User.objects.get(email=teacher.email)
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.save()
            except User.DoesNotExist:
                pass  # If user does not exist, no update is needed

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        teacher = self.get_object(pk)
        teacher.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkUploadTeachersView(APIView):
    """
    API View to handle bulk uploading of teachers from an Excel file.
    """

    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Load the Excel file
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active  # Assuming data is in the first sheet

            # Expected columns in the Excel file
            columns = [
                "first_name",
                "middle_name",
                "last_name",
                "phone_number",
                "employment_id",
                "short_name",
                "subject_specialization",  # Should match subject names as a comma-separated string
                "address",
                "gender",
                "date_of_birth",
                "salary",
            ]

            teachers_to_create = []
            not_created = []

            for i, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                # Map row data to the expected columns
                teacher_data = dict(zip(columns, row))

                try:
                    # Generate email based on first_name and last_name
                    generated_email = (
                        f"{teacher_data['first_name'].lower()}."
                        f"{teacher_data['last_name'].lower()}@hayatul.com"
                    )
                    teacher_data["email"] = generated_email

                    # Check for duplicate email
                    if Teacher.objects.filter(user__email=generated_email).exists():
                        raise ValueError(f"Email '{generated_email}' already exists.")

                    # Check for duplicate phone number
                    if Teacher.objects.filter(
                        user__phone_number=teacher_data["phone_number"]
                    ).exists():
                        raise ValueError(
                            f"Phone number '{teacher_data['phone_number']}' already exists."
                        )

                    # Validate subject specialization
                    subjects = []
                    subject_names = (
                        teacher_data["subject_specialization"].lower().split(",")
                        if teacher_data["subject_specialization"].lower()
                        else []
                    )
                    for subject_name in subject_names:
                        try:
                            subject = Subject.objects.get(name=subject_name.strip())
                            subjects.append(subject)
                        except Subject.DoesNotExist:
                            raise ValueError(
                                f"Subject '{subject_name.strip()}' does not exist."
                            )

                    # Create Teacher object
                    teacher = Teacher(
                        first_name=teacher_data["first_name"].lower(),
                        middle_name=teacher_data["middle_name"].lower(),
                        last_name=teacher_data["last_name"].lower(),
                        email=generated_email,
                        short_name=teacher_data["short_name"].upper(),
                        phone_number=teacher_data["phone_number"],
                        empId=teacher_data["employment_id"],
                        address=teacher_data["address"].lower(),
                        gender=teacher_data["gender"],
                        date_of_birth=teacher_data["date_of_birth"],
                        salary=teacher_data["salary"],
                    )
                    teacher.save()

                    # Assign subjects
                    if subjects:
                        teacher.subject_specialization.set(subjects)

                    # Create corresponding user
                    if not teacher.username:
                        teacher.username = f"{teacher.first_name.lower()}{teacher.last_name.lower()}{get_random_string(4)}"
                    teacher.save()

                    user, created = User.objects.get_or_create(
                        email=teacher.email,
                        defaults={
                            "first_name": teacher.first_name,
                            "last_name": teacher.last_name,
                            "is_teacher": True,
                        },
                    )
                    if created:
                        default_password = f"Complex.{teacher.empId[-4:] if teacher.empId and len(teacher.empId) >= 4 else '0000'}"
                        user.set_password(default_password)
                        user.save()

                        # Add to "teacher" group
                        group, _ = Group.objects.get_or_create(name="teacher")
                        user.groups.add(group)

                    teachers_to_create.append(teacher)

                except Exception as e:
                    # Add row data and error message to the not_created list
                    teacher_data["error"] = str(e)
                    not_created.append(teacher_data)

            return Response(
                {
                    "message": f"{len(teachers_to_create)} teachers successfully uploaded.",
                    "not_created": not_created,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# Teacher Dashboard View
class TeacherDashboardView(APIView):
    """
    Teacher Dashboard API
    GET /api/users/teacher/dashboard/
    Returns: stats, today's schedule, my classes, activities, assessments
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from schedule.models import Period
        from examination.models import ExaminationListHandler
        from academic.models import AllocatedSubject

        try:
            # Get the teacher object for the logged-in user
            teacher = Teacher.objects.get(user=request.user)
        except Teacher.DoesNotExist:
            return Response(
                {"error": "Teacher profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        today = timezone.now().date()
        current_time = timezone.now().time()

        # Get teacher's allocated subjects (classes they teach)
        allocated_subjects = AllocatedSubject.objects.filter(
            teacher_name=teacher
        ).select_related('class_room', 'subject')

        # ===== BASIC STATS =====
        total_classes = allocated_subjects.count()
        total_students = sum(
            alloc.class_room.capacity if alloc.class_room else 0
            for alloc in allocated_subjects
        )

        # Today's periods
        todays_periods = Period.objects.filter(
            teacher=teacher,
            day_of_week=today.strftime('%A'),
            is_active=True
        ).select_related('classroom', 'subject').order_by('start_time')

        # Pending grades (exams without full marks submitted)
        from examination.models import MarksManagement
        teacher_exams = ExaminationListHandler.objects.filter(
            created_by=teacher
        ).values_list('id', flat=True)

        pending_grades = 0
        for exam_id in teacher_exams:
            exam = ExaminationListHandler.objects.get(id=exam_id)
            expected_marks = sum(
                classroom.capacity for classroom in exam.classrooms.all()
            )
            submitted_marks = MarksManagement.objects.filter(exam_name_id=exam_id).count()
            if submitted_marks < expected_marks:
                pending_grades += (expected_marks - submitted_marks)

        stats = {
            "totalClasses": total_classes,
            "totalStudents": total_students,
            "todaysClasses": todays_periods.count(),
            "pendingGrades": pending_grades
        }

        # ===== TODAY'S SCHEDULE =====
        todays_schedule = []
        for period in todays_periods:
            period_status = 'upcoming'
            if period.end_time < current_time:
                period_status = 'completed'
            elif period.start_time <= current_time <= period.end_time:
                period_status = 'ongoing'

            todays_schedule.append({
                "id": period.id,
                "subject_name": period.subject.subject.name if period.subject and period.subject.subject else 'N/A',
                "classroom_name": period.classroom.class_name if period.classroom else 'N/A',
                "start_time": period.start_time.strftime('%H:%M'),
                "end_time": period.end_time.strftime('%H:%M'),
                "status": period_status
            })

        # ===== MY CLASSES =====
        my_classes = []
        for alloc in allocated_subjects[:5]:  # Top 5 classes
            my_classes.append({
                "id": alloc.id,
                "name": alloc.class_room.class_name if alloc.class_room else 'N/A',
                "subject": alloc.subject.name if alloc.subject else 'N/A',
                "student_count": alloc.class_room.capacity if alloc.class_room else 0
            })

        # ===== RECENT ACTIVITIES =====
        recent_activities = []

        # Recent grade submissions
        recent_marks = MarksManagement.objects.filter(
            created_by=teacher
        ).select_related('exam_name', 'student').order_by('-date_time')[:3]

        for mark in recent_marks:
            recent_activities.append({
                "id": f"grade_{mark.id}",
                "type": "grade",
                "icon": "lucide:award",
                "title": "Grades Submitted",
                "description": f"{mark.exam_name.name if mark.exam_name else 'Assessment'} - {mark.student.first_name if mark.student else 'Student'}",
                "time": f"{(timezone.now() - mark.date_time).days} days ago"
            })

        # ===== UPCOMING ASSESSMENTS =====
        upcoming_assessments = []
        future_exams = ExaminationListHandler.objects.filter(
            created_by=teacher,
            start_date__gte=today
        ).order_by('start_date')[:3]

        for exam in future_exams:
            upcoming_assessments.append({
                "id": exam.id,
                "name": exam.name,
                "type": "Exam",
                "subject": "Multiple" if exam.classrooms.count() > 1 else "Single Class",
                "classroom": f"{exam.classrooms.count()} classes",
                "date": exam.start_date.strftime('%Y-%m-%d')
            })

        return Response({
            "stats": stats,
            "todaysSchedule": todays_schedule,
            "myClasses": my_classes,
            "recentActivities": recent_activities,
            "upcomingAssessments": upcoming_assessments
        })


# Parent Dashboard View
class ParentDashboardView(APIView):
    """
    Parent Dashboard API
    GET /api/users/parent/dashboard/
    Returns: children data, performance, attendance, fees, events, activities
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from finance.models import StudentFeeAssignment, Receipt
        from attendance.models import StudentAttendance
        from administration.models import SchoolEvent
        from examination.models import Result

        try:
            # Get the parent object for the logged-in user
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return Response(
                {"error": "Parent profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        today = timezone.now().date()
        first_day_of_month = today.replace(day=1)

        # Get all children of this parent
        children_data = []
        for student in parent.students.all():
            # Performance data
            latest_result = Result.objects.filter(student=student).order_by('-created_on').first()
            performance = {
                "average_grade": latest_result.overall_grade if latest_result and hasattr(latest_result, 'overall_grade') else 'N/A',
                "position": latest_result.position if latest_result and hasattr(latest_result, 'position') else 'N/A'
            }

            # Attendance data (this month)
            attendance_records = StudentAttendance.objects.filter(
                student=student,
                date__gte=first_day_of_month,
                date__lte=today
            )

            total_days = attendance_records.count()
            present_count = attendance_records.filter(
                Q(status__name__iexact='PRESENT') | Q(status__name__iexact='present')
            ).count()
            absent_count = attendance_records.filter(
                Q(status__name__iexact='ABSENT') | Q(status__name__iexact='absent')
            ).count()
            late_count = attendance_records.filter(
                Q(status__name__iexact='LATE') | Q(status__name__iexact='late')
            ).count()

            attendance_rate = round((present_count / total_days * 100) if total_days > 0 else 0, 0)

            # Fee data
            fee_assignments = StudentFeeAssignment.objects.filter(student=student)
            total_fee = sum(assignment.total_amount for assignment in fee_assignments)

            receipts = Receipt.objects.filter(student=student)
            total_paid = sum(receipt.amount_paid for receipt in receipts)
            balance = total_fee - total_paid

            fee_status = 'Paid' if balance == 0 else 'Partial' if total_paid > 0 else 'Unpaid'

            children_data.append({
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "class_name": student.class_level.name if student.class_level else 'N/A',
                "status": "active" if student.is_active else "inactive",
                "performance": performance,
                "attendance": {
                    "rate": int(attendance_rate),
                    "present": present_count,
                    "absent": absent_count,
                    "late": late_count
                },
                "fees": {
                    "total": float(total_fee),
                    "paid": float(total_paid),
                    "balance": float(balance),
                    "status": fee_status
                }
            })

        # ===== UPCOMING EVENTS =====
        upcoming_events = []
        future_events = SchoolEvent.objects.filter(
            start_date__gte=today
        ).order_by('start_date')[:3]

        for event in future_events:
            upcoming_events.append({
                "id": event.id,
                "name": event.name,
                "date": event.start_date.strftime('%B %d, %Y')
            })

        # ===== RECENT ACTIVITIES =====
        recent_activities = []

        for student in parent.students.all()[:2]:  # Latest 2 children
            # Recent grades
            recent_results = Result.objects.filter(student=student).order_by('-created_on')[:1]
            for result in recent_results:
                recent_activities.append({
                    "id": f"grade_{result.id}",
                    "type": "grade",
                    "icon": "lucide:award",
                    "child_name": f"{student.first_name} {student.last_name}",
                    "description": f"Result published: {result.overall_grade if hasattr(result, 'overall_grade') else 'Grade available'}",
                    "time": f"{(timezone.now().date() - result.created_on).days} days ago" if hasattr(result, 'created_on') else "Recently"
                })

            # Recent payments
            recent_receipts = Receipt.objects.filter(student=student).order_by('-paid_on')[:1]
            for receipt in recent_receipts:
                recent_activities.append({
                    "id": f"payment_{receipt.id}",
                    "type": "payment",
                    "icon": "lucide:wallet",
                    "child_name": f"{student.first_name} {student.last_name}",
                    "description": f"Fee payment of ₦{receipt.amount_paid:,.0f} received",
                    "time": f"{(timezone.now().date() - receipt.paid_on).days} days ago"
                })

        return Response({
            "children": children_data,
            "upcomingEvents": upcoming_events,
            "recentActivities": recent_activities
        })


# Invitation Views
class UserInvitationListCreateView(generics.ListCreateAPIView):
    """
    API View for listing and creating user invitations
    GET /api/users/invitations/ - List all invitations
    GET /api/users/invitations/?role=teacher - Filter by role
    POST /api/users/invitations/ - Create a new invitation
    """
    queryset = UserInvitation.objects.all()
    serializer_class = UserInvitationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter invitations by role if provided"""
        queryset = UserInvitation.objects.all()
        role = self.request.query_params.get('role', None)
        if role:
            queryset = queryset.filter(role=role)
        return queryset

    def perform_create(self, serializer):
        """Automatically set the invited_by field to current user"""
        serializer.save(invited_by=self.request.user)


class UserInvitationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API View for retrieving, updating, or deleting a specific invitation
    GET /api/users/invitations/{id}/ - Get invitation details
    PUT /api/users/invitations/{id}/ - Update invitation
    DELETE /api/users/invitations/{id}/ - Delete invitation
    """
    queryset = UserInvitation.objects.all()
    serializer_class = UserInvitationSerializer
    permission_classes = [IsAuthenticated]


class ValidateInvitationView(APIView):
    """
    API View to validate an invitation token
    GET /api/users/invitations/validate/{token}/
    Returns invitation details if valid
    """
    permission_classes = []  # Public endpoint

    def get(self, request, token):
        try:
            invitation = UserInvitation.objects.get(token=token)

            if not invitation.is_valid():
                return Response(
                    {
                        "error": "This invitation has expired or has already been used.",
                        "status": invitation.status,
                        "is_expired": invitation.is_expired
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = UserInvitationSerializer(invitation)
            return Response(serializer.data)

        except UserInvitation.DoesNotExist:
            return Response(
                {"error": "Invalid invitation token."},
                status=status.HTTP_404_NOT_FOUND
            )


class AcceptInvitationView(APIView):
    """
    API View to accept an invitation and create user account
    POST /api/users/invitations/accept/
    Body: { token, password, password_confirm }
    """
    permission_classes = []  # Public endpoint

    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            # Generate tokens for the new user
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "Account created successfully",
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token)
                }
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendInvitationView(APIView):
    """
    API View to resend an invitation email
    POST /api/users/invitations/{id}/resend/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            invitation = UserInvitation.objects.get(pk=pk)

            if invitation.status != 'pending':
                return Response(
                    {"error": "Can only resend pending invitations."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Send invitation email based on role
            try:
                from core.email_utils import (
                    send_teacher_invitation,
                    send_parent_invitation,
                    send_accountant_invitation
                )

                if invitation.role == 'teacher':
                    send_teacher_invitation(invitation)
                elif invitation.role == 'parent':
                    send_parent_invitation(invitation)
                elif invitation.role == 'accountant':
                    send_accountant_invitation(invitation)
                else:
                    return Response(
                        {"error": f"Unknown invitation role: {invitation.role}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            except Exception as e:
                return Response(
                    {"error": f"Failed to send invitation email: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response({
                "message": "Invitation email resent successfully",
                "invitation": UserInvitationSerializer(invitation).data
            })

        except UserInvitation.DoesNotExist:
            return Response(
                {"error": "Invitation not found."},
                status=status.HTTP_404_NOT_FOUND
            )
