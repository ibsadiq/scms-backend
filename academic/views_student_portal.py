"""
Student Portal ViewSets - Phase 1.6: Optional Student Portal

API endpoints for:
- Student registration (phone + password)
- Student authentication
- Student dashboard
- Student profile management
- View own academic records
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Student
from users.models import CustomUser
from .serializers import (
    StudentRegistrationSerializer,
    StudentLoginSerializer,
    StudentProfileSerializer,
    StudentDashboardSerializer
)


class StudentAuthViewSet(viewsets.ViewSet):
    """
    ViewSet for student registration and authentication.

    Endpoints:
    - POST /api/students/auth/register/ - Register student account
    - POST /api/students/auth/login/ - Login with phone + password
    - POST /api/students/auth/change-password/ - Change password
    """

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        """
        Register a student account using phone number and password.

        Request body:
        {
            "phone_number": "+2348012345678",
            "password": "SecurePassword123",
            "password_confirm": "SecurePassword123",
            "admission_number": "STD/2020/001"  # To verify student identity
        }

        Returns JWT tokens for immediate login.
        """
        serializer = StudentRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Find student by admission number
        try:
            student = Student.objects.get(
                admission_number=data['admission_number'],
                is_active=True
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Student with this admission number not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if student already has an account
        if student.user:
            return Response(
                {'error': 'This student already has an account. Please login instead.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if student is allowed to login
        if not student.can_login:
            return Response(
                {'error': 'Student portal access not enabled for this student. Contact administration.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if phone number is already in use
        if CustomUser.objects.filter(phone_number=data['phone_number']).exists():
            return Response(
                {'error': 'This phone number is already registered'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create user account
        user = CustomUser.objects.create(
            phone_number=data['phone_number'],
            email=f"{student.admission_number.replace('/', '_')}@student.local",  # Generate email
            first_name=student.first_name,
            last_name=student.last_name,
            is_student=True,
            is_active=True
        )
        user.set_password(data['password'])
        user.save()

        # Add to student group
        student_group, _ = Group.objects.get_or_create(name='student')
        user.groups.add(student_group)

        # Link user to student
        student.user = user
        student.phone_number = data['phone_number']
        student.save()

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        # Get current classroom enrollment
        from administration.models import AcademicYear
        from .models import StudentClassEnrollment

        classroom_id = None
        classroom_name = None
        current_year = AcademicYear.objects.filter(active_year=True).first()
        if current_year:
            enrollment = StudentClassEnrollment.objects.filter(
                student=student,
                academic_year=current_year,
                is_active=True
            ).first()
            if enrollment:
                classroom_id = enrollment.classroom.id
                classroom_name = str(enrollment.classroom)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'student': {
                'id': student.id,
                'admission_number': student.admission_number,
                'first_name': student.first_name,
                'middle_name': student.middle_name,
                'last_name': student.last_name,
                'phone_number': student.phone_number,
                'email': user.email if user.email else None,
                'classroom': classroom_id,
                'classroom_name': classroom_name
            }
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def login(self, request):
        """
        Login student using phone number and password.

        Request body:
        {
            "phone_number": "+2348012345678",
            "password": "SecurePassword123"
        }

        Returns JWT tokens.
        """
        serializer = StudentLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Find user by phone number
        try:
            user = CustomUser.objects.get(phone_number=data['phone_number'])
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Invalid phone number or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check password
        if not user.check_password(data['password']):
            return Response(
                {'error': 'Invalid phone number or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check if user is a student
        if not user.is_student:
            return Response(
                {'error': 'This account is not a student account'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if user is active
        if not user.is_active:
            return Response(
                {'error': 'This account has been deactivated'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get student profile
        try:
            student = user.student_profile
        except Student.DoesNotExist:
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if student portal access is enabled
        if not student.can_login:
            return Response(
                {'error': 'Student portal access has been disabled. Contact administration.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        # Get current classroom enrollment
        from administration.models import AcademicYear
        from .models import StudentClassEnrollment

        classroom_id = None
        classroom_name = None
        current_year = AcademicYear.objects.filter(active_year=True).first()
        if current_year:
            enrollment = StudentClassEnrollment.objects.filter(
                student=student,
                academic_year=current_year,
                is_active=True
            ).first()
            if enrollment:
                classroom_id = enrollment.classroom.id
                classroom_name = str(enrollment.classroom)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'student': {
                'id': student.id,
                'admission_number': student.admission_number,
                'first_name': student.first_name,
                'middle_name': student.middle_name,
                'last_name': student.last_name,
                'phone_number': student.phone_number,
                'email': user.email if user.email else None,
                'classroom': classroom_id,
                'classroom_name': classroom_name
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """
        Change student password.

        Request body:
        {
            "current_password": "OldPassword123",
            "new_password": "NewPassword456",
            "new_password_confirm": "NewPassword456"
        }
        """
        user = request.user

        # Check if user is a student
        if not user.is_student:
            return Response(
                {'error': 'Only students can use this endpoint'},
                status=status.HTTP_403_FORBIDDEN
            )

        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        new_password_confirm = request.data.get('new_password_confirm')

        # Validate input
        if not all([current_password, new_password, new_password_confirm]):
            return Response(
                {'error': 'All fields are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check current password
        if not user.check_password(current_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check password confirmation
        if new_password != new_password_confirm:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check password strength (minimum 8 characters)
        if len(new_password) < 8:
            return Response(
                {'error': 'Password must be at least 8 characters long'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update password
        user.set_password(new_password)
        user.save()

        return Response({
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)


class StudentPortalViewSet(viewsets.ViewSet):
    """
    ViewSet for student portal operations.

    Endpoints:
    - GET /api/students/portal/dashboard/ - Get student dashboard
    - GET /api/students/portal/profile/ - Get student profile
    - PUT /api/students/portal/profile/ - Update profile (limited fields)
    """
    permission_classes = [IsAuthenticated]

    def _get_student(self, request):
        """Helper to get student from authenticated user"""
        if not request.user.is_student:
            return None

        try:
            return request.user.student_profile
        except Student.DoesNotExist:
            return None

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Get student dashboard with overview of academic data.

        Returns:
        - Basic info (name, admission number, class, photo)
        - Current term results summary
        - Attendance summary
        - Upcoming assignments
        - Fee balance
        - Recent notifications
        """
        student = self._get_student(request)
        if not student:
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = StudentDashboardSerializer(student, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def profile(self, request):
        """
        Get student profile.

        Returns full student profile information.
        """
        student = self._get_student(request)
        if not student:
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = StudentProfileSerializer(student, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['put', 'patch'])
    def update_profile(self, request):
        """
        Update student profile (limited fields only).

        Students can update:
        - Phone number
        - Stream preference (for SS1)

        Cannot update:
        - Name, admission number, class (admin only)
        """
        student = self._get_student(request)
        if not student:
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Only allow updating specific fields
        allowed_fields = ['phone_number', 'preferred_stream']
        update_data = {k: v for k, v in request.data.items() if k in allowed_fields}

        if not update_data:
            return Response(
                {'error': 'No valid fields provided for update'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update student
        for field, value in update_data.items():
            setattr(student, field, value)

        try:
            student.save()
        except Exception as e:
            return Response(
                {'error': f'Failed to update profile: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = StudentProfileSerializer(student, context={'request': request})
        return Response({
            'message': 'Profile updated successfully',
            'profile': serializer.data
        }, status=status.HTTP_200_OK)
