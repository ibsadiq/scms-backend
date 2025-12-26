# Student Login Response Format - Updated

## Changes Made

Updated the student authentication endpoints to match the frontend's expected response format.

### Affected Endpoints

1. **POST /api/academic/students/auth/login/** - Student login
2. **POST /api/academic/students/auth/register/** - Student registration

---

## Updated Response Format

### Before (Old Format)
```json
{
  "message": "Login successful",
  "student_id": 505,
  "admission_number": "TEST/2024/001",
  "full_name": "Jane Mary Doe",
  "tokens": {
    "refresh": "eyJhbGci...",
    "access": "eyJhbGci..."
  }
}
```

### After (New Format - Matches Frontend)
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "student": {
    "id": 505,
    "admission_number": "TEST/2024/001",
    "first_name": "jane",
    "middle_name": "mary",
    "last_name": "doe",
    "phone_number": "08098765432",
    "email": "TEST/2024/001@student.local",
    "classroom": 1,
    "classroom_name": "Primary 1"
  }
}
```

---

## Key Changes

1. **Tokens at Root Level**: `access` and `refresh` tokens are now at the root level instead of nested in a `tokens` object
2. **Student Object**: All student information is now nested in a `student` object
3. **Separate Name Fields**: Instead of `full_name`, the response now includes `first_name`, `middle_name`, and `last_name` separately
4. **Classroom Information**: Added `classroom` (ID) and `classroom_name` fields from current enrollment
5. **Email Field**: Added student's email address

---

## Frontend TypeScript Interface

The response now matches this TypeScript interface:

```typescript
interface StudentLoginResponse {
  access: string
  refresh: string
  student: {
    id: number
    admission_number: string
    first_name: string
    middle_name?: string | null
    last_name: string
    phone_number: string
    email?: string | null
    classroom?: number | null
    classroom_name?: string | null
  }
}
```

---

## Classroom Enrollment Logic

The `classroom` and `classroom_name` fields are populated from the student's current enrollment:

- Looks up the active academic year (`active_year=True`)
- Finds the student's enrollment for that year
- Returns the classroom ID and name if found
- Returns `null` if no active enrollment exists

---

## Example Usage

### Login Request
```bash
POST http://localhost:8000/api/academic/students/auth/login/
Content-Type: application/json

{
  "phone_number": "08098765432",
  "password": "student123"
}
```

### Successful Response (200 OK)
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY1MTI0NTMzLCJpYXQiOjE3NjUwMzgxMzMsImp0aSI6IjMzODk5NTYzYWVlYzRlZjQ5MjY1NmNjZGJhYmNhYWViIiwidXNlcl9pZCI6MTI3fQ.GjBCiAH-JBZ3B2hclaz1SFHgeEljq6R68SMiO_1bey8",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc2NTY0MjkzMywiaWF0IjoxNzY1MDM4MTMzLCJqdGkiOiI4ZWYzZjhkNWE1Nzg0ZDQ5OTA5MWRlM2ZlZjQyYTJmOSIsInVzZXJfaWQiOjEyN30.vA7KHuqtfNCvLewEj7QBtFR9jAFs7vtw861ZJ_WzXN0",
  "student": {
    "id": 505,
    "admission_number": "TEST/2024/001",
    "first_name": "jane",
    "middle_name": "mary",
    "last_name": "doe",
    "phone_number": "08098765432",
    "email": "TEST/2024/001@student.local",
    "classroom": 1,
    "classroom_name": "Primary 1"
  }
}
```

### Using the Access Token
```bash
GET http://localhost:8000/api/academic/students/portal/dashboard/
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Files Modified

- `academic/views_student_portal.py` - Updated both `login` and `register` endpoints

---

## Testing

Tested with test credentials:
- **Phone:** 08098765432
- **Password:** student123
- **Result:** ✅ Response matches expected format

---

**Date:** December 6, 2025  
**Status:** ✅ Complete and tested
