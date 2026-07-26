"""
Run Decompose over the Layer 2 suite and freeze the generated symptoms.

Decompose is an LLM call, so the same description can produce slightly
different symptom strings on different runs. Calibration has to be done
against a fixed set, otherwise the measurements move underneath you. So the
symptoms are generated once, written to disk, and treated as an artifact -
same discipline as the Layer 1 baseline.

Writes after every entry, so a crash or an interrupt at item 12 does not
throw away the first 11. Re-running skips anything already present unless
--force is passed.

Usage:
    python -m scripts.freeze_symptoms
    python -m scripts.freeze_symptoms --force        # regenerate everything
    python -m scripts.freeze_symptoms --only L2-003  # redo one entry
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.agent import create_state, decompose_node

SUITE_PATH = Path("data/eval/layer2_suite.json")
OUT_PATH = Path("data/eval/layer2_symptoms.json")


def load_existing(path: Path) -> dict:
    """Return {id: entry} for whatever has already been generated."""
    if not path.exists():
        return {}
    data = json.load(open(path))
    return {e["id"]: e for e in data.get("entries", [])}


def save(path: Path, entries: dict, suite_path: Path) -> None:
    output = {
        "run_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "suite": str(suite_path),
            "count": len(entries),
        },
        "entries": [entries[k] for k in sorted(entries)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(output, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--force", action="store_true",
                        help="regenerate entries that already exist")
    parser.add_argument("--only", type=str, default=None,
                        help="regenerate a single id, e.g. L2-003")
    args = parser.parse_args()

    suite = json.load(open(args.suite))
    entries = load_existing(args.out)

    todo = []
    for q in suite:
        if args.only and q["id"] != args.only:
            continue
        if q["id"] in entries and not (args.force or args.only):
            continue
        todo.append(q)

    if not todo:
        print(f"Nothing to do. {len(entries)} entries already in {args.out}")
        print("Use --force to regenerate, or --only <id> for one entry.")
        return

    print(f"Generating symptoms for {len(todo)} of {len(suite)} descriptions.")
    print("Each is one qwen3 call on CPU - expect a few minutes each.\n")

    start_all = time.time()

    for i, q in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {q['id']} ({q['kind']})")
        print(f"    {q['description'][:80]}...")

        t0 = time.time()
        state = create_state(q["description"])
        result = decompose_node(state)
        elapsed = time.time() - t0

        symptoms = result["symptoms"]

        entries[q["id"]] = {
            "id": q["id"],
            "kind": q["kind"],
            "description": q["description"],
            "symptoms": symptoms,
            "symptom_count": len(symptoms),
            "seconds": round(elapsed, 1),
        }

        # Save after every entry so an interrupt costs one call, not all of them
        save(args.out, entries, args.suite)

        print(f"    -> {len(symptoms)} symptoms in {elapsed:.0f}s")
        for s in symptoms:
            print(f"       - {s}")
        print()

    total = time.time() - start_all
    print(f"Done. {len(entries)} entries in {args.out}")
    print(f"Total time: {total / 60:.1f} minutes")


if __name__ == "__main__":
    main()