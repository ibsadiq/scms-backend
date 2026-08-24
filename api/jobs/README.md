# Background jobs

`BackgroundJob` is the tenant-owned, user-visible status record. Celery remains
an execution mechanism: its task identifier is internal and is never an API
lookup key. Migrated tasks receive both `schema_name` and `job_public_id`, enter
that schema explicitly, and update only controlled status/progress/result fields.

## Producer inventory (Phase 4A.5)

- Class result computation: user-facing; migrated to `BackgroundJob`.
- Custom and tenant-wide finance reminders: user-facing; migrated.
- Single/bulk report-card generation: user-facing but currently returns its
  existing `ReportCard` resource (or no task identifier), not a raw Celery ID;
  deferred to a later async-contract consolidation.
- Tenant provisioning: platform administration/internal; no tenant user job.
- Tenant statistics, scheduled fee reminders, notifications and periodic work:
  internal or scheduled system tasks; no user-owned job required.
- AI tasks: explicitly outside Phase 4A.5.

Completed job rows are retained. A scheduled cleanup policy is intentionally
deferred until audit/data-retention governance defines the retention period.
Cleanup must never delete active jobs.
