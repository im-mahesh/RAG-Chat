# Backup and Disaster Recovery Plan

This plan describes how the platform is protected against infrastructure failure and what the recovery objectives are.

## Objectives

The recovery point objective for the primary database is 15 minutes: at most 15 minutes of writes may be lost in a disaster. The recovery time objective is 4 hours for the full platform. These targets are tested twice a year and the results are shared with the executive team.

## Replication

The primary database streams changes to two replicas in different availability zones. Replicas are read-only and are also used to serve reporting queries. Replication lag is monitored continuously and an alert fires when it exceeds 30 seconds.

## Failover drills

Engineering runs a database failover drill every quarter using the dbctl drill command in the staging environment. The drill measures how long promotion takes and whether the application reconnects cleanly. Findings are recorded in the reliability backlog.

## Regional outage

If an entire region becomes unavailable the platform can be restored in the secondary region from the most recent snapshot and replayed logs. Restoring in a new region takes several hours and is declared by the incident commander as a SEV1 event.

## Restore testing

Backups are only useful if they can be restored. Every month an automated job restores the latest snapshot into an isolated environment and runs integrity checks. A failed restore test pages the infrastructure team.

## Object storage

Customer uploads are stored in object storage with versioning enabled and replicated to a second region. Deleted objects can be recovered by support for 14 days after deletion, after which they are permanently removed.

## Communication during a disaster

The incident commander decides when to invoke this plan. Customers are told through the status page and, for enterprise accounts, by direct email from the account manager.
