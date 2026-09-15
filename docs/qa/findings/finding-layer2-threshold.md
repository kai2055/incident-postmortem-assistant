# Finding: Layer 2 Needs Its Own Relevance Threshold

**Date:** 24 July 2026  
**Measured on:** 15 incident descriptions, 27 frozen symptoms, 5 no-match symptoms

---

## The problem in one line

Layer 2 was using Layer 1's threshold. Layer 1's threshold was tuned on complete questions. Layer 2 sends symptom fragments. Fragments score worse, so everything was thrown away.

---

## Why fragments score worse

A post-mortem chunk describes a whole incident—the trigger, the failure, the cascade, the recovery. Many concepts in one paragraph.

A complete question matches that richness. A fragment matches one small part of it, so the distance is worse even though it describes the same event.

**The whole description is closer to the document than any of its parts.**

| Input type | Typical distance |
|---|---|
| Layer 1 complete questions | 0.20 - 0.27 |
| Layer 2 symptom fragments | 0.32 - 0.41 |
| The threshold both were using | **0.30** |

The cutoff sits in the gap. Layer 1 clears it every time. Layer 2 never does.

---

## What was actually failing

Every symptom measured against the real retriever:

| Verdict | Count | Meaning |
|---|---|---|
| PASS | **0** | found, kept, and visible to the agent |
| THRESHOLD | **25** | found the right document, then discarded |
| RANK | 0 | found but ranked too deep to be seen |
| MISS | 2 | never found at all |

**25 of 27 symptoms found the correct document and had it thrown away.**

Retrieval was working. Filtering was calibrated for the wrong input.

The correct document was ranked **first** for many of them:

| Symptom | Target found at | Distance |
|---|---|---|
| main database disappeared | rank 1 | 0.3228 |
| Database switched over to the backup on its own | rank 1 | 0.3171 |
| service registry got sluggish | rank 1 | 0.3360 |
| Main database deleted | rank 1 | 0.3294 |
| nothing can authenticate | rank 1 | 0.3808 |

---

## The sweep

Each threshold tested against the same frozen symptoms.

| Threshold | Entries fed | Symptoms hit | Wrong doc | Junk leaked |
|---|---|---|---|---|
| 0.30 | 0/13 (0.00) | 0/27 | 1 | 0/5 |
| 0.32 | 1/13 (0.08) | 1/27 | 3 | 0/5 |
| 0.34 | 7/13 (0.54) | 9/27 | 3 | 1/5 |
| 0.35 | 8/13 (0.61) | 11/27 | 4 | 1/5 |
| **0.36** | **9/13 (0.69)** | **13/27** | **4** | **1/5** |
| 0.38 | 9/13 (0.69) | 16/27 | 4 | 2/5 |
| 0.40 | 10/13 (0.77) | 17/27 | 5 | 5/5 |
| 0.45 | 11/13 (0.85) | 20/27 | 6 | 5/5 |
| 0.50 | 11/13 (0.85) | 21/27 | 6 | 5/5 |

**What the columns mean**

- **Entries fed**—descriptions where at least one symptom found its target. An entry at zero means the agent starts with no evidence at all and can only produce an empty diagnosis.
- **Symptoms hit**—individual symptoms that retrieved their target.
- **Wrong doc**—symptoms that returned results, none of them correct. Worse than silence: the agent reasons over the wrong incident and produces a confident wrong answer.
- **Junk leaked**—symptoms from the two no-match descriptions that returned anything at all.

---

## Reading the table

**0.30 to 0.34 is where everything happens.** Entries fed goes from 0 to 7 and junk only rises to 1 of 5.

**0.36 is the best point.** 9 of 13 entries get evidence, junk still 1 of 5.

**0.38 buys nothing.** Entries stay at 9—more individual symptoms hit, but no new description gets unblocked—while junk doubles. Pure cost.

**0.40 is a cliff.** Junk goes from 2/5 to 5/5. Every no-match symptom leaks. Decline behaviour collapses entirely.

Usable range: **0.34 to 0.36**.

---

## Decision

`LAYER2_THRESHOLD = 0.36`, passed by the Retrieve node.

Layer 1 keeps `RELEVANCE_THRESHOLD = 0.30`. ADR-013 is unaffected. The parameter already existed on `retrieve()`, so this is a one-line change per caller rather than a redesign.

---

## What this does not fix

Stated plainly, because 0.36 is not a solution:

- **4 of 13 descriptions still get nothing.** The agent still fails on those.
- **4 symptoms return the wrong document.** The agent reasons over a wrong incident, which during an outage is worse than returning nothing.
- **1 junk symptom leaks.** A description with nothing matching in the corpus gets treated as if it matched.

Layer 2 goes from never working to working roughly two thirds of the time, with some false leads.

---

## The overlap problem

The reason no threshold is clean:

| | Distance |
|---|---|
| Junk: machines shut themselves down | 0.3340 |
| Real: servers dropping everything | 0.3444 |
| Junk: air conditioning failed | 0.3623 |
| Real: write operations started failing | 0.3611 |

The bands interleave. Junk sometimes scores better than real hits.

**No cutoff separates them, because the separation does not exist in the data.** More samples would describe the overlap more precisely; they would not create a boundary.

So the honest conclusion is not "0.36 is the right number." It is:

**A distance score alone cannot separate signal from noise on short symptom fragments.**

---

## Confidence in this number

Low, and deliberately so.

27 symptom measurements across 13 descriptions is thin. Layer 1's threshold came from 31 queries and still had failures at margins of 0.0055.

0.36 is a round number picked from where the table turns, not a value fitted to these specific measurements. It is a working setting that makes the component functional, and it should be revisited when the suite grows.

---

## What to try next

The threshold fix treats the symptom. The cause is that fragments carry less signal than whole descriptions.

**Search the full description alongside each symptom** and merge the results. That matches rich text against rich chunks, which is the comparison the embedding model is good at. Evidence for this: the Layer 1 plain-English suite, using complete descriptions, scored 0.870 at threshold 0.30. The same content split into fragments scores zero at the same threshold.

That would widen the gap between signal and noise rather than moving a line through the middle of it.

---

## Reproduction

```bash
python -m scripts.freeze_symptoms          # generate symptoms once, freeze them
python -m scripts.measure_layer2           # per-symptom verdicts
python -m scripts.sweep_layer2             # the table above
```

Symptoms are frozen to `data/eval/layer2_symptoms.json` because Decompose is an LLM call and produces slightly different strings each run. Calibrating against a moving input would make measurements incomparable between runs.