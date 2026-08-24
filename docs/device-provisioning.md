# SSync attendance-device provisioning

SSync's core ingestion API is hardware-neutral. Vendor adapters translate reader output into this API; vendor protocols do not belong in attendance services.

## Register and configure a device

1. A school administrator creates a device with `POST /api/attendance/devices/` inside the school's tenant endpoint.
2. Record the returned `device_identifier` and one-time `secret`. The secret and its hash are not returned by later GET requests.
3. Configure the adapter to send scans to the same tenant host (or the deployment's trusted tenant-routing mechanism) at `POST /api/attendance/device-scans/`.
4. Configure the headers below. Do not select a tenant from untrusted card data.

Required headers:

```text
X-Device-ID: configured device identifier
X-Device-Secret: one-time provisioned secret
X-Request-Timestamp: current Unix timestamp in seconds
X-Request-ID: unique opaque value, at most 64 characters
X-Device-Signature: lowercase hexadecimal HMAC-SHA256
Content-Type: application/json
```

Request IDs must never be reused by a device. The HTTP request timestamp must be within five minutes of the server. An offline adapter may submit a historical `scanned_at` value up to seven days old while signing the request with its current transmission timestamp.

## Canonical signature

Hash the exact transmitted request-body bytes with SHA-256. Construct these five UTF-8 lines with `\n` separators and no final newline:

```text
POST
/api/attendance/device-scans/
<X-Request-Timestamp>
<X-Request-ID>
<lowercase SHA-256 hex of exact body bytes>
```

Calculate lowercase hexadecimal `HMAC-SHA256(device_secret, canonical_bytes)`. Changing the method, path, timestamp, request ID, whitespace, JSON ordering, or body changes the signature.

Example body:

```json
{"uid":"04A627925F6180","scanned_at":"2026-08-22T07:31:14+01:00","direction":"ENTRY"}
```

Successful responses contain `success`, `result`, `direction`, `scan_id`, and optionally `attendance_status`. Authentication errors return stable result codes without cryptographic details.

## Rotation and disablement

`POST /api/attendance/devices/{id}/rotate-secret/` returns a new secret once and immediately invalidates the old secret/signing key. Update the adapter atomically. `POST /api/attendance/devices/{id}/disable/` stops attendance processing while retaining authenticated attempts as operational evidence.

Rate limits permit normal bursts but reject excessive per-device traffic. Never share one device credential between physical readers.
