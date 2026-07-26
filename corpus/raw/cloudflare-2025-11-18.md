---
id: cloudflare-2025-11-18
title: "Bot Management configuration file caused global proxy outage"
company: Cloudflare
date: 2025-11-18
severity: critical
duration_minutes: 346
affected_services:
  - Core CDN and security services
  - Turnstile
  - Workers KV
  - Dashboard
  - Email Security
  - Access
root_cause_category: configuration-error
---

## Summary
On November 18, 2025, Cloudflare suffered a global outage lasting approximately 3 hours of major impact, with full recovery after 5 hours 46 minutes. A database permission change deployed at 11:05 UTC inadvertently caused the Bot Management configuration file to be generated at roughly double its normal size. When the core proxy service loaded the bloated file, it crashed, returning HTTP 5xx errors to all users. The failure was intermittent at first — the file was regenerated every 5 minutes from a ClickHouse cluster, and only nodes that had received the permission update produced the bad file. This fluctuation initially led the team to suspect a DDoS attack. Once all nodes were updated, the failure became persistent. Major websites including Spotify, ChatGPT, X, and Canva became unreachable. The incident was resolved by stopping the propagation of the bad file, manually injecting a known‑good file, and forcing a global restart of the proxy. Cloudflare described this as their worst outage since 2019.

## Timeline
- **11:05 UTC** – Database access control change deployed.
- **11:28 UTC** – Impact starts; deployment reaches customer environments, first errors on HTTP traffic.
- **11:31 UTC** – First automated test detects the issue.
- **11:32 UTC** – Manual investigation begins; elevated error rates on Workers KV observed.
- **11:35 UTC** – Incident call created.
- **13:05 UTC** – Bypass implemented for Workers KV and Cloudflare Access, falling back to a prior proxy version. Impact reduced.
- **13:37 UTC** – Work focused on rolling back the Bot Management configuration file to a last‑known‑good version.
- **14:24 UTC** – Stopped creation and propagation of new Bot Management configuration files. Test with old file completed successfully.
- **14:30 UTC** – Correct Bot Management configuration file manually injected into the distribution queue; core proxy restarted globally. Main impact resolved.
- **17:06 UTC** – All downstream services restarted; 5xx error volume returned to normal. Incident fully resolved.

## Root Cause
A database access control change gave the Bot Management configuration query permission to see additional metadata tables in the `r0` database. As a result, the query that generates the bot feature configuration file began returning duplicate column entries, roughly doubling the number of “features.” The Bot Management system preallocates memory for up to 200 features (normal usage was ~60). The bloated file contained more than 200 features, causing the proxy module to panic and crash with a 5xx error. The file was regenerated every 5 minutes from a ClickHouse cluster where the permission change rolled out gradually; this created intermittent crashes until all nodes were updated, after which the failure became permanent. The configuration file was automatically distributed to every proxy instance worldwide, making the outage global.

## Resolution
1. At 13:05 UTC, engineers bypassed the core proxy for Workers KV and Access, reducing downstream impact.
2. At 13:37 UTC, teams focused on restoring a previous known‑good version of the Bot Management configuration file.
3. At 14:24 UTC, automatic generation and propagation of new configuration files was halted. A test with the old file showed successful recovery.
4. At 14:30 UTC, a known‑good file was manually placed into the distribution queue and a global proxy restart was forced. Core services began functioning normally.
5. By 17:06 UTC, all remaining downstream services were restarted and error rates returned to baseline.

## Prevention
Cloudflare committed to:
- Hardening ingestion of internally generated configuration files, applying the same validation as for user‑supplied input.
- Enabling more global kill switches for rapid feature isolation.
- Eliminating the ability for core dumps or error reports to overwhelm system resources.
- Reviewing failure modes for error conditions across all core proxy modules.