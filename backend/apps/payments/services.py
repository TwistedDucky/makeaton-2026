"""
Business logic and write services for payments and allocations.

TODO: Future record_payment service implementation rules:
---------------------------------------------------------
When building the `record_payment` service in subsequent tasks, the service
MUST enforce the following domain integrity rules inside a single atomic transaction:

1. Customer Consistency:
   - `payment.customer` MUST equal each allocated invoice's `customer`.
   - Cross-customer payment allocations are strictly forbidden.

2. Allocation Sum Equality:
   - The exact sum of all `PaymentAllocation.amount` values MUST equal `payment.amount`.
   - Neither under-allocation nor over-allocation of the payment amount is permitted.

3. Balance Integrity:
   - For each allocated invoice, the allocation amount MUST NOT exceed the invoice's
     remaining outstanding balance (`invoice.total - invoice.amount_paid`).

4. Invoice Status Guard:
   - Each target invoice MUST currently be in `confirmed` status.
   - Payments cannot be allocated to `draft` or `cancelled` invoices.

5. Atomic Concurrency Lock:
   - The service MUST lock invoice rows using `.select_for_update()` within `transaction.atomic()`.
   - In the same atomic transaction, update each `invoice.amount_paid += allocation.amount`.
   - If the updated `amount_paid >= total`, call `invoice.mark_paid()`.
"""
