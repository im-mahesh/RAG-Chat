# Public API Reference

The Acme public API lets customers manage their projects and data programmatically. All requests are made over HTTPS to api.acme.example and all bodies are JSON.

## Authentication

Authenticate with a bearer token in the Authorization header. Tokens are created in the dashboard under Settings and Developers. For security, rotate every token at least every 90 days; tokens older than that stop working and return 401 with the error code token_expired.

## Rate limits

The Free plan allows 60 requests per minute, the Pro plan 600 requests per minute and the Enterprise plan 6,000 requests per minute. When you exceed the limit the API returns status 429 with a Retry-After header giving the number of seconds to wait. Well-behaved clients should back off and retry rather than hammering the endpoint.

## Pagination

List endpoints use cursor-based pagination. Each response contains a next_cursor value; pass it as the cursor query parameter to fetch the following page. The limit parameter controls the page size and accepts values from 1 to 100, defaulting to 25. When next_cursor is null you have reached the end of the list.

## Idempotency

To make POST requests safe to retry, send an Idempotency-Key header containing a unique string such as a UUID. If the API sees the same key again within 24 hours it returns the original response instead of creating a duplicate resource. Keys are scoped to your account.

## Webhooks

Webhook deliveries are signed with HMAC-SHA256 and the signature is sent in the X-Signature header. Verify it with your endpoint secret before trusting the payload. If your endpoint does not respond with a 2xx status, we retry up to 5 times with exponential backoff: after 1 minute, 5 minutes, 30 minutes, 2 hours and 12 hours.

## Errors

Errors use standard HTTP status codes. 400 means the request was malformed, 401 means authentication failed, 403 means you lack permission, 404 means the resource does not exist, 409 signals a conflict, 422 means validation failed and 500 means something went wrong on our side. The response body contains a code, a human-readable message and a request_id to quote to support.

## Versioning

The API is versioned by date. Send the API-Version header, for example 2025-06-01, to pin your integration to that behaviour. Breaking changes are only released under a new version, and old versions are supported for at least 12 months after deprecation is announced.
