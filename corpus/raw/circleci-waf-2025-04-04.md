---
id: circleci-waf-2025-04-04
title: "Manual WAF change outside Terraform blocks legitimate traffic to UI and builds"
company: CircleCI
date: 2025-04-04
severity: critical
duration_minutes: 93
affected_services:
  - CircleCI UI
  - Build triggering
  - api.circleci.com CloudFront distribution
  - circleci.com CloudFront distribution
root_cause_category: configuration-error
---

## Summary

On April 4, 2025, from 00:16 to 01:49 UTC, CircleCI experienced a service disruption affecting both its user interface and build capabilities. Customers were unable to access the CircleCI UI or initiate new builds for approximately 1 hour and 33 minutes. The disruption was caused by a Web Application Firewall rule that was inadvertently applied and blocked legitimate traffic to the api.circleci.com and circleci.com CloudFront distributions. An IAM misconfiguration had left a role able to change infrastructure without going through CircleCI's Terraform pipeline, and an operator reviewing routine security monitoring modified WAF configuration while believing they were taking read-only actions. Diagnosis was slowed by two factors: the incident began as teams were concluding a separate, unrelated incident, and responders did not investigate WAF configuration because they assumed any change would have gone through Terraform and no such change was recorded. Automated Terraform drift detection identified the discrepancy nearly 80 minutes after the change was made, which led directly to the resolution.

## Timeline

All times UTC.

- **00:16** — A WAF rule is inadvertently introduced and begins blocking legitimate traffic to CircleCI services.
- **00:26–00:52** — Monitoring detects degraded performance across multiple services, just as teams are concluding a separate unrelated incident, causing initial confusion about whether the two are connected. Customers report inability to access the UI or start builds. The team notes a drop in GitHub webhooks and widespread connectivity issues between frontend and backend services, and spends time confirming these are not aftereffects of the previous incident.
- **00:52** — Established as a separate incident. A new incident process is launched and a dedicated response team assembled.
- **01:15** — Investigation reveals broad connectivity issues between the frontend and backing APIs, including CORS errors. The team explores recent deployments and infrastructure changes; the cause remains unclear.
- **01:35** — Automated Terraform drift detection identifies a difference between defined and current WAF settings, revealing a WAF rule changed outside the standard Terraform deployment process and blocking legitimate traffic to the api.circleci.com and circleci.com CloudFront distributions.
- **01:41** — The problematic WAF rule is reverted from both affected CloudFront distributions.
- **01:49** — Monitoring confirms error rates decrease across all affected services as traffic routes correctly again.
- **01:55** — Full service restoration confirmed.
- **02:59** — Incident closed after a period of monitoring confirms stable operation.

## Root Cause

CircleCI manages its infrastructure, including WAF, almost entirely with Terraform. During this incident a misconfiguration in IAM controls was discovered that allowed a specific role to make changes without using that infrastructure-as-code tooling.

While investigating routine security monitoring, an operator manually modified WAF configuration in the belief that they were taking read-only actions. The resulting change blocked legitimate traffic to CircleCI's services.

The same assumption then slowed diagnosis. Responders did not prioritise investigating WAF configuration, because they expected any change would have gone through the Terraform pipeline and there was no record of such a change. The diverse symptoms produced across the platform, combined with the incident occurring shortly after a separate unrelated incident, led to time spent on lines of inquiry that proved fruitless.

Automated drift detection eventually identified the exact configuration change responsible, but nearly 80 minutes elapsed between the initial change and its detection.

## Resolution

Terraform drift detection flagged the difference between defined and current WAF settings at 01:35, identifying the specific rule and the two CloudFront distributions affected. The rule was reverted from both distributions at 01:41. Error rates decreased across affected services by 01:49, full restoration was confirmed at 01:55, and the incident was closed at 02:59 after monitoring confirmed stable operation.

## Prevention

- Stricter IAM policies implemented to prevent direct modification of infrastructure managed by the infrastructure-as-code pipeline.
- Drift detection capabilities enhanced to provide faster alerts when critical infrastructure components deviate from their expected state, with technical guardrails added to ensure all configuration management follows this approach.
- Better protocols established for implementing and testing WAF rules before they reach production, plus monitoring specifically for WAF behaviour and traffic patterns to detect issues more quickly.
- Investigating Security Control Policies to provide organization-wide restrictions on IAM roles, creating hard boundaries on what actions can be performed on critical systems such as WAFs.