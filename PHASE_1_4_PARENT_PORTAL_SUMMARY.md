# Phase 1.4: Parent Portal & Dashboard

**Implementation Date**: 2025-12-04
**Status**: ✅ Complete
**Module**: Examination - Parent Portal

---

## 🎯 Overview

Phase 1.4 implements a comprehensive **Parent Portal** that provides parents with secure, read-only access to their children's academic information. Parents can monitor their children's performance, attendance, fees, and schedules through a dedicated API.

---

## ✨ Key Features

### 1. **Parent Dashboard**
- Overview of all children with key metrics
- Latest published results summary
- Attendance rates (last 30 days)
- Fee balance status
- Current term and academic year information

### 2. **Academic Results Viewing**
- View all **published** results for each child
- Detailed term-by-term breakdowns
- Subject-level performance
- Class position and grades

### 3. **Attendance Monitoring**
- Daily attendance records
- Attendance summary statistics
- Filter by date range
- Absence reasons and notes

### 4. **Fee Management**
- Current fee balances
- Payment history
- Receipt details
- Fee allocations breakdown

### 5. **Timetable Access**
- View child's class timetable
- Subject schedules with teachers
- Room numbers and timings

---

## 🔐 Security & Permissions

### Permission System

**Two Custom Permission Classes:**

1. **`IsParentOfStudent`**
   - Ensures user has a parent profile
   - Verifies parent-child relationship
   - Blocks access to other children's data

2. **`CanViewChildData`**
   - Extends parent permission
   - Enforces published-only result viewing
   - Allows attendance and fee access

### Security Rules

✅ **Allowed:**
- Parents can ONLY view their own children's data
- Results must be **published** to be visible
- Attendance records are always viewable
- Fee information is always viewable
- Timetables are viewable for assigned classrooms

❌ **Blocked:**
- Parents **cannot** view unpublished results
- Parents **cannot** view other children's data
- Parents **cannot** modify any data
- Parents **cannot** enter marks or attendance

---

## 📡 API Endpoints

### Base URL: `/api/examination/parent/`

---

### 1. Parent Dashboard

**Endpoint:** `GET /api/examination/parent/dashboard/`
**Permission:** `IsParentOfStudent`
**Description:** Overview of all children with summary statistics

**Response:**
```json
{
  "parent_name": "John Doe",
  "parent_email": "john.doe@example.com",
  "parent_phone": "+256700000000",
  "total_children": 2,
  "current_term": "Term 1 2025",
  "current_academic_year": "2025",
  "children": [
    {
      "student_id": 101,
      "admission_number": "STD2023001",
      "full_name": "Jane Doe",
      "classroom": "Primary 4 A",
      "class_level": "Primary 4",
      "latest_result": {
        "term": "Term 1 2025",
        "average": 85.5,
        "position": 3,
        "total_students": 40,
        "grade": "A"
      },
      "attendance_summary": {
        "total_days": 20,
        "absent_days": 1,
        "late_days": 2,
        "attendance_rate": 95.0
      },
      "fee_summary": {
        "total_fees": 500000.00,
        "total_paid": 300000.00,
        "balance": 200000.00,
        "status": "Partial"
      }
    }
  ]
}
```

---

### 2. Children List

**Endpoint:** `GET /api/examination/parent/children/`
**Permission:** `IsParentOfStudent`
**Description:** Get list of parent's children with basic info

**Response:**
```json
{
  "count": 2,
  "children": [
    {
      "id": 101,
      "admission_number": "STD2023001",
      "full_name": "Jane Doe",
      "classroom": "Primary 4 A",
      "class_level": "Primary 4",
      "gender": "Female",
      "date_of_birth": "2015-03-15"
    }
  ]
}
```

---

### 3. Child Detail

**Endpoint:** `GET /api/examination/parent/{student_id}/child_detail/`
**Permission:** `IsParentOfStudent`
**Description:** Detailed information about a specific child

**Response:**
```json
{
  "id": 101,
  "admission_number": "STD2023001",
  "full_name": "Jane Doe",
  "first_name": "Jane",
  "middle_name": "",
  "last_name": "Doe",
  "gender": "Female",
  "date_of_birth": "2015-03-15",
  "classroom": "Primary 4 A",
  "class_level": "Primary 4",
  "admission_date": "2023-01-10T08:00:00Z",
  "blood_group": "O+",
  "religion": "Christian",
  "address": "123 Main St, Kampala, Central"
}
```

---

### 4. Child Results

**Endpoint:** `GET /api/examination/parent/results/child/{child_id}/`
**Permission:** `CanViewChildData`
**Description:** All published results for a child

**Response:**
```json
{
  "child_name": "Jane Doe",
  "admission_number": "STD2023001",
  "total_results": 3,
  "results": [
    {
      "id": 45,
      "student_name": "Jane Doe",
      "term": "Term 1 2025",
      "academic_year": "2025",
      "classroom": "Primary 4 A",
      "average": 85.5,
      "total_marks": 855,
      "possible_marks": 1000,
      "position": 3,
      "total_students": 40,
      "grade": "A",
      "remarks": "Excellent performance",
      "is_published": true,
      "published_date": "2025-03-20T10:00:00Z"
    }
  ]
}
```

---

### 5. Term Result Detail

**Endpoint:** `GET /api/examination/parent/results/{term_result_id}/term/`
**Permission:** `CanViewChildData`
**Description:** Detailed term result with subject breakdown

**Response:**
```json
{
  "term_result": {
    "id": 45,
    "student_name": "Jane Doe",
    "term": "Term 1 2025",
    "average": 85.5,
    "position": 3,
    "grade": "A"
  },
  "subject_results": [
    {
      "id": 301,
      "subject_name": "Mathematics",
      "total_marks": 92,
      "possible_marks": 100,
      "percentage": 92.0,
      "grade": "A",
      "points": 4.0,
      "remarks": "Excellent"
    },
    {
      "id": 302,
      "subject_name": "English",
      "total_marks": 88,
      "possible_marks": 100,
      "percentage": 88.0,
      "grade": "A",
      "points": 4.0,
      "remarks": "Very Good"
    }
  ]
}
```

---

### 6. Child Attendance

**Endpoint:** `GET /api/examination/parent/attendance/child/{child_id}/`
**Permission:** `IsParentOfStudent`
**Query Parameters:**
- `start_date` (optional): Filter from date (YYYY-MM-DD)
- `end_date` (optional): Filter to date (YYYY-MM-DD)
- `status` (optional): Filter by status (absent, late, etc.)

**Response:**
```json
{
  "child_name": "Jane Doe",
  "admission_number": "STD2023001",
  "total_records": 15,
  "attendance": [
    {
      "id": 1201,
      "date": "2025-03-15",
      "status": "Absent",
      "status_code": "A",
      "is_absent": true,
      "is_late": false,
      "is_excused": true,
      "notes": "Medical appointment"
    },
    {
      "id": 1202,
      "date": "2025-03-14",
      "status": "Late",
      "status_code": "L",
      "is_absent": false,
      "is_late": true,
      "is_excused": false,
      "notes": "Traffic"
    }
  ]
}
```

---

### 7. Attendance Summary

**Endpoint:** `GET /api/examination/parent/attendance/summary/{child_id}/`
**Permission:** `IsParentOfStudent`
**Query Parameters:**
- `term_id` (optional): Filter by term
- `year` (optional): Filter by year (YYYY)

**Response:**
```json
{
  "child_name": "Jane Doe",
  "admission_number": "STD2023001",
  "summary": {
    "total_days_tracked": 60,
    "absent_days": 3,
    "late_days": 5,
    "excused_absences": 2,
    "attendance_rate": 95.0,
    "present_days": 57
  }
}
```

---

### 8. Child Fees

**Endpoint:** `GET /api/examination/parent/fees/child/{child_id}/`
**Permission:** `IsParentOfStudent`
**Query Parameters:**
- `term_id` (optional): Filter by term

**Response:**
```json
{
  "child_name": "Jane Doe",
  "admission_number": "STD2023001",
  "summary": {
    "total_fees": 800000.00,
    "total_paid": 500000.00,
    "total_balance": 300000.00,
    "payment_status": "Partial"
  },
  "fees": [
    {
      "id": 501,
      "fee_name": "Tuition Fee - Term 1",
      "fee_type": "Tuition",
      "amount": 500000.00,
      "paid": 300000.00,
      "balance": 200000.00,
      "term": "Term 1 2025",
      "academic_year": "2025",
      "due_date": "2025-03-31",
      "status": "Partial"
    },
    {
      "id": 502,
      "fee_name": "Transport Fee",
      "fee_type": "Transport",
      "amount": 300000.00,
      "paid": 200000.00,
      "balance": 100000.00,
      "term": "Term 1 2025",
      "academic_year": "2025",
      "due_date": "2025-03-31",
      "status": "Partial"
    }
  ]
}
```

---

### 9. Payment History

**Endpoint:** `GET /api/examination/parent/fees/payments/{child_id}/`
**Permission:** `IsParentOfStudent`
**Query Parameters:**
- `start_date` (optional): Filter from date
- `end_date` (optional): Filter to date

**Response:**
```json
{
  "child_name": "Jane Doe",
  "admission_number": "STD2023001",
  "total_payments": 5,
  "total_amount_paid": 500000.00,
  "payments": [
    {
      "id": 801,
      "receipt_number": 1001,
      "date": "2025-03-01",
      "amount": 200000.00,
      "paid_through": "Bank Transfer",
      "payer": "John Doe",
      "term": "Term 1 2025",
      "allocated_to": [
        {
          "fee_name": "Tuition Fee - Term 1",
          "amount_allocated": 150000.00
        },
        {
          "fee_name": "Transport Fee",
          "amount_allocated": 50000.00
        }
      ],
      "notes": "Payment via bank transfer"
    }
  ]
}
```

---

### 10. Child Timetable

**Endpoint:** `GET /api/examination/parent/timetable/child/{child_id}/`
**Permission:** `IsParentOfStudent`
**Query Parameters:**
- `day` (optional): Filter by specific day (Monday, Tuesday, etc.)

**Response:**
```json
{
  "child_name": "Jane Doe",
  "classroom": "Primary 4 A",
  "timetable": {
    "Monday": [
      {
        "subject": "Mathematics",
        "teacher": "John Smith",
        "start_time": "08:00",
        "end_time": "09:00",
        "room_number": "Room 201",
        "notes": null
      },
      {
        "subject": "English",
        "teacher": "Mary Johnson",
        "start_time": "09:00",
        "end_time": "10:00",
        "room_number": "Room 203",
        "notes": null
      }
    ],
    "Tuesday": [...],
    "Wednesday": [...],
    "Thursday": [...],
    "Friday": [...]
  }
}
```

---

## 📊 Data Flow & Architecture

### Permission Flow

```
Request → Authentication → Parent Profile Check → Child Relationship Check → Published Check (for results) → Data Access
```

### Database Relationships

```
Parent (academic.Parent)
  ↓ (parent_guardian FK)
Student (academic.Student)
  ↓ (student FK)
├── TermResult (examination_results.TermResult) [Published Only]
├── StudentAttendance (attendance.StudentAttendance) [All Records]
├── FeeAssignment (finance.FeeAssignment) [All Records]
└── Receipt (finance.Receipt) [All Records]
```

---

## 🔄 Integration with Existing Modules

### 1. **Examination Module**
- Uses `TermResult` and `SubjectResult` models
- Filters by `is_published=True` for parent access
- Reuses existing serializers

### 2. **Attendance Module**
- Reads from `StudentAttendance` model
- Uses `AttendanceStatus` for status codes
- No modifications to existing models

### 3. **Finance Module**
- Reads `FeeAssignment` for balances
- Reads `Receipt` for payment history
- Uses `FeePaymentAllocation` for allocation details

### 4. **Schedule Module**
- Reads `Period` model for timetables
- Filters by child's classroom
- Shows subject and teacher assignments

### 5. **Academic Module**
- Uses `Student`, `Parent`, `ClassRoom` models
- Validates parent-child relationships
- No schema changes required

---

## 🎨 Frontend Integration Examples

### 1. Parent Dashboard Widget

```javascript
// Fetch dashboard data
fetch('/api/examination/parent/dashboard/', {
  headers: {
    'Authorization': 'Bearer ' + token
  }
})
.then(res => res.json())
.then(data => {
  // Display children cards
  data.children.forEach(child => {
    displayChildCard({
      name: child.full_name,
      classroom: child.classroom,
      latestGrade: child.latest_result?.grade,
      attendanceRate: child.attendance_summary.attendance_rate,
      feeBalance: child.fee_summary.balance
    });
  });
});
```

### 2. Results Viewer

```javascript
// Fetch child's results
fetch(`/api/examination/parent/results/child/${childId}/`, {
  headers: {
    'Authorization': 'Bearer ' + token
  }
})
.then(res => res.json())
.then(data => {
  data.results.forEach(result => {
    displayResultCard({
      term: result.term,
      average: result.average,
      position: result.position,
      grade: result.grade
    });
  });
});
```

### 3. Attendance Calendar

```javascript
// Fetch attendance with date range
const startDate = '2025-01-01';
const endDate = '2025-03-31';

fetch(`/api/examination/parent/attendance/child/${childId}/?start_date=${startDate}&end_date=${endDate}`, {
  headers: {
    'Authorization': 'Bearer ' + token
  }
})
.then(res => res.json())
.then(data => {
  renderAttendanceCalendar(data.attendance);
});
```

### 4. Fee Status Display

```javascript
// Fetch fee information
fetch(`/api/examination/parent/fees/child/${childId}/`, {
  headers: {
    'Authorization': 'Bearer ' + token
  }
})
.then(res => res.json())
.then(data => {
  displayFeeSummary({
    totalFees: data.summary.total_fees,
    totalPaid: data.summary.total_paid,
    balance: data.summary.total_balance,
    status: data.summary.payment_status
  });

  data.fees.forEach(fee => {
    displayFeeRow(fee);
  });
});
```

---

## 🧪 Testing Guide

### 1. Setup Test Data

```python
# Create parent user
parent_user = CustomUser.objects.create_user(
    email='parent@example.com',
    password='testpass123',
    first_name='John',
    last_name='Doe'
)

# Create parent profile
parent = Parent.objects.create(
    user=parent_user,
    phone_number='+256700000000',
    email='parent@example.com'
)

# Create child
child = Student.objects.create(
    first_name='Jane',
    last_name='Doe',
    admission_number='STD2023001',
    parent_guardian=parent,
    classroom=primary_4a,
    is_active=True
)

# Create published result
term_result = TermResult.objects.create(
    student=child,
    term=term1,
    academic_year=year_2025,
    is_published=True,  # IMPORTANT!
    average=85.5,
    position=3
)
```

### 2. Test Dashboard Access

```bash
# Login as parent
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "parent@example.com",
    "password": "testpass123"
  }'

# Get dashboard
curl -X GET http://localhost:8000/api/examination/parent/dashboard/ \
  -H "Authorization: Bearer {token}"
```

**Expected Response:**
- Should see all children
- Should see published results only
- Should see attendance and fee summaries

### 3. Test Permission Restrictions

```bash
# Try to access another parent's child (should fail)
curl -X GET http://localhost:8000/api/examination/parent/results/child/999/ \
  -H "Authorization: Bearer {token}"

# Expected: 404 Not Found
```

### 4. Test Published-Only Results

```bash
# Create unpublished result
unpublished_result = TermResult.objects.create(
    student=child,
    term=term2,
    is_published=False  # Not published
)

# Try to fetch results
curl -X GET http://localhost:8000/api/examination/parent/results/child/{child_id}/ \
  -H "Authorization: Bearer {token}"

# Expected: Should NOT see unpublished result
```

---

## 🔒 Security Considerations

### 1. **Authentication Required**
- All endpoints require valid JWT token
- Unauthenticated requests return 401

### 2. **Parent Profile Required**
- User must have associated Parent profile
- Non-parents cannot access endpoints

### 3. **Relationship Validation**
- Every request validates parent-child relationship
- Returns 403/404 for unauthorized access

### 4. **Published-Only Results**
- Draft/unpublished results are hidden
- Only admin can publish results

### 5. **Read-Only Access**
- Parents cannot POST, PUT, PATCH, or DELETE
- All endpoints are GET-only

### 6. **Data Isolation**
- Parents see ONLY their children's data
- No cross-parent data leakage

---

## 📝 Permission Matrix

| Role        | Dashboard | Results (Published) | Results (Unpublished) | Attendance | Fees | Timetable |
|-------------|-----------|---------------------|------------------------|------------|------|-----------|
| Parent      | ✅ Own    | ✅ Own Children     | ❌                     | ✅ Own     | ✅ Own | ✅ Own    |
| Teacher     | ❌        | ✅ Allocated        | ✅ Allocated           | ✅ Class   | ❌    | ✅ Own    |
| Admin       | ✅ All    | ✅ All              | ✅ All                 | ✅ All     | ✅ All | ✅ All    |

---

## 🚀 Deployment Checklist

### Before Deployment:

- [x] Parent permission classes created
- [x] Parent viewsets implemented
- [x] URL routes registered
- [x] Documentation completed
- [ ] Test with real parent accounts
- [ ] Verify published-only filtering
- [ ] Test cross-parent access blocking
- [ ] Performance test with multiple children
- [ ] Frontend integration testing

### Post-Deployment:

- [ ] Monitor API response times
- [ ] Check for unauthorized access attempts
- [ ] Verify data accuracy in parent portal
- [ ] Collect parent feedback
- [ ] Document any issues

---

## 💡 Usage Examples

### Scenario 1: Parent Checks Child's Latest Results

```bash
# 1. Login
token=$(curl -X POST /api/token/ -d '{"username":"parent@example.com","password":"pass"}' | jq -r '.access')

# 2. Get dashboard to see latest results
curl -X GET /api/examination/parent/dashboard/ \
  -H "Authorization: Bearer $token"

# 3. Get detailed results for specific term
curl -X GET /api/examination/parent/results/45/term/ \
  -H "Authorization: Bearer $token"
```

### Scenario 2: Parent Reviews Attendance

```bash
# Get attendance for last 30 days
curl -X GET /api/examination/parent/attendance/child/101/ \
  -H "Authorization: Bearer $token"

# Get attendance summary for current term
curl -X GET "/api/examination/parent/attendance/summary/101/?term_id=5" \
  -H "Authorization: Bearer $token"
```

### Scenario 3: Parent Checks Fee Balance

```bash
# Get current fee status
curl -X GET /api/examination/parent/fees/child/101/ \
  -H "Authorization: Bearer $token"

# Get payment history
curl -X GET /api/examination/parent/fees/payments/101/ \
  -H "Authorization: Bearer $token"
```

### Scenario 4: Parent Views Timetable

```bash
# Get full week timetable
curl -X GET /api/examination/parent/timetable/child/101/ \
  -H "Authorization: Bearer $token"

# Get Monday's schedule only
curl -X GET "/api/examination/parent/timetable/child/101/?day=Monday" \
  -H "Authorization: Bearer $token"
```

---

## 🐛 Troubleshooting

### Issue 1: "User does not have a parent profile"

**Cause:** User account not linked to Parent model

**Solution:**
```python
# Create parent profile for user
parent = Parent.objects.create(
    user=user,
    phone_number='+256700000000'
)
```

---

### Issue 2: Parent sees no results

**Possible Causes:**
1. Results not published yet
2. No results created for child
3. Wrong child ID

**Check:**
```python
# Check if results exist
TermResult.objects.filter(student=child)

# Check if published
TermResult.objects.filter(student=child, is_published=True)
```

---

### Issue 3: 404 when accessing child data

**Cause:** Parent-child relationship not set

**Solution:**
```python
# Link child to parent
child.parent_guardian = parent
child.save()
```

---

### Issue 4: Timetable shows empty

**Cause:** Child not assigned to classroom

**Solution:**
```python
# Assign child to classroom
child.classroom = classroom
child.save()
```

---

## 📈 Future Enhancements (Optional)

### Phase 1.5 Ideas:

1. **Parent-Teacher Messaging**
   - Direct messaging between parents and teachers
   - Message history and notifications

2. **Homework Viewing**
   - Parents can see assigned homework
   - Submission status tracking

3. **Event Notifications**
   - School event calendar
   - Parent-specific notifications

4. **Progress Reports**
   - Visual charts of child's progress
   - Comparison with previous terms

5. **Multiple Children Management**
   - Side-by-side comparison
   - Combined reports for siblings

6. **Mobile App Support**
   - Push notifications for parents
   - Offline data viewing

7. **Document Access**
   - View report cards (PDFs)
   - Download fee receipts

---

## ✅ Files Modified/Created

### New Files:
- `examination/views_parent.py` (810 lines) - Parent viewsets
- `PHASE_1_4_PARENT_PORTAL_SUMMARY.md` - This documentation

### Modified Files:
- `examination/permissions.py` - Added parent permission classes
- `api/examination/urls.py` - Registered parent routes

### No Database Migrations Required
All functionality uses existing models:
- `academic.Parent`
- `academic.Student`
- `examination_results.TermResult`
- `examination_results.SubjectResult`
- `attendance.StudentAttendance`
- `finance.Receipt`
- `finance.FeeAssignment`
- `schedule.Period`

---

## 📞 Support & Feedback

For issues or questions about the Parent Portal:

1. Check this documentation first
2. Review permission matrix for access rules
3. Verify parent-child relationships in database
4. Test with published results only

---

## 🎉 Summary

Phase 1.4 successfully implements a **secure, read-only Parent Portal** that allows parents to:

✅ Monitor children's academic performance
✅ Track attendance and punctuality
✅ View fee balances and payment history
✅ Access class timetables
✅ View only **published** results
✅ Access only **their own children's** data

**Key Achievement:** Parents now have comprehensive visibility into their children's academic journey while maintaining strict data security and privacy controls.

---

**Implementation by**: Claude Code
**Date**: 2025-12-04
**Phase**: 1.4 - Parent Portal & Dashboard
**Status**: ✅ Complete & Ready for Testing
