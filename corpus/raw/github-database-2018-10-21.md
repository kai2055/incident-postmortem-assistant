---
id: github-database-2018-10-21
title: "Network partition triggers cross-country database failover causing 24-hour outage"
company: GitHub
date: 2018-10-21
severity: critical
duration_minutes: 1451
affected_services:
  - GitHub.com
  - GitHub API
  - Webhooks
  - GitHub Pages
  - Git operations
  - MySQL clusters
root_cause_category: database-storage
---

## Summary

On October 21, 2018, GitHub experienced a 24-hour and 11-minute incident that resulted in degraded service across multiple systems. At 22:52 UTC, routine maintenance work to replace failing 100G optical equipment caused a 43-second loss of connectivity between GitHub's US East Coast network hub and primary US East Coast data center. This brief network partition triggered a chain of events that led to a database failover. Orchestrator, GitHub's MySQL cluster management tool, automatically failed over database primaries from the East Coast to the West Coast data center. However, the East Coast database contained a brief period of writes that had not yet replicated to the West Coast. This created a split-brain situation where both data centers had writes the other didn't have. GitHub prioritized data integrity over site availability, choosing to fail forward with the West Coast as primary rather than risk data loss. This required restoring from backups, which took hours due to the large database sizes (up to 5TB) and remote backup storage. During the incident, webhooks and Pages builds were paused (5 million+ hook events, 80,000 Pages builds queued). No user data was lost, but manual reconciliation for a few seconds of database writes continued after the incident. The site was fully restored at 23:03 UTC on October 22.

## Timeline

All timestamps in UTC.

| Time | Event |
|------|-------|
| **October 21 22:52** | Routine maintenance causes 43-second loss of connectivity between US East Coast network hub and primary data center |
| **October 21 22:52** | Orchestrator fails over database primaries from East Coast to West Coast. East Coast has writes that haven't replicated to West Coast |
| **October 21 22:54** | Internal monitoring alerts trigger |
| **October 21 23:02** | Engineers determine database topologies are in unexpected state. West Coast topology only visible |
| **October 21 23:07** | Deployment tooling manually locked to prevent additional changes |
| **October 21 23:09** | Site status set to yellow (degraded) |
| **October 21 23:11** | Incident coordinator joins |
| **October 21 23:13** | Site status set to red (major outage). Database engineering team paged |
| **October 21 23:19** | Webhook delivery and Pages builds paused to prioritize data integrity |
| **October 22 00:05** | Plan developed: restore from backups, synchronize replicas, fall back to stable topology |
| **October 22 00:41** | Backup process initiated for all affected MySQL clusters |
| **October 22 06:51** | First clusters restored. Slow site performance due to cross-country writes |
| **October 22 07:46** | Blog post published providing context |
| **October 22 11:12** | All database primaries established in East Coast. Site more responsive |
| **October 22 13:15** | Replication delays increasing. Additional read replicas provisioned in East Coast public cloud |
| **October 22 16:24** | Replicas in sync. Failover to original topology completed |
| **October 22 16:45** | Backlog processing begins: 5 million+ webhooks, 80,000 Pages builds |
| **October 22 23:03** | All backlogs processed. Site status set to green. Incident resolved |

## Root Cause

The incident was caused by a database failover and split-brain condition triggered by a brief network partition:

1. **Network partition (43 seconds)** — Routine maintenance on 100G optical equipment caused a 43-second loss of connectivity between GitHub's US East Coast network hub and primary data center.

2. **Automatic database failover** — Orchestrator, GitHub's MySQL cluster management tool, detected the partition and failed over database primaries to the US West Coast data center. Orchestrator's actions behaved as configured, but the application tier was unable to support the sudden cross-country latency.

3. **Split-brain condition** — The East Coast database contained a brief period of writes (several seconds worth) that had not yet replicated to the West Coast before the partition. Both data centers now contained writes the other didn't have.

4. **Data integrity vs. availability trade-off** — GitHub prioritized data integrity over site availability. Failing forward with West Coast as primary was the only way to preserve user data. However, applications in the East Coast couldn't tolerate the cross-country latency for writes, making the service unusable for many users.

5. **Slow recovery** — Restoring from backups took hours because:
   - Backups were stored remotely in a public cloud blob storage service
   - Database sizes ranged up to 5TB
   - The restore process involved decompressing, checksumming, preparing, and loading large backup files

6. **Replication delays** — After restoration, read replicas were delayed hours behind the primary. Recovery took longer than estimated because replication delays followed a power decay function, not linear, and were compounded by increased write load as users began their workday.

## Resolution

1. **Network partition resolved (22:52 UTC)** — Connectivity restored in 43 seconds, but failover already triggered

2. **Manual intervention (23:07 UTC)** — Deployment tooling locked to prevent additional changes

3. **Pause non-critical services (23:19 UTC)** — Webhooks and Pages builds paused to protect data integrity

4. **Backup restoration (00:41 UTC onwards)** — Restored from backups for affected MySQL clusters. Process took hours due to large database sizes and remote storage

5. **Additional read replicas provisioned** — East Coast public cloud replicas added to spread read load and allow replication to catch up

6. **Failback to East Coast (16:24 UTC)** — Replicas synced, topology restored to original configuration

7. **Backlog processing (16:45–23:03 UTC)** — Processed 5 million+ queued webhooks and 80,000 Pages builds

8. **Full recovery (23:03 UTC)** — All backlogs processed, site status green

## Prevention

GitHub committed to multiple improvements:

1. **Orchestrator configuration alignment** — Adjust Orchestrator configuration to prevent promotion of database primaries across regional boundaries and align with application expectations

2. **Faster backup restoration** — Test backup restoration processes more thoroughly. Backups were tested daily, but a full cluster rebuild had never been performed before

3. **N+1 redundancy at facility level** — Ensure redundancy so that a single facility failure does not impact service availability

4. **Chaos engineering and fault injection** — Proactive testing of assumptions through fault injection and chaos engineering to validate failure scenarios before they affect users