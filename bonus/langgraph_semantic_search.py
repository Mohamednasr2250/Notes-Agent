"""
Semantic search example using LangGraph.

This file stores embeddings for notes, performs semantic search, and uses an LLM to generate a natural-language answer.
"""

import json
import os
import sqlite3
from typing import TypedDict, List, Tuple, Optional

# Load environment variables from a .env file.

def _load_dotenv_simple(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv_simple()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notes_agent.storage import NotesStore
from notes_agent.llm_providers import _clean_harmony_leakage

_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


# Load the embedding model when it is first needed.


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model

# Convert text into an embedding vector.


def embed(text: str) -> List[float]:
    return _get_model().encode([text])[0].tolist()


# Create the embeddings table if it does not exist.


def ensure_embeddings_table(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS note_embeddings (note_id INTEGER PRIMARY KEY, vector TEXT NOT NULL)"
    )
    conn.commit()

# Create or update a note's embedding.


def upsert_embedding(conn: sqlite3.Connection, note_id: int, text: str):
    vec = embed(text)
    conn.execute(
        "INSERT INTO note_embeddings (note_id, vector) VALUES (?, ?) "
        "ON CONFLICT(note_id) DO UPDATE SET vector=excluded.vector",
        (note_id, json.dumps(vec)),
    )
    conn.commit()

# Calculate cosine similarity between two vectors.


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0

# Find the most similar notes for a query.


def semantic_search(conn: sqlite3.Connection, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
    q_vec = embed(query)
    cur = conn.execute("SELECT note_id, vector FROM note_embeddings")
    scored = [(note_id, _cosine(q_vec, json.loads(v))) for note_id, v in cur.fetchall()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]

# Shared state used by the LangGraph workflow.



class SearchState(TypedDict):
    query: str
    conn: sqlite3.Connection
    store: NotesStore
    results: List[Tuple[int, float]]
    answer: str

# Retrieve the most similar notes.



def retrieve(state: SearchState) -> SearchState:
    results = semantic_search(state["conn"], state["query"], top_k=5)
    return {**state, "results": results}

# Generate a natural-language answer from the search results.



def generate_answer(state: SearchState) -> SearchState:
    results = state["results"]
    if not results:
        return {**state, "answer": "No notes matched that closely enough."}

    matches = []
    for note_id, score in results:
        note = state["store"].get_note(note_id)
        if note:
            matches.append(f"#{note_id} ({score:.2f}): {note.title} — {note.body}")
    if not matches:
        return {**state, "answer": "No notes matched that closely enough."}

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=os.environ.get("HF_MODEL", "openai/gpt-oss-120b:together"),
        api_key=os.environ.get("HF_TOKEN"),
        base_url="https://router.huggingface.co/v1",
    )
    prompt = (
        f"The user searched for: \"{state['query']}\"\n\n"
        f"These notes matched semantically (id, similarity score, title, body):\n"
        + "\n".join(matches)
        + "\n\nWrite a short, plain-language answer summarizing what matched and why "
          "it's relevant, even if the exact search words don't appear in the note text."
    )
    reply = llm.invoke(prompt)
    return {**state, "answer": _clean_harmony_leakage(reply.content)}

# Build the LangGraph workflow.


def build_graph():
    from langgraph.graph import StateGraph, END

    graph = StateGraph(SearchState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate_answer", generate_answer)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate_answer")
    graph.add_edge("generate_answer", END)
    return graph.compile()


if __name__ == "__main__":
    store = NotesStore(":memory:")
    n1 = store.add_note("Launch plan", "ship the final report by Friday or we lose the client", ["urgent"])
    n2 = store.add_note("Groceries", "buy milk and eggs", ["personal"])

    ensure_embeddings_table(store.conn)
    upsert_embedding(store.conn, n1.id, f"{n1.title} {n1.body}")
    upsert_embedding(store.conn, n2.id, f"{n2.title} {n2.body}")

    app = build_graph()
    result = app.invoke({
        "query": "project deadline",
        "conn": store.conn,
        "store": store,
        "results": [],
        "answer": "",
    })
    print(result["answer"])
