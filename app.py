# app.py — local demo UI for the Incident Post-Mortem Diagnostic Assistant
# Run:      streamlit run app.py
# Requires: Ollama running (embeddings) + LLM_PROVIDER=openrouter in .env (fast generation)

import os
import streamlit as st
from dotenv import load_dotenv

# ⚠️ Change this import to match your actual agent filename (the grep hit).
from src.agent import build_diagnostic_graph, create_state

load_dotenv()  # read LLM_PROVIDER / OPENROUTER_API_KEY exactly like your scripts do

st.set_page_config(page_title="Incident Diagnostic Assistant", layout="wide")

# Compile the LangGraph pipeline once, not on every click.
@st.cache_resource
def get_graph():
    return build_diagnostic_graph()

graph = get_graph()

st.title("Incident Post-Mortem Diagnostic Assistant")
st.caption(
    f"Provider: {os.getenv('LLM_PROVIDER', 'ollama')}  ·  embeddings run locally via Ollama"
)

query = st.text_area(
    "Describe the incident you're seeing",
    height=140,
    placeholder="e.g. API latency spiked to 5s, database CPU pinned at 100%, "
                "users getting intermittent 502s...",
)

if st.button("Diagnose", type="primary") and query.strip():
    with st.spinner("Decomposing symptoms, retrieving past incidents, diagnosing..."):
        final_state = graph.invoke(create_state(query))

    # 1. Symptoms extracted
    st.subheader("Symptoms extracted")
    if final_state["symptoms"]:
        for s in final_state["symptoms"]:
            st.markdown(f"- {s}")
    else:
        st.write("No distinct symptoms extracted.")

    # 2. Diagnosis — or the decline (the reliability moment)
    st.subheader("Differential diagnosis")
    diagnosis = final_state["diagnosis"]
    if diagnosis:
        st.table([
            {"Cause": d["cause"], "Evidence": d["evidence"], "Confidence": d["confidence"]}
            for d in diagnosis
        ])
    else:
        st.warning(
            "No confident match. The system declined to diagnose rather than guess — "
            "nothing in the corpus grounded a cause for these symptoms."
        )

    # Show the evidence gap even when a diagnosis exists (partial-evidence case)
    if not final_state["sufficient"] and final_state["gap_reason"]:
        st.info(f"Evidence gap: {final_state['gap_reason']}")

    # 3. Cross-reference findings
    if final_state["findings"]:
        with st.expander("Cross-reference findings"):
            st.write(final_state["findings"])

    # 4. Retrieved evidence per symptom — the receipts
    with st.expander("Retrieved past incidents (evidence)"):
        for symptom, hits in final_state["retrieved"].items():
            st.markdown(f"**{symptom}**")
            if not hits:
                st.markdown("— no incident retrieved for this symptom")
                continue
            for h in hits:
                meta = h.get("metadata", {})
                label = f"{meta.get('company', 'Unknown')} ({meta.get('date', 'n/a')}) — {meta.get('section', '')}"
                st.markdown(
                    f"- `{h.get('id', '?')}` · {label} · distance {h.get('distance', 'n/a')} (lower = closer)"
                )

    # 5. Optional model reasoning (only if SHOW_REASONING=true in .env)
    if final_state.get("reasoning"):
        with st.expander("Model reasoning"):
            st.write(final_state["reasoning"])