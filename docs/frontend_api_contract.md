# SSync frontend API contract

This guide records the canonical integration surface. The generated OpenAPI schema remains the field-level source of truth. Tenant requests use the tenant's known host (or the supported tenant header during bootstrap) and tenant-bound bearer JWTs.

## Common conventions

- Authentication: `Authorization: Bearer <token>`. Tokens are tenant-bound. Public admissions endpoints are the documented exception.
- Validation errors use DRF field arrays or `{"detail": "..."}`. Stable domain conflicts may also include `code`. SQL, tracebacks, schema names, storage paths, Celery IDs, and provider errors are never a client contract.
- Standard resource lists use `{count,next,previous,results}`. Messaging recipient discovery is intentionally an unpaginated, minimized array. Reports use their documented report envelope.
- Unauthorized collection access is `403`; inaccessible object detail is normally `404`; invalid filter values are `400`.

## Authentication and users

- `POST /api/users/login/`, `POST /api/users/token/refresh/`: tenant-bound token lifecycle.
- `GET /api/users/profile/`, `GET /api/users/roles/`, `POST /api/users/switch-role/`: current-user operations.
- School administration user/teacher/parent/accountant routes are admin-only unless the schema states a narrower self-service operation.

## Admissions

- Public discovery: `GET /api/public/admissions/sessions/`, `active-session/`, `fee-structures/`, and `available-classes/`.
- Application creation: `POST /api/public/admissions/applications/`; collection `GET` is not supported.
- Token-scoped tracking and mutation use the opaque tracking token. Application `PUT`/`DELETE` are not supported; lifecycle status is administration-owned.
- Documents use UUID public identifiers. Integer document routes are removed.
- Administration uses `/api/admin/admissions/`, including numbering policies and the transactional conversion workflow. School admins only.

## SIS and academic structure

- `/api/sis/students/` is role-scoped: school admin tenant-wide, teacher assigned students, parent linked children, student self. Non-admin representations are minimized.
- Student status filter values are `active`, `inactive`, `graduated`, and `withdrawn` (case-insensitive); invalid values return `400`.
- Mutations and related medical/academic history writes are school-admin-only. An inaccessible detail object returns `404`.
- Academic structure, allocation, enrollment, curriculum, lesson planning and advancement live under `/api/academic/`; structural mutations require school-admin authority.

## Attendance, RFID and ID cards

- `/api/attendance/` is the canonical service-backed attendance/RFID surface. Role-scoped reads and explicit mark/scan actions preserve immutable event history.
- `/api/idcards/` owns card issuance, replacement and RFID credential lifecycle. Active-card and UID collisions use stable validation/conflict responses.
- Clients must submit storage-neutral file uploads and consume returned storage URLs; they must not assume Cloudinary or local filesystem semantics.

## Finance and reports

- `/api/finance/` owns fee structures, assignments, receipts and allocations. Clients must not calculate authoritative balances locally.
- `/api/reports/students/`, `academic/`, `attendance/`, and `financial/` are the canonical aggregate/report APIs. Export endpoints reuse the same authorization and filters.
- Finance defaulter data is limited to admission number, student name, class name and balance.

## Examination, CBT, assignments and schedule

- `/api/examination/` owns assessment/result lifecycle; `/api/reports/academic/` is read-only reporting, not a mutation alternative.
- `/api/cbt/`, `/api/assignments/`, and `/api/schedule/` own their respective workflows. Use only methods advertised by OpenAPI; lifecycle enums are server-defined and should not be inferred from labels.

## Notifications and direct messaging

- `/api/notifications/` owns notification records. Direct messaging uses `/api/notifications/messages/`.
- Message collection supports `GET` and `POST`; detail supports `GET`; read state changes only through the explicit `mark_read` action. Messages are immutable.
- `/api/notifications/messages/recipients/` is minimized to `user_id`, `display_name`, `role`, and `relationship`.

## Background jobs

- `GET /api/jobs/{public_id}/` is the only tenant-facing status contract. It returns safe status, bounded progress, safe result metadata, error code, and timestamps.
- Raw Celery task IDs and `/api/tasks/{task_id}/` are not public contracts.
- `/api/celery/health/` is internal platform-operator infrastructure and intentionally excluded from public OpenAPI.

## Versioning

SSync currently uses unversioned `/api/` routes. Introducing `/api/v1/` now would duplicate or move the entire verified route surface and force immediate frontend and compatibility work without resolving a current defect. Defer path versioning until a planned breaking-contract release; use additive changes and explicit deprecation meanwhile.
