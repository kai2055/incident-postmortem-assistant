---
id: cloudflare-thanksgiving-2023-11-23
title: "Nation-state attacker uses stolen Okta credentials to access Atlassian systems"
company: Cloudflare
date: 2023-11-23
severity: major
duration_minutes: 1124
affected_services:
  - Cloudflare Atlassian Suite (Jira, Confluence, Bitbucket)
root_cause_category: credential-auth
---

## Summary

On November 23, 2023 (Thanksgiving Day), Cloudflare detected a nation-state threat actor on its self-hosted Atlassian server. The attacker had gained access using one access token and three service account credentials that were stolen during the October 18, 2023 Okta compromise and that Cloudflare failed to rotate, mistakenly believing them unused. Note on duration: this is a security breach rather than a service outage, so `duration_minutes` here measures the detection-to-eviction window — from the first alert at November 23 16:00 UTC to the last evidence of threat activity at November 24 10:44 UTC (roughly 18.7 hours). The attacker probed Cloudflare's systems starting November 14, accessed the internal wiki (Confluence) and bug database (Jira) from November 15, and on November 22 established persistent access using the Sliver framework installed via the ScriptRunner for Jira plugin. They accessed 36 Jira tickets (out of 2,059,357), 202 wiki pages (out of 194,100), and viewed 120 code repositories (out of 11,904), downloading 76 of them. Attempts at lateral movement — including to a non-production console server in the São Paulo data center — were blocked by Cloudflare's Zero Trust controls, firewall rules, and hard security keys. The security team deactivated the compromised service account 35 minutes after the first alert and removed all threat actor access by November 24. No customer data, SSL keys, global network systems, or production configurations were impacted. Cloudflare then launched "Code Red", a company-wide remediation effort that rotated over 5,000 production credentials, performed forensic triage on 4,893 systems, and reimaged every machine in the global network.

---

## Timeline

All times are UTC.

| Time | Event |
|------|-------|
| **October 18** | Okta compromise. Cloudflare fails to rotate one service token and three service accounts that were exposed |
| **November 14 09:22:49** | Threat actor begins probing and reconnaissance. Attempts to log into Cloudflare's Okta instance and Dashboard are denied; actor accesses the segmented AWS environment powering the Apps marketplace (no global-network or customer-data access) |
| **November 15 16:28:38** | Threat actor accesses Atlassian Jira and Confluence, authenticating via the Moveworks service token and then using the Smartsheet service account |
| **November 16 14:36:37** | Threat actor uses the Smartsheet credential to create an Atlassian user account for persistence, adding it to several groups |
| **November 17 14:33:52 – November 20 09:26:53** | Threat actor takes a break, aside from briefly testing continued access on November 20 and 21 |
| **November 22 14:18:22** | Threat actor installs the Sliver C2 framework via the ScriptRunner for Jira plugin, gaining persistent access; over the next day views 120 repositories and downloads 76. An attempt to reach a non-production console server in São Paulo is denied |
| **November 23 15:58** | Threat actor adds the Smartsheet service account to an administrator group |
| **November 23 16:00** | Automated alert about the 15:58 change reaches the security team |
| **November 23 16:12** | Cloudflare SOC begins investigating |
| **November 23 16:35** | Smartsheet service account deactivated (35 minutes after the alert) |
| **November 23 17:23** | Threat actor-created Atlassian user account found and deactivated |
| **November 23 17:43** | Internal Cloudflare incident declared |
| **November 23 21:31** | Firewall rules put in place to block the attacker's known IP addresses |
| **November 24 10:44** | Last known threat actor activity (confirmed by CrowdStrike) |
| **November 24 11:59** | Sliver removed from the Atlassian server; all access terminated |
| **November 26** | CrowdStrike forensic team engaged for independent analysis |
| **November 27** | "Code Red" remediation effort launched |
| **January 5, 2024** | Immediate "Code Red" effort ends |

---

## Root Cause

The root cause was Cloudflare's failure to rotate four credentials that were exposed during the October 2023 Okta compromise. These were not rotated because they were mistakenly believed to be unused — which was incorrect, and was how the threat actor gained initial access and persistence. Cloudflare explicitly noted this was not an error on the part of Atlassian, AWS, Moveworks, or Smartsheet; these were simply credentials Cloudflare failed to rotate.

The four credentials were:

1. **Moveworks service token** — granted remote access into the Atlassian system.
2. **Smartsheet service account** — had administrative access to Atlassian Jira (this admin access is what later allowed the Sliver install).
3. **Bitbucket service account** — used to access the source code management system.
4. **AWS environment account** — used to power the Cloudflare Apps marketplace, segmented with no access to the global network or customer data.

The attacker operated methodically: reconnaissance over several days, creation of a backup user account in case the service account was revoked, installation of the Sliver C2 framework for long-term access, and repeated lateral-movement attempts. Those lateral attempts failed because of Cloudflare's access controls, firewall rules, and hard security keys enforced through its own Zero Trust tools — which contained the breach to the Atlassian environment.

---

## Resolution

1. **Detection** — At 16:00 UTC on November 23, an automated alert about the Smartsheet account being added to an administrator group triggered the investigation.
2. **Containment** — The SOC deactivated the Smartsheet service account at 16:35 (35 minutes after the alert) and the attacker-created Atlassian account at 17:23. Firewall rules blocked the attacker's known IPs at 21:31.
3. **Eradication** — The Sliver framework was removed from the Atlassian server by 11:59 UTC on November 24; CrowdStrike confirmed the last evidence of activity was 10:44 UTC that day.
4. **Independent verification** — CrowdStrike's forensic team, engaged November 26, performed an independent assessment and found no activity Cloudflare had missed.
5. **Remediation ("Code Red")** — From November 27, a large part of Cloudflare's technical staff worked to rotate over 5,000 production credentials, physically segment test and staging systems, perform forensic triage on 4,893 systems, reimage and reboot every machine in the global network (including all Atlassian products), and return São Paulo data center equipment to manufacturers for forensic examination. The immediate effort ended January 5, 2024.

---

## Prevention

Cloudflare's hardening work centered on closing the gap that caused the breach and reducing what an attacker could do if they got in again.

On credential management, the central failure was an incomplete rotation after a third-party compromise, so the response was a mass rotation of every production credential (more than 5,000) and improved processes to ensure credentials are fully rotated after any third-party compromise — treating "believed unused" credentials as still requiring rotation.

On containment, Cloudflare credited its existing Zero Trust architecture — access controls, firewall rules, and hard security keys — with limiting the attacker's lateral movement, and continued to enforce these as the primary barrier preventing a single compromise from spreading.

On systems and source code, Cloudflare reviewed the 76 accessed repositories for embedded secrets (rotating any found, even though they were encrypted) and for vulnerabilities; physically replaced equipment in the São Paulo data center; reimaged systems the attacker touched; and searched for unused accounts, stale software packages, and secrets left in Jira tickets or source code, deleting HAR files uploaded to the wiki in case they contained tokens.

On detection, CrowdStrike was engaged for independent forensic analysis, and Cloudflare committed to improved logging and alerting to detect similar intrusions faster. Work continued past the immediate effort around credential management, software hardening, vulnerability management, and additional alerting.