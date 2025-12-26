# Result Computation API - Testing Guide

**Date**: 2025-12-04
**Status**: ✅ All System Tests Passed (5/5)

---

## 🎉 Test Results Summary

```
✓ PASS - Models (TermResult, SubjectResult working)
✓ PASS - Grade Scale Configuration (1 scale with 6 rules)
✓ PASS - Grading Engine (configurable grading working)
✓ PASS - Data Availability (504 students, 12 classrooms, 3 terms)
✓ PASS - Result Computation (service initialized successfully)
```

**Current Grade Scale**: Standard Grade Scale
```
90-100  → A (4.0)
80-89   → B (3.5)
70-79   → C (3.0)
60-69   → D (2.5)
50-59   → E (2.0)
0-49    → F (1.0)
```

---

## 📋 Prerequisites

Before testing the API, ensure you have:

1. ✅ **Migrations run**: `uv run manage.py migrate`
2. ✅ **Grade scale configured**: Check Django Admin → Grade Scales
3. ⚠️ **Marks data entered**: You need CA and Exam marks in MarksManagement

### How to Add Marks (Required)

You need to enter marks for students before computing results. Use one of these methods:

#### Option 1: Via Django Admin
1. Go to: http://localhost:8000/admin/examination/marksmanagement/
2. For each student and subject:
   - Create CA marks (exam name containing 'CA' or 'Test')
   - Create Exam marks (final exam)

#### Option 2: Via API
```http
POST /api/examination/marks/
Content-Type: application/json
Authorization: Bearer {token}

{
  "exam_name": 1,  // ExaminationListHandler ID (CA or Exam)
  "student": 5,     // StudentClassEnrollment ID
  "subject": 3,     // Subject ID
  "points_scored": 35,
  "created_by": 1   // Teacher/User ID
}
```

---

## 🚀 API Endpoint Testing

### 1. Compute Results for a Classroom

**Endpoint**: `POST /api/examination/term-results/compute/`

**Request**:
```http
POST http://localhost:8000/api/examination/term-results/compute/
Content-Type: application/json
Authorization: Bearer {your_token}

{
  "term_id": 1,
  "classroom_id": 1,
  "grade_scale_id": 1,  // Optional - uses default if not provided
  "recompute": false
}
```

**Expected Response** (Success):
```json
{
  "message": "Results computed successfully",
  "summary": {
    "total_students": 42,
    "computed": 42,
    "failed": 0,
    "errors": []
  }
}
```

**Expected Response** (Results Already Exist):
```json
{
  "error": "Results already exist for this classroom and term. Set recompute=true to recompute."
}
```

**Expected Response** (No Marks):
```json
{
  "error": "Computation failed: No marks found for student..."
}
```

---

### 2. Get Classroom Results (Ranked)

**Endpoint**: `GET /api/examination/term-results/by_classroom/`

**Request**:
```http
GET http://localhost:8000/api/examination/term-results/by_classroom/?classroom_id=1&term_id=1
Authorization: Bearer {your_token}
```

**Response**:
```json
[
  {
    "id": 1,
    "student": 5,
    "student_name": "John Doe",
    "student_admission_number": "2024/001",
    "term": 1,
    "term_name": "One",
    "academic_year": 1,
    "academic_year_name": "2025/2026",
    "classroom": 1,
    "classroom_name": "Primary 1",
    "total_marks": 850.00,
    "total_possible": 1000.00,
    "average_percentage": 85.00,
    "percentage_str": "85.00%",
    "grade": "B",
    "gpa": 3.50,
    "position_in_class": 1,
    "total_students": 42,
    "is_published": false,
    "published_date": null,
    "computed_date": "2025-12-04T10:30:00Z",
    "status": "Unpublished"
  }
]
```

---

### 3. Get Student Results

**Endpoint**: `GET /api/examination/term-results/by_student/`

**Request**:
```http
GET http://localhost:8000/api/examination/term-results/by_student/?student_id=5&term_id=1
Authorization: Bearer {your_token}
```

**Response**: Same format as classroom results, but filtered for one student.

---

### 4. Get Detailed Result with Subject Breakdown

**Endpoint**: `GET /api/examination/term-results/{id}/`

**Request**:
```http
GET http://localhost:8000/api/examination/term-results/1/
Authorization: Bearer {your_token}
```

**Response**:
```json
{
  "id": 1,
  "student": 5,
  "student_name": "John Doe",
  "student_admission_number": "2024/001",
  "term": 1,
  "term_name": "One",
  "academic_year": 1,
  "academic_year_name": "2025/2026",
  "classroom": 1,
  "classroom_name": "Primary 1",
  "total_marks": 850.00,
  "total_possible": 1000.00,
  "average_percentage": 85.00,
  "percentage_str": "85.00%",
  "grade": "B",
  "gpa": 3.50,
  "position_in_class": 1,
  "total_students": 42,
  "class_teacher_remarks": "",
  "principal_remarks": "",
  "computed_date": "2025-12-04T10:30:00Z",
  "computed_by": 1,
  "computed_by_name": "Admin User",
  "is_published": false,
  "published_date": null,
  "subject_results": [
    {
      "id": 1,
      "subject": 3,
      "subject_name": "Mathematics",
      "subject_code": "MATH101",
      "teacher": 2,
      "teacher_name": "Jane Smith",
      "ca_score": 35.00,
      "ca_max": 40.00,
      "exam_score": 55.00,
      "exam_max": 60.00,
      "total_score": 90.00,
      "total_possible": 100.00,
      "percentage": 90.00,
      "grade": "A",
      "grade_point": 4.00,
      "position_in_subject": 1,
      "total_students": 42,
      "highest_score": 90.00,
      "lowest_score": 45.00,
      "class_average": 72.50,
      "teacher_remarks": "",
      "status": "Excellent"
    }
  ],
  "status": "Unpublished"
}
```

---

### 5. Update Remarks

**Endpoint**: `PATCH /api/examination/term-results/{id}/`

**Request**:
```http
PATCH http://localhost:8000/api/examination/term-results/1/
Content-Type: application/json
Authorization: Bearer {your_token}

{
  "class_teacher_remarks": "Excellent performance. Keep it up!",
  "principal_remarks": "Well done. Continue working hard."
}
```

**Response**:
```json
{
  "id": 1,
  "student_name": "John Doe",
  ...
  "class_teacher_remarks": "Excellent performance. Keep it up!",
  "principal_remarks": "Well done. Continue working hard.",
  ...
}
```

---

### 6. Publish Results

**Endpoint**: `POST /api/examination/term-results/publish/`

**Request**:
```http
POST http://localhost:8000/api/examination/term-results/publish/
Content-Type: application/json
Authorization: Bearer {your_token}

{
  "term_id": 1,
  "classroom_id": 1,
  "action": "publish"
}
```

**Response**:
```json
{
  "message": "Results published successfully",
  "term": "One",
  "classroom": "Primary 1"
}
```

---

### 7. Unpublish Results

**Request**:
```http
POST http://localhost:8000/api/examination/term-results/publish/
Content-Type: application/json
Authorization: Bearer {your_token}

{
  "term_id": 1,
  "classroom_id": 1,
  "action": "unpublish"
}
```

---

### 8. Recompute Results (After Mark Updates)

**Use Case**: Teacher updated a mark and wants to recompute results.

**Request**:
```http
POST http://localhost:8000/api/examination/term-results/compute/
Content-Type: application/json
Authorization: Bearer {your_token}

{
  "term_id": 1,
  "classroom_id": 1,
  "recompute": true  // This will delete and recompute
}
```

---

## 🧪 Testing Workflow

### Complete Test Scenario

1. **Add Marks for Students** (via admin or API)
   - CA marks for all subjects
   - Exam marks for all subjects

2. **Compute Results**
   ```bash
   curl -X POST http://localhost:8000/api/examination/term-results/compute/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer {token}" \
     -d '{"term_id": 1, "classroom_id": 1}'
   ```

3. **View Results**
   ```bash
   curl -X GET "http://localhost:8000/api/examination/term-results/by_classroom/?classroom_id=1&term_id=1" \
     -H "Authorization: Bearer {token}"
   ```

4. **Add Remarks** (for top students)
   ```bash
   curl -X PATCH http://localhost:8000/api/examination/term-results/1/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer {token}" \
     -d '{"class_teacher_remarks": "Excellent work!"}'
   ```

5. **Publish Results**
   ```bash
   curl -X POST http://localhost:8000/api/examination/term-results/publish/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer {token}" \
     -d '{"term_id": 1, "classroom_id": 1, "action": "publish"}'
   ```

6. **Verify Published Status**
   - Non-staff users can now see results
   - Check `is_published: true` in response

---

## 🔍 Common Test IDs (From Your Database)

Based on your test results:
- **Students**: 504 active students
- **Classrooms**: 12 classrooms (e.g., "Primary 1" is ID 1)
- **Terms**: 3 terms (e.g., "One" is ID 1)
- **Academic Year**: "2025/2026"
- **Grade Scale**: "Standard Grade Scale" (ID 1)

### Find Your IDs

Run these commands to get actual IDs:

```bash
# Get classroom IDs
uv run python manage.py shell -c "from academic.models import ClassRoom; [print(f'{c.id}: {c}') for c in ClassRoom.objects.all()]"

# Get term IDs
uv run python manage.py shell -c "from administration.models import Term; [print(f'{t.id}: {t.name}') for t in Term.objects.all()]"

# Get student IDs for a classroom
uv run python manage.py shell -c "from academic.models import Student; [print(f'{s.id}: {s.full_name}') for s in Student.objects.filter(classroom_id=1, is_active=True)[:5]]"
```

---

## ⚠️ Important Notes

### Permission Requirements
- **Staff users**: Can see all results (published and unpublished)
- **Non-staff users**: Can only see published results
- **Computation**: Only authenticated staff can compute results
- **Publishing**: Only authenticated staff can publish/unpublish

### Result Integrity
- Results are computed once and stored
- Any mark changes require recomputation with `recompute=true`
- Publishing control ensures results aren't visible until approved

### Current Limitations
1. **CA Aggregation**: Sums all CA marks - may need normalization if tests have different max scores
2. **Exam Selection**: Takes most recent exam - may need to specify which exam to use
3. **Missing Marks**: Students with no marks default to 0 - consider validation

---

## 🐛 Troubleshooting

### "No subjects allocated to classroom"
**Solution**: Create `AllocatedSubject` records linking Teacher → Subject → Classroom for the term.

### "Student not enrolled in classroom"
**Solution**: Create `StudentClassEnrollment` record for the student and classroom.

### "Results already exist"
**Solution**: Use `recompute=true` to overwrite existing results.

### "No marks found for student"
**Solution**: Ensure marks are entered in `MarksManagement` for both CA and Exam.

### "401 Unauthorized"
**Solution**: Ensure you're passing a valid JWT token in the Authorization header.

---

## 📊 Expected Data Flow

```
1. Teacher enters marks → MarksManagement
   ├─ CA marks (Tests, Quizzes)
   └─ Exam marks (Final Exam)

2. Admin triggers computation → POST /api/examination/term-results/compute/
   ├─ ResultComputationService runs
   ├─ Aggregates marks per subject
   ├─ Applies grade scale
   ├─ Calculates GPA and rankings
   └─ Creates TermResult + SubjectResults

3. Results available in system
   ├─ Admin reviews in Django Admin
   ├─ Teachers add remarks via API
   └─ Admin publishes via API

4. Published results visible to:
   ├─ Parents (via parent portal - Phase 1.4)
   ├─ Students (via student portal)
   └─ Report cards (Phase 1.2)
```

---

## ✅ Next Steps After API Testing

Once you've successfully tested the API:

1. **Phase 1.2**: Report Card Generator (PDF generation)
2. **Phase 1.3**: Teacher Permissions for Result Entry
3. **Phase 1.4**: Parent Portal & Dashboard
4. **Phase 1.5**: Automated Notifications System

---

**🎓 System Status**: Ready for API testing!

To test with real data, you need to:
1. Add marks in MarksManagement (CA + Exam marks)
2. Use the API endpoints above to compute and manage results

**Created by**: Claude Code
**Test Date**: 2025-12-04
**Test Status**: 5/5 Passed ✅
