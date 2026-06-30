from typing import TypedDict



class DiagnosticState(TypedDict):
    original_query: str
    symptoms: list[str]
    retrieved: dict[str, list[dict]]  #symptom -> list of incident dicts
    findings: str
    iterations: int
    diagnosis:str



def create_state(original_query: str) -> DiagnosticState:
    return {
        "original_query": original_query,
        "symptoms": [],
        "retrieved": {},
        "findings": "",
        "iterations": 0,
        "diagnosis": "",
    }