---
id: github-dns-2024-10-11
title: "Database migration triggers cascading DNS failure, causing 19-hour degraded performance across GitHub services"
company: GitHub
date: 2024-10-11
severity: critical
duration_minutes: 1152
affected_services:
  - Copilot
  - Actions
  - Code Search
  - Customer Migrations
  - support.github.com
  - Artifact Attestations
root_cause_category: cascading-failure
---

## Summary

On 11 October 2024, GitHub experienced a **19-hour and 12-minute** incident of degraded performance across its services, stemming from a DNS infrastructure failure following a database migration.

The incident began at **05:59 UTC** when DNS infrastructure in one of GitHub's sites started failing to resolve lookups after a database migration. Attempts to recover the database led to cascading failures that further impacted the DNS systems for that site. The team worked to restore the infrastructure, and **no customer impact was observed until 17:31 UTC**.

Customer impact was broad and severe. **4% of Copilot users** experienced degraded IDE code completions, **25% of Actions workflow users** encountered delays exceeding 5 minutes (with 1% errors), and **100% of code search requests failed** for approximately four hours. Additional services including customer migrations, support.github.com, and Artifact Attestations were also impacted.

The first mitigation attempt — repointing the degraded DNS site to a different location — was partially successful but introduced connectivity issues from healthy sites back to the degraded site. A second remediation plan was finalised at **20:52 UTC**, deploying temporary DNS resolution capabilities to the affected site. DNS resolution began recovering at **21:46 UTC** and was fully healthy by **22:16 UTC**. Lingering issues with code search persisted until **01:11 UTC on 12 October**.

---

## Timeline

All timestamps are in Coordinated Universal Time (UTC).

| Time | Event |
|------|-------|
| **05:59** | DNS infrastructure in one of GitHub's sites begins failing to resolve lookups following a database migration. No customer impact yet. |
| **17:31** | **IMPACT BEGINS** — First customer impact observed. Copilot degradation begins. |
| **17:53** | Incident declared and investigation initiated. |
| **18:05** | Engineering attempts to repoint the degraded DNS site to a different site to restore DNS functionality. |
| **18:16** | Customer migrations begin failing — running migrations stop and new ones cannot start. |
| **18:26** | Test system validates the repointing approach; progressive rollout proceeds over the next hour. |
| **18:41** | Customer migrations remain paused. Copilot users in organisations with Content Exclusions feature experience disabled completions. |
| **19:05** | Problem identified as related to maintenance performed in networking infrastructure. Artifact Attestations cannot be created. |
| **19:28** | support.github.com becomes unavailable. |
| **20:15** | Code search becomes unavailable. |
| **20:28** | Actions delays and errors begin — 25% of runs delayed by over 5 minutes. |
| **20:52** | First mitigation attempt does not resolve the issue. Team proceeds with different resolution path. |
| **21:28** | Actions begins recovery. |
| **21:46** | DNS resolution in the degraded site begins to recover. |
| **22:14** | support.github.com recovers. |
| **22:16** | DNS resolution fully healthy. Copilot recovers. |
| **22:57** | Copilot operating normally. Actions services recovered. |
| **23:12** | Customer migrations recover. |
| **00:14** (Oct 12) | Code search issue identified. |
| **00:46** (Oct 12) | Code search query failures end. |
| **01:11** (Oct 12) | **IMPACT ENDS** — Lingering code search issues fully resolved. |

---

## Root Cause

The **immediate trigger** was a database migration that caused DNS infrastructure in one of GitHub's sites to fail to resolve lookups. Attempts to recover the database led to **cascading failures** that further impacted the DNS systems for that site.

However, the following **systemic failures** contributed to the incident's severity and duration:

1. **Cascading failure propagation** — A single database migration failure cascaded into DNS infrastructure failure, demonstrating insufficient isolation between systems.

2. **Mitigation attempt introduced new problems** — The initial remediation strategy — repointing the degraded DNS site to a different location — was effective at restoring connectivity within the degraded site, but it **caused connectivity issues from healthy sites back to the degraded site**. This necessitated a second, more complex remediation effort.

3. **Slow remediation planning** — The first mitigation attempt failed, and the team did not finalise a successful remediation plan until **20:52 UTC**, approximately **3 hours after customer impact began**.

4. **Broad blast radius** — The DNS failure impacted multiple downstream services simultaneously:
   - Copilot (4% of users affected)
   - Actions (25% of workflows delayed >5 minutes, 1% errors)
   - Code search (100% failure rate for ~4 hours)
   - Customer migrations
   - support.github.com
   - Artifact Attestations

5. **Prolonged code search recovery** — Even after DNS resolution was fully restored at 22:16 UTC, code search remained degraded until 01:11 UTC the following day.

---

## Resolution

1. **Initial mitigation attempted (18:05 UTC)** — Engineering attempted to repoint the degraded site DNS to a different site to restore DNS functionality. At 18:26 UTC, the test system validated this approach and a progressive rollout to the affected hosts proceeded over the next hour.

2. **Mitigation introduced new issues** — While this approach was effective at restoring connectivity within the degraded site, it caused issues with connectivity from healthy sites back to the degraded site. The team proceeded to plan out a different remediation effort.

3. **Second remediation plan (20:52 UTC)** — The team finalised a new remediation plan and began the next phase of mitigation by deploying temporary DNS resolution capabilities to the degraded site.

4. **DNS recovery (21:46 – 22:16 UTC)** — DNS resolution in the degraded site began to recover at 21:46 UTC and was fully healthy at 22:16 UTC.

5. **Code search recovery (01:11 UTC, 12 October)** — Lingering issues with code search were resolved at 01:11 UTC on October 12.

6. **Full restoration** — The team continued to restore the original functionality within the site after public service functionality was restored.

---

## Impact

| Product/Service | Impact |
|-----------------|--------|
| **Copilot** | Degradation in IDE code completions for **4% of active users** during the incident from 17:31 UTC to 21:45 UTC. |
| **Actions** | **25% of workflow runs** delayed by over 5 minutes; **1% error rate** between 20:28 UTC and 21:30 UTC. Errors while creating Artifact Attestations. |
| **Code Search** | **100% of queries failed** between 20:16 UTC on 11 October and 00:46 UTC on 12 October. |
| **Customer Migrations** | Running migrations stopped and new ones could not start from 18:16 UTC to 23:12 UTC. |
| **support.github.com** | Unavailable from 19:28 UTC to 22:14 UTC. |
| **All GitHub Services** | Broad degraded performance across the platform during the incident window. |

---

## Prevention

GitHub has committed to the following improvements:

1. **Hardened resiliency** — GitHub is working to strengthen the resiliency of the affected infrastructure to prevent similar cascading failures.

2. **Improved automation** — Enhancing automation processes around DNS and database infrastructure to enable faster diagnosis and resolution of issues.

3. **Faster mitigation** — Reducing the time required to identify and deploy effective remediation strategies, particularly avoiding mitigation attempts that introduce new failure modes.

