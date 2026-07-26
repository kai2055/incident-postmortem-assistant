---
id: cloudflare-route-leak-2026-01-22
title: "Removing a prefix-list leaves a routing policy permissive enough to leak internal IPv6 prefixes"
company: Cloudflare
date: 2026-01-22
severity: major
duration_minutes: 25
affected_services:
  - Cloudflare backbone (Miami–Atlanta)
  - IPv6 transit and peering at Miami (MIA01)
root_cause_category: network-bgp
---

## Summary

On January 22, 2026, an automated routing policy configuration error caused Cloudflare to unintentionally leak BGP prefixes from a router at its Miami data center. The leak lasted 25 minutes and affected IPv6 traffic only. A change intended to remove BGP announcements from Miami for a Bogotá data center deleted prefix-lists from several policy terms, leaving those terms matching on `route-type internal` alone. In JunOS that match accepts any non-external route type, including IBGP, so every IPv6 prefix Cloudflare redistributes internally across its backbone was advertised to all BGP neighbours in Miami. Cloudflare took routes received from peers and readvertised them to peers and providers, producing a mixture of Type 3 and Type 4 route leaks as defined in RFC7908. The consequences fell on Cloudflare and on external networks alike: congestion on the backbone between Miami and Atlanta caused elevated loss and higher latency for some Cloudflare customer traffic, while traffic belonging to the leaked networks was funnelled into the Miami router and discarded by firewall filters designed to accept only Cloudflare and customer traffic — roughly 12Gbps at peak.

## Timeline

All times UTC.

- **2026-01-22 19:52** — A change that ultimately triggers the routing policy bug is merged into the network automation code repository.
- **2026-01-22 20:25** — Automation runs on a single Miami edge router, producing unexpected advertisements to BGP transit providers and peers. **Impact starts.**
- **2026-01-22 20:40** — Network team begins investigating unintended route advertisements from Miami.
- **2026-01-22 20:44** — Incident raised to coordinate response.
- **2026-01-22 20:50** — A network operator manually reverts the bad configuration change and pauses automation for the router so it cannot run again. **Impact stops.**
- **2026-01-22 21:47** — The change that triggered the leak is reverted from the code repository.
- **2026-01-22 22:07** — Operators confirm automation is healthy to run again on the Miami router, without the routing policy bug.
- **2026-01-22 22:40** — Automation is unpaused on the single router in Miami.

## Root Cause

The intended change was routine. Cloudflare had previously forwarded some IPv6 traffic through Miami toward a data center in Bogotá, Colombia, and infrastructure upgrades had removed the need to do so. The change removed the BGP announcements for Bogotá from Miami.

The diff removed the `6-BOG04-SITE-LOCAL` prefix-list from nine policy statements — the export policies for Cogent, Comcast, GTT, Level3, Telefónica and Telia, and the anycast and public-peer output policies.

The failure is in what was left behind rather than what was removed. With the prefix-list gone, a policy term such as the Telia export policy retained only its `from route-type internal` match:

```
policy-options policy-statement 6-TELIA-ACCEPT-EXPORT {
    term ADV-SITELOCAL-GRE-RECEIVER {
        from route-type internal;
        then {
            community add STATIC-ROUTE;
            ...
            accept;
        }
    }
}
```

The term now marked every prefix of type "internal" as acceptable and, critically, accepted it through the policy filter — so prefixes intended to remain internal were advertised externally. In JunOS and JunOS EVO, `route-type internal` matches any non-external route type, including Internal BGP routes.

The result was that every IPv6 prefix Cloudflare redistributes internally across its backbone was advertised to all BGP neighbours in Miami. **Removing a filter made the policy more permissive rather than narrower.**

In routing terms, AS13335 took prefixes received from peers — for example 2a03:2880:f077::/48 from Meta, AS32934 — and readvertised them toward upstream transit providers such as Lumen, AS3356. Routes received from peers should only be readvertised to downstream customer networks, never laterally to other peers or upward to providers. This violates valley-free routing and constitutes a mixture of Type 3 and Type 4 route leaks under RFC7908.

Cloudflare notes this is very similar to an outage they experienced in 2020.

## Resolution

The network team began investigating at 20:40, fifteen minutes after impact began, and raised an incident at 20:44. A network operator manually reverted the bad configuration change at 20:50, ending impact 25 minutes after it started, and paused automation for the affected router so it could not reapply the change.

The triggering change was then reverted from the code repository at 21:47. Operators confirmed at 22:07 that automation was healthy to run again on the Miami router without the routing policy bug, and unpaused automation on that router at 22:40.

## Prevention

On routing policy configuration and automation:

- Patching the failure in the routing policy automation that caused the leak, mitigating this failure mode and others like it.
- Implementing additional BGP community-based safeguards in routing policies that explicitly reject routes received from providers and peers on external export policies.
- Adding automatic routing policy evaluation into CI/CD pipelines, looking specifically for empty or erroneous policy terms.
- Improving early detection of problems with network configurations and the negative effects of an automated change.

On route leaks in general:

- Validating routing equipment vendors' implementation of RFC9234 (BGP roles and the Only-to-Customer attribute) ahead of rollout — the only mechanism independent of routing policy that prevents route leaks caused at the local Autonomous System.
- Encouraging long-term adoption of RPKI Autonomous System Provider Authorization (ASPA), which would let networks automatically reject routes containing anomalous AS paths.