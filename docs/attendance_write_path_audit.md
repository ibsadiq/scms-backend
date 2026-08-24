# Attendance write-path audit

Canonical daily attendance mutations belong to `StudentAttendanceService` and
`StaffAttendanceService`. They lock the holder, reconcile the unique daily row,
and append an immutable `AttendanceEvent`.

| Path | Classification | Policy |
| --- | --- | --- |
| `attendance/services/student_attendance_service.py` | CANONICAL SERVICE | Student manual and RFID writes. |
| `attendance/services/staff_attendance_service.py` | CANONICAL SERVICE | Staff manual and RFID writes. |
| `attendance/services/scan_service.py` | CANONICAL SERVICE | Delegates scans to holder services. |
| attendance, examination, reporting, portal query code | LEGACY READ-ONLY | Reads daily rows only. |
| migrations and historical data operations | MIGRATION/HISTORICAL | Never rewritten. |
| test modules | TEST | Fixtures may create or delete rows directly. |
| `generate_rich_attendance.py` and sample-data commands | MIGRATION/HISTORICAL | Offline sample-data tooling, not an application request path. |
| `academic/views/teacher.py` | CANONICAL SERVICE | Teacher marking delegates to the student service. |

Daily rows are read-only in Django admin. The student attendance API rejects
deletion and requires corrective service mutations, preserving the event trail.

