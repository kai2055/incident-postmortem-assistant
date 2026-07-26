# ADR-018: Root-Cause Category Definitions and the supply-chain Exception

**Status:** Accepted
**Date:** 25 July 2026
**Supersedes:** ADR-009 (agent-ai left empty for lack of a first-party source)

---

## Context

The corpus schema listed nine `root_cause_category` values but never defined
them. The working rule was "tag the origin, not the downstream effect" — an
operator disabling a storage service is `human-error`, not `database-storage`.

That rule held in principle and slipped in practice. During corpus expansion,
three candidate documents were nearly tagged by their affected service rather
than their origin, and one already-committed document turned out to be
mis-tagged. Without written definitions, the rule could not be applied
consistently.

## Decision

Write explicit definitions into `corpus/README.md`, keyed to origin, with worked
examples for the cases that recur. Full table in the schema; the operative rule
is unchanged — tag what started the failure, not what the failure touched.

## The one exception: supply-chain

Most categories describe how a failure **started**. `supply-chain` describes how
it **propagated** — through a distributed artefact into someone else's
environment.

Nearly every supply-chain compromise begins with a stolen credential or a bad
merge, so tagging by origin alone would leave the category permanently empty:
Codecov would be `credential-auth`, TanStack would be `configuration-error`.

**The test:** did tampered material leave the organisation and run inside
someone else's environment? If yes, `supply-chain`, whatever the initial
foothold was.

This is a deliberate, documented exception to the tag-the-origin rule, and the
only one. Codecov 2021 (leaked HMAC key → tampered Bash Uploader ran in
customers' CI) and TanStack 2026 (compromised CI → malicious npm packages) are
`supply-chain`. CircleCI's January 2023 breach (stolen session cookie, secrets
exfiltrated, nothing tampered distributed) is `credential-auth` — it looks like
a supply-chain story and is not.

## agent-ai: superseding ADR-009

ADR-009 left `agent-ai` empty because no first-party source had been found. The
GitHub Pages DNS incident of 13 April 2026 fills it: an automated DNS management
tool deleted a live production record after its upstream data source
intermittently failed to return that record, and the tool treated the absence
as evidence the record was stale.

`agent-ai` is defined as: an automated or AI-driven system took the failing
action. This incident qualifies — the deletion was made by automation acting on
bad input, not by an operator. The category now holds one document. ADR-009 is
superseded.

## The definitions caught a real error

Writing the definitions immediately surfaced a mis-tag that four evaluation runs
had missed. `github-auth-2026-02-17` was tagged `credential-auth` because
authentication was the affected service. Its actual origin is a replication
break in the token-verification database cluster under write load — a datastore
failure. Retagged to `database-storage`.

This is the definitions doing real work, not just tidying: an unwritten rule had
allowed a service-based tag to survive since the document was added.

## Consequences

Category counts after expansion and the retag:

| Category | Count |
|---|---|
| configuration-error | 4 |
| database-storage | 4 |
| human-error | 3 |
| cascading-failure | 2 |
| credential-auth | 2 |
| network-bgp | 2 |
| supply-chain | 2 |
| agent-ai | 1 |

Every category is now populated. The thin ones (agent-ai, network-bgp,
supply-chain) reflect that those failure modes are genuinely rarer, which is a
more honest corpus than one padded to look even.

Evaluation artefacts filter on `root_cause_category`, so the two retags
(`github-auth` → database-storage) require re-running the Layer 1 suite to
confirm filter queries still pass. The affected filter queries are
severity-scoped, so no breakage is expected, but it must be confirmed.