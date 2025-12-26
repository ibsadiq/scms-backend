# Announcement & Messaging System Documentation

## Overview

The system uses a **Notification System** for announcements and messaging. It supports:
- ✅ In-app notifications
- ✅ Email delivery
- ✅ SMS delivery (with integration support)
- ✅ User preferences for delivery channels
- ✅ Template-based messaging
- ✅ Bulk notifications (announcements)

---

## How It Works

### 1. Notification Types

The system supports these notification types:

| Type | Use Case | Example |
|------|----------|---------|
| `general` | School-wide announcements | "School closes early tomorrow" |
| `attendance` | Attendance alerts | "Your child was absent today" |
| `fee` | Fee reminders | "Term fee payment due" |
| `result` | Results published | "Exam results are now available" |
| `exam` | Upcoming exams | "Math exam on Monday" |
| `event` | School events | "Sports day this Friday" |
| `promotion` | Promotion decisions | "Student promoted to Grade 8" |
| `report_card` | Report cards | "Report card ready for download" |
| `assignment` | Assignment updates | "New homework assigned" |

---

## 2. Architecture

### Components:

1. **Notification Model** - Stores notification records
2. **NotificationPreference Model** - User delivery preferences
3. **NotificationTemplate Model** - Message templates
4. **NotificationService** - Business logic for sending
5. **ViewSets/API** - REST API endpoints
6. **Signal Handlers** - Automatic notifications

---

## 3. API Endpoints

### For Students/Parents/Teachers

#### Get Notifications
```bash
GET /api/notifications/
GET /api/notifications/?is_read=false
GET /api/notifications/?notification_type=general
GET /api/notifications/?priority=high
```

**Response:**
```json
[
  {
    "id": 1,
    "notification_type": "general",
    "priority": "high",
    "title": "Important Announcement",
    "message": "School closes early tomorrow at 12 PM",
    "is_read": false,
    "created_at": "2025-12-06T10:00:00Z",
    "expires_at": null,
    "related_student": null,
    "delivery_status": "email, in-app"
  }
]
```

#### Mark as Read
```bash
POST /api/notifications/{id}/mark-read/
```

#### Mark All as Read
```bash
POST /api/notifications/mark-all-read/
```

#### Get Unread Count
```bash
GET /api/notifications/unread/
```

**Response:**
```json
{
  "unread_count": 5
}
```

---

### For Admins (Sending Announcements)

#### Send Single Notification
```bash
POST /api/notifications/
```

**Request:**
```json
{
  "recipient_id": 123,
  "notification_type": "general",
  "title": "Important Announcement",
  "message": "School closes early tomorrow at 12 PM due to weather",
  "priority": "high",
  "send_email": true,
  "send_sms": false,
  "expires_at": "2025-12-07T23:59:59Z"
}
```

#### Send Bulk Announcement
```bash
POST /api/notifications/bulk/
```

**Request:**
```json
{
  "recipient_ids": [123, 124, 125, 126],
  "notification_type": "general",
  "title": "School Announcement",
  "message": "Sports day has been rescheduled to next Friday",
  "priority": "normal",
  "send_email": true,
  "send_sms": false
}
```

**Response:**
```json
{
  "message": "Bulk notifications sent to 4 users",
  "created": 4,
  "email_sent": 4,
  "sms_sent": 0
}
```

---

## 4. User Preferences

### Get Preferences
```bash
GET /api/notification-preferences/
```

**Response:**
```json
{
  "id": 1,
  "user": 123,
  "email_enabled": true,
  "email_attendance": true,
  "email_fees": true,
  "email_results": true,
  "email_exams": true,
  "email_events": true,
  "email_assignments": true,
  "sms_enabled": false,
  "sms_attendance": false,
  "sms_fees": true,
  "sms_urgent_only": true,
  "daily_digest": false,
  "digest_time": "18:00:00"
}
```

### Update Preferences
```bash
PUT /api/notification-preferences/{id}/
```

**Request:**
```json
{
  "email_enabled": true,
  "email_events": false,
  "sms_enabled": true,
  "sms_urgent_only": true
}
```

---

## 5. Automatic Notifications

The system automatically sends notifications for these events:

### Attendance
- Triggered when student is marked absent
- Sent to: Parents
- Channels: Email, SMS (if enabled)

### Fee Reminders
- Triggered when payment is due
- Sent to: Parents
- Channels: Email, SMS

### Results Published
- Triggered when teacher publishes results
- Sent to: Students, Parents
- Channels: Email, In-app

### Assignments
- Triggered when teacher creates/grades assignment
- Sent to: Students, Parents
- Channels: Email, In-app

### Report Cards
- Triggered when report card is generated
- Sent to: Students, Parents
- Channels: Email, In-app

---

## 6. How to Send Announcements

### Method 1: Via API (Programmatic)

```python
from notifications.services import NotificationService
from users.models import CustomUser

service = NotificationService()

# Get all parents
parents = CustomUser.objects.filter(is_parent=True)

# Send announcement
for parent in parents:
    service.create_notification(
        recipient=parent,
        notification_type='general',
        title='School Announcement',
        message='Sports day rescheduled to next Friday',
        priority='normal',
        send_email=True,
        send_sms=False
    )
```

### Method 2: Via Admin Panel

1. Go to Django Admin
2. Navigate to Notifications > Notifications
3. Click "Add Notification"
4. Fill in details:
   - Recipient
   - Type: General
   - Title & Message
   - Priority
5. Save

### Method 3: Via REST API (Recommended for Frontend)

```typescript
// Send announcement to multiple users
const sendAnnouncement = async (recipientIds: number[], title: string, message: string) => {
  const response = await fetch('http://localhost:8000/api/notifications/bulk/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      recipient_ids: recipientIds,
      notification_type: 'general',
      title: title,
      message: message,
      priority: 'normal',
      send_email: true,
      send_sms: false
    })
  })
  
  return await response.json()
}

// Example: Send to all parents
const allParents = await getParentIds() // Your function to get parent IDs
await sendAnnouncement(
  allParents,
  'School Announcement',
  'Sports day has been rescheduled to next Friday'
)
```

---

## 7. Priority Levels

| Priority | Use Case | SMS Behavior |
|----------|----------|--------------|
| `low` | General info | Not sent |
| `normal` | Standard announcements | Not sent (unless enabled) |
| `high` | Important notices | Sent if enabled |
| `urgent` | Emergency alerts | Always sent (overrides preferences) |

---

## 8. Message Templates

Admins can create reusable templates for common notifications.

### Create Template
```bash
POST /api/notification-templates/
```

**Request:**
```json
{
  "template_type": "event",
  "title_template": "{{event_name}} - {{event_date}}",
  "message_template": "Reminder: {{event_name}} is scheduled for {{event_date}} at {{event_time}}. {{event_details}}",
  "email_subject_template": "Upcoming Event: {{event_name}}",
  "email_body_template": "Dear {{recipient_name}},\n\n{{message_template}}\n\nBest regards,\nSchool Administration",
  "sms_template": "{{event_name}} on {{event_date}} at {{event_time}}",
  "is_active": true
}
```

---

## 9. Features

### ✅ Implemented
- In-app notifications
- Email delivery
- SMS integration support (placeholders ready)
- User preferences
- Bulk notifications
- Priority levels
- Read/unread tracking
- Automatic notifications (via signals)
- Template system
- Expiration dates
- Related object linking

### 🔄 Email/SMS Integration
To enable actual email/SMS delivery:

1. **Email**: Configure in `settings.py`
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = 'School Name <noreply@school.com>'
```

2. **SMS**: Integrate Twilio/Africa's Talking
```python
SMS_ENABLED = True
SMS_PROVIDER = 'twilio'  # or 'africas_talking'
SMS_API_KEY = 'your-api-key'
SMS_SENDER_ID = 'SCHOOL'
```

---

## 10. TypeScript Integration

```typescript
// Notification interface
interface Notification {
  id: number
  notification_type: string
  priority: string
  title: string
  message: string
  is_read: boolean
  created_at: string
  expires_at: string | null
  related_student: number | null
  delivery_status: string
}

// Get notifications
const getNotifications = async (isRead?: boolean) => {
  let url = 'http://localhost:8000/api/notifications/'
  if (isRead !== undefined) {
    url += `?is_read=${isRead}`
  }
  
  const response = await fetch(url, {
    headers: { 'Authorization': `Bearer ${accessToken}` }
  })
  
  return await response.json() as Notification[]
}

// Mark as read
const markAsRead = async (notificationId: number) => {
  const response = await fetch(
    `http://localhost:8000/api/notifications/${notificationId}/mark-read/`,
    {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${accessToken}` }
    }
  )
  
  return await response.json()
}

// Get unread count
const getUnreadCount = async () => {
  const response = await fetch(
    'http://localhost:8000/api/notifications/unread/',
    {
      headers: { 'Authorization': `Bearer ${accessToken}` }
    }
  )
  
  const data = await response.json()
  return data.unread_count
}
```

---

## 11. Best Practices

1. **Use Appropriate Types**: Choose the right notification type for context
2. **Set Priority Correctly**: Reserve `urgent` for emergencies only
3. **Respect Preferences**: System automatically checks user preferences
4. **Use Templates**: Create reusable templates for common messages
5. **Set Expiration**: Add `expires_at` for time-sensitive notifications
6. **Bulk for Announcements**: Use `/bulk/` endpoint for school-wide messages
7. **Test First**: Test with small groups before sending to all users

---

## 12. Summary

The notification system provides a **complete announcement and messaging solution**:

- ✅ Multi-channel delivery (in-app, email, SMS)
- ✅ User-controlled preferences
- ✅ Bulk sending for announcements
- ✅ Automatic notifications for events
- ✅ Template-based messaging
- ✅ Priority-based delivery
- ✅ Full REST API

**It's not a separate "announcement system" - notifications ARE the announcement/messaging system.**

---

**Date:** December 6, 2025  
**Status:** ✅ Fully implemented and ready to use
