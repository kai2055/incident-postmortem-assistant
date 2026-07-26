---
id: cloudflare-bgp-2019-06-24
title: "Verizon BGP route leak causes global internet outage"
company: Cloudflare
date: 2019-06-24
severity: major
duration_minutes: 129
affected_services:
  - Internet (global)
  - Cloudflare
  - Amazon
  - Linode
  - Many other internet services
root_cause_category: network-bgp
---

## Summary

On June 24, 2019, a BGP route leak caused a global internet outage affecting many major services including Cloudflare, Amazon, and Linode. The incident lasted approximately 2 hours (10:30 UTC to 12:39 UTC). At its worst, Cloudflare observed a loss of about 15% of its global traffic. The leak was triggered when DQE Communications (AS33154), a small ISP in Pennsylvania, was using a BGP optimizer product from Noction that split IP prefixes into smaller, more-specific routes. These routes were sent to their customer Allegheny Technologies (AS396531), which then propagated them to their transit provider Verizon (AS701). Verizon, failing to implement proper filtering (prefix limits, IRR-based filtering, or RPKI validation), forwarded these invalid routes to the rest of the internet. This caused traffic destined for Cloudflare and other services to be routed through small networks that were not equipped to handle the traffic volume, resulting in widespread service disruption. The leak was resolved when DQE Communications stopped advertising the optimized routes to Allegheny Technologies. Approximately 2,400 ASNs (networks) were affected. There was no evidence of malicious activity or data compromise.

---

## Timeline

- **10:30 UTC** — BGP route leak begins. DQE Communications (AS33154) using BGP optimizer splits Cloudflare routes into more-specific prefixes and announces them to Allegheny Technologies (AS396531)
- **10:30 UTC** — Allegheny Technologies propagates these routes to Verizon (AS701)
- **10:30 UTC** — Verizon forwards invalid routes to the global internet, causing traffic to be misrouted to small networks not equipped to handle the volume
- **10:30–10:34 UTC** — Impact rapidly spreads globally. Cloudflare observes traffic loss starting
- **10:34:25 UTC** — First leaked routes observed in RIPE NCC data
- **~11:00 UTC** — Cloudflare network engineers reach out to affected networks (DQE Communications and Verizon)
- **~11:30 UTC** — Cloudflare makes contact with DQE Communications
- **12:38:54 UTC** — Last leaked route observed. DQE Communications stops advertising optimized routes to Allegheny Technologies
- **~12:39 UTC** — Internet stabilizes. Route leak ends
- **~19:58 UTC** — Cloudflare publishes first blog post about the incident

---

## Root Cause

The immediate trigger was a BGP route leak caused by a combination of factors:

1. **BGP optimizer usage** — DQE Communications (AS33154) was using a BGP optimizer product from Noction. This product has a feature that splits received IP prefixes into smaller, more-specific parts (e.g., 104.20.0.0/20 → 104.20.0.0/21 and 104.20.8.0/21). These more-specific routes override general routes in BGP routing.

2. **Route propagation** — DQE announced these specific routes to their customer Allegheny Technologies (AS396531). Allegheny then sent all routing information to their transit provider Verizon (AS701).

3. **Verizon lacked filtering** — Verizon failed to implement proper BGP filtering, including:
   - **Prefix limits** — No hard limit on number of prefixes received from a customer. A prefix limit would have shut down the BGP session when too many routes were announced.
   - **IRR-based filtering** — No filtering based on Internet Routing Registry (IRR) records. The IRR records for the affected networks did not contain Cloudflare's routes, so Verizon should have rejected them.
   - **RPKI validation** — No RPKI-based filtering. Cloudflare routes are RPKI-signed with a maximum length of /20, meaning any more-specific prefix (/21, /22, etc.) should have been rejected. Verizon did not have RPKI validation enabled.

4. **NO_EXPORT community not used** — The NO_EXPORT BGP community (which prevents routes from being advertised outside a network) was not applied, allowing the leak to spread.

---

## Resolution

1. **Cloudflare engineers identified the issue** — The network team observed traffic loss and identified the route leak originating from AS396531 via AS701.

2. **Contacted affected networks** — Cloudflare engineers reached out to DQE Communications (AS33154) and Verizon (AS701). Verizon did not respond (no reply received over 8 hours after the incident). DQE Communications responded quickly.

3. **DQE stopped advertising** — DQE Communications worked with Cloudflare engineers to stop advertising the "optimized" routes to Allegheny Technologies. This removed the invalid routes from the global routing table.

4. **Internet stabilized** — Once the invalid routes were withdrawn, traffic returned to normal.

---

## Prevention

1. **Prefix limits** — BGP sessions should be configured with a hard limit on the number of prefixes received from a customer. This would have terminated the BGP session when DQE sent too many routes to Allegheny, stopping the leak.

2. **IRR-based filtering** — Networks should implement filtering based on Internet Routing Registry (IRR) records. If Verizon had used IRR filtering, they would have rejected the invalid more-specific routes.

3. **RPKI deployment** — Networks should enable BGP Origin Validation using RPKI. RPKI indicates that Cloudflare's prefixes have a maximum length of /20, so the /21 routes should have been rejected. AT&T (AS7018) has RPKI validation enabled and was not affected by this leak. Cloudflare encourages all network operators to deploy RPKI.

4. **AS-PATH filtering** — Tier 1 networks should implement AS-PATH filters that reject routes containing other Tier 1 ASNs in the path. This would have prevented the leak from propagating beyond Verizon.

5. **Community tagging** — The NO_EXPORT BGP community should be used to prevent routes from being advertised outside a network.

6. **Adopt MANRS** — The Mutually Agreed Norms for Routing Security (MANRS) provides a framework for routing security best practices.

7. **IPv6** — The leak was IPv4-only. Networks should enable IPv6 to provide an alternative path during IPv4 routing incidents.