---
id: cloudflare-control-plane-2023-11-02
title: "Data center power failure cascades into control plane and analytics outage"
company: Cloudflare
date: 2023-11-02
severity: major
duration_minutes: 1541
affected_services:
  - Cloudflare Dashboard
  - Cloudflare API
  - Cloudflare Analytics
  - Log Push
  - Stream (uploads)
  - Magic WAN
  - Various control plane services
root_cause_category: cascading-failure
---

## Summary

From November 2 at 11:44 UTC to November 4 at 04:25 UTC, Cloudflare experienced a multi-day outage affecting its control plane (Dashboard, API) and analytics services. The outage was triggered by a cascading power failure at Flexential's PDX-DC04 data center in Hillsboro, Oregon. A utility power feed went offline at 08:50 UTC due to unplanned maintenance. Flexential failed over to generators but did not inform Cloudflare. At 11:40 UTC, a ground fault on the remaining utility feed shut down all generators and both utility feeds, causing total power loss. The facility's UPS batteries failed after only 4 minutes instead of the expected 10. Attempts to restore power were hampered by faulty circuit breakers and understaffed overnight shift.

Cloudflare had designed its control plane to run across three independent data centers, with high-availability clustering to survive the failure of any single facility. However, hidden dependencies on services exclusively running in PDX-DC04 caused critical systems to fail. Kafka and ClickHouse (log processing and analytics) were only available in PDX-DC04 but had services depending on them in the high-availability cluster. Some newer products had not been onboarded to the high-availability cluster at all. The disaster recovery facility in Europe was activated at 13:40 UTC, with most control plane services restored by 17:57 UTC. However, log processing remained unavailable for the duration, and some newer products took until full resolution on November 4 to restore. Throughout the incident, Cloudflare's network and security services continued to function as expected; traffic was not impacted.

---

## Timeline

All timestamps in UTC.

- **08:50** — Portland General Electric (PGE) unplanned maintenance affects one utility power feed into PDX-DC04. Flexential starts generators and fails over. Flexential does not inform Cloudflare
- **11:40** — Ground fault on the remaining utility feed at PDX-DC04. All 10 generators and both utility feeds shut down. PDX-DC04 loses all power
- **11:44** — UPS batteries fail (after 4 minutes, expected 10). Two routers connecting PDX-DC04 to the internet go offline. Cloudflare first alerted to issue
- **11:44** — Impact begins. Control plane and analytics services begin failing
- **12:01** — UPS batteries fully depleted. All customers of PDX-DC04 lose power
- **12:28** — First communication from Flexential to Cloudflare acknowledging power issue
- **12:48** — Flexential restarts generators. Power returns to facility
- **12:48** — Flexential attempts to restore power to Cloudflare circuits. Multiple circuit breakers found faulty. Replacement breakers not available onsite
- **13:40** — Cloudflare decides to fail over to disaster recovery site in Europe
- **13:43** — First services turned up on disaster recovery site. Thundering herd problem occurs; rate limits implemented
- **17:57** — Most control plane services stable on disaster recovery site. Most customers no longer directly impacted
- **22:48** — Flexential replaces faulty circuit breakers and restores clean power to PDX-DC04
- **November 3, ~08:00** — Team begins restoring service in PDX-DC04. Network gear powered on, thousands of servers booted
- **November 3, ~11:00** — Configuration management servers rebuilt (3 hours)
- **November 3, 11:00 – November 4, 04:25** — Servers rebuilt in parallel. Each server takes 10 minutes to 2 hours. Dependencies require some services to be brought up in sequence
- **November 4, 04:25** — All services fully restored. Impact ends

---

## Root Cause

The outage was caused by a cascade of failures, not a single event:

1. **Data center power failure** — Flexential's PDX-DC04 lost both utility feeds and all 10 generators due to a ground fault. UPS batteries failed prematurely (4 minutes vs 10 minutes expected). Recovery was delayed by faulty circuit breakers, lack of spare parts, and understaffed overnight shift (one inexperienced technician).

2. **Hidden dependencies** — Cloudflare designed its control plane to run across three independent data centers with high-availability clustering. However, critical services (Kafka, ClickHouse) were only available in PDX-DC04 but had dependencies in the high-availability cluster. These dependencies should have failed more gracefully, but they didn't.

3. **Newer products not onboarded** — Products designated Generally Available (GA) were not formally required to integrate with the high-availability cluster before GA. This meant Stream, Magic WAN, and other services lacked redundancy.

4. **Incomplete disaster recovery testing** — Cloudflare had tested taking each other facility offline, and had tested taking the high-availability portion of PDX-DC04 offline. However, they had never tested fully taking the entire PDX-DC04 facility offline. The hidden dependencies were therefore never discovered.

5. **Insufficient communication from Flexential** — Flexential did not inform Cloudflare when they failed over to generator power. Cloudflare's observability tools could not detect the power source change. Had they been informed, Cloudflare would have proactively moved services out of the degraded facility.

---

## Resolution

1. **Disaster recovery activation (13:40 UTC, November 2)** — With power restoration uncertain, Cloudflare failed over critical control plane services to the disaster recovery site in Europe.

2. **Rate limiting implemented** — When services came online, a thundering herd of retried API calls overwhelmed systems. Rate limits brought request volume under control.

3. **Most control plane restored (17:57 UTC, November 2)** — Services successfully moved to disaster recovery site stabilized. Most customers no longer directly impacted. Some products (Magic WAN, Stream uploads, bespoke APIs) remained unavailable.

4. **Power restored to PDX-DC04 (22:48 UTC, November 2)** — Flexential replaced faulty circuit breakers and restored clean power. Team delayed restoration until morning to avoid compounding mistakes due to fatigue.

5. **Facility rebuild (November 3)** — Network gear powered on. Thousands of servers booted. Configuration management servers rebuilt (3 hours). Services restored in parallel, with dependencies requiring sequential bring-up for some.

6. **Full resolution (04:25 UTC, November 4)** — All services fully restored. Some analytics datasets not replicated in Europe had persistent gaps. Log Push logs were not processed during the event and will not be recovered.

---

## Prevention

Cloudflare committed to multiple improvements:

**Code Orange process** — Shift all non-critical engineering resources to focus on control plane reliability. A formal crisis response process similar to Google's Code Yellow/Red.

**Architectural changes:**
- Remove dependencies on core data centers for control plane configuration of all services. Move to powering services from the distributed network edge
- Ensure control plane continues to function even if all core data centers are offline

**Product requirements:**
- Mandate that all Generally Available products must rely on the high-availability cluster (if they rely on any core data centers) without software dependencies on specific facilities
- Require all GA products to have a tested disaster recovery plan

**Testing improvements:**
- Test blast radius of system failures and minimize number of services impacted
- More rigorous chaos testing of all data center functions, including full removal of each core data center facility
- Thorough auditing of all core data centers with plans for reaudit

**Logging and analytics:**
- Disaster recovery plan for logging to ensure no logs are dropped even in case of failure of all core facilities

**Data center oversight:**
- Regular audits of all core data centers to ensure compliance with Cloudflare's standards
- Proactive monitoring of facility health and better communication protocols with data center providers