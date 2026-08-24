# API legacy cleanup and compatibility register

## Removed or superseded

- Public admissions collection list/update/delete and stale exam/interview actions are not routed.
- Integer admission-document identifiers are not routed; UUID public identifiers are canonical.
- Raw Celery task-status lookup is removed; application-owned `/api/jobs/{public_id}/` is canonical.
- Mutable direct-message ModelViewSet behavior is superseded by immutable collection/detail plus `mark_read`.
- Duplicate SIS history serializers formerly declared inside the views module were removed in Phase 4B; serializers now have one owner in `sis.serializers`.
- A stale reports URL-module contract that claimed administrative reports exposed fees/attendance was removed.

## Retained compatibility APIs

- Existing unversioned `/api/` paths remain canonical for this release. No mass `/api/v1/` alias was added.
- Service-backed attendance compatibility routes remain because they are routed and covered by Phase 2/3 regressions; removal requires caller telemetry.
- Examination homeroom action spellings currently have compatibility aliases. They are documented as a future removal candidate because source inspection alone does not prove external callers are absent.

## Internal only

- `/api/celery/health/` is restricted to a public-schema superuser/platform operator and excluded from the tenant-facing OpenAPI schema because it exposes worker topology.
- Scheduled/system Celery tasks have no user-owned job resource unless a routed user workflow requires one.

## Deferred cleanup

- Remaining schema warnings for ambiguous serializer method return hints, operation-ID aliases, enum-name collisions, schema-time queryset access, and untyped custom parameters require domain-by-domain cleanup. They are not suppressed globally.
- Unrouted commented example ViewSets and offline import/migration utilities should only be deleted after caller and operational-tooling verification.

## AWS compatibility findings

- New Phase 4A/4B contracts are database-, tenant-, and Django-storage-driven; no new Cloudinary, localhost Redis, worker-hostname or local-path coupling was introduced.
- `academic/serializers/admission.py` correctly derives document access from the `FileField` storage URL, but currently converts it to an absolute request URL. That remains storage-compatible; private S3 delivery will require the storage backend (or a download service) to issue short-lived URLs.
- `examination/models.py` still imports `RawMediaCloudinaryStorage` directly for a report-card field. This is confirmed provider coupling and must be replaced by a Django `STORAGES` alias before the AWS migration; changing historical migrations is not appropriate.
- `finance/tasks.py` and `examination/services/report_card_generator.py` accept HTTP URLs and local paths while rendering. Their `FileField.open()` path is storage-neutral, but the HTTP/local fallbacks need removal or a controlled storage download abstraction before private S3 objects are enabled.
- `tenants/utils.py`, `notifications/services.py`, `tenants/services.py`, and `tenants/models.py` contain localhost fallback URLs. They are configuration fallbacks rather than AWS credentials, but production deployment must require explicit frontend/backend/base-domain settings.
- `users/views.py` constructs a password-reset URL from the request host when no frontend URL is supplied. Production should use an allow-listed configured frontend origin before launch to avoid host-derived reset links.
- Generated exports must move through storage-neutral application references before asynchronous S3 delivery is introduced. Phase 4B does not perform that infrastructure migration.

## OpenAPI warning register

- FIXED: tenant-bound JWT was previously unknown to drf-spectacular; `tenantBearerAuth` now documents bearer authentication and tenant routing.
- FIXED: hardened reports, SIS detail/history, public admissions, messaging, and background-job routes are represented; the platform worker-detail endpoint is deliberately excluded.
- ACCEPTED: DRF format-suffix resolver entries are real compatibility routes and remain in resolver inventory, while OpenAPI presents normalized paths.
- FIXED: all 22 previously unresolved composite/legacy API views now have explicit domain-specific request/response schema contracts. Validated generation reports `Errors: 0 (0 unique)`, down from `123 (22 unique)`.
- DEFERRED: validated generation reports 377 warning occurrences across 189 unique warnings, primarily serializer-method return hints, schema-time queryset access, enum component naming, compatibility operation-ID collisions, and untyped custom path parameters. Global warning suppression or a generic fallback serializer was intentionally not added.

## Authoritative inventory

Run `python manage.py api_route_inventory` for the complete resolver-derived JSON inventory (URL, name, methods, view, declared serializer and permissions). Generate OpenAPI with `python manage.py spectacular --file openapi.yaml --validate`. Resolver output is authoritative for routing; OpenAPI is authoritative for the supported frontend contract.
