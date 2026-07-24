"""
Generation module for the RAG pipeline.

Takes retrieved chunks and the user's question, formats them with 
numbered citations, sends to Ollama, and returns a grounded answer
with a deterministic source list

"""

from typing import List, Dict, Any, Optional

import ollama
import os
import requests
from dotenv import load_dotenv


from src.embedding import retrieve


NO_MATCH_MESSAGE = "I don't have a matching incident in the sources."


load_dotenv()
# config
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
GEN_MODEL = "qwen3:8b"          # local, via Ollama
OPENROUTER_MODEL = "qwen/qwen3-8b"  # same weights, hosted
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"




# helpers
def _prettify_section(section: str) -> str:
    """Convert 'root_cause' to 'Root Cause' for display"""
    return section.replace("_", " ").title()

def _build_sources(results: List[Dict[str, Any]]) -> tuple:
    """
    Build the context block and source list from retrieved results.

    Args:
        results: List of result dicts from retrieve()
    
    Returns:
        (context_block, source_list)
            - context_block: Formatted sources for the prompt (with text)
            - source_list: Display labels for the final output (no text)
 
    """
    context_block = ""
    source_list = []

    for i, result in enumerate(results, start=1):
        metadata = result.get("metadata", {})
        company = metadata.get("company", "Unknown")
        date = metadata.get("date", "Unknown Date")
        section = metadata.get("section", "Unknoen Section")
        text = result.get("text", "")

        pretty_section = _prettify_section(section)

        # Context block: includes the full text for the model
        context_block += f"[{i}] {company} ({date}) - {pretty_section}\n"
        context_block += f"{text}\n\n"

        source_list.append({
            "number": i,
            "company": company,
            "date": date,
            "section": pretty_section,
            "id": result.get("id", ""),
        })

    return context_block, source_list

def _build_prompt(question: str, context_block: str) -> str:
    """
    Build the full prompt with role, rules, sources, and question
    
    Args:
        question: User's question
        context_block: Formatted sources with labels and text

    Returns:
        Full prompt string to send to the model.

    """
    return f"""You are an assistant that helps engineers investigate past incidents.
    You answer questions using only the incident post-mortems provided below
    Your goal is to give accurate, grounded answers that engineers can trust during an 
    outage.
    
    ## Rules

    1. **Grounding.** Use only the information from the sources below.
    Do not use any outside knowlwdge, even if you think you know the answer from 
    your training data. If the answer is not in the procided sources, say so.

    2. **Honesty on no answer.** If the provided sources do not contain enough information
    to answer the question, say "I do not have a matching incident in the sources" - do not
    guess or make up an answer. A clear "I don't know" is better than a confident wrong answer.

    3. Citations.** After each claim, put the source number in brackets like [1], [2],
    etc. Only cite source numbers that actually appear in the sources below. Do not
    invent citation numbers.


    ## Sources

    {context_block}

    ## Question


    {question}

    ## Answer

    Write a clear, concise answer that directly adresses the question. Prioritize
    the most relevant sources first. If multiple sources cover the same information, 
    cite the most relevant one.
    """

def generate_answer(question: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate an answer from the retrieved chunks.

    Args:
        question: User's question.
        results: List of result dicts from retrieve()

    Returns:
        Dict with:
            - answer: The model's generated answer
            - sources: List of source dicts (number, date, section, id)
    
    """

    # Build sources
    context_block, source_list = _build_sources(results)

    # Build prompt
    prompt = _build_prompt(question, context_block)

    # Shared LLM caller
    answer = call_llm(prompt)

    return {
        "answer": answer,
        "sources": source_list,
    }



def answer_query(
    question: str,
    top_k: int = 5,
    filter_metadata: Optional[Dict[str, Any]] = None,

) -> Dict[str, Any]:
    """
    Full RAG orchestrator: retrieve, then generate.
    If nothing relevant is retrieved, skip the model and return the no-match message.

    Args:
        question: User's question
        top_k: Number of chunks to retrieve
        filter_metadata: Optional filter for retrieval

    Returns:
        Dict with answer and sources.
    """
    # Retrieve relevant chunks
    results = retrieve(question, top_k=top_k, filter_metadata=filter_metadata)

    # Nothing close enough - no wastage of model call, return the fixed message
    if not results:
        return {
            "answer": NO_MATCH_MESSAGE,
            "sources": [],
        }
    
    return generate_answer(question, results)

def call_llm(prompt: str, model: str = None) -> str:
    """
    Send a prompt to the model and return the text response.

    Single point of contact with the LLM. Provider is chosen by the 
    LLM_PROVIDER environment variable:
        ollama      - local inference, the supported production path
        openrouter  - hosted inference, used for evaluation runs
    
    Same model weights either way (qwen 8B), so results transfer.

    """
    if LLM_PROVIDER == "openrouter":
        return _call_openrouter(prompt, model or OPENROUTER_MODEL)
    return _call_ollama(prompt, model or GEN_MODEL)


def _call_ollama(prompt: str, model:str) -> str:
    response = ollama.generate(model=model, prompt=prompt)
    return response.get("response", "")

def _call_openrouter(prompt: str, model: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is not set. "
            "Add it to .env"

        )
    response = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# Main

def main():
    """Test the generation pipeline"""
    question = "What caused the CLoudflare R2 outage?"

    print(f"Question: {question}")
    print("=" * 80)

    result = answer_query(question, top_k=3)

    print("\n" + "=" * 80)
    print("ANSWER:")
    print("=" * 80)
    print(result["answer"])
    print("\n" + "=" * 80)
    print("SOURCES:")
    print("=" * 80)
    for source in result["sources"]:
        print(f"    [{source['number']}] {source['company']} ({source['date']}) - {source['section']}")



if __name__ == "__main__":
    main()

