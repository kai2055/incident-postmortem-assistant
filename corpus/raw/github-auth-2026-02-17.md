---
id: github-auth-2026-02-17
title: "Replication lag in the token verification cluster causes intermittent authentication failures"
company: GitHub
date: 2026-02-17
severity: minor
duration_minutes: 119
affected_services:
  - GitHub Actions
  - Git operations (SSH read)
  - GitHub App server-to-server tokens
root_cause_category: database-storage
---

## Summary

On February 17, 2026, between 17:07 UTC and 19:06 UTC, some GitHub customers experienced intermittent authentication failures affecting GitHub Actions, parts of Git operations, and other authentication-dependent requests. The Actions error rate averaged approximately 0.6% of affected API requests, and the Git operations SSH-read error rate averaged approximately 0.29%; SSH write and HTTP operations were not impacted. The failures came from token verification lookups intermittently failing, which produced 401 errors and degraded reliability for affected workflows. The root cause was elevated replication lag in the token verification database cluster: in the days leading up to the incident, the token store's write volume grew enough to exceed the cluster's available capacity, so under peak load older replica hosts could not keep up, replica lag increased, and some token lookups became inconsistent. GitHub mitigated the incident by adjusting the database replica topology to route reads away from lagging replicas and by bringing additional replica capacity online. Service health improved progressively, with GitHub Actions recovering by approximately 19:00 UTC and the incident resolved at 19:06 UTC. This was a minor, low-error-rate incident; impact was intermittent rather than a full outage. (Source depth note: this incident is documented via GitHub's status page rather than a full availability-report post-mortem, so the timeline and prevention detail below reflect what GitHub published there.)

## Timeline

All times UTC. Times are drawn from GitHub's status-page updates for this incident.

| Time | Event |
|------|-------|
| **~17:07** | Impact begins — intermittent authentication failures affecting Actions, Git operations, and authentication-dependent API requests |
| **17:46** | GitHub posts that it is investigating degraded performance for Actions and Git operations |
| **17:46** | GitHub identifies a low rate of authentication failures affecting GitHub App server-to-server tokens, GitHub Actions authentication tokens, and Git operations; states it believes it has identified the cause and is working to mitigate |
| **18:18** | Mitigation rolled out; early signs of recovery; monitoring continues |
| **18:55** | Continued monitoring, continued signs of recovery |
| **~19:00** | GitHub Actions recovers |
| **19:06** | Incident resolved |

## Root Cause

The incident was caused by elevated replication lag in the token verification database cluster — the data store GitHub uses to verify authentication tokens. In the days leading up to the incident, the token store's write volume grew enough to exceed the cluster's available capacity. The failure then developed under peak load:

1. Older replica hosts in the cluster were unable to keep up with the write volume.
2. Replica lag increased beyond acceptable thresholds.
3. Because token lookups could be served by lagging replicas, some lookups returned inconsistent results — some succeeded, some failed.
4. The failed lookups surfaced to users as intermittent 401 authentication errors.

The failure was confined to token verification: it affected GitHub App server-to-server tokens, GitHub Actions authentication tokens, and SSH-read Git operations. SSH-write and HTTP operations were not impacted, which is why the overall error rates stayed low and the impact was intermittent rather than total.

## Resolution

1. **Cause identified** — GitHub traced the intermittent 401s to replication lag causing inconsistent token lookups in the token verification cluster.
2. **Replica topology adjusted** — Reads were routed away from the lagging replicas toward replicas that were keeping up, restoring consistent token lookups.
3. **Capacity added** — Additional replica capacity was brought online to handle the increased write volume that had outgrown the cluster.
4. **Progressive recovery** — Service health improved after the changes, with GitHub Actions recovering by approximately 19:00 UTC.
5. **Resolution** — The incident was marked resolved at 19:06 UTC.

## Prevention

GitHub stated it is working to prevent recurrence by improving the resilience and scalability of the underlying token verification data stores so they can better handle continued growth in write volume — the pressure that had caused the cluster to exceed its capacity and fall behind on replication.