# Complete API Documentation - Django School Management System

**Version:** 1.7.0
**Last Updated:** December 5, 2025
**API Base URL:** `http://localhost:8000/api/`
**Documentation:** `http://localhost:8000/` (Swagger UI)

---

## 📋 Table of Contents

1. [Authentication](#authentication)
2. [User Management](#user-management)
3. [Academic Module](#academic-module)
4. [Administration Module](#administration-module)
5. [Assignments Module](#assignments-module)
6. [Attendance Module](#attendance-module)
7. [Examination Module](#examination-module)
8. [Finance Module](#finance-module)
9. [Notifications Module](#notifications-module)
10. [Schedule/Timetable Module](#schedule-module)
11. [File Uploads](#file-uploads)
12. [Error Handling](#error-handling)
13. [Data Models](#data-models)

---

## 🔑 Authentication

### JWT Token Authentication (Teachers, Parents, Admin)

#### Login
```http
POST /api/users/token/
Content-Type: application/json

{
  "email": "user@school.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### Refresh Token
```http
POST /api/users/token/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### Verify Token
```http
POST /api/users/token/verify/
Content-Type: application/json

{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### Student Portal Authentication (Phone + Password)

#### Register Student
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

#### Student Login
```http
POST /api/academic/students/auth/login/
Content-Type: application/json

{
  "phone_number": "08012345678",
  "password": "StudentPass123"
}
```

#### Change Password
```http
POST /api/academic/students/auth/change-password/
Authorization: Bearer {token}
Content-Type: application/json

{
  "old_password": "OldPass123",
  "new_password": "NewPass123",
  "new_password_confirm": "NewPass123"
}
```

---

## 👥 User Management

### Get Current User
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

### User List (Admin only)
```http
GET /api/users/users/
Authorization: Bearer {token}
```

### Create User
```http
POST /api/users/users/
Authorization: Bearer {token}
Content-Type: application/json

{
  "email": "newuser@school.com",
  "password": "SecurePass123",
  "first_name": "Jane",
  "last_name": "Doe",
  "is_teacher": true
}
```

---

## 🎓 Academic Module

### Students

#### List Students
```http
GET /api/academic/students/
Authorization: Bearer {token}
```

**Query Parameters:**
- `classroom`: Filter by classroom ID
- `is_active`: true/false
- `search`: Search by name or admission number

**Response:**
```json
{
  "count": 150,
  "next": "http://localhost:8000/api/academic/students/?page=2",
  "previous": null,
  "results": [
    {
      "id": 45,
      "admission_number": "2024/001",
      "full_name": "Jane Doe",
      "first_name": "Jane",
      "middle_name": "",
      "last_name": "Doe",
      "gender": "F",
      "date_of_birth": "2010-05-15",
      "phone_number": "08012345678",
      "email": "jane@student.school.com",
      "is_active": true,
      "can_login": true,
      "parent_guardian": 12,
      "parent_name": "Mr. John Doe",
      "current_classroom": "Form 3A"
    }
  ]
}
```

#### Get Student Details
```http
GET /api/academic/students/{id}/
Authorization: Bearer {token}
```

#### Create Student
```http
POST /api/academic/students/
Authorization: Bearer {token}
Content-Type: application/json

{
  "admission_number": "2024/050",
  "first_name": "John",
  "middle_name": "Paul",
  "last_name": "Smith",
  "gender": "M",
  "date_of_birth": "2010-03-20",
  "parent_guardian": 15,
  "phone_number": "08098765432",
  "is_active": true
}
```

#### Update Student
```http
PUT /api/academic/students/{id}/
Authorization: Bearer {token}
Content-Type: application/json
```

#### Bulk Upload Students (CSV)
```http
POST /api/academic/students/bulk-upload/
Authorization: Bearer {token}
Content-Type: multipart/form-data

file: students.csv
```

---

### Teachers

#### List Teachers
```http
GET /api/academic/teachers/
Authorization: Bearer {token}
```

#### Get Teacher Details
```http
GET /api/academic/teachers/{id}/
Authorization: Bearer {token}
```

#### Teacher's Classes (Current teacher)
```http
GET /api/academic/allocated-subjects/my-classes/
Authorization: Bearer {teacher_token}
```

**Response:**
```json
[
  {
    "id": 12,
    "classroom": {
      "id": 5,
      "name": "Form 3A",
      "grade_level": "JSS 3"
    },
    "subject": {
      "id": 8,
      "name": "Mathematics",
      "code": "MATH"
    },
    "teacher": {
      "id": 3,
      "name": "Mr. John Smith"
    }
  }
]
```

---

### Classrooms

#### List Classrooms
```http
GET /api/academic/classrooms/
Authorization: Bearer {token}
```

**Response:**
```json
[
  {
    "id": 5,
    "name": "Form 3A",
    "class_level": "JSS 3",
    "grade_level": "Junior Secondary",
    "class_year": "Year 3",
    "stream": "Science",
    "capacity": 40,
    "current_enrollment": 35
  }
]
```

#### Get Classroom Students
```http
GET /api/academic/classrooms/{classroom_id}/students/
Authorization: Bearer {token}
```

#### Create Classroom
```http
POST /api/academic/classrooms/
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Form 4A",
  "class_level": 8,
  "grade_level": 3,
  "capacity": 40
}
```

---

### Subjects

#### List Subjects
```http
GET /api/academic/subjects/
Authorization: Bearer {token}
```

**Response:**
```json
[
  {
    "id": 8,
    "name": "Mathematics",
    "code": "MATH",
    "department": "Sciences",
    "is_compulsory": true,
    "is_active": true
  }
]
```

#### Create Subject
```http
POST /api/academic/subjects/
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Physics",
  "code": "PHY",
  "department": 2,
  "is_compulsory": true
}
```

---

### Parents

#### List Parents
```http
GET /api/academic/parents/
Authorization: Bearer {token}
```

#### Get Parent Details
```http
GET /api/academic/parents/{id}/
Authorization: Bearer {token}
```

**Response:**
```json
{
  "id": 12,
  "user": 45,
  "first_name": "John",
  "last_name": "Doe",
  "email": "parent@email.com",
  "phone_number": "08012345678",
  "children": [
    {
      "id": 23,
      "full_name": "Jane Doe",
      "admission_number": "2024/001",
      "classroom": "Form 3A"
    },
    {
      "id": 24,
      "full_name": "Jack Doe",
      "admission_number": "2024/002",
      "classroom": "Form 1B"
    }
  ]
}
```

---

### Student Portal

#### Student Dashboard
```http
GET /api/academic/students/portal/dashboard/
Authorization: Bearer {student_token}
```

**Response:**
```json
{
  "student": {
    "id": 45,
    "full_name": "Jane Doe",
    "admission_number": "2024/001",
    "classroom": "Form 3A",
    "academic_year": "2024/2025"
  },
  "attendance_summary": {
    "total_days": 120,
    "present": 110,
    "absent": 10,
    "attendance_rate": 91.7
  },
  "fee_balance": {
    "total_balance": 150000,
    "amount_paid": 100000,
    "remaining": 50000,
    "term": "First Term"
  },
  "recent_results": [...],
  "upcoming_assignments": [...],
  "unread_notifications": 5
}
```

#### Student Profile
```http
GET /api/academic/students/portal/profile/
Authorization: Bearer {student_token}
```

#### Update Student Profile
```http
PUT /api/academic/students/portal/update-profile/
Authorization: Bearer {student_token}
Content-Type: application/json

{
  "phone_number": "08098765432",
  "preferred_stream": "science"
}
```

---

### Promotions (Phase 2.1)

#### List Promotion Rules
```http
GET /api/academic/promotion-rules/
Authorization: Bearer {token}
```

#### Create Promotion Rule
```http
POST /api/academic/promotion-rules/
Authorization: Bearer {token}
Content-Type: application/json

{
  "from_class": 5,
  "to_class": 6,
  "academic_year": 3,
  "min_attendance_percent": 75,
  "min_average_score": 50,
  "required_subjects_passed": 5,
  "auto_promote": true
}
```

#### List Student Promotions
```http
GET /api/academic/promotions/
Authorization: Bearer {token}
```

**Query Parameters:**
- `academic_year`: Filter by academic year
- `status`: promoted|repeated|graduated|conditional
- `from_class`: Filter by current class
- `to_class`: Filter by target class

#### Process Promotions (Bulk)
```http
POST /api/academic/promotions/process-bulk/
Authorization: Bearer {token}
Content-Type: application/json

{
  "academic_year": 3,
  "from_class": 5,
  "promotion_rule": 12
}
```

---

### Class Advancement (Phase 2.2)

#### Advance Classes
```http
POST /api/academic/class-advancement/advance-classes/
Authorization: Bearer {token}
Content-Type: application/json

{
  "from_academic_year": 3,
  "to_academic_year": 4,
  "advancement_date": "2025-09-01"
}
```

#### Assign Streams (for SS1)
```http
POST /api/academic/stream-assignments/assign-bulk/
Authorization: Bearer {token}
Content-Type: application/json

{
  "students": [45, 46, 47],
  "stream": "science"
}
```

---

## 🏛️ Administration Module

### Academic Years

#### List Academic Years
```http
GET /api/administration/academic-years/
Authorization: Bearer {token}
```

**Response:**
```json
[
  {
    "id": 3,
    "name": "2024/2025",
    "start_date": "2024-09-01",
    "end_date": "2025-08-31",
    "is_current": true
  }
]
```

#### Create Academic Year
```http
POST /api/administration/academic-years/
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "2025/2026",
  "start_date": "2025-09-01",
  "end_date": "2026-08-31",
  "is_current": false
}
```

---

### Terms

#### List Terms
```http
GET /api/administration/terms/
Authorization: Bearer {token}
```

**Response:**
```json
[
  {
    "id": 8,
    "name": "First Term",
    "academic_year": 3,
    "academic_year_name": "2024/2025",
    "start_date": "2024-09-01",
    "end_date": "2024-12-15",
    "is_current": true,
    "default_term_fee": 50000
  }
]
```

#### Create Term
```http
POST /api/administration/terms/
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Second Term",
  "academic_year": 3,
  "start_date": "2025-01-10",
  "end_date": "2025-04-15",
  "default_term_fee": 50000
}
```

---

### School Events

#### List Events
```http
GET /api/administration/events/
Authorization: Bearer {token}
```

#### Create Event
```http
POST /api/administration/events/
Authorization: Bearer {token}
Content-Type: application/json

{
  "title": "Annual Sports Day",
  "description": "School-wide sports competition",
  "date": "2025-03-15",
  "event_type": "sports",
  "audience": "all"
}
```

---

## 📝 Assignments Module (Phase 1.7)

### Teacher Endpoints

#### List Assignments
```http
GET /api/assignments/teacher/assignments/
Authorization: Bearer {teacher_token}
```

**Query Parameters:**
- `status`: draft|published|closed
- `classroom`: classroom ID
- `subject`: subject ID
- `term`: term ID
- `search`: search text

**Response:**
```json
{
  "count": 25,
  "results": [
    {
      "id": 45,
      "title": "Mathematics Homework - Chapter 5",
      "assignment_type": "homework",
      "subject_name": "Mathematics",
      "classroom_name": "Form 3A",
      "due_date": "2025-12-15T23:59:00Z",
      "max_score": 100,
      "status": "published",
      "is_overdue": false,
      "submission_rate": 65.5,
      "total_students": 30,
      "submission_count": 20,
      "graded_count": 15
    }
  ]
}
```

#### Create Assignment
```http
POST /api/assignments/teacher/assignments/
Authorization: Bearer {teacher_token}
Content-Type: application/json

{
  "title": "Physics Lab Report - Experiment 3",
  "description": "Complete the lab report for Newton's Laws experiment",
  "assignment_type": "lab_report",
  "classroom": 5,
  "subject": 12,
  "academic_year": 3,
  "term": 2,
  "due_date": "2025-12-20T17:00:00Z",
  "max_score": 100,
  "allow_late_submission": true,
  "late_penalty_percent": 10,
  "status": "published"
}
```

#### Get Assignment Details
```http
GET /api/assignments/teacher/assignments/{id}/
Authorization: Bearer {teacher_token}
```

#### Update Assignment
```http
PUT /api/assignments/teacher/assignments/{id}/
Authorization: Bearer {teacher_token}
Content-Type: application/json
```

#### Delete Assignment
```http
DELETE /api/assignments/teacher/assignments/{id}/
Authorization: Bearer {teacher_token}
```

#### Upload Attachment
```http
POST /api/assignments/teacher/assignments/{id}/upload_attachment/
Authorization: Bearer {teacher_token}
Content-Type: multipart/form-data

file: document.pdf
```

#### Get Submissions
```http
GET /api/assignments/teacher/assignments/{id}/submissions/
Authorization: Bearer {teacher_token}
```

**Query Parameters:**
- `graded`: true|false
- `late`: true|false

#### Grade Submission
```http
POST /api/assignments/teacher/assignments/{id}/grade_submission/
Authorization: Bearer {teacher_token}
Content-Type: application/json

{
  "submission_id": 123,
  "score": 85,
  "late_penalty_applied": 0,
  "feedback": "Excellent work! Very thorough analysis."
}
```

#### Update Grade
```http
PUT /api/assignments/teacher/assignments/{id}/update_grade/
Authorization: Bearer {teacher_token}
Content-Type: application/json

{
  "submission_id": 123,
  "score": 90,
  "feedback": "Updated: Outstanding work!"
}
```

#### Get Statistics
```http
GET /api/assignments/teacher/assignments/{id}/statistics/
Authorization: Bearer {teacher_token}
```

**Response:**
```json
{
  "total_students": 30,
  "submission_count": 25,
  "submission_rate": 83.3,
  "graded_count": 20,
  "pending_grading": 5,
  "late_submissions": 3,
  "on_time_submissions": 22,
  "average_score": 78.5,
  "is_overdue": false
}
```

---

### Student Endpoints

#### List Assignments
```http
GET /api/assignments/student/assignments/
Authorization: Bearer {student_token}
```

**Query Parameters:**
- `subject`: subject ID
- `submitted`: true|false

**Response:**
```json
[
  {
    "id": 45,
    "title": "Mathematics Homework",
    "description": "Complete exercises 1-20",
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
      "late_penalty_applied": 0
    },
    "attachments": [...]
  }
]
```

#### Submit Assignment
```http
POST /api/assignments/student/assignments/{id}/submit/
Authorization: Bearer {student_token}
Content-Type: multipart/form-data

submission_text: "Here are my completed answers..."
files: answer_sheet.pdf
files: graphs.jpg
```

#### Update Submission
```http
PUT /api/assignments/student/assignments/{id}/update_submission/
Authorization: Bearer {student_token}
Content-Type: multipart/form-data

submission_text: "Updated answers..."
files: revised_answers.pdf
```

#### Get My Submission
```http
GET /api/assignments/student/assignments/{id}/my_submission/
Authorization: Bearer {student_token}
```

---

### Parent Endpoints

#### Children Overview
```http
GET /api/assignments/parent/assignments/children_overview/
Authorization: Bearer {parent_token}
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
  }
]
```

#### List Assignments
```http
GET /api/assignments/parent/assignments/
Authorization: Bearer {parent_token}
```

**Query Parameters:**
- `child`: child ID

#### View Child's Submission
```http
GET /api/assignments/parent/assignments/{assignment_id}/child_submission/?child_id=45
Authorization: Bearer {parent_token}
```

---

## 📊 Attendance Module

### Student Attendance

#### List Attendance
```http
GET /api/attendance/student-attendance/
Authorization: Bearer {token}
```

**Query Parameters:**
- `student`: student ID
- `classroom`: classroom ID
- `date`: YYYY-MM-DD
- `date_from`: start date
- `date_to`: end date
- `status`: attendance status ID

**Response:**
```json
[
  {
    "id": 123,
    "student": 45,
    "student_name": "Jane Doe",
    "date": "2025-12-05",
    "classroom": "Form 3A",
    "status": {
      "id": 2,
      "name": "Absent",
      "code": "A"
    },
    "notes": "Sick"
  }
]
```

#### Mark Attendance
```http
POST /api/attendance/student-attendance/
Authorization: Bearer {token}
Content-Type: application/json

{
  "student": 45,
  "date": "2025-12-05",
  "classroom": 5,
  "status": 2,
  "notes": "Medical appointment"
}
```

#### Bulk Mark Attendance
```http
POST /api/attendance/student-attendance/bulk-mark/
Authorization: Bearer {token}
Content-Type: application/json

{
  "classroom": 5,
  "date": "2025-12-05",
  "attendance_data": [
    {"student": 45, "status": 1},
    {"student": 46, "status": 2, "notes": "Sick"},
    {"student": 47, "status": 1}
  ]
}
```

#### Get Attendance Summary
```http
GET /api/attendance/student-attendance/summary/?student=45
Authorization: Bearer {token}
```

**Response:**
```json
{
  "student": 45,
  "total_days": 120,
  "present": 110,
  "absent": 10,
  "late": 5,
  "excused": 3,
  "attendance_rate": 91.7
}
```

---

### Teacher Attendance

```http
GET  /api/attendance/teacher-attendance/
POST /api/attendance/teacher-attendance/
```

---

## 📚 Examination Module

### Exams

#### List Exams
```http
GET /api/academic/examinations/
Authorization: Bearer {token}
```

#### Create Exam
```http
POST /api/academic/examinations/
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "First Term Exam",
  "exam_type": "end_of_term",
  "subject": 12,
  "classroom": 5,
  "date": "2025-12-15",
  "duration": 120,
  "total_marks": 100
}
```

---

### Results

#### List Results
```http
GET /api/academic/examinations/results/
Authorization: Bearer {token}
```

**Query Parameters:**
- `student`: student ID
- `term`: term ID
- `academic_year`: academic year ID

**Response:**
```json
[
  {
    "id": 89,
    "student": 45,
    "student_name": "Jane Doe",
    "term": 8,
    "term_name": "First Term",
    "academic_year": "2024/2025",
    "annual_average": 78.5,
    "total_score": 785,
    "position": 3,
    "grade": "B",
    "subjects": [
      {
        "subject_name": "Mathematics",
        "ca_score": 25,
        "exam_score": 68,
        "total": 93,
        "grade": "A",
        "position": 2
      }
    ]
  }
]
```

#### Compute Results
```http
POST /api/academic/examinations/results/compute/
Authorization: Bearer {token}
Content-Type: application/json

{
  "term": 8,
  "classroom": 5
}
```

---

### Report Cards

#### List Report Cards
```http
GET /api/academic/examinations/report-cards/
Authorization: Bearer {token}
```

**Query Parameters:**
- `student`: student ID
- `term`: term ID
- `academic_year`: academic year ID

#### Generate Report Card
```http
POST /api/academic/examinations/report-cards/generate/
Authorization: Bearer {token}
Content-Type: application/json

{
  "student": 45,
  "term": 8
}
```

#### Download Report Card (PDF)
```http
GET /api/academic/examinations/report-cards/{id}/download/
Authorization: Bearer {token}
```

**Response:** PDF file download

---

## 💰 Finance Module

### Fee Structures

#### List Fee Structures
```http
GET /api/finance/fee-structures/
Authorization: Bearer {token}
```

**Response:**
```json
[
  {
    "id": 12,
    "name": "JSS 3 Fees",
    "description": "Fees for Junior Secondary 3",
    "class_level": "JSS 3",
    "amount": 50000,
    "term": "First Term",
    "academic_year": "2024/2025",
    "is_active": true,
    "components": [
      {"name": "Tuition", "amount": 30000},
      {"name": "Books", "amount": 10000},
      {"name": "Activities", "amount": 10000}
    ]
  }
]
```

#### Create Fee Structure
```http
POST /api/finance/fee-structures/
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "SS1 Science Fees",
  "class_level": 5,
  "amount": 60000,
  "term": 8,
  "academic_year": 3
}
```

---

### Receipts

#### List Receipts
```http
GET /api/finance/receipts/
Authorization: Bearer {token}
```

**Query Parameters:**
- `student`: student ID
- `term`: term ID
- `date_from`: start date
- `date_to`: end date

**Response:**
```json
[
  {
    "id": 456,
    "receipt_number": "RCT-2024-001",
    "student": 45,
    "student_name": "Jane Doe",
    "amount": 25000,
    "payment_date": "2024-09-15",
    "term": "First Term",
    "paid_through": "Bank Transfer",
    "payer": "John Doe (Parent)"
  }
]
```

#### Create Receipt
```http
POST /api/finance/receipts/
Authorization: Bearer {token}
Content-Type: application/json

{
  "student": 45,
  "amount": 25000,
  "payment_date": "2024-12-05",
  "term": 8,
  "paid_through": "cash",
  "payer": "John Doe"
}
```

#### Download Receipt (PDF)
```http
GET /api/finance/receipts/{id}/download/
Authorization: Bearer {token}
```

---

### Payments

#### List Payments
```http
GET /api/finance/payments/
Authorization: Bearer {token}
```

#### Get Student Fee Balance
```http
GET /api/finance/fee-balance/?student=45
Authorization: Bearer {token}
```

**Response:**
```json
{
  "student": 45,
  "student_name": "Jane Doe",
  "term": "First Term",
  "total_fee": 50000,
  "amount_paid": 35000,
  "balance": 15000,
  "payment_history": [...]
}
```

---

## 🔔 Notifications Module (Phase 1.5)

### User Notifications

#### List Notifications
```http
GET /api/notifications/notifications/
Authorization: Bearer {token}
```

**Query Parameters:**
- `is_read`: true|false
- `notification_type`: assignment|attendance|fee|result|promotion|event|exam|general
- `priority`: urgent|high|normal|low

**Response:**
```json
{
  "count": 25,
  "unread_count": 8,
  "results": [
    {
      "id": 123,
      "title": "New Assignment: Mathematics Homework",
      "message": "Your teacher has assigned Mathematics Homework...",
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

#### Get Notification
```http
GET /api/notifications/notifications/{id}/
Authorization: Bearer {token}
```

#### Mark as Read
```http
PATCH /api/notifications/notifications/{id}/mark-read/
Authorization: Bearer {token}
```

#### Mark All as Read
```http
PATCH /api/notifications/notifications/mark-all-read/
Authorization: Bearer {token}
```

#### Delete Notification
```http
DELETE /api/notifications/notifications/{id}/
Authorization: Bearer {token}
```

---

### Notification Preferences

#### Get Preferences
```http
GET /api/notifications/preferences/
Authorization: Bearer {token}
```

**Response:**
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

#### Update Preferences
```http
PUT /api/notifications/preferences/
Authorization: Bearer {token}
Content-Type: application/json

{
  "email_assignments": true,
  "email_attendance": false,
  "email_fees": true
}
```

---

### Notification Templates (Admin)

```http
GET  /api/notifications/templates/
POST /api/notifications/templates/
PUT  /api/notifications/templates/{id}/
```

---

## 📅 Schedule/Timetable Module

### Periods

#### List Periods
```http
GET /api/timetable/periods/
Authorization: Bearer {token}
```

**Query Parameters:**
- `classroom`: classroom ID
- `day_of_week`: monday|tuesday|wednesday|thursday|friday
- `is_active`: true|false

**Response:**
```json
[
  {
    "id": 234,
    "classroom": "Form 3A",
    "subject": "Mathematics",
    "teacher": "Mr. John Smith",
    "day_of_week": "monday",
    "start_time": "08:00:00",
    "end_time": "09:00:00",
    "period_number": 1,
    "is_active": true
  }
]
```

#### Create Period
```http
POST /api/timetable/periods/
Authorization: Bearer {token}
Content-Type: application/json

{
  "classroom": 5,
  "subject": 12,
  "teacher": 3,
  "day_of_week": "monday",
  "start_time": "08:00:00",
  "end_time": "09:00:00",
  "period_number": 1
}
```

---

### Timetable Views

#### Get Classroom Timetable
```http
GET /api/timetable/timetable/?classroom=5
Authorization: Bearer {token}
```

#### Get Teacher Timetable
```http
GET /api/timetable/timetable/?teacher=3
Authorization: Bearer {token}
```

**Response:**
```json
{
  "classroom": "Form 3A",
  "timetable": {
    "monday": [
      {
        "period": 1,
        "time": "08:00 - 09:00",
        "subject": "Mathematics",
        "teacher": "Mr. John Smith"
      },
      {
        "period": 2,
        "time": "09:00 - 10:00",
        "subject": "English",
        "teacher": "Mrs. Jane Brown"
      }
    ],
    "tuesday": [...]
  }
}
```

---

## 📁 File Uploads

### Supported File Types

**Assignment Attachments (Teacher):**
- Documents: pdf, doc, docx, txt
- Presentations: ppt, pptx
- Spreadsheets: xls, xlsx
- Images: jpg, png

**Student Submissions:**
- All teacher types PLUS zip

### Upload Examples

#### Single File
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch('/api/assignments/teacher/assignments/45/upload_attachment/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});
```

#### Multiple Files
```javascript
const formData = new FormData();
formData.append('submission_text', 'My answers...');
for (let file of fileInput.files) {
  formData.append('files', file);
}

fetch('/api/assignments/student/assignments/45/submit/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});
```

### File Download
```javascript
// Direct download
window.open(fileUrl, '_blank');

// Or fetch and download
fetch(fileUrl, {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
.then(response => response.blob())
.then(blob => {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'filename.pdf';
  a.click();
});
```

---

## ⚠️ Error Handling

### Standard Error Responses

#### 400 Bad Request
```json
{
  "detail": "Validation error",
  "field_name": ["This field is required."]
}
```

#### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

#### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

#### 404 Not Found
```json
{
  "detail": "Not found."
}
```

#### 500 Internal Server Error
```json
{
  "detail": "An error occurred on the server."
}
```

### Token Expiry Handling

```javascript
async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    'Authorization': `Bearer ${getAccessToken()}`
  };

  let response = await fetch(url, options);

  if (response.status === 401) {
    const refreshed = await refreshToken();
    if (refreshed) {
      options.headers['Authorization'] = `Bearer ${getAccessToken()}`;
      response = await fetch(url, options);
    } else {
      window.location.href = '/login';
    }
  }

  return response;
}

async function refreshToken() {
  const response = await fetch('/api/users/token/refresh/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({refresh: getRefreshToken()})
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

## 📊 Data Models (TypeScript Interfaces)

### User & Authentication

```typescript
interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
  is_teacher: boolean;
  is_parent: boolean;
  is_student: boolean;
  is_accountant: boolean;
  teacher_id?: number;
  student_id?: number;
  parent_id?: number;
}

interface TokenResponse {
  refresh: string;
  access: string;
}
```

### Academic Models

```typescript
interface Student {
  id: number;
  admission_number: string;
  full_name: string;
  first_name: string;
  middle_name: string;
  last_name: string;
  gender: 'M' | 'F';
  date_of_birth: string;
  phone_number?: string;
  email?: string;
  is_active: boolean;
  can_login: boolean;
  parent_guardian?: number;
  parent_name?: string;
  current_classroom?: string;
}

interface Teacher {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  department: string;
  subjects: number[];
}

interface Classroom {
  id: number;
  name: string;
  class_level: string;
  grade_level: string;
  capacity: number;
  current_enrollment: number;
  stream?: string;
}

interface Subject {
  id: number;
  name: string;
  code: string;
  department: string;
  is_compulsory: boolean;
  is_active: boolean;
}

interface Parent {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  children: Student[];
}
```

### Assignment Models

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
  term?: number;
  term_name?: string;
  assigned_date: string;
  due_date: string;
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
}

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
  grade?: Grade;
}

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
}

interface AttachmentFile {
  id: number;
  file: string;
  file_url: string;
  file_name: string;
  file_size: number;
  uploaded_at: string;
}
```

### Other Models

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

interface Attendance {
  id: number;
  student: number;
  student_name: string;
  date: string;
  classroom: string;
  status: {
    id: number;
    name: string;
    code: string;
  };
  notes?: string;
}

interface Result {
  id: number;
  student: number;
  student_name: string;
  term: number;
  term_name: string;
  academic_year: string;
  annual_average: number;
  total_score: number;
  position: number;
  grade: string;
  subjects: SubjectResult[];
}

interface SubjectResult {
  subject_name: string;
  ca_score: number;
  exam_score: number;
  total: number;
  grade: string;
  position: number;
}
```

---

## 🎯 User Role Matrix

| Feature | Admin | Teacher | Student | Parent |
|---------|-------|---------|---------|--------|
| **Academic** |
| Manage Students | ✅ | ❌ | ❌ | ❌ |
| View Students | ✅ | ✅ | ❌ | Own children |
| Manage Teachers | ✅ | ❌ | ❌ | ❌ |
| Manage Classrooms | ✅ | ❌ | ❌ | ❌ |
| **Assignments** |
| Create Assignments | ✅ | ✅ | ❌ | ❌ |
| Submit Assignments | ❌ | ❌ | ✅ | ❌ |
| Grade Assignments | ✅ | ✅ | ❌ | ❌ |
| View Assignments | ✅ | Own classes | Own | Children's |
| **Attendance** |
| Mark Attendance | ✅ | ✅ | ❌ | ❌ |
| View Attendance | ✅ | ✅ | Own | Children's |
| **Examinations** |
| Create Exams | ✅ | ✅ | ❌ | ❌ |
| Compute Results | ✅ | ✅ | ❌ | ❌ |
| View Results | ✅ | ✅ | Own | Children's |
| Generate Report Cards | ✅ | ✅ | ❌ | ❌ |
| **Finance** |
| Manage Fees | ✅ | ❌ | ❌ | ❌ |
| Create Receipts | ✅ | ❌ | ❌ | ❌ |
| View Fee Balance | ✅ | ❌ | Own | Children's |
| **Notifications** |
| View Notifications | ✅ | ✅ | ✅ | ✅ |
| Configure Preferences | ✅ | ✅ | ✅ | ✅ |

---

## 📞 Testing & Support

### Test the API

#### Using cURL
```bash
# Login
curl -X POST http://localhost:8000/api/users/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@school.com","password":"password"}'

# Use token
curl http://localhost:8000/api/academic/students/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Using Postman
1. Import OpenAPI schema from `http://localhost:8000/api/schema/`
2. Set environment variable `BASE_URL` = `http://localhost:8000`
3. Configure JWT authentication
4. Test all endpoints

### Resources
- **Backend URL:** http://localhost:8000
- **API Documentation:** http://localhost:8000/
- **OpenAPI Schema:** http://localhost:8000/api/schema/

---

**Complete! All 9 modules documented with full endpoints, examples, and data models.** 🎉

*Last Updated: December 5, 2025*
*Version: 1.7.0*
