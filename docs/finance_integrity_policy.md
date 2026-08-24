# Finance integrity policy

`FeePaymentAllocation` is a transactional ledger operation. Application code must
not call `FeePaymentAllocation.objects.bulk_create()`, because Django bulk inserts
bypass allocation validation, receipt/assignment locks, and `amount_paid`
synchronization.

Single and multi-row allocations must use
`finance.services.PaymentAllocationService.allocate()`. Imports requiring bulk
allocation must validate their complete batch and call that service; raw ORM bulk
insertion is reserved for historical migrations that explicitly rebuild balances.

Mandatory fee fan-out uses `FeeAssignmentService`. Signals schedule it with
`transaction.on_commit()`, keeping fan-out outside the originating model-save
transaction. The service iterates students in bounded chunks and treats a
concurrent uniqueness winner as idempotent success. It remains synchronous after
commit so API callers retain immediate consistency; moving it to Celery is a later
scaling option if schools outgrow request-time fan-out.
