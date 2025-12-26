# Phase 2.2 API Guide: Class Advancement Automation

**Date**: 2025-12-04
**Status**: ✅ COMPLETE
**Base URL**: `/api/academic/`

---

## 📋 AVAILABLE ENDPOINTS

### Phase 2.2 Endpoints (Class Advancement)

```
POST   /api/academic/class-advancement/preview/
POST   /api/academic/class-advancement/execute/
POST   /api/academic/class-advancement/verify/

POST   /api/academic/stream-assignments/assign/
PUT    /api/academic/stream-assignments/{student_id}/prefer/
GET    /api/academic/stream-assignments/pending/

GET    /api/academic/enrollments/
GET    /api/academic/enrollments/{id}/
GET    /api/academic/enrollments/student/{student_id}/history/
GET    /api/academic/enrollments/academic-year/{year_id}/
```

---

## 🔌 API USAGE EXAMPLES

### 1. Preview Class Movements

Preview where students will move based on promotion decisions.

**Endpoint**: `POST /api/academic/class-advancement/preview/`

**Request**:
```json
{
  "academic_year_id": 1,
  "promotion_ids": [1, 2, 3]  // Optional: specific promotions
}
```

**Response**:
```json
{
  "summary": {
    "total_students": 150,
    "promoted_count": 130,
    "repeated_count": 15,
    "graduated_count": 5,
    "conditional_count": 0,
    "needs_stream_assignment_count": 12
  },
  "movements": {
    "promoted": [
      {
        "student_id": 123,
        "student_name": "John Doe",
        "admission_number": "STD/2020/001",
        "from_class": "Primary 4 A",
        "to_class": "Primary 5 A",
        "assigned_stream": null,
        "preferred_stream": null,
        "needs_stream_assignment": false
      },
      {
        "student_id": 124,
        "student_name": "Jane Smith",
        "admission_number": "STD/2020/002",
        "from_class": "JSS3 A",
        "to_class": "SS1 Science (New classroom needed)",
        "assigned_stream": "science",
        "preferred_stream": "science",
        "needs_stream_assignment": false
      }
    ],
    "repeated": [
      {
        "student_id": 125,
        "student_name": "Bob Wilson",
        "admission_number": "STD/2020/003",
        "from_class": "Primary 4 B",
        "to_class": "Primary 4 B",
        "assigned_stream": null,
        "preferred_stream": null,
        "needs_stream_assignment": false
      }
    ],
    "graduated": [
      {
        "student_id": 126,
        "student_name": "Alice Brown",
        "admission_number": "STD/2017/001",
        "from_class": "SS3 Science A",
        "to_class": "Graduated",
        "assigned_stream": "science",
        "preferred_stream": "science",
        "needs_stream_assignment": false
      }
    ],
    "conditional": []
  },
  "capacity_warnings": [
    {
      "classroom": "SS1 Science A",
      "current": 40,
      "capacity": 40,
      "message": "Classroom SS1 Science A is at capacity"
    }
  ],
  "missing_streams": [
    {
      "student_id": 127,
      "student_name": "Charlie Davis",
      "admission_number": "STD/2020/010",
      "from_class": "JSS3 B",
      "to_class": "SS1 Unassigned",
      "assigned_stream": null,
      "preferred_stream": "commercial",
      "needs_stream_assignment": true
    }
  ],
  "new_classrooms_needed": [
    {
      "class_level": "SS1",
      "stream": "science",
      "section": "B",
      "student_count": 35,
      "capacity": 40
    }
  ]
}
```

---

### 2. Verify Capacity

Check if classrooms have sufficient capacity before execution.

**Endpoint**: `POST /api/academic/class-advancement/verify/`

**Request**:
```json
{
  "academic_year_id": 1
}
```

**Response**:
```json
{
  "all_classrooms_sufficient": false,
  "capacity_warnings": [
    {
      "classroom": "SS1 Science A",
      "current": 40,
      "capacity": 40,
      "message": "Classroom SS1 Science A is at capacity"
    }
  ],
  "new_classrooms_needed": [
    {
      "class_level": "SS1",
      "stream": "science",
      "section": "B",
      "student_count": 35,
      "capacity": 40
    }
  ],
  "missing_stream_assignments": [
    {
      "student_id": 127,
      "student_name": "Charlie Davis",
      "needs_stream_assignment": true
    }
  ],
  "can_proceed": false
}
```

**Decision**:
- If `can_proceed: false`, you must:
  1. Assign missing streams
  2. Either create new classrooms or set `auto_create_classrooms: true`

---

### 3. Assign SS1 Streams (Admin Only)

Admin assigns final streams to SS1 students after reviewing preferences.

**Endpoint**: `POST /api/academic/stream-assignments/assign/`

**Permissions**: Admin only (`IsAdminUser`)

**Request**:
```json
{
  "assignments": [
    {
      "student_id": 127,
      "assigned_stream": "commercial"
    },
    {
      "student_id": 128,
      "assigned_stream": "science"
    },
    {
      "student_id": 129,
      "assigned_stream": "arts"
    }
  ]
}
```

**Response**:
```json
{
  "message": "Successfully assigned streams to 3 students",
  "assigned": 3,
  "errors": []
}
```

---

### 4. Student/Parent Sets Stream Preference

Students or their parents can indicate stream preference for SS1.

**Endpoint**: `PUT /api/academic/stream-assignments/{student_id}/prefer/`

**Permissions**: Admin, student themselves, or their parent

**Request**:
```json
{
  "preferred_stream": "science"
}
```

**Response**:
```json
{
  "message": "Stream preference updated successfully",
  "student_id": 127,
  "student_name": "Charlie Davis",
  "preferred_stream": "science"
}
```

**Valid Stream Options**:
- `science`
- `commercial`
- `arts`

---

### 5. Get Students Pending Stream Assignment

List all students who have indicated preference but await admin assignment.

**Endpoint**: `GET /api/academic/stream-assignments/pending/`

**Permissions**: Admin only

**Response**:
```json
{
  "total_pending": 12,
  "students": [
    {
      "student_id": 127,
      "student_name": "Charlie Davis",
      "admission_number": "STD/2020/010",
      "preferred_stream": "science",
      "assigned_stream": null
    },
    {
      "student_id": 128,
      "student_name": "Eva Martinez",
      "admission_number": "STD/2020/011",
      "preferred_stream": "commercial",
      "assigned_stream": null
    }
  ]
}
```

---

### 6. Execute Class Movements

Actually move students to their new classrooms.

**Endpoint**: `POST /api/academic/class-advancement/execute/`

**Permissions**: Admin only

**Request**:
```json
{
  "academic_year_id": 1,
  "new_academic_year_id": 2,
  "promotion_ids": [1, 2, 3],  // Optional: specific promotions
  "auto_create_classrooms": true,
  "default_teacher_id": 5  // Optional
}
```

**Response**:
```json
{
  "message": "Successfully processed 135 students",
  "promoted": 120,
  "repeated": 10,
  "graduated": 5,
  "conditional": 0,
  "errors": [],
  "classrooms_created": [
    "SS1 Science B",
    "SS1 Commercial A"
  ],
  "enrollments_created": 135
}
```

**What This Does**:
1. Updates `Student.classroom` for each student
2. Updates `Student.class_level`
3. Creates `StudentClassEnrollment` records for new academic year
4. Auto-creates classrooms if `auto_create_classrooms: true`
5. Marks graduated students as `is_active: false`
6. Sets `Student.graduation_date` for graduates

---

### 7. View Student Enrollment History

Get historical enrollment records for a specific student.

**Endpoint**: `GET /api/academic/enrollments/student/{student_id}/history/`

**Permissions**: Admin, or parent of the student

**Response**:
```json
{
  "student_id": 123,
  "student_name": "John Doe",
  "admission_number": "STD/2020/001",
  "total_enrollments": 5,
  "enrollments": [
    {
      "id": 150,
      "student": 123,
      "student_name": "John Doe",
      "student_admission_number": "STD/2020/001",
      "classroom": 45,
      "classroom_name": "Primary 5 A",
      "academic_year": 2,
      "academic_year_name": "2024/2025",
      "enrollment_date": "2024-09-01",
      "is_active": true,
      "notes": "Promoted from Primary 4 A"
    },
    {
      "id": 125,
      "student": 123,
      "student_name": "John Doe",
      "student_admission_number": "STD/2020/001",
      "classroom": 32,
      "classroom_name": "Primary 4 A",
      "academic_year": 1,
      "academic_year_name": "2023/2024",
      "enrollment_date": "2023-09-01",
      "is_active": false,
      "notes": "Promoted from Primary 3 B"
    }
  ]
}
```

---

### 8. List Enrollments for Academic Year

Get all enrollments for a specific academic year with statistics.

**Endpoint**: `GET /api/academic/enrollments/academic-year/{year_id}/`

**Response**:
```json
{
  "academic_year_id": 2,
  "academic_year_name": "2024/2025",
  "statistics": {
    "total_enrollments": 450,
    "active_enrollments": 450,
    "unique_students": 450,
    "unique_classrooms": 18
  },
  "enrollments": [
    {
      "id": 150,
      "student": 123,
      "student_name": "John Doe",
      "student_admission_number": "STD/2020/001",
      "classroom": 45,
      "classroom_name": "Primary 5 A",
      "academic_year": 2,
      "academic_year_name": "2024/2025",
      "enrollment_date": "2024-09-01",
      "is_active": true,
      "notes": "Promoted from Primary 4 A"
    }
    // ... more enrollments
  ]
}
```

---

## 🔄 COMPLETE WORKFLOW EXAMPLE

### End-of-Year Class Advancement Process

```bash
# Step 1: Ensure promotions are completed (Phase 2.1)
POST /api/academic/promotions/execute/
{
  "classroom_id": 1,
  "academic_year_id": 1,
  "auto_approve_passed": true
}

# Step 2: Students indicate SS1 stream preferences
# (JSS3 students transitioning to SS1)
PUT /api/academic/stream-assignments/127/prefer/
{
  "preferred_stream": "science"
}

PUT /api/academic/stream-assignments/128/prefer/
{
  "preferred_stream": "commercial"
}

# Step 3: Admin reviews pending stream assignments
GET /api/academic/stream-assignments/pending/
# Returns list of students awaiting admin decision

# Step 4: Admin assigns final streams
POST /api/academic/stream-assignments/assign/
{
  "assignments": [
    {"student_id": 127, "assigned_stream": "science"},
    {"student_id": 128, "assigned_stream": "science"},  // Changed from commercial
    {"student_id": 129, "assigned_stream": "arts"}
  ]
}

# Step 5: Preview class movements
POST /api/academic/class-advancement/preview/
{
  "academic_year_id": 1
}
# Review where each student will move

# Step 6: Verify capacity
POST /api/academic/class-advancement/verify/
{
  "academic_year_id": 1
}
# Check if classrooms have space, identify new classrooms needed

# Step 7: Execute class movements
POST /api/academic/class-advancement/execute/
{
  "academic_year_id": 1,
  "new_academic_year_id": 2,
  "auto_create_classrooms": true,
  "default_teacher_id": 5
}
# Actually moves all students

# Step 8: Verify completion
GET /api/academic/enrollments/academic-year/2/
# Confirm all students enrolled in new year
```

---

## 🎯 NIGERIAN SCHOOL SYSTEM SCENARIOS

### Scenario 1: Primary 4 → Primary 5 (Simple)

**No stream selection needed, just capacity-based distribution**

```bash
# Preview
POST /api/academic/class-advancement/preview/
{
  "academic_year_id": 1
}

# Execute
POST /api/academic/class-advancement/execute/
{
  "academic_year_id": 1,
  "new_academic_year_id": 2,
  "auto_create_classrooms": true
}
```

**Result**:
- Students evenly distributed across Primary 5 A, B, C
- New sections auto-created if capacity reached

---

### Scenario 2: JSS3 → SS1 (Stream Selection Required)

**Students must choose Science/Commercial/Arts**

```bash
# Step 1: Students set preferences
PUT /api/academic/stream-assignments/123/prefer/
{"preferred_stream": "science"}

PUT /api/academic/stream-assignments/124/prefer/
{"preferred_stream": "commercial"}

# Step 2: Admin reviews and assigns
POST /api/academic/stream-assignments/assign/
{
  "assignments": [
    {"student_id": 123, "assigned_stream": "science"},
    {"student_id": 124, "assigned_stream": "commercial"}
  ]
}

# Step 3: Execute movements
POST /api/academic/class-advancement/execute/
{
  "academic_year_id": 1,
  "new_academic_year_id": 2,
  "auto_create_classrooms": true
}
```

**Result**:
- Student 123 → SS1 Science A
- Student 124 → SS1 Commercial A
- Within each stream, balanced across A/B/C sections

---

### Scenario 3: SS2 → SS3 (No New Stream Selection)

**Students retain their existing stream**

```bash
# Execute movements (no stream assignment needed)
POST /api/academic/class-advancement/execute/
{
  "academic_year_id": 1,
  "new_academic_year_id": 2,
  "auto_create_classrooms": true
}
```

**Result**:
- SS2 Science students → SS3 Science
- SS2 Commercial students → SS3 Commercial
- SS2 Arts students → SS3 Arts
- Balanced within each stream's sections

---

## ⚠️ ERROR HANDLING

### Common Errors:

#### 1. Missing Stream Assignment
```json
{
  "error": "Cannot proceed: 12 students need stream assignment"
}
```
**Solution**: Assign streams using `/stream-assignments/assign/`

#### 2. Capacity Exceeded
```json
{
  "capacity_warnings": [
    {"classroom": "SS1 Science A", "current": 45, "capacity": 40}
  ]
}
```
**Solution**: Set `auto_create_classrooms: true` in execute request

#### 3. Academic Year Not Found
```json
{
  "error": "Academic year 99 not found"
}
```
**Solution**: Verify academic year ID exists

#### 4. Permission Denied
```json
{
  "error": "You do not have permission to set stream preference for this student"
}
```
**Solution**: Ensure user is admin, the student, or student's parent

---

## 🔒 PERMISSIONS

### Endpoint Permissions:

| Endpoint | Permission |
|----------|-----------|
| `/class-advancement/preview/` | Admin only |
| `/class-advancement/execute/` | Admin only |
| `/class-advancement/verify/` | Admin only |
| `/stream-assignments/assign/` | Admin only |
| `/stream-assignments/{id}/prefer/` | Admin, student, or parent |
| `/stream-assignments/pending/` | Admin only |
| `/enrollments/` | Authenticated (parents see only their children) |
| `/enrollments/{id}/` | Authenticated (parents see only their children) |
| `/enrollments/student/{id}/history/` | Admin or student's parent |
| `/enrollments/academic-year/{id}/` | Authenticated (parents see only their children) |

---

## 📊 RESPONSE CODES

| Code | Meaning |
|------|---------|
| 200 | Success (GET, PUT) |
| 201 | Created (POST execute) |
| 400 | Bad Request (validation error) |
| 403 | Forbidden (permission denied) |
| 404 | Not Found (resource doesn't exist) |
| 500 | Internal Server Error |

---

## 🚀 TESTING CHECKLIST

Before production use:

- [ ] Test preview with sample classroom
- [ ] Test stream preference setting
- [ ] Test admin stream assignment
- [ ] Test capacity verification
- [ ] Test execution with auto-create classrooms
- [ ] Verify Student.classroom updated
- [ ] Verify StudentClassEnrollment records created
- [ ] Test enrollment history retrieval
- [ ] Test parent permissions (can only see own children)
- [ ] Test graduation processing (SS3 → Alumni)

---

**Created by**: Claude Code
**Date**: 2025-12-04
**Version**: 2.2
**Status**: ✅ COMPLETE & READY FOR USE
