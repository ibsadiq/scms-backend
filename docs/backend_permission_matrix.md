# Backend permission matrix

This matrix describes the Phase 2 frontend-facing authorization contract. `ASSIGNED`
means a teacher's homeroom or allocated classroom/subject. `OWN` includes a student
or a parent's linked children. All entries are tenant-local after middleware schema
resolution and tenant-bound JWT authentication.

| Domain | Endpoint/action | Admin | Teacher | Staff | Student | Parent | Accountant | Anonymous |
|---|---|---|---|---|---|---|---|---|
| Attendance | Student attendance list/detail | READ/WRITE | ASSIGNED READ/WRITE | NONE | OWN READ | OWN READ | NONE | NONE |
| Attendance | Student attendance delete | NONE | NONE | NONE | NONE | NONE | NONE | NONE |
| Attendance | Bulk mark | WRITE | ASSIGNED WRITE | NONE | NONE | NONE | NONE | NONE |
| Attendance | Student summary | READ | ASSIGNED READ | NONE | OWN READ | OWN READ | NONE | NONE |
| Attendance | School-wide summary | READ | NONE | NONE | NONE | NONE | NONE | NONE |
| Attendance | Class summary/marked dates | READ | ASSIGNED READ | NONE | NONE | NONE | NONE | NONE |
| Attendance | Legacy teacher attendance | READ | OWN READ | NONE | NONE | NONE | NONE | NONE |
| Attendance | Legacy period attendance | READ | ASSIGNED READ | NONE | NONE | NONE | NONE | NONE |
| Attendance | Legacy writes | NONE | NONE | NONE | NONE | NONE | NONE | NONE |
| Finance | Optional services/fee structures | READ/WRITE | NONE | NONE | NONE | NONE | READ/WRITE | NONE |
| Finance | Subscriptions/fee assignments/receipts | READ/WRITE | NONE | NONE | OWN READ | OWN READ | READ/WRITE | NONE |
| Finance | Payments/categories/reminders | READ/WRITE | NONE | NONE | NONE | NONE | READ/WRITE | NONE |
| Finance | Student balance | READ | NONE | NONE | OWN | OWN | READ | NONE |
| Finance | School dashboard/audit logs | READ | NONE | NONE | NONE | NONE | READ | NONE |
| Finance | Parent fees | NONE | NONE | NONE | NONE | OWN | NONE | NONE |
| Examination | Assessment sessions read | READ | READ | READ | READ | READ | READ | NONE |
| Examination | Assessment sessions mutate | WRITE | NONE | NONE | NONE | NONE | NONE | NONE |
| Examination | Term results | READ/WRITE | ASSIGNED | NONE | OWN READ when published | OWN READ when published | NONE | NONE |
| Examination | Annual results | READ/WRITE | ASSIGNED READ | NONE | OWN READ when published | OWN READ when published | NONE | NONE |
| Examination | Result audit logs | READ | NONE | NONE | NONE | NONE | NONE | NONE |
| Examination | Marked scripts | READ/WRITE | OWN-UPLOAD READ/WRITE | NONE | OWN visible READ | OWN visible READ | NONE | NONE |
| Academic | Structure, subjects, classrooms | READ/WRITE | READ | READ | READ | READ | READ | NONE |
| Academic | Allocations/enrollments | READ/WRITE | ASSIGNED READ | READ | OWN where scoped | OWN | READ | NONE |
| Academic/SIS | Student/enrollment/bulk mutations | WRITE | NONE | NONE | NONE | NONE | NONE | NONE |
| Administration | Academic years/terms | READ/WRITE | READ | READ | READ | READ | READ | NONE |
| Administration | Dashboard statistics | READ | NONE | NONE | NONE | NONE | NONE | NONE |
| Device | Scan ingestion | PUBLIC signed-device request | PUBLIC signed-device request | PUBLIC signed-device request | PUBLIC signed-device request | PUBLIC signed-device request | PUBLIC signed-device request | PUBLIC |

`Staff` means an authenticated non-admin/non-teacher/non-accountant employee. Django
`is_staff` remains an existing school-admin signal through `AcademicAuthorityService`.
