# ADR-010: Corpus Documents Assembled by Claude Under First-Party Verification

**Date:** 2026-06-26

**Status:** Accepted

**Context:**
Building each corpus incident by hand — finding the post-mortem, fitting it to the schema, scoring it, transcribing details — is time-consuming, and the project's learning priority is building the system (pipeline, agent, evaluation), not hand-authoring post-mortems. Going deep on each incident is a rabbit hole that displaces system work. At the same time, the corpus is the evaluation framework's ground truth, so its integrity cannot be compromised for speed.

**Decision:**
Claude assembles corpus documents from a draft or source URL the user provides: it fetches the first-party source, builds the document strictly from it, verifies every specific detail against the source, enforces the schema, scores against the rubric, and returns the final file. The user provides the real incident and source, and reviews the result.

**The hard constraints that make this safe (unchanged):**
- Every incident must trace to a real first-party source that Claude has actually fetched and read.
- Claude never supplies incident facts from its own memory, and never builds from third-party-only sources.
- No reconstructed or fictional incidents.
- The user still owns sourcing: if no fetchable first-party post-mortem exists, the incident is not built (it is rejected or the category stays uncovered).

**Options considered:**
- A: User hand-authors every document. Maximum control, but slow, and diverts the user's limited focus time from the system itself.
- B: Claude generates incidents from its own knowledge. Fast, but catastrophic for integrity — it would produce plausible, unverifiable, partly-fabricated incidents. Rejected outright.
- C: Claude assembles from a user-provided real source, verifying every detail against it (chosen). Fast for the user, integrity preserved because everything still traces to a fetched first-party source.

**Rationale:**
Option C. The division of labor matches where the value is: the user supplies the real incident and source and keeps learning the system; Claude does the mechanical assembly and verification. The integrity rules are unchanged from when documents were hand-built — the *who assembles it* changed, the *what makes it valid* did not. This was stress-tested in practice: an early Claude-assembled Sentry draft contained an invented timeline and duration; fetching the actual source and verifying every detail against it caught and corrected the fabrication before it entered the corpus. That episode is the proof the verification step is load-bearing, not ceremonial.

**Consequences:**
- Corpus throughput increases without lowering the sourcing bar.
- Claude must fetch and read the actual first-party source for every document; a provided URL alone is not sufficient — it must be retrieved and checked.
- The user retains a review step, partly to keep the incidents in their own head for interviews (the corpus is a means, but they should still know its contents).
- The failure mode to guard against is a convincing, well-written document that was not actually verified against a source — "accurate-sounding" is not "sourced." Verification against the fetched source is the only thing that distinguishes them.