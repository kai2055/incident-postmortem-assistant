# Corpus Documentation

## Schema

Each incident is stored as a Markdown file with YAML frontmatter and five body sections.

### YAML frontmatter fields
- `id`: Unique identifier (e.g., `cloudflare-2025-11-18`)
- `title`: Human-readable incident name
- `company`: Company name
- `date`: Incident date (YYYY-MM-DD)
- `severity`: One of `critical`, `major`, `minor`
- `duration_minutes`: Time from **first observable customer impact** to **all services fully restored and confirmed operational**. Applied consistently across all incidents (not "time to main fix" or "restore copy duration").
- `affected_services`: List of affected service names, in YAML block-list form:
    affected_services:
      - Service One
      - Service Two
- `root_cause_category`: One of `configuration-error`, `cascading-failure`, `credential-auth`, `network-bgp`, `database-storage`, `agent-ai`, `supply-chain`, `human-error`, `other`


### Category definitions

**Tag the origin, not the downstream effect.** An operator disabling a storage
service is `human-error`, not `database-storage`. A config change that
withdraws BGP routes is `configuration-error`, not `network-bgp`.

| Category | Definition |
|---|---|
| `configuration-error` | A change to configuration, rules, or policy caused the failure |
| `human-error` | An operator action — wrong command, wrong parameter, wrong target |
| `credential-auth` | Compromised, expired, or mis-deployed credentials |
| `database-storage` | The datastore itself failed — limits hit, corruption, replication break |
| `cascading-failure` | One component's degradation propagated through dependencies |
| `network-bgp` | Routing itself failed — a leak or hijack, not a config change with routing symptoms |
| `supply-chain` | See exception below |
| `agent-ai` | An automated or AI-driven system took the failing action |
| `other` | None of the above; use sparingly and explain in Root Cause |

#### The one exception: `supply-chain`

This category answers a different question from the rest. The others describe
how a failure **started**. `supply-chain` describes how it **propagated** —
through a distributed artefact into someone else's environment.

Nearly every supply-chain compromise begins with a stolen credential or a bad
merge, so tagging by origin alone would leave this category permanently empty.

**The test:** did tampered material leave the organisation and run inside
someone else's environment? If yes, `supply-chain`, whatever the initial
foothold was.

| Incident | Tag | Why |
|---|---|---|
| Codecov 2021 | `supply-chain` | A leaked HMAC key was the foothold, but the tampered Bash Uploader ran in customers' CI |
| TanStack 2026 | `supply-chain` | Compromised CI published malicious npm packages |
| CircleCI Jan 2023 | `credential-auth` | Stolen session cookie, secrets exfiltrated — nothing tampered was distributed |

This is a deliberate exception to the tag-the-origin rule, and the only one.




### Body sections
1. **Summary** – one-paragraph description of what happened
2. **Timeline** – bullet list of events with UTC timestamps
3. **Root Cause** – detailed technical root cause
4. **Resolution** – exact steps taken to fix
5. **Prevention** – long-term fixes and lessons learned

## Quality Gate – Completeness Score

Before normalization, each incident is scored 0–5:
- Clear timeline with timestamps: 1 point
- Detailed root cause: 1 point
- Resolution steps: 1 point
- Impact quantification (users/services/duration): 1 point
- Prevention / lessons learned: 1 point

Only incidents with score ≥ 3 are admitted to the corpus.