# Incident Response Runbook

This runbook is for the on-call engineer. Follow it when monitoring pages you or a customer reports a problem with the production platform.

## Severity levels

SEV1 is a full outage or data loss affecting most customers. SEV2 is a partial outage or a major feature failing for a subset of customers. SEV3 is a minor defect with a workaround. When in doubt, declare the higher severity and downgrade later. Only the incident commander can change a severity once it is declared.

## Paging and escalation

The primary on-call engineer must acknowledge a page within 5 minutes. If there is no acknowledgement, the page escalates to the secondary on-call after 15 minutes and then to the engineering manager. Acknowledge the page even if you are still investigating, so nobody else starts duplicate work.

## Communication

For a SEV1 the incident commander updates the public status page every 30 minutes until the incident is resolved, even if there is nothing new to report. Use the incident channel for technical discussion and keep customer-facing wording factual and free of speculation. Support receives a summary message at the start of each incident.

## Rolling back a release

If the incident started shortly after a deploy, roll back first and investigate afterwards. Run `deployctl rollback --to previous` from the release console. A rollback normally completes in under 10 minutes. Confirm that error rates return to baseline on the main dashboard before declaring the mitigation successful.

## Database failover

If the primary database is unreachable, promote the standby by running `dbctl promote db-replica-2`. Before promoting, confirm the replica lag is below 30 seconds to avoid losing recent writes. After promotion, point the application at the new primary and rebuild the old primary as a replica once it recovers.

## Postmortems

Every SEV1 and SEV2 requires a blameless postmortem published within 5 business days. The document describes the timeline, the root cause, what went well, what went badly and the follow-up actions with owners and due dates. Action items are tracked in the reliability backlog until they are closed.

## On-call handoff

The on-call rotation changes every Monday at 10:00 UTC. The outgoing engineer writes a handoff note listing open incidents, flaky alerts and any risky changes scheduled for the week. The incoming engineer reads it and replies to confirm.
