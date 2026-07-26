"""Diagnostic: raw distances vs. what survives the threshold."""

import sys

sys.path.insert(0, ".")

from src.embedding import RELEVANCE_THRESHOLD, retrieve

QUERY = "BGP route leak"

print(f"query     : {QUERY}")
print(f"threshold : {RELEVANCE_THRESHOLD}\n")

print("RAW - threshold off, everything Chroma returns")
raw = retrieve(QUERY, top_k=15, threshold=None)
for r in raw:
    verdict = "KEEP" if r["distance"] <= RELEVANCE_THRESHOLD else "drop"
    print(f"  {r['distance']:.4f}  {verdict}  {r['id']}")

print("\nFILTERED - threshold on, what the system actually returns")
filtered = retrieve(QUERY, top_k=5)
print(f"  survivors: {len(filtered)}")
for r in filtered:
    print(f"  {r['distance']:.4f}  {r['id']}")