"""Send one prompt through whichever provider is configured, and time it."""

import sys
sys.path.insert(0, ".")

import time
from src.generation import call_llm, LLM_PROVIDER

PROMPT = "List three symptoms of a database outage, one per line, no preamble."

print(f"provider: {LLM_PROVIDER}\n")

t0 = time.time()
answer = call_llm(PROMPT)
elapsed = time.time() - t0

print(answer)
print(f"\n--- {elapsed:.1f} seconds ---")