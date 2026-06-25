---
id: sentry-postgres-2015-07-20
title: "Postgres transaction ID wraparound causes a working-day outage"
company: Sentry
date: 2015-07-20
severity: major
duration_minutes: 420
affected_services:
  - Sentry (hosted service)
  - Event ingestion (writes)
root_cause_category: database-storage
---

## Summary

On July 20, 2015, Sentry experienced a major outage that affected the hosted Sentry service for most of the US working day (approximately seven hours; the source gives the impact as "most of the US working day" rather than an exact figure). The outage was caused by Postgres transaction ID (XID) wraparound on a heavily write-loaded database. Postgres uses finite transaction IDs to determine row visibility for MVCC. When the XID counter approaches its limit of around 2 billion, Postgres stops accepting writes to prevent XID re-use, which would cause data corruption. Sentry had configured autovacuum — the maintenance process that prevents wraparound — aggressively, but a large table prevented vacuum from completing. Recovery was complicated by the inability to determine whether the running autovacuums would resolve the issue. After several hours, the team identified one remaining large mapping table that had not been vacuumed. The table stored event-to-rollup mappings, was non-critical for core functionality, and had full backups available via replicas. The team truncated the table, and the system was fully restored within five minutes. Sentry implemented configuration changes and hardware upgrades to prevent recurrence.

---

## Timeline

The source provides approximate relative times, not exact clock times.

- **Start (during the US working day)** — Postgres begins rejecting writes due to XID wraparound protection and enters a read-only state. Sentry stops accepting new events. The team identifies the cause and fails the primary master over to newly provisioned hardware.
- **First few hours** — Multiple autovacuums are running on large tables. The team chooses to let them finish rather than risk interruption by restarting, fearing a restart would increase total downtime.
- **Around three hours in** — Autovacuums finish, but Postgres still rejects writes. The logs show no failure, so the reason one table did not complete is unclear. Querying Postgres internal statistics reveals that one large table — the event-to-rollup mapping table — had not been vacuumed.
- **The decision** — The team decides to truncate the problematic table after confirming it is non-critical and that full backups exist via replicas, accepting the risk of losing that table's data in order to recover immediately.
- **Five minutes after truncation** — Postgres accepts writes again. Service is fully restored.
- **After recovery** — The backlog of queued events, which had been flushed during the incident to prevent the situation worsening, is processed.

---

## Root Cause

The outage was caused by Postgres transaction ID wraparound. In Postgres's MVCC implementation, the first time a transaction modifies data (via INSERT, UPDATE, or DELETE) a global XID counter is incremented, and XIDs are used to determine row visibility. The counter has a maximum value of approximately 2 billion. As it nears that limit, Postgres halts and stops accepting commands to prevent XID re-use, which would otherwise cause data corruption such as deleted rows reappearing or updated rows reverting to previous states.

Postgres prevents this through routine vacuuming (autovacuum), which "freezes" old XIDs so their values can be reused. Sentry's database was very write-heavy, and a large mapping table — storing event-to-rollup mappings, with one entry for every event received — prevented vacuum from completing in time. The failure left no trace in the logs, and the team did not have sufficient verbosity enabled to diagnose why that table's vacuum did not complete.

Contributing configuration factors, identified during and after the incident:

1. **`autovacuum_freeze_max_age` set too high** — allowing the freeze threshold to be reached.
2. **Default of 3 autovacuum workers** — insufficient for a write-heavy workload of this scale.
3. **Too much vacuuming delay** — lower system load, but more idle time in maintenance, slowing the freeze the database needed.
4. **Misunderstood `maintenance_work_mem`** — set to 10GB, but Postgres has a hard internal limit of 1GB for the relevant paths, so the extra memory was not used for the vacuum as intended.

---

## Resolution

1. **Identify the problem** — The team identified XID wraparound as the cause and used read replicas to maintain read-only access during the outage.
2. **Failover to new hardware** — They had recently provisioned new hardware with more memory and CPUs dedicated to maintenance, and failed the primary master over to it to run the vacuums.
3. **Wait for autovacuum to finish** — They allowed the running autovacuums to complete (around three hours), judging that interrupting them risked a longer outage. A test machine on older hardware running the same vacuum in single-user mode was still running 24 hours later, confirming this was the right call.
4. **Identify the remaining table** — After the autovacuums finished and Postgres still rejected writes, querying internal statistics revealed one large table had not been vacuumed.
5. **Truncate the table** — The team truncated the table after confirming it served only non-critical features and had full backups via replicas, accepting the risk of losing that table's data to recover immediately.
6. **Restore service** — Postgres accepted writes within five minutes of the truncation, and the flushed backlog of events was processed afterward.

---

## Prevention

Sentry implemented hardware upgrades, configuration changes, and longer-term architectural plans.

Hardware was upgraded to 256GB of memory (from 128GB, with the additional memory dedicated to vacuuming), 24 cores (dual hexcore), and 3 separate RAIDs for the OS, WAL, and data to improve I/O.

The autovacuum configuration was retuned to vacuum more aggressively:

autovacuum_freeze_max_age = 500000000
autovacuum_max_workers = 6
autovacuum_naptime = '15s'
autovacuum_vacuum_cost_delay = 0
maintenance_work_mem = '10GB'
vacuum_freeze_min_age = 10000000

Several lessons were folded into ongoing practice: `maintenance_work_mem` has a hard internal limit of 1GB for the relevant paths, so configuring it higher does not help the vacuum; `vacuum_freeze_table_age` had not been updated alongside the new configuration and was corrected after the incident; better logging and monitoring of autovacuum operations was needed; and the team noted the importance of distinguishing memory used by `shared_buffers` and `effective_cache_size` from `maintenance_work_mem`. Architecturally, Sentry planned to split relations across multiple databases to reduce vacuum pressure on any single database, and signalled a longer-term intent to move away from a purely SQL-based architecture.