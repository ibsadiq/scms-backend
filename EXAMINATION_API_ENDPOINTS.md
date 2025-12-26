# Examination API Endpoints - Complete Guide

## Overview

The examination endpoints have been added to the system. These endpoints handle student results and report cards.

**Base URL**: `/api/examination/`

---

## 1. Student Results (Term Results)

### List Student Results
**GET** `/api/examination/term-results/?student={student_id}`

Returns all term results for a specific student.

#### Query Parameters:
- `student` (optional) - Filter by student ID
- `term` (optional) - Filter by term ID
- `classroom` (optional) - Filter by classroom ID

#### Response Structure (List):
```json
[
  {
    "id": 1,
    "student": 505,
    "student_name": "Jane Mary Doe",
    "student_admission_number": "TEST/2024/001",
    "term": 1,
    "term_name": "First Term",
    "academic_year": 1,
    "academic_year_name": "2024/2025",
    "classroom": 1,
    "classroom_name": "Primary 1",
    "total_marks": 450,
    "total_possible": 500,
    "average_percentage": 90.0,
    "percentage_str": "90.0%",
    "grade": "A",
    "gpa": 4.0,
    "position": 1,
    "remarks": "Excellent performance",
    "is_published": true,
    "computed_date": "2025-12-06T10:30:00Z",
    "published_date": "2025-12-06T14:00:00Z"
  }
]
```

### Get Single Result (Detailed)
**GET** `/api/examination/term-results/{id}/`

Returns detailed result with subject breakdown.

#### Response Structure (Detail):
```json
{
  "id": 1,
  "student": 505,
  "student_name": "Jane Mary Doe",
  "student_admission_number": "TEST/2024/001",
  "term": 1,
  "term_name": "First Term",
  "academic_year": 1,
  "academic_year_name": "2024/2025",
  "classroom": 1,
  "classroom_name": "Primary 1",
  "total_marks": 450,
  "total_possible": 500,
  "average_percentage": 90.0,
  "percentage_str": "90.0%",
  "grade": "A",
  "gpa": 4.0,
  "position": 1,
  "remarks": "Excellent performance",
  "is_published": true,
  "computed_date": "2025-12-06T10:30:00Z",
  "published_date": "2025-12-06T14:00:00Z",
  "computed_by_name": "Admin User",
  "subject_results": [
    {
      "id": 1,
      "subject": 5,
      "subject_name": "Mathematics",
      "subject_code": "MATH",
      "ca_score": 25,
      "exam_score": 70,
      "total_score": 95,
      "percentage": 95.0,
      "grade": "A",
      "position": 1,
      "remarks": "Excellent",
      "teacher": 2,
      "teacher_name": "John Smith"
    },
    {
      "id": 2,
      "subject": 6,
      "subject_name": "English",
      "subject_code": "ENG",
      "ca_score": 23,
      "exam_score": 65,
      "total_score": 88,
      "percentage": 88.0,
      "grade": "A",
      "position": 2,
      "remarks": "Very Good",
      "teacher": 3,
      "teacher_name": "Jane Doe"
    }
  ]
}
```

---

## 2. Report Cards

### List Student Report Cards
**GET** `/api/examination/report-cards/?student={student_id}`

Returns all generated report cards for a specific student.

#### Query Parameters:
- `student` (optional) - Filter by student ID
- `term` (optional) - Filter by term ID

#### Response Structure:
```json
[
  {
    "id": 1,
    "student": 505,
    "student_name": "Jane Mary Doe",
    "admission_number": "TEST/2024/001",
    "term": 1,
    "term_name": "First Term",
    "academic_year": 1,
    "academic_year_name": "2024/2025",
    "generated_date": "2025-12-06T15:00:00Z",
    "generated_by": 1,
    "generated_by_name": "Admin User",
    "download_url": "http://localhost:8000/api/examination/report-cards/1/download/",
    "download_count": 5,
    "last_downloaded": "2025-12-06T16:30:00Z"
  }
]
```

### Get Single Report Card
**GET** `/api/examination/report-cards/{id}/`

Returns details of a specific report card.

#### Response Structure:
Same as list item above.

### Download Report Card PDF
**GET** `/api/examination/report-cards/{id}/download/`

Downloads the report card as a PDF file.

#### Response:
- **Content-Type**: `application/pdf`
- **Content-Disposition**: `attachment; filename="report_card_Jane_Mary_Doe.pdf"`

Returns the PDF file for download.

---

## Frontend Integration

### TypeScript Interfaces

```typescript
// Student Result (List View)
interface StudentResult {
  id: number
  student: number
  student_name: string
  student_admission_number: string
  term: number
  term_name: string
  academic_year: number
  academic_year_name: string
  classroom: number
  classroom_name: string
  total_marks: number
  total_possible: number
  average_percentage: number
  percentage_str: string
  grade: string
  gpa: number
  position: number
  remarks: string
  is_published: boolean
  computed_date: string
  published_date: string | null
}

// Student Result (Detail View)
interface StudentResultDetail extends StudentResult {
  computed_by_name: string
  subject_results: SubjectResult[]
}

// Subject Result
interface SubjectResult {
  id: number
  subject: number
  subject_name: string
  subject_code: string
  ca_score: number
  exam_score: number
  total_score: number
  percentage: number
  grade: string
  position: number
  remarks: string
  teacher: number
  teacher_name: string
}

// Report Card
interface ReportCard {
  id: number
  student: number
  student_name: string
  admission_number: string
  term: number
  term_name: string
  academic_year: number
  academic_year_name: string
  generated_date: string
  generated_by: number
  generated_by_name: string | null
  download_url: string | null
  download_count: number
  last_downloaded: string | null
}
```

### Example API Calls

```typescript
// Get student results
const getStudentResults = async (studentId: number) => {
  const response = await fetch(
    `http://localhost:8000/api/examination/term-results/?student=${studentId}`,
    {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    }
  )
  return await response.json() as StudentResult[]
}

// Get detailed result
const getResultDetail = async (resultId: number) => {
  const response = await fetch(
    `http://localhost:8000/api/examination/term-results/${resultId}/`,
    {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    }
  )
  return await response.json() as StudentResultDetail
}

// Get student report cards
const getStudentReportCards = async (studentId: number) => {
  const response = await fetch(
    `http://localhost:8000/api/examination/report-cards/?student=${studentId}`,
    {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    }
  )
  return await response.json() as ReportCard[]
}

// Download report card
const downloadReportCard = (reportCardId: number) => {
  const url = `http://localhost:8000/api/examination/report-cards/${reportCardId}/download/`
  window.open(url, '_blank')
}
```

---

## Important Notes

1. **Authentication Required**: All endpoints require authentication via Bearer token
2. **Permissions**: 
   - Non-staff users can only see published results
   - Staff users can see all results
3. **Empty Results**: When no results are found, endpoints return an empty array `[]`
4. **Report Card PDF**: Report cards must be generated first before they can be downloaded

---

## Creating Test Data

To test these endpoints, you'll need to:

1. Create examination records (marks)
2. Compute results using: `POST /api/examination/term-results/compute/`
3. Publish results using: `POST /api/examination/term-results/publish/`
4. Generate report cards using: `POST /api/examination/report-cards/generate/`

---

**Date**: December 6, 2025  
**Status**: ✅ Endpoints configured and ready
