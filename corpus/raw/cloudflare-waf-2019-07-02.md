---
id: cloudflare-waf-2019-07-02
title: "WAF rule with catastrophic backtracking causes global 502 errors"
company: Cloudflare
date: 2019-07-02
severity: major
duration_minutes: 27
affected_services:
  - Cloudflare WAF
  - Cloudflare CDN
  - Cloudflare Proxy
  - Cloudflare Dashboard
  - Cloudflare API
root_cause_category: configuration-error
---

## Summary

On July 2, 2019, Cloudflare experienced a 27-minute global outage that caused 502 errors for all domains using Cloudflare's proxy, CDN, and WAF services. The outage was triggered by a WAF Managed Rules update containing a poorly written regular expression that caused catastrophic backtracking, exhausting CPU on every core handling HTTP/HTTPS traffic worldwide. The CPU exhaustion brought down Cloudflare's core proxying functionality. The rule was deployed at 13:42 UTC via Quicksilver, Cloudflare's fast global key-value store. The first alerts fired at 13:45 UTC. The team identified the WAF as the cause at 14:00 UTC and executed a global WAF termination at 14:07 UTC, with traffic recovering by 14:09 UTC. The WAF was fully re-enabled at 14:52 UTC after testing. The outage was caused by multiple factors: a poorly written regex, a missing CPU protection mechanism, insufficient performance testing in CI, and a deployment SOP that allowed non-emergency WAF changes to bypass staged rollouts. Cloudflare has since re-introduced CPU protections, inspected all WAF rules, and is migrating to regex engines with runtime guarantees.

---

## Timeline

All timestamps in UTC.

- **13:31** — Engineer merges Pull Request containing WAF rule change after approval
- **13:37** — TeamCity builds rules and runs tests. Tests pass
- **13:42** — WAF rules deployed globally via Quicksilver
- **13:45** — First PagerDuty alert fires (synthetic WAF test fails). Other alerts follow rapidly
- **13:45** — Global traffic drop alert fires. SRE declares P0 incident
- **14:00** — WAF identified as the component causing the problem. Attack dismissed
- **14:02** — Global WAF termination proposed. Team struggles to access internal tools (Cloudflare Access down, credentials expired)
- **14:07** — Global WAF termination executed using bypass mechanism
- **14:09** — Traffic levels and CPU return to expected levels worldwide
- **14:09–14:52** — Team performs negative and positive tests in a single city to verify rollback
- **14:52** — WAF re-enabled globally. Full resolution

---

## Root Cause

The outage was caused by a confluence of multiple factors, not a single failure:

1. **Poorly written regular expression** — A WAF rule targeting XSS attacks contained a regex that caused catastrophic backtracking: `(?:(?:\"|'|\]|\}|\\|\d|(?:nan|infinity|true|false|null|undefined|symbol|math)|\`|\-|\+)+[)]*;?((?:\s|-|~|!|{}|\|\||\+)*.*(?:.*=.*)))`. The subpattern `.*(?:.*=.*)` caused the regex engine to backtrack enormously.

2. **Missing CPU protection** — A protection mechanism that would have prevented excessive CPU use by regular expressions was removed by mistake during a refactoring weeks prior. The refactoring was intended to make the WAF use less CPU, but the protection was inadvertently dropped.

3. **No regex complexity guarantees** — The WAF used Lua with PCRE, which uses backtracking for matching and has no mechanism to protect against runaway expressions.

4. **Insufficient test coverage** — The test suite lacked performance profiling for rules. It tested correctness (blocking/not blocking) but did not test for CPU utilization or execution time. The CI tests did not detect the issue.

5. **SOP allowed global deployment** — The Standard Operating Procedure for WAF rule changes allowed non-emergency rules to be pushed globally without staged rollouts (unlike other Cloudflare software which uses DOG → PIG → Canary → Global). The assumption was that WAF needed to respond rapidly to threats.

6. **Speed of distribution** — Quicksilver distributed the change globally in seconds, meaning the CPU exhaustion happened everywhere simultaneously.

7. **Access issues during outage** — Cloudflare's own products (Access, Dashboard, Jira) were unavailable because they rely on the Cloudflare edge. This made diagnosis and rollback harder. Credentials had also timed out for security reasons.

---

## Resolution

1. **WAF identified as cause** — At 14:00 UTC, the Performance Team pulled live CPU data and strace output showing the WAF was responsible. Error logs confirmed the WAF was in trouble.

2. **Global WAF termination executed** — At 14:07 UTC, a team member executed the global WAF termination (a mechanism to disable a single component worldwide). This was delayed by difficulty accessing internal systems.

3. **Traffic recovered** — By 14:09 UTC, CPU and traffic levels were back to expected levels worldwide.

4. **Testing before re-enable** — The team performed both negative tests (confirming it was the change) and positive tests (verifying rollback worked) in a single city using a subset of traffic, excluding paying customers.

5. **WAF re-enabled** — At 14:52 UTC, the WAF was re-enabled globally after the team was satisfied the fix was correct.

---

## Prevention

Cloudflare implemented multiple improvements:

**Immediate actions:**
- Re-introduced excessive CPU usage protection that was removed during refactoring (completed)
- Manually inspected all 3,868 WAF Managed Rules to find and correct other instances of possible excessive backtracking (inspection complete)

**Testing improvements:**
- Introduced performance profiling for all rules to the test suite (ETA: July 19)
- CI tests now detect CPU utilization issues before deployment

**Regex engine migration:**
- Switching to either the re2 or Rust regex engine, both of which have runtime guarantees and linear-time execution (ETA: July 31)
- This eliminates catastrophic backtracking as a failure mode

**Deployment process changes:**
- Changed SOP to do staged rollouts of rules using DOG → PIG → Canary → Global process
- Retained ability to do emergency global deployment for active attacks (e.g., critical 0-day vulnerabilities)

**Access improvements:**
- Emergency ability to take the Cloudflare Dashboard and API off Cloudflare's edge so they remain accessible during edge outages
- Automated Cloudflare Status page updates
- Improved training on bypass procedures for internal systems

**Long-term:**
- Porting the WAF to a new firewall engine (faster, with additional protection layers)