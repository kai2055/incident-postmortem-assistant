# Corpus Documentation

## Schema

Each incident is stored as a Markdown file with YAML frontmatter and five body sections.

### YAML frontmatter fields
- `id`: Unique identifier (e.g., `cloudflare-2025-11-18`)
- `title`: Human-readable incident name
- `company`: Company name
- `date`: Incident date (YYYY-MM-DD)
- `severity`: One of `critical`, `major`, `minor`
- `duration_minutes`: Total outage duration in minutes
- `affected_services`: List of affected service names
- `root_cause_category`: One of `configuration-error`, `cascading-failure`, `credential-auth`, `network-bgp`, `database-storage`, `agent-ai`, `supply-chain`, `other`

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