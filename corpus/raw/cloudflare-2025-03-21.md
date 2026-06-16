---
id: cloudflare-r2-2025-03-21
title: "Credential rotation mis-deployment causes 67-minute global outage for R2 object storage"
company: Cloudflare
date: 2025-03-21
severity: critical
duration_minutes: 67
affected_services:
  - R2 Object Storage
  - Cache Reserve
  - Images
  - Log Delivery
  - Stream
  - Vectorize
  - Email Security
  - Key Transparency Auditor
  - Billing
root_cause_category: human-error
---

## Summary

On 21 March 2025, Cloudflare R2 object storage experienced a 67‑minute global outage (21:38 UTC – 22:45 UTC) after a credential rotation was mis‑deployed to a development environment instead of production. During the incident window, **100% of write operations** and approximately **35% of read operations** failed globally.

While rotating credentials used by the R2 Gateway service (the API frontend) to authenticate with Cloudflare's distributed storage infrastructure, the R2 engineering team inadvertently omitted the `--env production` parameter when running `wrangler secret put` and `wrangler deploy` commands. The new credentials were deployed to the **default (non‑production) Worker** instead of the production Worker. When the old credentials were later deleted from the storage infrastructure (as the final step of the rotation process), the production R2 Gateway service lost the ability to authenticate — resulting in widespread authentication failures.

The incident was exacerbated by a lack of visibility into which credentials the production Gateway Worker was actively using, delaying root cause identification. There was **no data loss or corruption**: any in‑flight uploads or mutations that returned successful HTTP status codes were persisted. However, downstream services that depend on R2 — including Cache Reserve, Images, Stream, Vectorize, Log Delivery, and Email Security — experienced varying degrees of impact.

Once the root cause was identified (after approximately 58 minutes of investigation), the team deployed the correct credentials to the production Gateway Worker, and service availability recovered immediately.

---

## Timeline

All timestamps are in Coordinated Universal Time (UTC).

| Time | Event |
|------|-------|
| **19:49** | R2 engineering team begins credential rotation process. New credentials (ID and key pair) for storage infrastructure are created. Old credentials are maintained to avoid downtime during the changeover. |
| **20:19** | Team executes `wrangler secret put` (to set the new credential secret) and `wrangler deploy` (to update the credential ID environment variable) for the R2 Gateway service. **Critical error:** The `--env` parameter is inadvertently omitted from both commands. Credentials are deployed to the **default (non‑production) Worker** instead of the production Worker. |
| **20:20** | The R2 Gateway Worker assigned to the **default** environment begins using the updated credentials. The team incorrectly believes the credentials have been updated on the production Worker. |
| **20:37** | Old credentials are removed from the storage infrastructure to complete the rotation process. |
| **21:38** | **IMPACT BEGINS** — R2 availability metrics begin to show signs of service degradation. The impact is gradual and not immediately obvious due to a delay in propagation of the credential deletion to the storage infrastructure. |
| **21:45** | R2 global availability alerts trigger (indicating 2% of error budget burn rate). R2 engineering team begins investigating operational dashboards and logs. |
| **21:50** | Internal incident declared. |
| **21:51** | Team observes gradual but consistent decline in R2 availability for both read and write operations. Metadata‑only operations (e.g., head and list) are unaffected. Suspicion falls on a potential regression in credential propagation. |
| **22:05** | Public incident status page published. |
| **22:15** | Team creates a new set of storage credentials in an attempt to force re‑propagation. No improvement observed. Investigation continues. |
| **22:30** | Team deploys another new set of credentials to the R2 Gateway Worker to validate whether the credentials themselves were the issue. **The `--env` parameter is still omitted**, so deployment again targets the wrong (non‑production) Worker. No improvement. |
| **22:36** | **ROOT CAUSE IDENTIFIED** — By reviewing the production Worker release history, the team discovers that credentials were deployed to a non‑production Worker, not the production Worker. |
| **22:45** | **IMPACT ENDS** — Correct credentials are deployed to the production R2 Gateway Worker. R2 availability recovers immediately. |
| **22:54** | Incident is considered resolved. |

---

## Root Cause

The **immediate trigger** was a human error: an engineer omitted the `--env production` parameter when running `wrangler secret put` and `wrangler deploy` commands during a routine credential rotation. This resulted in the new credentials being deployed to the **default (development)** R2 Gateway Worker instead of the production Worker. When the old credentials were subsequently deleted from the storage infrastructure, the production Gateway lost the ability to authenticate and serve requests.

However, the following **systemic failures** contributed to the incident and delayed recovery:

1. **Lack of credential visibility** — The R2 engineering team had no way to observe which credential ID the production Gateway Worker was actively using to authenticate with the storage infrastructure. Without this visibility, the team could not quickly confirm whether the correct credentials were deployed.

2. **Manual, error‑prone command‑line process** — The credential rotation relied entirely on manually entered `wrangler` commands. The process had no safety checks or guardrails to prevent mis‑deployment to the wrong environment (e.g., confirmation prompts, environment validation, or automated release tooling).

3. **Gradual failure propagation** — The deletion of the old credentials from the storage infrastructure did not propagate immediately, causing the availability degradation to be gradual rather than immediate. This delayed detection: the error rate increased slowly over 7 minutes (21:38–21:45) before crossing the alert threshold, and the team initially suspected a propagation issue rather than a mis‑deployment.

4. **Insufficient validation steps** — The key rotation process did not include a mandatory step to validate that the new credentials were being used by the production Gateway *before* deleting the old credentials from the storage infrastructure.

5. **Credential re‑deployment attempts were repeated errors** — At 22:30, the team attempted to deploy a new set of credentials to validate the issue but **again omitted the `--env` parameter**, losing critical time before root cause discovery.

---

## Resolution

1. **Root cause identified (22:36 UTC)** — By reviewing the production Worker release history, the team discovered that credentials had been deployed to the default (non‑production) Worker rather than the production Worker.

2. **Correct credentials deployed (22:45 UTC)** — The team deployed the new credentials to the **production** R2 Gateway Worker using the correct `--env production` parameter. R2 availability recovered immediately.

3. **Incident declared resolved (22:54 UTC)** — Once R2 metrics stabilised and all dependent services recovered, the incident was formally closed.

There was **no data loss** during the incident. R2's storage subsystem remained intact; the issue was limited to a temporary authentication failure between R2's API frontend and the storage infrastructure. The intermediate read cache sitting in front of storage also mitigated read impact, serving cached objects even when direct storage authentication failed.

---

## Prevention

Cloudflare has committed to the following improvements to prevent recurrence:

### Immediate Actions (Completed)

1. **Enhanced credential observability** — Added logging tags that include the suffix of the credential ID the R2 Gateway Worker uses to authenticate with the storage infrastructure. With this change, engineers can explicitly confirm which credential is being used by the production service at any time.

2. **Mandatory confirmation step** — The internal process now requires explicit confirmation that the suffix of the new token ID matches logs from the storage infrastructure **before** deleting the previous token.

3. **Automated release tooling** — Key rotations must now take place through the hotfix release tooling rather than relying on manual `wrangler` command entry. This tooling explicitly enforces the environment configuration and contains additional safety checks.

4. **Two‑person validation** — Standard operating procedures (SOPs) have been updated to explicitly require that key rotation changes be validated by at least two engineers before proceeding.

### In Progress

5. **Closed‑loop health checks** — Extending the existing closed‑loop health check system to test new keys, automate reporting of their status through the alerting platform, and ensure global propagation prior to releasing the Gateway Worker.

6. **Improved observability dashboards** — Updating the observability platform to include views of upstream success rates that bypass caching, giving clearer indication of issues serving requests for any reason.

