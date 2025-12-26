# Admission System - Frontend Integration Guide

## Overview

The admission system manages the complete lifecycle from application submission through student enrollment. It features a public portal (no authentication) for parents and an admin portal (authenticated) for school staff.

---

## Table of Contents

1. [Public Portal Endpoints](#public-portal-endpoints)
2. [Admin Portal Endpoints](#admin-portal-endpoints)
3. [Data Models](#data-models)
4. [Workflow States](#workflow-states)
5. [Integration Examples](#integration-examples)
6. [Email Notifications](#email-notifications)

---

## Public Portal Endpoints

**Base URL:** `/api/public/admissions/`

**No authentication required** - accessible to anyone

### 1. View Admission Sessions

```http
GET /api/public/admissions/sessions/
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "2024/2025 Admission",
    "academic_year_display": "2024/2025",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "is_open": true,
    "application_instructions": "Please complete all required fields..."
  }
]
```

### 2. Get Active Session

```http
GET /api/public/admissions/sessions/active/
```

Returns the currently active admission session.

### 3. View Fee Structures

```http
GET /api/public/admissions/fee-structures/?session=1
```

**Response:**
```json
[
  {
    "id": 1,
    "class_room": 5,
    "class_room_name": "Primary 1",
    "application_fee": 5000,
    "application_fee_required": true,
    "entrance_exam_required": true,
    "entrance_exam_fee": 2000,
    "interview_required": false,
    "acceptance_fee": 10000,
    "acceptance_fee_required": true,
    "acceptance_fee_is_part_of_tuition": true,
    "minimum_age": 5,
    "maximum_age": 7,
    "has_capacity": true
  }
]
```

### 4. View Available Classes

```http
GET /api/public/admissions/classes/
```

Returns list of class levels accepting applications.

### 5. Create Application (Draft)

```http
POST /api/public/admissions/applications/
Content-Type: application/json

{
  "admission_session": 1,
  "applying_for_class": 5,

  // Student Information
  "first_name": "John",
  "middle_name": "Paul",
  "last_name": "Doe",
  "gender": "M",
  "date_of_birth": "2018-05-15",

  // Nigerian-specific
  "state_of_origin": "Lagos",
  "lga": "Ikeja",
  "religion": "Christianity",
  "blood_group": "O+",

  // Contact
  "address": "123 Main Street",
  "city": "Lagos",

  // Parent/Guardian
  "parent_first_name": "Jane",
  "parent_last_name": "Doe",
  "parent_email": "jane.doe@email.com",
  "parent_phone": "08012345678",
  "parent_occupation": "Teacher",
  "parent_relationship": "Mother",

  // Alternative Contact (Optional)
  "alt_contact_name": "Uncle Mike",
  "alt_contact_phone": "08098765432",
  "alt_contact_relationship": "Uncle",

  // Previous School (Optional)
  "previous_school": "ABC Nursery School",
  "previous_class": "Nursery 2",

  // Medical (Optional)
  "medical_conditions": "None",
  "special_needs": ""
}
```

**Response:**
```json
{
  "id": 123,
  "application_number": "APP-2024-001",
  "tracking_token": "a1b2c3d4e5f6...64-char-token",
  "status": "DRAFT",
  "full_name": "John Paul Doe",
  "parent_email": "jane.doe@email.com",
  "created_at": "2024-01-15T10:30:00Z",
  "can_submit": false,  // true when application fee is paid
  "next_steps": "Please pay the application fee to submit..."
}
```

**Important:** Save the `tracking_token` - it's the only way to access this application later!

### 6. Track Application

```http
POST /api/public/admissions/applications/track/
Content-Type: application/json

{
  "application_number": "APP-2024-001",
  "parent_email": "jane.doe@email.com"
}
```

OR

```json
{
  "application_number": "APP-2024-001",
  "parent_phone": "08012345678"
}
```

**Response:**
```json
{
  "tracking_token": "a1b2c3d4e5f6...",
  "message": "Application found. Use the tracking token to view details."
}
```

### 7. View Application Details

```http
GET /api/public/admissions/applications/{tracking_token}/
```

**Response:** Full application details including status, fees paid, documents uploaded, etc.

### 8. Update Draft Application

```http
PATCH /api/public/admissions/applications/{tracking_token}/
Content-Type: application/json

{
  "first_name": "Johnny",
  "medical_conditions": "Asthma - managed with inhaler"
}
```

**Note:** Only works when status is `DRAFT`

### 9. Submit Application

```http
POST /api/public/admissions/applications/{tracking_token}/submit/
```

Moves application from `DRAFT` → `SUBMITTED`

**Requirements:**
- Application fee must be paid
- All required fields must be filled

**Response:**
```json
{
  "message": "Application submitted successfully",
  "application": { /* full application details */ }
}
```

### 10. Accept Admission Offer

```http
POST /api/public/admissions/applications/{tracking_token}/accept_offer/
```

Moves application from `APPROVED` → `ACCEPTED`

**Requirements:**
- Application must be in `APPROVED` status
- Acceptance fee must be paid (if required)
- Offer must not be expired

### 11. Get Payment Information

```http
GET /api/public/admissions/applications/{tracking_token}/payment_info/
```

**Response:**
```json
{
  "application_fee": {
    "required": true,
    "amount": 5000,
    "paid": false,
    "payment_date": null
  },
  "exam_fee": {
    "required": true,
    "amount": 2000,
    "paid": false,
    "payment_date": null
  },
  "acceptance_fee": {
    "required": true,
    "amount": 10000,
    "paid": false,
    "payment_date": null,
    "is_part_of_tuition": true
  },
  "total_unpaid": 17000
}
```

### 12. Get Next Steps

```http
GET /api/public/admissions/applications/{tracking_token}/next_steps/
```

**Response:**
```json
{
  "current_status": "SUBMITTED",
  "next_steps": "Your application is under review. We will contact you within 5 business days.",
  "actions_required": [],
  "can_submit": false,
  "can_accept_offer": false
}
```

### 13. Upload Document

```http
POST /api/public/admissions/applications/{tracking_token}/documents/
Content-Type: multipart/form-data

document_type: BIRTH_CERTIFICATE
file: [file upload]
description: Original birth certificate
```

**Document Types:**
- `BIRTH_CERTIFICATE`
- `PASSPORT_PHOTO`
- `PREVIOUS_REPORT`
- `IMMUNIZATION_RECORD`
- `PARENT_ID`
- `OTHER`

### 14. List Documents

```http
GET /api/public/admissions/applications/{tracking_token}/documents/
```

**Response:**
```json
[
  {
    "id": 1,
    "document_type": "BIRTH_CERTIFICATE",
    "document_type_display": "Birth Certificate",
    "file_url": "https://api.school.com/media/admissions/docs/cert.pdf",
    "description": "Original birth certificate",
    "verified": false,
    "uploaded_at": "2024-01-15T14:30:00Z"
  }
]
```

### 15. Delete Document

```http
DELETE /api/public/admissions/documents/{document_id}/
```

**Note:** Only allowed if document is not yet verified

---

## Admin Portal Endpoints

**Base URL:** `/api/admissions/`

**Authentication required** - Admin/staff only

### Session Management

#### List Sessions

```http
GET /api/admissions/sessions/
```

#### Create Session

```http
POST /api/admissions/sessions/
Content-Type: application/json

{
  "name": "2025/2026 Admission",
  "academic_year": 2,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "is_active": true,
  "allow_public_applications": true,
  "application_instructions": "Welcome to our admission process...",
  "require_acceptance_fee": true,
  "acceptance_fee_deadline_days": 14,
  "offer_expiry_days": 30
}
```

#### Activate Session

```http
POST /api/admissions/sessions/{id}/activate/
```

Deactivates all other sessions and activates this one.

#### Get Session Statistics

```http
GET /api/admissions/sessions/{id}/statistics/
```

**Response:**
```json
{
  "total_applications": 150,
  "by_status": {
    "draft": 10,
    "submitted": 25,
    "under_review": 30,
    "approved": 40,
    "rejected": 15,
    "accepted": 20,
    "enrolled": 10
  },
  "by_class": {
    "Primary 1": 50,
    "Primary 2": 40,
    "JSS 1": 60
  },
  "pending_actions": {
    "new_submissions": 25,
    "pending_documents": 8,
    "pending_exams": 12,
    "pending_interviews": 5,
    "awaiting_acceptance": 40
  },
  "revenue": {
    "application_fees": 120,
    "exam_fees": 80,
    "acceptance_fees": 30
  }
}
```

### Application Management

#### List Applications (with Filters)

```http
GET /api/admissions/applications/
```

**Query Parameters:**
- `?session={id}` - Filter by session
- `?status=SUBMITTED` - Filter by status
- `?applying_for_class={id}` - Filter by class
- `?search=John` - Search by name, email, phone, app number
- `?payment_status=paid` or `unpaid`
- `?pending_action=new_submissions` - Show new submissions
- `?pending_action=pending_documents` - Show waiting for docs
- `?pending_action=pending_exams` - Show scheduled exams
- `?pending_action=awaiting_acceptance` - Show approved offers

**Response:**
```json
{
  "count": 150,
  "next": "...",
  "previous": null,
  "results": [
    {
      "id": 123,
      "application_number": "APP-2024-001",
      "full_name": "John Paul Doe",
      "age": 6,
      "gender": "M",
      "applying_for_class": 5,
      "applying_for_class_name": "Primary 1",
      "status": "SUBMITTED",
      "status_display": "Submitted",
      "parent_email": "jane.doe@email.com",
      "parent_phone": "08012345678",
      "application_fee_paid": true,
      "exam_fee_paid": false,
      "acceptance_fee_paid": false,
      "submitted_at": "2024-01-15T10:30:00Z",
      "created_at": "2024-01-14T08:00:00Z"
    }
  ]
}
```

#### View Application Details

```http
GET /api/admissions/applications/{id}/
```

Returns full application details including all fields, documents, assessments, etc.

#### Update Application

```http
PATCH /api/admissions/applications/{id}/
Content-Type: application/json

{
  "admin_notes": "Candidate shows strong potential",
  "application_fee_paid": true
}
```

### Workflow Actions

#### Start Review

```http
POST /api/admissions/applications/{id}/start_review/
```

Changes status: `SUBMITTED` → `UNDER_REVIEW`

#### Request Documents

```http
POST /api/admissions/applications/{id}/request_documents/
Content-Type: application/json

{
  "notes": "Please upload your child's birth certificate and passport photo"
}
```

Changes status: `SUBMITTED`/`UNDER_REVIEW` → `DOCUMENTS_PENDING`

Sends email notification to parent.

#### Schedule Exam

```http
POST /api/admissions/applications/{id}/schedule_exam/
Content-Type: application/json

{
  "exam_date": "2024-02-15",
  "exam_time": "09:00:00",
  "exam_venue": "School Main Hall"
}
```

Changes status → `EXAM_SCHEDULED`

Sends exam invitation email.

#### Mark Exam Completed

```http
POST /api/admissions/applications/{id}/mark_exam_completed/
```

Changes status: `EXAM_SCHEDULED` → `EXAM_COMPLETED`

#### Schedule Interview

```http
POST /api/admissions/applications/{id}/schedule_interview/
Content-Type: application/json

{
  "interview_date": "2024-02-20",
  "interview_time": "14:00:00",
  "interview_venue": "Principal's Office"
}
```

Changes status → `INTERVIEW_SCHEDULED`

Sends interview invitation email.

#### Approve Application

```http
POST /api/admissions/applications/{id}/approve/
Content-Type: application/json

{
  "approval_notes": "Excellent performance. We're pleased to offer admission."
}
```

Changes status → `APPROVED`

Sends admission offer email.

Automatically calculates `offer_expiry_date` based on session settings.

#### Reject Application

```http
POST /api/admissions/applications/{id}/reject/
Content-Type: application/json

{
  "rejection_reason": "Applicant does not meet minimum age requirement for this class."
}
```

Changes status → `REJECTED`

Sends rejection email.

#### Enroll Student

```http
POST /api/admissions/applications/{id}/enroll/
```

**What it does:**
1. Creates `Student` record
2. Creates `CustomUser` account with temporary password
3. Enrolls student in current academic year
4. Changes status → `ENROLLED`
5. Sends enrollment confirmation email with login credentials

**Requirements:**
- Status must be `ACCEPTED`

**Response:**
```json
{
  "message": "Student enrolled successfully",
  "application": { /* application details */ },
  "student_id": 456,
  "username": "jane.doe@email.com"
}
```

**Default Password:** `ChangeMe123!` (user must change on first login)

#### Withdraw Application

```http
POST /api/admissions/applications/{id}/withdraw/
Content-Type: application/json

{
  "withdrawal_reason": "Parent requested withdrawal - enrolled elsewhere"
}
```

Changes status → `WITHDRAWN`

#### Export Applications

```http
GET /api/admissions/applications/export/
```

Downloads CSV file with all applications (respects current filters).

### Document Management

#### List Documents

```http
GET /api/admissions/documents/?application={id}
```

#### Verify Document

```http
POST /api/admissions/documents/{id}/verify/
Content-Type: application/json

{
  "verification_notes": "Birth certificate verified - matches application details"
}
```

Sets `verified = true`

If all required documents are verified, moves application from `DOCUMENTS_PENDING` → `UNDER_REVIEW`

#### Reject Document

```http
POST /api/admissions/documents/{id}/reject/
Content-Type: application/json

{
  "rejection_reason": "Image is too blurry, please upload a clearer copy"
}
```

Sends notification to parent.

### Fee Structure Management

#### List Fee Structures

```http
GET /api/admissions/fee-structures/?session={id}
```

#### Create Fee Structure

```http
POST /api/admissions/fee-structures/
Content-Type: application/json

{
  "admission_session": 1,
  "class_room": 5,
  "application_fee": 5000,
  "application_fee_required": true,
  "entrance_exam_required": true,
  "entrance_exam_fee": 2000,
  "entrance_exam_pass_score": 60,
  "interview_required": false,
  "acceptance_fee": 10000,
  "acceptance_fee_required": true,
  "acceptance_fee_is_part_of_tuition": true,
  "minimum_age": 5,
  "maximum_age": 7,
  "max_applications": 100
}
```

---

## Data Models

### AdmissionApplication

**Key Fields:**
- `application_number` - Unique identifier (e.g., "APP-2024-001")
- `tracking_token` - 64-char random string for anonymous access
- `status` - Current workflow state (see below)
- `admission_session` - Which admission cycle
- `applying_for_class` - Target class level

**Student Info:**
- `first_name`, `middle_name`, `last_name`
- `gender` - "M" or "F"
- `date_of_birth`
- `state_of_origin`, `lga` - Nigerian states/LGAs
- `religion`, `blood_group`
- `address`, `city`

**Parent/Guardian:**
- `parent_first_name`, `parent_last_name`
- `parent_email`, `parent_phone`
- `parent_occupation`, `parent_relationship`
- `alt_contact_name`, `alt_contact_phone`, `alt_contact_relationship`

**Previous Education:**
- `previous_school`, `previous_class`

**Medical:**
- `medical_conditions`, `special_needs`

**Payment Status:**
- `application_fee_paid` - Boolean
- `application_fee_payment_date`
- `exam_fee_paid` - Boolean
- `exam_fee_payment_date`
- `acceptance_fee_paid` - Boolean
- `acceptance_fee_payment_date`

**Exam/Interview:**
- `exam_date`, `exam_time`, `exam_venue`
- `interview_date`, `interview_time`, `interview_venue`

**Admin Fields:**
- `admin_notes` - Internal notes
- `rejection_reason` - Why rejected
- `reviewed_by` - Staff who reviewed
- `approval_notes` - Notes on approval
- `acceptance_deadline` - Deadline to accept offer

**Timestamps:**
- `submitted_at`, `approved_at`, `accepted_at`, `enrolled_at`
- `created_at`, `updated_at`

**Computed Properties:**
- `full_name` - First + middle + last
- `age` - Calculated from date_of_birth
- `can_submit` - True if ready to submit
- `can_accept_offer` - True if ready to accept
- `all_fees_paid` - True if all required fees paid

---

## Workflow States

### State Diagram

```
DRAFT
  ↓ [parent submits]
SUBMITTED
  ↓ [admin starts review]
UNDER_REVIEW
  ↓ [admin requests docs]
DOCUMENTS_PENDING
  ↓ [all docs verified]
UNDER_REVIEW
  ↓ [admin schedules exam]
EXAM_SCHEDULED
  ↓ [exam completed]
EXAM_COMPLETED
  ↓ [admin schedules interview]
INTERVIEW_SCHEDULED
  ↓ [admin approves]
APPROVED
  ↓ [parent accepts]
ACCEPTED
  ↓ [admin enrolls]
ENROLLED
```

**Alternative Paths:**
- Any state → `REJECTED` (admin rejects)
- Any state → `WITHDRAWN` (parent or admin withdraws)

### State Descriptions

1. **DRAFT** - Application created but not submitted
   - Parent can edit all fields
   - Can delete application

2. **SUBMITTED** - Application submitted, awaiting review
   - Parent can no longer edit
   - Admin can start review

3. **UNDER_REVIEW** - Being reviewed by admissions team
   - Admin can request documents, schedule assessments, approve, or reject

4. **DOCUMENTS_PENDING** - Waiting for additional documents
   - Parent can upload documents
   - Auto-transitions to UNDER_REVIEW when all required docs verified

5. **EXAM_SCHEDULED** - Entrance exam scheduled
   - Parent receives exam details via email
   - Admin marks as completed after exam

6. **EXAM_COMPLETED** - Exam taken, awaiting results/next steps
   - Admin can schedule interview or make decision

7. **INTERVIEW_SCHEDULED** - Interview scheduled
   - Parent receives interview details

8. **APPROVED** - Admission offer sent
   - Parent must pay acceptance fee (if required)
   - Parent can accept or decline
   - Offer has expiry date

9. **REJECTED** - Application rejected
   - Terminal state
   - Parent notified with reason

10. **ACCEPTED** - Parent accepted the offer
    - Ready for enrollment
    - Admin can create student account

11. **ENROLLED** - Student enrolled, account created
    - Terminal state (successful)
    - Student and parent receive login credentials

12. **WITHDRAWN** - Application withdrawn
    - Terminal state
    - Can be done by parent or admin

---

## Integration Examples

### Example 1: Parent Application Flow

```javascript
// 1. Get active session and fee structures
const session = await fetch('/api/public/admissions/sessions/active/');
const fees = await fetch(`/api/public/admissions/fee-structures/?session=${session.id}`);

// 2. Create application (DRAFT)
const app = await fetch('/api/public/admissions/applications/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    admission_session: session.id,
    applying_for_class: 5,
    first_name: 'John',
    // ... other fields
  })
});

// IMPORTANT: Save tracking_token!
localStorage.setItem('admission_tracking_token', app.tracking_token);

// 3. Parent goes to pay application fee...

// 4. Update payment status (this would be done by payment webhook)
await fetch(`/api/public/admissions/applications/${app.tracking_token}/`, {
  method: 'PATCH',
  body: JSON.stringify({ application_fee_paid: true })
});

// 5. Submit application
await fetch(`/api/public/admissions/applications/${app.tracking_token}/submit/`, {
  method: 'POST'
});

// Application is now SUBMITTED and parent waits for admin review
```

### Example 2: Admin Review Flow

```javascript
// 1. Get new submissions
const apps = await fetch('/api/admissions/applications/?pending_action=new_submissions', {
  headers: { 'Authorization': 'Bearer <admin_token>' }
});

// 2. View application details
const app = await fetch(`/api/admissions/applications/${appId}/`, {
  headers: { 'Authorization': 'Bearer <admin_token>' }
});

// 3. Start review
await fetch(`/api/admissions/applications/${appId}/start_review/`, {
  method: 'POST',
  headers: { 'Authorization': 'Bearer <admin_token>' }
});

// 4. Request additional documents
await fetch(`/api/admissions/applications/${appId}/request_documents/`, {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer <admin_token>',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    notes: 'Please upload birth certificate'
  })
});

// 5. After docs uploaded, verify them
await fetch(`/api/admissions/documents/${docId}/verify/`, {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer <admin_token>',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    verification_notes: 'Birth certificate verified'
  })
});

// 6. Schedule exam
await fetch(`/api/admissions/applications/${appId}/schedule_exam/`, {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer <admin_token>',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    exam_date: '2024-02-15',
    exam_time: '09:00:00',
    exam_venue: 'Main Hall'
  })
});

// 7. After exam, mark completed
await fetch(`/api/admissions/applications/${appId}/mark_exam_completed/`, {
  method: 'POST',
  headers: { 'Authorization': 'Bearer <admin_token>' }
});

// 8. Approve application
await fetch(`/api/admissions/applications/${appId}/approve/`, {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer <admin_token>',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    approval_notes: 'Excellent candidate'
  })
});

// Parent receives offer email and accepts via public portal...

// 9. Enroll student
const enrollment = await fetch(`/api/admissions/applications/${appId}/enroll/`, {
  method: 'POST',
  headers: { 'Authorization': 'Bearer <admin_token>' }
});

// enrollment.student_id and enrollment.username are now available
```

### Example 3: Application Tracking

```javascript
// Parent lost their tracking token, use email to track
const result = await fetch('/api/public/admissions/applications/track/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    application_number: 'APP-2024-001',
    parent_email: 'jane.doe@email.com'
  })
});

// Save the tracking token
localStorage.setItem('admission_tracking_token', result.tracking_token);

// Now view application
const app = await fetch(`/api/public/admissions/applications/${result.tracking_token}/`);
```

---

## Email Notifications

The system automatically sends emails at key workflow stages:

### 1. Application Confirmation
**Trigger:** Application submitted (DRAFT → SUBMITTED)
**Template:** `admission_confirmation.html`
**To:** Parent email
**Contains:**
- Application number
- Tracking token
- Next steps
- Link to track application

### 2. Documents Required
**Trigger:** Admin requests documents
**Template:** `admission_documents_required.html`
**To:** Parent email
**Contains:**
- List of required documents
- Upload link
- Deadline (if set)

### 3. Exam Scheduled
**Trigger:** Admin schedules exam
**Template:** `admission_exam_scheduled.html`
**To:** Parent email
**Contains:**
- Exam date, time, venue
- What to bring
- Important instructions
- Exam fee status

### 4. Interview Scheduled
**Trigger:** Admin schedules interview
**Template:** `admission_interview_scheduled.html`
**To:** Parent email
**Contains:**
- Interview date, time, venue
- Who should attend
- What to bring

### 5. Admission Offer
**Trigger:** Application approved
**Template:** `admission_approved.html`
**To:** Parent email
**Contains:**
- Congratulations message
- Acceptance fee details
- Offer expiry date
- Link to accept offer

### 6. Rejection Notification
**Trigger:** Application rejected
**Template:** `admission_rejected.html`
**To:** Parent email
**Contains:**
- Polite rejection message
- Reason (if provided)
- Future opportunities

### 7. Acceptance Confirmation
**Trigger:** Parent accepts offer
**Template:** `admission_accepted.html`
**To:** Parent email
**Contains:**
- Welcome message
- Next steps for enrollment
- Documents needed
- Important dates

### 8. Enrollment Complete
**Trigger:** Admin enrolls student
**Template:** `admission_enrolled.html`
**To:** Parent email
**Contains:**
- Student ID
- Login credentials (username & temporary password)
- Portal URL
- Orientation details
- Welcome message

---

## Payment Integration

### Payment Workflow

1. **Get Payment Info**
   ```javascript
   const paymentInfo = await fetch(
     `/api/public/admissions/applications/${trackingToken}/payment_info/`
   );
   ```

2. **Initiate Payment**
   - Use your payment gateway (Paystack, Flutterwave, etc.)
   - Include `application_id` in metadata

3. **Payment Webhook**
   - When payment succeeds, update application:
   ```javascript
   await fetch(`/api/admissions/applications/${appId}/`, {
     method: 'PATCH',
     body: JSON.stringify({
       application_fee_paid: true,
       application_fee_payment_date: new Date().toISOString()
     })
   });
   ```

4. **Link to Finance System**
   - Optionally link to `finance.Receipt` model for full audit trail

---

## Field Validation

### Age Validation
- System automatically validates applicant age against class requirements
- Age calculated from `date_of_birth`
- Must be between `minimum_age` and `maximum_age` for class

### Capacity Validation
- Each class has `max_applications` limit
- System prevents new applications when capacity reached
- Check `has_capacity` in fee structure before allowing application

### Required Fields
**Minimum required:**
- Student: first_name, last_name, date_of_birth, gender
- Parent: parent_email OR parent_phone
- Class: applying_for_class
- Session: admission_session

**All other fields are optional** but recommended for complete application.

---

## Best Practices

### For Frontend Developers

1. **Save Tracking Token**
   - Store in localStorage or parent's account
   - It's the only way to access application without login

2. **Handle Status Changes**
   - Different UI for each status
   - Show relevant actions based on status
   - Display next steps clearly

3. **Validate Before Submit**
   - Check all required fields filled
   - Verify payment status
   - Show clear error messages

4. **Document Upload UX**
   - Support multiple file formats (PDF, JPG, PNG)
   - Show upload progress
   - Display verification status
   - Allow deletion of unverified docs

5. **Payment Flow**
   - Clear payment instructions
   - Show fee breakdown
   - Update UI immediately after payment
   - Handle failed payments gracefully

6. **Mobile Responsiveness**
   - Parents will likely use mobile devices
   - Optimize file uploads for mobile
   - Ensure emails display well on mobile

7. **Email Integration**
   - All workflow emails sent automatically
   - Include tracking links in emails
   - Email templates use school branding from database

---

## Error Handling

### Common Errors

**400 Bad Request**
```json
{
  "error": "Validation error",
  "details": {
    "date_of_birth": ["Applicant must be at least 5 years old for this class"]
  }
}
```

**403 Forbidden**
```json
{
  "error": "Only draft applications can be updated"
}
```

**404 Not Found**
```json
{
  "error": "Application not found or invalid tracking token"
}
```

### Handle Gracefully
- Show user-friendly error messages
- Log errors for debugging
- Provide clear next steps
- Contact support option

---

## Testing Checklist

### Public Portal
- [ ] Create application (DRAFT)
- [ ] Update draft application
- [ ] Track application by email
- [ ] Track application by phone
- [ ] Submit application
- [ ] Upload documents
- [ ] Delete document
- [ ] Accept admission offer
- [ ] View payment info
- [ ] View next steps

### Admin Portal
- [ ] List applications with filters
- [ ] Search applications
- [ ] View application details
- [ ] Start review
- [ ] Request documents
- [ ] Verify documents
- [ ] Schedule exam
- [ ] Mark exam completed
- [ ] Schedule interview
- [ ] Approve application
- [ ] Reject application
- [ ] Enroll student
- [ ] Export to CSV
- [ ] View session statistics

### Email Flow
- [ ] Application confirmation sent
- [ ] Document request sent
- [ ] Exam invitation sent
- [ ] Interview invitation sent
- [ ] Offer letter sent
- [ ] Rejection sent
- [ ] Acceptance confirmation sent
- [ ] Enrollment welcome sent

---

## Support & Documentation

For additional help:
- **Full Documentation:** `/ADMISSION_SYSTEM_COMPLETE.md`
- **Field Reference:** `/ADMISSION_QUICK_FIX.md`
- **Model Definitions:** `/academic/models.py` (AdmissionApplication, AdmissionSession, etc.)
- **Serializers:** `/academic/serializers_admission.py`
- **API Views:** `/academic/views_admission_public.py`, `/academic/views_admission_admin.py`

---

## Quick Reference: API Endpoints Summary

### Public (No Auth)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/public/admissions/sessions/` | List sessions |
| GET | `/api/public/admissions/sessions/active/` | Get active session |
| GET | `/api/public/admissions/fee-structures/` | List fees |
| GET | `/api/public/admissions/classes/` | List classes |
| POST | `/api/public/admissions/applications/` | Create application |
| POST | `/api/public/admissions/applications/track/` | Track by email/phone |
| GET | `/api/public/admissions/applications/{token}/` | View application |
| PATCH | `/api/public/admissions/applications/{token}/` | Update draft |
| POST | `/api/public/admissions/applications/{token}/submit/` | Submit application |
| POST | `/api/public/admissions/applications/{token}/accept_offer/` | Accept offer |
| GET | `/api/public/admissions/applications/{token}/payment_info/` | Payment details |
| GET | `/api/public/admissions/applications/{token}/next_steps/` | Next steps |
| GET | `/api/public/admissions/applications/{token}/documents/` | List documents |
| POST | `/api/public/admissions/applications/{token}/documents/` | Upload document |
| DELETE | `/api/public/admissions/documents/{id}/` | Delete document |

### Admin (Auth Required)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET/POST | `/api/admissions/sessions/` | List/create sessions |
| POST | `/api/admissions/sessions/{id}/activate/` | Activate session |
| GET | `/api/admissions/sessions/{id}/statistics/` | Session stats |
| GET/POST | `/api/admissions/fee-structures/` | List/create fees |
| GET | `/api/admissions/applications/` | List (with filters) |
| GET/PATCH | `/api/admissions/applications/{id}/` | View/update app |
| POST | `/api/admissions/applications/{id}/start_review/` | Start review |
| POST | `/api/admissions/applications/{id}/request_documents/` | Request docs |
| POST | `/api/admissions/applications/{id}/schedule_exam/` | Schedule exam |
| POST | `/api/admissions/applications/{id}/mark_exam_completed/` | Complete exam |
| POST | `/api/admissions/applications/{id}/schedule_interview/` | Schedule interview |
| POST | `/api/admissions/applications/{id}/approve/` | Approve |
| POST | `/api/admissions/applications/{id}/reject/` | Reject |
| POST | `/api/admissions/applications/{id}/enroll/` | Enroll student |
| POST | `/api/admissions/applications/{id}/withdraw/` | Withdraw |
| GET | `/api/admissions/applications/export/` | Export CSV |
| GET | `/api/admissions/documents/` | List documents |
| POST | `/api/admissions/documents/{id}/verify/` | Verify document |
| POST | `/api/admissions/documents/{id}/reject/` | Reject document |

---

**Last Updated:** December 2024
**API Version:** 1.0
**Contact:** Backend Team
