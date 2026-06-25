---
id: tanstack-npm-2026-05-11
title: "npm supply-chain compromise via GitHub Actions cache poisoning and OIDC token extraction"
company: TanStack
date: 2026-05-11
severity: critical
duration_minutes: 275
affected_services:
  - "@tanstack/* npm packages (Router/Start monorepo)"
  - npm registry distribution
root_cause_category: supply-chain
---

## Summary

On May 11, 2026, between 19:20 and 19:26 UTC, an attacker published 84 malicious versions across 42 @tanstack/* npm packages by chaining three vulnerabilities in TanStack's GitHub Actions CI pipeline: the `pull_request_target` "Pwn Request" pattern, GitHub Actions cache poisoning across the fork-to-base trust boundary, and runtime extraction of an OIDC token from the GitHub Actions runner's memory. Note on duration: this is a software supply-chain compromise rather than a service outage, so `duration_minutes` here measures the window from the first malicious publish (19:20 UTC) to the last malicious tarball being removed by npm (23:55 UTC) — roughly 4 hours 35 minutes. The attacker forked the TanStack/router repository (renaming the fork to evade fork-list searches), opened a pull request, and used a malicious commit to poison the shared GitHub Actions cache. That poisoned cache was later restored during a legitimate release workflow, placing attacker-controlled code on the release runner. That code read the runner process's memory to extract an OIDC token and used it to publish malicious packages directly to npm, bypassing the workflow's own publish step. When installed, the malicious packages ran an obfuscated ~2.3 MB `router_init.js` that harvested credentials and self-propagated to other packages the victim maintained. The compromise was detected publicly within about 26 minutes by an external researcher at StepSecurity; no npm credentials were stolen and the npm publish workflow itself was not compromised. TanStack deprecated all 84 versions within about 1 hour 43 minutes of the publish, and npm removed the tarballs registry-side by 23:55 UTC. Only the Router/Start monorepo packages were affected; all other TanStack package families remained secure.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| **May 10 17:16** | Attacker creates fork `github.com/zblgg/configuration` (a fork of TanStack/router, renamed to evade fork-list searches) |
| **May 10 23:29** | Malicious commit `65bf499d` authored on the fork by a fabricated identity (`claude@users.noreply.github.com` — not the real Anthropic Claude). Adds `packages/history/vite_setup.mjs`, a ~30,000-line bundled JS payload. Commit message prefixed `[skip ci]` to suppress CI on push |
| **May 11 ~10:49** | PR #7378 opened against TanStack/router main, titled "WIP: simplify history build", by `zblgg` |
| **May 11 10:49+** | `bundle-size.yml` and `labeler.yml` (both `pull_request_target`) auto-run for the PR — no first-time-contributor approval required, because `pull_request_target` bypasses that gate. `pr.yml` (which uses `pull_request`) does NOT run, blocked pending approval that never came |
| **May 11 11:01–11:11** | Multiple force-pushes to the PR head, each triggering more `pull_request_target` runs |
| **May 11 11:11** | A force-push lands the malicious commit on the PR head. `bundle-size.yml`'s `benchmark-pr` job checks out the fork's merge ref, runs `pnpm install` and the bundle-size build, executing `vite_setup.mjs` |
| **May 11 11:29** | A 1.1 GB cache entry (`Linux-pnpm-store-6f9233...`) is saved to the GitHub Actions cache for TanStack/router under scope `refs/heads/main` — keyed to match what `release.yml` will look up on the next push to main |
| **May 11 11:31** | Attacker force-pushes the PR back to current main HEAD, making the visible PR a 0-file no-op. PR closed and branch deleted the same minute. Cache poison persists |
| **May 11 19:15:44** | Release workflow run 25613093674 (a re-run, attempt #4, of a workflow originally from PR #7369 merged May 9) runs against main HEAD. The poisoned cache is restored on the runner |
| **May 11 19:16:18** | Maintainer merges PR #7382 → push to main triggers a fresh `release.yml` run (25691781302), which restores the same poisoned cache |
| **May 11 19:20:39** | Malicious publish: `@tanstack/history@1.161.9` and 41 sibling packages (~half of the 84 versions). Authenticated via the workflow's OIDC trusted-publisher binding, but minted by the malware during the test/cleanup phase and POSTed directly to npm — not from the workflow's own (skipped) Publish step |
| **May 11 19:20:48** | Run 25613093674 completes (status: failure) |
| **May 11 19:26:14** | Malicious publish: the second version per package (`@tanstack/history@1.161.12` etc.) from run 25691781302, same mechanism |
| **May 11 19:26:22** | Run 25691781302 completes (status: failure) |
| **May 11 19:46** | External researcher (StepSecurity) opens issue #7383 with a full writeup and an initial list of 14 of the 42 packages |
| **May 11 ~19:50** | Researcher notifies npm security directly |
| **May 11 ~20:00** | Maintainer acknowledges in #7383; incident response begins |
| **May 11 ~20:10** | All other team push permissions removed on GitHub, in case maintainer machines were compromised |
| **May 11 20:19** | First two malicious versions deprecated |
| **May 11 20:41** | Batch deprecation across the initial 14-package / 28-version scope |
| **May 11 ~21:00** | A scan of all 295 @tanstack/* packages confirms full scope: 42 packages, 84 versions. Public disclosure posted on social channels |
| **May 11 21:03** | Final batch deprecation covering all 84 versions |
| **May 11 21:30** | Investigation identifies the `bundle-size.yml` cache-poisoning vector and the attacker fork. All cache entries for all TanStack/* repositories purged via API. Hardening PR merged; GitHub Security Advisory published |
| **May 11 22:13–23:55** | npm removes the affected tarballs registry-side (first at 22:13:38, last at 23:55:26) in response to the StepSecurity notification |
| **May 12 05:02** | Formal IOC email sent to npm and GitHub security |
| **May 15** | All-clear issued after a three-day security sweep and hardening pass |

## Root Cause

The compromise was a chain of three vulnerabilities. Each was necessary; none alone was sufficient.

1. **`pull_request_target` "Pwn Request" pattern in `bundle-size.yml`.** The workflow ran `pull_request_target` for fork PRs and, in that context, checked out the fork's PR-merge ref and ran a build — executing fork-controlled code. The author had attempted a trust split (keeping the benchmark job separate and read-only), but missed two facts: `actions/cache@v5`'s post-job save is not gated by `permissions:` (cache writes use a runner-internal token, not the workflow `GITHUB_TOKEN`), and cache scope is per-repo, shared across `pull_request_target` runs and pushes to main. So a fork PR running in the base repo's cache scope could poison entries that production workflows on main would later restore.

2. **GitHub Actions cache poisoning across the trust boundary.** The malicious `vite_setup.mjs` wrote data into the pnpm-store directory under exactly the key `release.yml` would compute and look up (`Linux-pnpm-store-${hashFiles('**/pnpm-lock.yaml')}`). When the PR's benchmark job ended, `actions/cache@v5` saved the poisoned store to that key. When `release.yml` next ran on a push to main, its setup step restored the poisoned entry — exactly as designed. This is a known GitHub Actions design issue (documented by Adnan Khan in 2024), not a TanStack-specific bug, and requires conscious mitigation.

3. **OIDC token extraction from runner memory.** `release.yml` declared `id-token: write` (legitimately needed for npm OIDC trusted publishing). When the poisoned store was restored, attacker-controlled binaries were on disk and ran during the build. They located the GitHub Actions `Runner.Worker` process via `/proc/*/cmdline`, read `/proc/<pid>/maps` and `/proc/<pid>/mem` to dump its memory, extracted the in-memory OIDC token, and used it to POST publish requests directly to `registry.npmjs.org` — bypassing the workflow's own Publish step entirely. This reused the exact memory-extraction technique (verbatim script, with its attribution comment intact) from the tj-actions/changed-files compromise of March 2025; the attacker recombined published research rather than inventing new tradecraft.

The chain worked because each vulnerability bridged a trust boundary the others assumed safe: fork PR code crossing into base-repo cache, base-repo cache crossing into release-workflow runtime, and release-workflow runtime crossing into npm write access. Notably, detection was external — TanStack had no internal alerting on its own publishes and learned of the compromise from a third-party researcher about 20 minutes after it happened.

## Resolution

1. **Detection (19:46 UTC)** — An external StepSecurity researcher opened issue #7383 with full technical analysis; a security firm (Socket.dev) also phoned the maintainer shortly after the war room began.
2. **Containment (~20:00–20:10 UTC)** — The team acknowledged the incident and removed all other team push permissions on GitHub in case any maintainer machine had been compromised.
3. **Deprecation (20:19–21:03 UTC)** — All 84 malicious versions were deprecated in batches: the first 2 at 20:19, the initial 28 at 20:41, and the full 84 by 21:03 (about 1h 43m after the first publish).
4. **Root-cause containment (21:30 UTC)** — Investigation identified the `bundle-size.yml` cache-poisoning vector; all cache entries across all TanStack/* repositories were purged via API, and a hardening PR was merged. A GitHub Security Advisory was published.
5. **Registry removal (22:13–23:55 UTC)** — npm removed the malicious tarballs server-side in response to the StepSecurity notification. (Deprecation alone does not remove tarballs; npm's "no unpublish if dependents exist" policy meant TanStack could not pull them itself and had to rely on npm security, which added hours of exposure.)
6. **All-clear (May 15)** — Issued after a three-day full security sweep.

## Prevention

The central failures were an un-audited dangerous workflow pattern, a cache that crossed trust boundaries, and an OIDC publish path with no per-publish review — so the hardening targeted each.

On workflows, `bundle-size.yml` was restructured to stop running fork-controlled code under `pull_request_target`, `repository_owner` guards were added to block cache poisoning across the fork-to-base boundary, and third-party action references were pinned to commit SHAs instead of floating tags like `@v6.0.2` and `@main`, which had created standing supply-chain risk.

On caching, all cache entries for all TanStack/* repositories were purged, and cache key scoping was changed to prevent cross-workflow poisoning.

On detection, the team committed to internal alerting on publish events — so a future compromise is caught in-house rather than via a third party — and to tighter feedback loops with ecosystem security researchers.

On publishing, TanStack flagged that OIDC trusted-publisher binding has no per-publish review (once configured, any code path in the workflow can mint a publish-capable token) and is evaluating either moving to short-lived classic tokens with manual review or adding provenance-source verification to detect publishes from unexpected workflow steps. The 7-maintainer npm scope was also noted as a risk — seven separate credential-theft targets for the same blast radius — and is being reviewed, with maintainer accounts hardened.