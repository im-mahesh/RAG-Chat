# API Changelog

A history of changes to the Acme public API, newest first. For current behaviour always check the API reference.

## 2025-03 rate limit increase

The Pro plan limit was raised from 300 to 600 requests per minute. The Free plan stays at 60 requests per minute. Customers who built clients around the old limit do not need to change anything, but can now send twice as many requests.

## 2025-01 webhook reliability

Webhook deliveries are now retried up to 5 times instead of 3, using the same exponential backoff schedule. Failed deliveries are visible in the dashboard for seven days, and an endpoint that fails continuously for three days is disabled automatically with an email notice.

## 2024-11 idempotency window

The window in which an Idempotency-Key is remembered was extended from 12 hours to 24 hours. Keys sent with a different request body now return a 422 error instead of silently returning the first response.

## 2024-09 pagination defaults

The default page size of list endpoints changed from 50 to 25 results, and the maximum from 200 to 100. Clients that relied on the old defaults should pass the limit parameter explicitly. The cursor format did not change.

## 2024-06 token lifetime

API tokens now expire after 90 days. Before this change tokens did not expire. Customers receive reminder emails 14 days and 3 days before a token expires so they can rotate it in time.

## 2024-03 error format

Error responses now include a request_id field. Quote it when contacting support. The older message-only format is no longer returned by any endpoint.

## 2023-12 versioning

The API-Version header was introduced. Requests without it use the version that was current when the account was created, so existing integrations keep working unchanged.
