import sys

sys.path.insert(0, ".")
from src.embedding import RELEVANCE_THRESHOLD, retrieve

symptoms = [
    "API started returning 503s",
    "database connection pool was exhausted",
    "checkout latency spiked",
]

print(f"threshold: {RELEVANCE_THRESHOLD}\n")
for s in symptoms:
    raw = retrieve(s, top_k=5, threshold=None)
    best = raw[0]["distance"] if raw else 999
    top_id = raw[0]["id"] if raw else "-"
    print(f"{best:.4f}  survivors={len(retrieve(s))}  {s}")
    print(f"          closest: {top_id}\n")
