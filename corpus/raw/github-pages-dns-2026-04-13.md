---
id: github-pages-dns-2026-04-13
title: "Automated DNS tool deletes a live record after its upstream source returns stale data"
company: GitHub
date: 2026-04-13
severity: major
duration_minutes: 97
affected_services:
  - GitHub Pages
root_cause_category: agent-ai
---

## Summary

On April 13, 2026, between 18:53 UTC and 20:30 UTC, the GitHub Pages service experienced elevated error rates. The error rate averaged 10.58% and peaked at 12.77% of requests to the service, producing approximately 17.5 million failed requests returning HTTP 500 errors. An automated DNS management tool erroneously deleted a DNS record for a GitHub Pages backend storage host: the tool's upstream data source intermittently failed to return the record, the tool treated that absence as evidence the record was stale, and removed it. Impact appeared gradually rather than immediately, as cached copies of the record expired across GitHub's systems and Pages servers progressively lost the ability to reach the affected storage host. Detection took approximately 53 minutes, which GitHub attributes to the gradual nature of the error increase and a gap in alerting for this type of failure. Once identified, the missing record was re-created and service returned to normal by 20:30 UTC, with the incident fully resolved at 20:35 UTC. Note on source depth: this incident is documented in GitHub's monthly availability report rather than a standalone post-mortem, so the timeline carries the timestamps GitHub published rather than a full event-by-event account.

## Timeline

All times UTC.

- **18:53** — Elevated error rates begin on GitHub Pages as cached copies of the deleted DNS record start expiring across GitHub's systems.
- **Detection ~53 minutes after onset** — The issue is identified. GitHub attributes the delay to the gradual nature of the error increase and a gap in alerting for this failure mode.
- **19:56** — Status page incident opened.
- **20:30** — The missing DNS record is re-created and service returns to normal.
- **20:35** — Incident fully resolved.

## Root Cause

An automated DNS management tool deleted a DNS record for a GitHub Pages backend storage host.

The tool relies on an upstream data source to determine which records should exist. That source intermittently failed to return the record in question. The tool interpreted the record's absence from its input as evidence that the record was stale, and removed it — treating missing data as authoritative rather than as a signal that its own input was unreliable.

The failure did not surface immediately. The deleted record remained in caches across GitHub's systems, so impact grew as those cached copies expired and Pages servers progressively lost the ability to reach the affected storage host. That gradual onset, combined with a gap in alerting for this type of failure, is why detection took approximately 53 minutes rather than minutes.

## Resolution

Once the issue was identified, the team traced it to the missing DNS record and re-created it. Service returned to normal by 20:30 UTC, and the incident was fully resolved at 20:35 UTC.

## Prevention

- Implementing availability-zone-tolerant routing in the GitHub Pages frontend, so that an unresolvable backend host triggers failover to healthy hosts rather than returning errors.
- Adding safeguards to prevent automated deletion of DNS records owned by other systems.
- Improving logging and alerting for DNS resolution failures in the GitHub Pages serving path.