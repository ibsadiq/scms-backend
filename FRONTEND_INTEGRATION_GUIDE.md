# Frontend Integration Guide - Django School Management System

**Backend Version:** 1.7.0
**API Type:** REST API (Django REST Framework)
**Authentication:** JWT (JSON Web Tokens)
**Date:** December 5, 2025

---

## 🚀 Quick Start for Frontend Developers

### Backend Server
```bash
# Start the backend server
cd django-scms
uv run python manage.py runserver

# Backend will be available at:
http://localhost:8000
```

### API Documentation
```
Swagger UI:     http://localhost:8000/
OpenAPI Schema: http://localhost:8000/api/schema/
Base API URL:   http://localhost:8000/api/
```

---

## 🔑 Authentication

### 1. **JWT Token Authentication** (Teachers, Parents, Admin)

#### Login - Get Tokens
```http
POST /api/users/token/
Content-Type: application/json

{
  "email": "teacher@school.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### Use Access Token
```http
GET /api/assignments/teacher/assignments/
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

#### Refresh Token (when access expires)
```http
POST /api/users/token/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Token Expiry:**
- Access Token: 60 minutes
- Refresh Token: 24 hours

---

### 2. **Student Portal Authentication** (Phone + Password)

#### Register Student Account
```http
POST /api/academic/students/auth/register/
Content-Type: application/json

{
  "phone_number": "08012345678",
  "password": "StudentPass123",
  "password_confirm": "StudentPass123",
  "admission_number": "2024/001"
}
```

**Response:**
```json
{
  "message": "Student account created successfully",
  "student": {
    "id": 45,
    "full_name": "John Doe",
    "admission_number": "2024/001",
    "phone_number": "08012345678"
  },
  "tokens": {
    "refresh": "...",
    "access": "..."
  }
}
```

#### Student Login
```http
POST /api/academic/students/auth/login/
Content-Type: application/json

{
  "phone_number": "08012345678",
  "password": "StudentPass123"
}
```

**Response:**
```json
{
  "message": "Login successful",
  "tokens": {
    "refresh": "...",
    "access": "..."
  },
  "student": {
    "id": 45,
    "full_name": "John Doe",
    "admission_number": "2024/001",
    "classroom": "Form 3A"
  }
}
```

---

## 📡 Main API Endpoints

### **Academic Module** - `/api/academic/`

#### Students
```http
GET    /api/academic/students/              # List students
POST   /api/academic/students/              # Create student
GET    /api/academic/students/{id}/         # Get student details
PUT    /api/academic/students/{id}/         # Update student
DELETE /api/academic/students/{id}/         # Delete student
```

#### Classrooms
```http
GET    /api/academic/classrooms/            # List classrooms
POST   /api/academic/classrooms/            # Create classroom
GET    /api/academic/classrooms/{id}/       # Get classroom
GET    /api/academic/classrooms/{id}/students/  # Get students in classroom
```

#### Subjects
```http
GET    /api/academic/subjects/              # List subjects
POST   /api/academic/subjects/              # Create subject
```

#### Student Portal
```http
POST   /api/academic/students/auth/register/        # Register student
POST   /api/academic/students/auth/login/           # Login student
POST   /api/academic/students/auth/change-password/ # Change password
GET    /api/academic/students/portal/dashboard/     # Student dashboard
GET    /api/academic/students/portal/profile/       # Student profile
PUT    /api/academic/students/portal/update-profile/ # Update profile
```

---

### **Assignment Module** - `/api/assignments/`

#### Teacher Endpoints - `/api/assignments/teacher/assignments/`

##### List/Create Assignments
```http
GET  /api/assignments/teacher/assignments/
POST /api/assignments/teacher/assignments/
```

**Query Parameters (GET):**
- `status`: draft | published | closed
- `classroom`: classroom ID
- `subject`: subject ID
- `term`: term ID
- `search`: search in title, description

**POST Body:**
```json
{
  "title": "Mathematics Homework - Chapter 5",
  "description": "Complete all exercises from pages 45-50",
  "assignment_type": "homework",  // homework|project|quiz|research|essay|lab_report|other
  "classroom": 5,
  "subject": 12,
  "academic_year": 3,
  "term": 2,
  "due_date": "2025-12-15T23:59:00Z",
  "max_score": 100,
  "allow_late_submission": true,
  "late_penalty_percent": 10,
  "status": "published"  // draft|published|closed
}
```

**Response:**
```json
{
  "id": 45,
  "title": "Mathematics Homework - Chapter 5",
  "description": "Complete all exercises from pages 45-50",
  "assignment_type": "homework",
  "teacher_name": "Mr. John Smith",
  "classroom_name": "Form 3A",
  "subject_name": "Mathematics",
  "due_date": "2025-12-15T23:59:00Z",
  "max_score": 100,
  "is_overdue": false,
  "total_students": 30,
  "submission_count": 12,
  "graded_count": 5,
  "submission_rate": 40.0,
  "attachments": [],
  "status": "published"
}
```

##### Assignment Details & Actions
```http
GET    /api/assignments/teacher/assignments/{id}/              # Get details
PUT    /api/assignments/teacher/assignments/{id}/              # Update
DELETE /api/assignments/teacher/assignments/{id}/              # Delete
POST   /api/assignments/teacher/assignments/{id}/upload_attachment/  # Upload file
DELETE /api/assignments/teacher/assignments/{id}/delete_attachment/ # Delete file
GET    /api/assignments/teacher/assignments/{id}/submissions/  # List submissions
POST   /api/assignments/teacher/assignments/{id}/grade_submission/ # Grade work
PUT    /api/assignments/teacher/assignments/{id}/update_grade/ # Update grade
GET    /api/assignments/teacher/assignments/{id}/statistics/   # Get stats
```

##### Upload Attachment
```http
POST /api/assignments/teacher/assignments/{id}/upload_attachment/
Content-Type: multipart/form-data

file: [binary file data]
```

**Allowed file types:** pdf, doc, docx, ppt, pptx, xls, xlsx, txt, jpg, png

##### Grade Submission
```http
POST /api/assignments/teacher/assignments/{id}/grade_submission/
Content-Type: application/json

{
  "submission_id": 123,
  "score": 85,
  "late_penalty_applied": 0,
  "feedback": "Excellent work! Well done on question 3."
}
```

**Response:**
```json
{
  "id": 67,
  "score": 85,
  "late_penalty_applied": 0,
  "final_score": 85,
  "percentage": 85.0,
  "grade_letter": "B",
  "feedback": "Excellent work! Well done on question 3.",
  "graded_by_name": "Mr. John Smith",
  "graded_at": "2025-12-05T10:30:00Z"
}
```

##### Get Submissions
```http
GET /api/assignments/teacher/assignments/{id}/submissions/
```

**Query Parameters:**
- `graded`: true | false
- `late`: true | false

**Response:**
```json
[
  {
    "id": 123,
    "student_name": "Jane Doe",
    "student_admission_number": "2024/002",
    "submission_text": "Here are my answers...",
    "submitted_at": "2025-12-10T14:30:00Z",
    "is_late": false,
    "is_graded": true,
    "attachments": [
      {
        "id": 45,
        "file_name": "homework.pdf",
        "file_size": 245678,
        "file_url": "http://localhost:8000/media/assignments/homework.pdf"
      }
    ],
    "grade": {
      "final_score": 85,
      "percentage": 85.0,
      "grade_letter": "B",
      "feedback": "Great work!"
    }
  }
]
```

---

#### Student Endpoints - `/api/assignments/student/assignments/`

##### List Assignments
```http
GET /api/assignments/student/assignments/
```

**Query Parameters:**
- `subject`: subject ID
- `submitted`: true | false (filter by submission status)

**Response:**
```json
[
  {
    "id": 45,
    "title": "Mathematics Homework - Chapter 5",
    "description": "Complete all exercises",
    "assignment_type": "homework",
    "subject_name": "Mathematics",
    "teacher_name": "Mr. John Smith",
    "due_date": "2025-12-15T23:59:00Z",
    "max_score": 100,
    "is_overdue": false,
    "has_submitted": true,
    "submission_id": 123,
    "is_graded": true,
    "grade": {
      "score": 85,
      "final_score": 85,
      "percentage": 85.0,
      "grade_letter": "B",
      "feedback": "Great work!",
      "late_penalty_applied": 0,
      "graded_at": "2025-12-10T16:00:00Z"
    },
    "attachments": [...]
  }
]
```

##### Submit Assignment
```http
POST /api/assignments/student/assignments/{id}/submit/
Content-Type: multipart/form-data

submission_text: "Here are my completed answers..."
files: [file1.pdf]
files: [file2.jpg]
```

**Allowed file types:** pdf, doc, docx, ppt, pptx, xls, xlsx, txt, jpg, png, zip

**Response:**
```json
{
  "id": 123,
  "assignment_title": "Mathematics Homework - Chapter 5",
  "submission_text": "Here are my completed answers...",
  "submitted_at": "2025-12-10T14:30:00Z",
  "is_late": false,
  "is_graded": false,
  "attachments": [
    {
      "id": 45,
      "file_name": "answers.pdf",
      "file_url": "http://localhost:8000/media/submissions/answers.pdf"
    }
  ]
}
```

##### Update Submission (before grading)
```http
PUT /api/assignments/student/assignments/{id}/update_submission/
Content-Type: multipart/form-data

submission_text: "Updated answers..."
files: [new_file.pdf]
```

##### Get My Submission
```http
GET /api/assignments/student/assignments/{id}/my_submission/
```

---

#### Parent Endpoints - `/api/assignments/parent/assignments/`

##### Children Overview
```http
GET /api/assignments/parent/assignments/children_overview/
```

**Response:**
```json
[
  {
    "student_id": 45,
    "student_name": "Jane Doe",
    "classroom": "Form 3A",
    "total_assignments": 15,
    "submitted": 12,
    "graded": 10,
    "pending": 3,
    "upcoming": 2,
    "overdue": 1
  },
  {
    "student_id": 46,
    "student_name": "John Doe",
    "classroom": "Form 1B",
    "total_assignments": 10,
    "submitted": 8,
    "graded": 6,
    "pending": 2,
    "upcoming": 1,
    "overdue": 0
  }
]
```

##### List Assignments for All Children
```http
GET /api/assignments/parent/assignments/
```

**Query Parameters:**
- `child`: child ID (filter by specific child)

##### View Child's Submission
```http
GET /api/assignments/parent/assignments/{assignment_id}/child_submission/?child_id=45
```

---

### **Notifications Module** - `/api/notifications/`

#### User Notifications
```http
GET    /api/notifications/notifications/             # List notifications
GET    /api/notifications/notifications/{id}/        # Get notification
PATCH  /api/notifications/notifications/{id}/mark-read/   # Mark as read
PATCH  /api/notifications/notifications/mark-all-read/    # Mark all read
DELETE /api/notifications/notifications/{id}/        # Delete notification
```

**Query Parameters:**
- `is_read`: true | false
- `notification_type`: assignment | attendance | fee | result | promotion | event | exam | general
- `priority`: urgent | high | normal | low

**Response:**
```json
{
  "count": 25,
  "next": "http://localhost:8000/api/notifications/notifications/?page=2",
  "previous": null,
  "results": [
    {
      "id": 123,
      "title": "New Assignment: Mathematics Homework",
      "message": "Your teacher has assigned Mathematics Homework for Mathematics...",
      "notification_type": "assignment",
      "priority": "normal",
      "is_read": false,
      "created_at": "2025-12-05T10:00:00Z",
      "related_student": {
        "id": 45,
        "full_name": "Jane Doe"
      }
    }
  ]
}
```

#### Notification Preferences
```http
GET  /api/notifications/preferences/      # Get user preferences
PUT  /api/notifications/preferences/      # Update preferences
```

**Response/Update:**
```json
{
  "email_assignments": true,
  "email_attendance": true,
  "email_fees": true,
  "email_results": true,
  "email_promotions": true,
  "email_events": true,
  "email_exams": true,
  "email_general": true
}
```

---

### **Attendance Module** - `/api/attendance/`

```http
GET  /api/attendance/student-attendance/           # List attendance
POST /api/attendance/student-attendance/           # Mark attendance
GET  /api/attendance/student-attendance/summary/   # Get summary
```

---

### **Examination Module** - `/api/academic/`

```http
GET  /api/academic/examinations/results/           # List results
GET  /api/academic/examinations/report-cards/      # List report cards
GET  /api/academic/examinations/report-cards/{id}/download/  # Download PDF
```

---

### **Finance Module** - `/api/finance/`

```http
GET  /api/finance/fee-structures/         # List fee structures
GET  /api/finance/receipts/               # List receipts
POST /api/finance/receipts/               # Create receipt
GET  /api/finance/payments/               # List payments
```

---

## 📊 Data Models & Structures

### Assignment Object
```typescript
interface Assignment {
  id: number;
  title: string;
  description: string;
  assignment_type: 'homework' | 'project' | 'quiz' | 'research' | 'essay' | 'lab_report' | 'other';
  teacher: number;
  teacher_name: string;
  classroom: number;
  classroom_name: string;
  subject: number;
  subject_name: string;
  academic_year: number;
  academic_year_name: string;
  term: number | null;
  term_name: string | null;
  assigned_date: string; // ISO 8601
  due_date: string; // ISO 8601
  max_score: number;
  allow_late_submission: boolean;
  late_penalty_percent: number;
  status: 'draft' | 'published' | 'closed';
  is_active: boolean;
  is_overdue: boolean;
  total_students: number;
  submission_count: number;
  graded_count: number;
  submission_rate: number;
  attachments: AttachmentFile[];
  created_at: string;
  updated_at: string;
}
```

### Submission Object
```typescript
interface AssignmentSubmission {
  id: number;
  assignment: number;
  assignment_title: string;
  student: number;
  student_name: string;
  student_admission_number: string;
  submission_text: string;
  submitted_at: string;
  updated_at: string;
  is_late: boolean;
  is_graded: boolean;
  attachments: AttachmentFile[];
  grade: Grade | null;
}
```

### Grade Object
```typescript
interface Grade {
  id: number;
  score: number;
  late_penalty_applied: number;
  final_score: number;
  percentage: number;
  grade_letter: 'A' | 'B' | 'C' | 'D' | 'F';
  feedback: string;
  graded_by: number;
  graded_by_name: string;
  graded_at: string;
  updated_at: string;
}
```

### Notification Object
```typescript
interface Notification {
  id: number;
  title: string;
  message: string;
  notification_type: 'assignment' | 'attendance' | 'fee' | 'result' | 'promotion' | 'event' | 'exam' | 'general';
  priority: 'urgent' | 'high' | 'normal' | 'low';
  is_read: boolean;
  created_at: string;
  related_student?: {
    id: number;
    full_name: string;
  };
}
```

### Student Object
```typescript
interface Student {
  id: number;
  admission_number: string;
  full_name: string;
  first_name: string;
  middle_name: string;
  last_name: string;
  date_of_birth: string;
  gender: 'M' | 'F';
  phone_number: string | null;
  email: string | null;
  is_active: boolean;
  can_login: boolean;
  parent_guardian: number | null;
  current_classroom: string;
}
```

---

## 🎨 User Roles & Permissions

### Role-based Access

| Endpoint | Admin | Teacher | Student | Parent |
|----------|-------|---------|---------|--------|
| `/api/assignments/teacher/` | ✅ | ✅ | ❌ | ❌ |
| `/api/assignments/student/` | ✅ | ❌ | ✅ | ❌ |
| `/api/assignments/parent/` | ✅ | ❌ | ❌ | ✅ |
| `/api/academic/students/portal/` | ✅ | ❌ | ✅ | ❌ |
| `/api/notifications/` | ✅ | ✅ | ✅ | ✅ |

### Detecting User Role

After login, check the user object or make a "whoami" call to determine role:

```http
GET /api/users/me/
Authorization: Bearer {token}
```

**Response:**
```json
{
  "id": 12,
  "email": "teacher@school.com",
  "first_name": "John",
  "last_name": "Smith",
  "is_staff": false,
  "is_teacher": true,
  "is_parent": false,
  "is_student": false,
  "is_accountant": false,
  "teacher_id": 5,
  "student_id": null,
  "parent_id": null
}
```

---

## 🔄 Real-time Updates (Notifications)

### Polling Strategy (Recommended)
```javascript
// Poll for new notifications every 30 seconds
setInterval(async () => {
  const response = await fetch('/api/notifications/notifications/?is_read=false', {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  const data = await response.json();
  // Update notification badge with data.count
}, 30000);
```

### WebSocket (Future Enhancement)
WebSockets are not currently implemented. Use polling for now.

---

## 📁 File Uploads

### Handling File Uploads

```javascript
// Teacher: Upload assignment attachment
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('/api/assignments/teacher/assignments/45/upload_attachment/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: formData
});

// Student: Submit assignment with files
const submissionData = new FormData();
submissionData.append('submission_text', 'My answers...');
submissionData.append('files', file1);
submissionData.append('files', file2);

await fetch('/api/assignments/student/assignments/45/submit/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: submissionData
});
```

### File Download
```javascript
// Download file from URL
const fileUrl = 'http://localhost:8000/media/assignments/homework.pdf';
window.open(fileUrl, '_blank');
```

---

## ⚠️ Error Handling

### Standard Error Responses

```json
// 400 Bad Request
{
  "detail": "Validation error message",
  "field_name": ["Error message for specific field"]
}

// 401 Unauthorized
{
  "detail": "Authentication credentials were not provided."
}

// 403 Forbidden
{
  "detail": "You do not have permission to perform this action."
}

// 404 Not Found
{
  "detail": "Not found."
}

// 500 Internal Server Error
{
  "detail": "An error occurred on the server."
}
```

### Token Expiry Handling
```javascript
async function makeAuthenticatedRequest(url, options = {}) {
  // Add auth header
  options.headers = {
    ...options.headers,
    'Authorization': `Bearer ${getAccessToken()}`
  };

  let response = await fetch(url, options);

  // If 401, try to refresh token
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry request with new token
      options.headers['Authorization'] = `Bearer ${getAccessToken()}`;
      response = await fetch(url, options);
    } else {
      // Refresh failed, redirect to login
      redirectToLogin();
    }
  }

  return response;
}

async function refreshAccessToken() {
  const response = await fetch('/api/users/token/refresh/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      refresh: getRefreshToken()
    })
  });

  if (response.ok) {
    const data = await response.json();
    saveAccessToken(data.access);
    return true;
  }
  return false;
}
```

---

## 🧪 Testing the API

### Using cURL
```bash
# 1. Login
curl -X POST http://localhost:8000/api/users/token/ \
  -H "Content-Type: application/json" \
  -d '{"email": "teacher@school.com", "password": "password"}'

# 2. Save token
export TOKEN="your_access_token"

# 3. List assignments
curl http://localhost:8000/api/assignments/teacher/assignments/ \
  -H "Authorization: Bearer $TOKEN"

# 4. Create assignment
curl -X POST http://localhost:8000/api/assignments/teacher/assignments/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Assignment",
    "description": "Test",
    "assignment_type": "homework",
    "classroom": 1,
    "subject": 1,
    "academic_year": 1,
    "due_date": "2025-12-31T23:59:00Z",
    "max_score": 100,
    "status": "published"
  }'
```

### Using Postman
1. Import OpenAPI schema from `http://localhost:8000/api/schema/`
2. Set up environment variable `BASE_URL` = `http://localhost:8000`
3. Create authentication with JWT bearer token
4. Test all endpoints

---

## 🌐 CORS Configuration

CORS is already configured in the backend. The following headers are allowed:
- `Content-Type`
- `Authorization`
- `Accept`

Allowed methods: GET, POST, PUT, PATCH, DELETE, OPTIONS

---

## 📱 Recommended Frontend Architecture

### Pages/Routes to Implement

#### **Teacher Dashboard**
- `/teacher/dashboard` - Overview, statistics
- `/teacher/assignments` - List assignments
- `/teacher/assignments/create` - Create new assignment
- `/teacher/assignments/:id` - View assignment details
- `/teacher/assignments/:id/submissions` - View submissions
- `/teacher/assignments/:id/grade/:submissionId` - Grade submission

#### **Student Portal**
- `/student/login` - Login page
- `/student/register` - Registration page
- `/student/dashboard` - Dashboard with overview
- `/student/assignments` - List assignments
- `/student/assignments/:id` - View assignment & submit
- `/student/assignments/:id/submission` - View own submission
- `/student/profile` - View/edit profile

#### **Parent Portal**
- `/parent/dashboard` - Overview of all children
- `/parent/children/:id/assignments` - Child's assignments
- `/parent/children/:id/progress` - Child's progress

#### **Common**
- `/notifications` - Notification center
- `/profile` - User profile

---

## 🎯 Key Features to Implement

### Must-Have Features
1. ✅ Authentication (login/logout/token refresh)
2. ✅ Assignment CRUD for teachers
3. ✅ Assignment submission for students
4. ✅ Grading interface for teachers
5. ✅ Notification center for all users
6. ✅ File upload/download
7. ✅ Student dashboard
8. ✅ Parent overview

### Nice-to-Have Features
1. 📊 Assignment analytics/charts
2. 📅 Calendar view of assignments
3. 🔔 Real-time notification badges
4. 📱 Responsive design
5. 🌙 Dark mode
6. 🔍 Advanced search/filtering
7. 📤 Export data (CSV, PDF)

---

## 📞 Support & Questions

### Backend Team Contact
- **Developer:** [Your Name]
- **Backend URL:** http://localhost:8000
- **Documentation:** Available in `/docs` folder

### Useful Resources
- OpenAPI Schema: http://localhost:8000/api/schema/
- Swagger UI: http://localhost:8000/
- Backend Repo: [Repository URL]

### Common Questions

**Q: How do I know if a user is a teacher, student, or parent?**
A: Check the user object returned after login. It has boolean flags: `is_teacher`, `is_student`, `is_parent`.

**Q: Can a student see other students' submissions?**
A: No, students can only see their own submissions. Parents can see their children's submissions.

**Q: How do notifications work?**
A: Notifications are created automatically by the backend when events happen (new assignment, grading, etc.). Poll the notifications endpoint to get updates.

**Q: What happens when a student submits late?**
A: The backend automatically marks it as late (`is_late: true`) and the teacher can apply late penalties when grading.

**Q: Can I test without real data?**
A: Yes! Use the Django admin panel (http://localhost:8000/admin/) to create test data: students, teachers, classrooms, subjects, and assignments.

---

## ✅ Integration Checklist

- [ ] Set up API client (axios/fetch)
- [ ] Implement JWT authentication flow
- [ ] Create login pages for each user type
- [ ] Implement token refresh logic
- [ ] Build teacher assignment management
- [ ] Build student submission interface
- [ ] Build parent monitoring dashboard
- [ ] Implement file upload/download
- [ ] Add notification center
- [ ] Handle error states
- [ ] Add loading states
- [ ] Test with backend team
- [ ] Deploy and test end-to-end

---

**Happy Coding! 🚀**

*Last Updated: December 5, 2025*
*Backend Version: 1.7.0*
