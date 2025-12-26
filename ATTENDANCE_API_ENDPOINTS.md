# Student Attendance API Endpoints

## Overview

Student attendance endpoints for tracking and summarizing attendance records.

**Base URL**: `/api/attendance/`

---

## Endpoints

### 1. List Student Attendance Records

**GET** `/api/attendance/student-attendance/`

Returns all attendance records (with optional filtering).

#### Query Parameters:
- `student` (optional) - Filter by student ID
- `classroom` (optional) - Filter by classroom ID  
- `start_date` (optional) - Filter from date (YYYY-MM-DD)
- `end_date` (optional) - Filter to date (YYYY-MM-DD)

#### Example:
```
GET /api/attendance/student-attendance/?student=505&start_date=2025-12-01&end_date=2025-12-31
```

---

### 2. Get Attendance Summary

**GET** `/api/attendance/student-attendance/summary/`

Returns attendance summary with statistics for a student.

#### Query Parameters:
- `student` (**required**) - Student ID
- `month` (optional) - Month number (1-12)
- `year` (optional) - Year (e.g., 2025)
- `start_date` (optional) - Custom start date (YYYY-MM-DD)
- `end_date` (optional) - Custom end date (YYYY-MM-DD)

**Note**: If no date parameters provided, defaults to current month.

#### Response Structure:
```json
{
  "student": {
    "id": 505,
    "name": "Jane Mary Doe",
    "admission_number": "TEST/2024/001"
  },
  "period": "December 2025",
  "summary": {
    "total_days": 20,
    "present": 18,
    "absent": 1,
    "late": 1,
    "excused": 0,
    "attendance_rate": 90.0
  },
  "recent_records": [
    {
      "id": 123,
      "student": 505,
      "date": "2025-12-06",
      "ClassRoom": 1,
      "status": {
        "id": 1,
        "name": "Present"
      },
      "notes": ""
    }
  ]
}
```

#### Examples:
```bash
# Get summary for December 2025
GET /api/attendance/student-attendance/summary/?student=505&month=12&year=2025

# Get summary for entire year
GET /api/attendance/student-attendance/summary/?student=505&year=2025

# Get summary for custom date range
GET /api/attendance/student-attendance/summary/?student=505&start_date=2025-11-01&end_date=2025-12-15

# Get summary for current month (no date params)
GET /api/attendance/student-attendance/summary/?student=505
```

---

### 3. Get Monthly Breakdown

**GET** `/api/attendance/student-attendance/monthly-breakdown/`

Returns month-by-month attendance breakdown for a full year.

#### Query Parameters:
- `student` (**required**) - Student ID
- `year` (optional) - Year (defaults to current year)

#### Response Structure:
```json
{
  "year": "2025",
  "months": [
    {
      "month": 1,
      "month_name": "January",
      "total_days": 22,
      "present": 20,
      "absent": 2,
      "attendance_rate": 90.9
    },
    {
      "month": 2,
      "month_name": "February",
      "total_days": 20,
      "present": 19,
      "absent": 1,
      "attendance_rate": 95.0
    },
    // ... months 3-12
  ]
}
```

#### Example:
```bash
GET /api/attendance/student-attendance/monthly-breakdown/?student=505&year=2025
```

---

## Frontend Integration

### TypeScript Interfaces

```typescript
// Attendance Summary Response
interface AttendanceSummary {
  student: {
    id: number
    name: string
    admission_number: string
  }
  period: string
  summary: {
    total_days: number
    present: number
    absent: number
    late: number
    excused: number
    attendance_rate: number
  }
  recent_records: AttendanceRecord[]
}

// Attendance Record
interface AttendanceRecord {
  id: number
  student: number
  date: string
  ClassRoom: number
  status: {
    id: number
    name: string
  }
  notes: string
}

// Monthly Breakdown Response
interface MonthlyBreakdown {
  year: string
  months: MonthData[]
}

interface MonthData {
  month: number
  month_name: string
  total_days: number
  present: number
  absent: number
  attendance_rate: number
}
```

### Example API Calls

```typescript
// Get attendance summary for current month
const getAttendanceSummary = async (studentId: number, month?: number, year?: number) => {
  let url = `http://localhost:8000/api/attendance/student-attendance/summary/?student=${studentId}`
  
  if (month && year) {
    url += `&month=${month}&year=${year}`
  }
  
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  })
  
  return await response.json() as AttendanceSummary
}

// Get monthly breakdown
const getMonthlyBreakdown = async (studentId: number, year?: number) => {
  let url = `http://localhost:8000/api/attendance/student-attendance/monthly-breakdown/?student=${studentId}`
  
  if (year) {
    url += `&year=${year}`
  }
  
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  })
  
  return await response.json() as MonthlyBreakdown
}
```

---

## Attendance Status Values

The system supports these attendance status values:
- **Present** - Student was present
- **Absent** - Student was absent without excuse
- **Late** - Student arrived late
- **Excused** - Student was absent with valid excuse

---

## Important Notes

1. **Authentication Required**: All endpoints require Bearer token authentication
2. **Empty Data**: Returns zero counts if no attendance records found for the period
3. **Date Filtering**: Can use either `month/year` OR `start_date/end_date`, not both
4. **Default Period**: If no date parameters provided, summary defaults to current month

---

**Date**: December 6, 2025  
**Status**: ✅ Endpoints ready and tested
