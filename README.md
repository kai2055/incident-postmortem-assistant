# Incident Post-Mortem Retrieval Assistant

A three-layer ML reliability pipeline that retrieves, diagnoses, and evaluates past incident post-mortems to assist engineers during live outages.

## Architecture
- **Layer 1: RAG Pipeline** – embeds and retrieves past incidents using local LLMs (Ollama) and ChromaDB.
- **Layer 2: Diagnostic Agent** – multi-step reasoning that decomposes symptoms, performs parallel retrieval, and produces differential diagnoses.
- **Layer 3: Evaluation Agent** – automated regression testing and metric tracking (hit rate, MRR, faithfulness) integrated into CI/CD.

## Corpus
 A curated collection of public post-mortems from Cloudflare, Google Cloud, GitHub, GitLab. See `corpus/README.md` for the schema and quality criteria.

## Setup (WIP)
1. Install dependencies: `pip install -r requirements.txt`
2. Run ingestion: `python src/ingestion.py`
3. Start API: `uvicorn src.api:app --reload`

## Evaluation
Metrics: retrieval hit rate, MRR, answer faithfulness, relevance. Baseline results will be recorded here.

## License
MIT