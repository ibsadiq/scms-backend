"""
Notification ViewSets - Phase 1.5: Automated Notifications System

API endpoints for:
- Listing user notifications
- Marking notifications as read
- Creating notifications (admin only)
- Managing notification preferences
- Managing notification templates (admin only)
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .models import Notification, NotificationPreference, NotificationTemplate, DirectMessage
from .serializers import (
    NotificationSerializer,
    NotificationCreateSerializer,
    BulkNotificationSerializer,
    NotificationPreferenceSerializer,
    NotificationTemplateSerializer,
    DirectMessageSerializer,
    DirectMessageCreateSerializer
)
from .services import NotificationService
from users.models import CustomUser
from academic.models import Student


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user notifications.

    Endpoints:
    - GET /api/notifications/ - List user's notifications
    - GET /api/notifications/{id}/ - Get specific notification
    - POST /api/notifications/ - Create notification (admin only)
    - POST /api/notifications/bulk/ - Send bulk notifications (admin only)
    - POST /api/notifications/{id}/mark-read/ - Mark as read
    - POST /api/notifications/mark-all-read/ - Mark all as read
    - GET /api/notifications/unread/ - Get unread count
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get notifications for current user"""
        user = self.request.user

        # Admin can see all notifications if admin_view param is set
        if user.is_staff and self.request.query_params.get('admin_view') == 'true':
            queryset = Notification.objects.all()
        else:
            # Regular users see only their own notifications
            queryset = Notification.objects.filter(recipient=user)

        # Filter by read status
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')

        # Filter by notification type
        notification_type = self.request.query_params.get('notification_type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)

        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        # Exclude expired notifications by default
        include_expired = self.request.query_params.get('include_expired')
        if include_expired != 'true':
            from django.utils import timezone
            queryset = queryset.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
            )

        return queryset.select_related(
            'recipient',
            'related_student'
        ).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """
        Create a notification (admin only).

        Request body:
        {
            "recipient_id": 123,
            "notification_type": "general",
            "title": "Test Notification",
            "message": "This is a test",
            "priority": "normal",
            "send_email": true,
            "send_sms": false
        }
        """
        if not request.user.is_staff:
            return Response(
                {'error': 'Only admins can create notifications'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = NotificationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Get recipient
        try:
            recipient = CustomUser.objects.get(id=data['recipient_id'])
        except CustomUser.DoesNotExist:
            return Response(
                {'error': f"User {data['recipient_id']} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get related student if provided
        related_student = None
        if data.get('related_student_id'):
            try:
                related_student = Student.objects.get(id=data['related_student_id'])
            except Student.DoesNotExist:
                return Response(
                    {'error': f"Student {data['related_student_id']} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Create notification
        service = NotificationService()
        notification = service.create_notification(
            recipient=recipient,
            notification_type=data['notification_type'],
            title=data['title'],
            message=data['message'],
            priority=data.get('priority', 'normal'),
            related_student=related_student,
            send_email=data.get('send_email', True),
            send_sms=data.get('send_sms', False),
            expires_at=data.get('expires_at')
        )

        response_serializer = self.get_serializer(notification)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def bulk(self, request):
        """
        Send bulk notifications to multiple users (admin only).

        Request body:
        {
            "recipient_ids": [123, 124, 125],
            "notification_type": "general",
            "title": "Important Announcement",
            "message": "School closes early tomorrow",
            "priority": "high",
            "send_email": true,
            "send_sms": false
        }
        """
        serializer = BulkNotificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Get recipients
        recipients = CustomUser.objects.filter(id__in=data['recipient_ids'])
        if not recipients.exists():
            return Response(
                {'error': 'No valid recipients found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Send bulk notifications
        service = NotificationService()
        results = service.send_bulk_notifications(
            recipients=list(recipients),
            notification_type=data['notification_type'],
            title=data['title'],
            message=data['message'],
            priority=data.get('priority', 'normal'),
            send_email=data.get('send_email', True),
            send_sms=data.get('send_sms', False)
        )

        return Response({
            'message': f"Bulk notifications sent to {results['created']} users",
            **results
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """
        Mark a notification as read.

        URL: /api/notifications/{id}/mark-read/
        """
        notification = self.get_object()

        # Users can only mark their own notifications as read
        if notification.recipient != request.user and not request.user.is_staff:
            return Response(
                {'error': 'You can only mark your own notifications as read'},
                status=status.HTTP_403_FORBIDDEN
            )

        notification.mark_as_read()

        return Response({
            'message': 'Notification marked as read',
            'notification_id': notification.id,
            'read_at': notification.read_at
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """
        Mark all user's notifications as read.

        URL: /api/notifications/mark-all-read/
        """
        from django.utils import timezone

        updated_count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )

        return Response({
            'message': f'Marked {updated_count} notifications as read',
            'count': updated_count
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def unread(self, request):
        """
        Get unread notification count.

        URL: /api/notifications/unread/
        """
        unread_count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

        return Response({
            'unread_count': unread_count
        }, status=status.HTTP_200_OK)


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for notification preferences.

    Endpoints:
    - GET /api/notification-preferences/ - Get user's preferences
    - PUT /api/notification-preferences/{id}/ - Update preferences
    """
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get preferences for current user"""
        user = self.request.user

        # Admin can see all preferences
        if user.is_staff and self.request.query_params.get('admin_view') == 'true':
            return NotificationPreference.objects.all()

        # Regular users see only their own preferences
        return NotificationPreference.objects.filter(user=user)

    def list(self, request, *args, **kwargs):
        """
        Get or create user's notification preferences.

        Returns the user's preferences, creating default ones if they don't exist.
        """
        prefs, created = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(prefs)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        """Update notification preferences"""
        instance = self.get_object()

        # Users can only update their own preferences
        if instance.user != request.user and not request.user.is_staff:
            return Response(
                {'error': 'You can only update your own preferences'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().update(request, *args, **kwargs)


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for notification templates (admin only).

    Endpoints:
    - GET /api/notification-templates/ - List templates
    - GET /api/notification-templates/{id}/ - Get template
    - POST /api/notification-templates/ - Create template
    - PUT /api/notification-templates/{id}/ - Update template
    - DELETE /api/notification-templates/{id}/ - Delete template
    """
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        """Get all templates, optionally filtered"""
        queryset = NotificationTemplate.objects.all()

        # Filter by template type
        template_type = self.request.query_params.get('template_type')
        if template_type:
            queryset = queryset.filter(template_type=template_type)

        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset.order_by('template_type')

class UnroutedLegacyDirectMessageViewSet(viewsets.ModelViewSet):
    """
    Legacy implementation retained temporarily for Phase 4B removal.

    This class is deliberately not routed. The secured immutable API lives in
    notifications.views_messages.DirectMessageViewSet.
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return DirectMessageCreateSerializer
        return DirectMessageSerializer

    def get_queryset(self):
        user = self.request.user
        return DirectMessage.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).select_related('sender', 'recipient', 'student').order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(sender=request.user)
        read_serializer = DirectMessageSerializer(message, context=self.get_serializer_context())
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        message = self.get_object()
        if message.recipient != request.user:
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        
        message.is_read = True
        message.save(update_fields=['is_read'])
        return Response({'status': 'Message marked as read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = DirectMessage.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})

    @action(detail=False, methods=['get'])
    def classroom_parents(self, request):
        """
        Get active students and their parents for a classroom (or all classrooms).
        Returns list of contacts for initiating conversations.
        """
        from academic.models import Student
        from users.models import CustomUser

        classroom_id = request.query_params.get('classroom_id')
        queryset = Student.objects.filter(is_active=True).select_related(
            'parent_guardian',
            'parent_guardian__user',
            'classroom',
            'classroom__name'
        )
        if classroom_id:
            queryset = queryset.filter(classroom_id=classroom_id)

        results = []
        for s in queryset:
            p = s.parent_guardian
            if not p:
                continue

            p_user = getattr(p, 'user', None) or (
                CustomUser.objects.filter(email=p.email, is_parent=True).first()
                if getattr(p, 'email', None) else None
            )

            if not p_user:
                continue

            c_name = str(s.classroom.name) if (s.classroom and hasattr(s.classroom, 'name') and s.classroom.name) else str(s.classroom or 'N/A')
            p_full_name = f"{p.first_name or ''} {p.last_name or ''}".strip() or p_user.get_full_name() or p.email or "Parent"

            results.append({
                "student_id": s.id,
                "student_name": s.full_name,
                "admission_number": s.admission_number,
                "classroom_id": s.classroom_id,
                "classroom_name": c_name,
                "parent_id": p.id,
                "parent_user_id": p_user.id,
                "parent_name": p_full_name,
                "parent_email": p.email or p_user.email,
                "phone_number": p.phone_number or getattr(p_user, 'phone_number', ''),
            })

        return Response(results)

    @action(detail=False, methods=['get'])
    def school_admins(self, request):
        """
        Return school administrator users for parents/teachers to message.
        """
        from users.models import CustomUser
        admins = CustomUser.objects.filter(
            Q(is_admin=True) | Q(is_superuser=True) | Q(active_role='admin') | Q(is_staff=True),
            is_active=True
        ).distinct()

        results = []
        for admin in admins:
            name = admin.get_full_name()
            results.append({
                "id": admin.id,
                "name": name or "School Administrator",
                "first_name": admin.first_name or "School",
                "last_name": admin.last_name or "Administrator",
                "email": admin.email,
                "role_label": "School Administrator",
            })
        return Response(results)
