---
id: github-auditlog-2026-04-01
title: "Failed credential rotation cuts audit log service from its backing data store"
company: GitHub
date: 2026-04-01
severity: minor
duration_minutes: 28
affected_services:
  - Audit log API
  - Audit log web UI
  - Audit log event streaming
root_cause_category: credential-auth
---

## Summary

On April 1, 2026, between 15:34 UTC and 16:02 UTC, GitHub's audit log service lost connectivity to its backing data store due to a failed credential rotation. During this 28-minute window, audit log history was unavailable via both the API and the web UI, producing 5xx errors for 4,297 API actors and 127 github.com users. Events created during the window were delayed by up to 29 minutes in github.com and in event streaming. No audit log events were lost — all were ultimately written and streamed successfully. Customers using GitHub Enterprise Cloud with data residency were not impacted. GitHub was alerted six minutes after onset and restored full service by recycling the affected environment. Note on source depth: this incident is documented in GitHub's monthly availability report rather than a standalone post-mortem, so the timeline below carries the three timestamps GitHub published and the root cause is stated at the level of detail available — a failed credential rotation, without further explanation of why the rotation failed.

## Timeline

All times UTC.

- **15:34** — The audit log service loses connectivity to its backing data store following a failed credential rotation. Audit log history becomes unavailable via API and web UI.
- **15:40** — GitHub is alerted to the infrastructure failure, six minutes after onset.
- **16:02** — Issue resolved by recycling the affected environment; full service restored.

## Root Cause

A credential rotation for the audit log service failed, leaving the service without valid credentials for its backing data store. With no working connection to that store, audit log history could not be read, and requests to both the API and the web UI returned 5xx errors.

The write path was not lost. Events created during the window were queued rather than dropped, and were delayed by up to 29 minutes in github.com and in event streaming before being written and streamed successfully.

GitHub's published account does not state why the rotation failed, only that it did and that the rotation process was subsequently strengthened.

## Resolution

GitHub was alerted to the infrastructure failure at 15:40 UTC, six minutes after onset. The issue was resolved by recycling the affected environment, restoring full service by 16:02 UTC. All audit log events created during the outage were ultimately written and streamed successfully; none were lost.

## Prevention

- The credential rotation process was updated and strengthened to improve resiliency and help prevent similar failures.
- Monitoring configuration was enhanced, including making paging thresholds more sensitive to improve detection speed and operator visibility into similar issues.