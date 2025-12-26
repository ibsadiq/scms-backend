# Admission System - Key Features Summary

## Overview

A comprehensive student admission system designed for Nigerian schools that provides full flexibility in configuring acceptance fees and admission requirements per session.

## Core Models

### 1. AdmissionSession
**Purpose:** Configure each admission cycle independently

**Key Configuration Options:**
- Start/end dates for applications
- **Acceptance fee requirement** (mandatory/optional/disabled)
- **Acceptance deadline** (configurable days)
- Application number prefix (e.g., "ADM", "APP")
- Email notification settings
- Custom approval messages

**Example:**
```python
session = AdmissionSession.objects.create(
    name="2025/2026 Admission",
    require_acceptance_fee=True,        # Enable acceptance fee
    acceptance_fee_deadline_days=14,    # 14 days to respond after approval
)
```

### 2. AdmissionFeeStructure
**Purpose:** Define fees per class within a session

**Configurable Fees:**
- **Application fee** (required/optional, amount)
- **Entrance exam fee** (required/optional, amount, pass score)
- **Acceptance fee** (required/optional, amount)
- Acceptance fee can be part of tuition or separate

**Example:**
```python
# Primary 1: Acceptance fee required
AdmissionFeeStructure.objects.create(
    admission_session=session,
    class_room=primary_1,
    application_fee=5000,
    application_fee_required=True,
    acceptance_fee=50000,
    acceptance_fee_required=True,          # ← Must pay to accept
    acceptance_fee_is_part_of_tuition=True # ← Deducted from term 1 fee
)

# Nursery: No acceptance fee
AdmissionFeeStructure.objects.create(
    admission_session=session,
    class_room=nursery,
    application_fee=2000,
    acceptance_fee_required=False,         # ← Can accept without paying
)
```

### 3. AdmissionApplication
**Purpose:** Track individual student applications

**Payment Tracking:**
- `application_fee_paid` + `application_fee_receipt`
- `exam_fee_paid` + `exam_fee_receipt`
- `acceptance_fee_paid` + `acceptance_fee_receipt`
- `acceptance_deadline` (auto-calculated on approval)

**12 Status States:**
1. DRAFT
2. SUBMITTED
3. UNDER_REVIEW
4. DOCUMENTS_PENDING
5. EXAM_SCHEDULED
6. EXAM_COMPLETED
7. INTERVIEW_SCHEDULED
8. APPROVED
9. REJECTED
10. ACCEPTED (by parent)
11. ENROLLED (converted to Student)
12. WITHDRAWN

## Acceptance Fee Scenarios

### Scenario A: Mandatory Acceptance Fee (Most Common)
**Configuration:**
```python
AdmissionSession: require_acceptance_fee=True, acceptance_fee_deadline_days=14
AdmissionFeeStructure: acceptance_fee=50000, acceptance_fee_required=True
```

**Parent Workflow:**
1. Application approved
2. Email: "Pay ₦50,000 within 14 days to accept offer"
3. Parent pays acceptance fee
4. Parent clicks "Accept Offer"
5. Status: APPROVED → ACCEPTED
6. Ready for enrollment

### Scenario B: No Acceptance Fee Required
**Configuration:**
```python
AdmissionSession: require_acceptance_fee=False
AdmissionFeeStructure: acceptance_fee_required=False
```

**Parent Workflow:**
1. Application approved
2. Email: "Click to accept your admission offer"
3. Parent clicks "Accept Offer" (no payment needed)
4. Status: APPROVED → ACCEPTED (immediate)
5. Ready for enrollment

### Scenario C: Optional Acceptance Fee
**Configuration:**
```python
AdmissionSession: require_acceptance_fee=True
AdmissionFeeStructure: acceptance_fee=30000, acceptance_fee_required=False
```

**Parent Workflow:**
1. Application approved
2. Email: "Acceptance fee of ₦30,000 encouraged but not required"
3. Parent can accept immediately OR pay first
4. Payment tracked but not blocking

## External Application Portal

### Public Endpoints (No Authentication)
```
POST   /api/public/admissions/applications/          # Submit application
GET    /api/public/admissions/applications/track/    # Track by app number
POST   /api/public/admissions/applications/{token}/documents/  # Upload docs
POST   /api/public/admissions/applications/{token}/accept/     # Accept offer
```

### Features
- No login required to apply
- Mobile-responsive form
- Auto-save drafts
- Application number for tracking
- Payment gateway integration (Paystack, Flutterwave)
- Document upload (birth cert, passport, previous results)

## Nigerian School-Specific Features

✅ **State of Origin & LGA** - All Nigerian states and local governments
✅ **Multiple Contacts** - Primary parent + alternative contact
✅ **Previous School Info** - Transfer tracking
✅ **Age Validation** - Per-class age requirements
✅ **Blood Group** - Medical records
✅ **Payment Gateways** - Paystack/Flutterwave integration
✅ **Naira Currency** - ₦ formatting

## Integration with Existing System

### Enrollment Process
When admin clicks "Enroll Student", the system automatically:

```python
def enroll_student_from_application(application):
    # 1. Create Student record
    student = Student.objects.create(...)

    # 2. Link/Create Parent (reuses if phone exists)
    parent, created = Parent.objects.get_or_create(
        phoneNumber=application.parent_phone,
        defaults={...}
    )

    # 3. Create StudentClassEnrollment
    StudentClassEnrollment.objects.create(
        student=student,
        class_room=application.applying_for_class,
        academic_year=application.academic_year
    )

    # 4. Assign FeeStructure (existing system)
    StudentFeeAssignment.objects.create(
        student=student,
        fee_structure=current_term_fee,
        # Deduct acceptance fee if applicable
    )

    # 5. Update application
    application.status = ENROLLED
    application.enrolled_student = student

    # 6. Send welcome emails
    send_welcome_parent_email(parent)
```

## Admin Dashboard Features

### Statistics
- Total applications (current session)
- Applications by status
- Applications by class
- Approval rate %
- Pending reviews
- Documents pending verification
- Upcoming exams/interviews
- Revenue from admission fees

### Bulk Actions
- Export to CSV/Excel
- Bulk approve/reject
- Send reminder emails
- Generate reports

### Filters
- By status
- By class
- By date range
- By payment status
- By exam scores

## Email Automation

### Emails Sent to Parents
1. **Application Confirmation** - After submission
2. **Payment Instructions** - Fee payment links
3. **Document Request** - Missing documents
4. **Exam Schedule** - Date, time, venue
5. **Interview Schedule** - Date, time
6. **Approval** - Congratulations + acceptance instructions
7. **Rejection** - Polite notice with reason
8. **Acceptance Confirmation** - After parent accepts
9. **Enrollment Welcome** - Login credentials

### Emails Sent to Admin
1. **New Application** - When submitted
2. **Document Uploaded** - For verification
3. **Payment Received** - Fee notifications
4. **Deadline Approaching** - Acceptance deadline warnings

## Configuration Flexibility

### Per-Session Configuration
Each admission session can have completely different rules:
- Different application fees
- Different acceptance requirements
- Different deadlines
- Different exam requirements
- Different capacity limits

### Per-Class Configuration
Within the same session, each class can have:
- Different fee amounts
- Different entrance exam requirements
- Different interview requirements
- Different acceptance fee policies
- Different application capacity

## Example: Complete Setup

```python
from academic.models import AdmissionSession, AdmissionFeeStructure
from administration.models import AcademicYear

# 1. Create academic year
year = AcademicYear.objects.create(year=2025, is_current=True)

# 2. Create admission session
session = AdmissionSession.objects.create(
    academic_year=year,
    name="2025/2026 New Students Admission",
    start_date="2025-01-15",
    end_date="2025-04-30",
    require_acceptance_fee=True,
    acceptance_fee_deadline_days=21,  # 3 weeks
    allow_public_applications=True,
    send_confirmation_emails=True,
    application_instructions="Welcome to our school! Please fill all fields carefully.",
    is_active=True
)

# 3. Set up fees for each class
classes_config = [
    # (class, app_fee, exam_required, exam_fee, acceptance_fee, acceptance_required)
    (nursery_1, 2000, False, 0, 0, False),           # Nursery: simple
    (nursery_2, 2000, False, 0, 0, False),
    (primary_1, 5000, True, 8000, 40000, True),      # Primary: with exam
    (primary_2, 5000, True, 8000, 40000, True),
    (jss_1, 7500, True, 12000, 75000, True),         # JSS: strict requirements
    (jss_2, 7500, True, 12000, 75000, True),
]

for class_room, app_fee, exam_req, exam_fee, accept_fee, accept_req in classes_config:
    AdmissionFeeStructure.objects.create(
        admission_session=session,
        class_room=class_room,
        application_fee=app_fee,
        application_fee_required=True,
        entrance_exam_required=exam_req,
        entrance_exam_fee=exam_fee,
        entrance_exam_pass_score=50.00 if exam_req else None,
        acceptance_fee=accept_fee,
        acceptance_fee_required=accept_req,
        acceptance_fee_is_part_of_tuition=True,
        interview_required=(class_room.name.startswith('JSS')),  # Interview for JSS only
        max_applications=50  # Max 50 per class
    )

print("✅ Admission session configured successfully!")
print(f"📅 Applications open: {session.start_date}")
print(f"📅 Applications close: {session.end_date}")
print(f"💰 Acceptance fee required: {session.require_acceptance_fee}")
print(f"⏰ Acceptance deadline: {session.acceptance_fee_deadline_days} days")
```

## Comprehensive Assessment System

### Multiple Assessment Types
The system supports **8 different assessment types**:

1. **Entrance Examination** - Traditional written exams with multiple subjects
2. **Interview** - Panel or one-on-one interviews with rating criteria
3. **Aptitude Test** - Logical reasoning and problem-solving
4. **Screening Test** - Quick initial assessment
5. **Oral Test** - Verbal assessments
6. **Practical Assessment** - Hands-on skills evaluation
7. **Psychometric Test** - Personality and behavioral assessment
8. **Portfolio Review** - For creative/arts programs

### Key Assessment Features

✅ **Multiple Assessments per Application** - Combine exam + interview + aptitude test
✅ **Assessment Templates** - Reusable templates with predefined criteria
✅ **Detailed Scoring** - Break down assessments into multiple criteria/subjects
✅ **Weighted Criteria** - Give different importance to different criteria
✅ **Assessor Assignment** - Assign specific staff members to conduct assessments
✅ **Scheduling & Venues** - Track date, time, location, duration
✅ **Status Tracking** - scheduled → in_progress → completed/no_show/cancelled
✅ **Pass/Fail Logic** - Automatic pass determination based on scores
✅ **Rich Feedback** - Notes, strengths, areas for improvement, recommendations
✅ **Assessment Dashboard** - View all upcoming assessments by date

### Assessment Models

**AdmissionAssessment** - Individual assessment instance
- Links to application
- Scheduling details (date, venue, duration, assessor)
- Overall score and pass/fail status
- Detailed feedback and recommendations

**AssessmentCriterion** - Individual scoring components
- Subject/skill name (e.g., "Mathematics", "Communication Skills")
- Max score and achieved score
- Weight/importance multiplier
- Specific feedback per criterion

**AssessmentTemplate** - Reusable assessment blueprints
- Predefined criteria and scoring structure
- Default settings (duration, pass mark, instructions)
- Applicable to specific classes
- One-click creation of assessments from templates

**AssessmentTemplateCriterion** - Template components
- Predefined criteria for templates
- Ensures consistency across admission cycles

### Example: JSS 1 Admission with Multiple Assessments

```
Applicant: Amaka Johnson (ADM/2025/156)

Assessment 1: Written Entrance Exam ✅ PASSED
├─ Mathematics: 45/50 (90%)
├─ English: 42/50 (84%)
├─ Science: 35/40 (87.5%)
└─ Overall: 122/140 (87%) - PASSED (pass mark: 70%)

Assessment 2: Aptitude Test ✅ PASSED
├─ Logical Reasoning: 18/20
├─ Problem Solving: 16/20
└─ Overall: 34/40 (85%) - PASSED

Assessment 3: Panel Interview ✅ PASSED
├─ Communication Skills: 9/10 (weight: 1.0)
├─ Confidence: 8/10 (weight: 1.0)
├─ Subject Knowledge: 14/15 (weight: 1.5) ← Weighted higher
├─ Critical Thinking: 9/10 (weight: 1.2)
└─ Overall: 45/50 (90%) - PASSED

All Assessments: PASSED ✅
Recommendation: Highly Recommended
Admin Decision: APPROVED
```

## Benefits

✅ **Maximum Flexibility** - Configure every aspect per session/class
✅ **Comprehensive Assessments** - 8 assessment types with detailed criteria
✅ **Assessment Templates** - Reusable templates for consistency
✅ **Multiple Assessments** - Combine different assessment types per applicant
✅ **Weighted Scoring** - Prioritize important criteria
✅ **Nigerian Context** - Built for Nigerian schools (states, LGAs, payment gateways)
✅ **External Portal** - Parents apply without login
✅ **Seamless Integration** - Works with existing Student/Parent/Fee models
✅ **Complete Tracking** - 12-state workflow with full audit trail
✅ **Automated Emails** - Parents and admins stay informed
✅ **Payment Integration** - Links to existing finance.Receipt model
✅ **Acceptance Fee Options** - Mandatory, optional, or disabled
✅ **Deadline Management** - Auto-calculate and track acceptance deadlines
✅ **Rich Reporting** - Statistics, exports, revenue tracking, assessment analytics

## Next Implementation Steps

1. **Database Models** - Create AdmissionSession, AdmissionFeeStructure, AdmissionApplication, AdmissionDocument
2. **API Endpoints** - Public (external portal) + Admin (management)
3. **Email Templates** - All admission-related emails
4. **Admin Interface** - Application management dashboard
5. **Frontend Integration Guide** - For external admission portal
