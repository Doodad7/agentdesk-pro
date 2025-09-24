# services/rag/rag_runner.py
import os
from typing import List, Dict
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

# optional LLMs
USE_OPENAI = bool(os.getenv("OPENAI_API_KEY", ""))
if USE_OPENAI:
    import openai

# fallback local HF model
try:
    from transformers import pipeline
    HF_PIPE = pipeline("text2text-generation", model="google/flan-t5-small")
except Exception:
    HF_PIPE = None

EMBED_MODEL = "all-MiniLM-L6-v2"
embed_model = SentenceTransformer(EMBED_MODEL)
qdrant = QdrantClient(url="http://localhost:6333")
COLLECTION = "agentdesk_docs"

def retrieve_docs(query: str, top_k: int = 5):
    qvec = embed_model.encode(query).tolist()
    hits = qdrant.search(collection_name=COLLECTION, query_vector=qvec, limit=50)
    # we will return top_k by len
    return hits[:top_k]

def build_prompt(query: str, hits) -> str:
    # hits: sequence of qdrant hits with payload text and doc info
    context = []
    for i, h in enumerate(hits):
        payload = h.payload
        context.append(f"[S-{i}] ({payload.get('doc_id')} chunk:{payload.get('chunk_id')})\n{payload.get('text')}\n")
    context_block = "\n---\n".join(context)
    prompt = (
        "You are a helpful assistant. Use the context to answer. "
        "Cite sources inline using [S-i] where appropriate.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {query}\n\nAnswer (be concise, and include citations like [S-0] when you use a source):"
    )
    return prompt

def call_llm(prompt: str, max_tokens: int = 256) -> str:
    if USE_OPENAI:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini" if os.getenv("OPENAI_USE_GPT4O") else "gpt-3.5-turbo",
            messages=[{"role":"user","content":prompt}],
            max_tokens=max_tokens
        )
        return resp["choices"][0]["message"]["content"].strip()
    elif HF_PIPE is not None:
        out = HF_PIPE(prompt, max_length=256)
        return out[0]['generated_text']
    else:
        return "LLM not configured. Set OPENAI_API_KEY or install transformers with a local model."

def answer_query(query: str, top_k: int = 5):
    hits = retrieve_docs(query, top_k=top_k)
    # simple transform to pass to prompt
    prompt = build_prompt(query, hits)
    answer = call_llm(prompt)
    # collect simple metadata to return
    sources = [{"doc_id": h.payload.get("doc_id"), "chunk_id": h.payload.get("chunk_id")} for h in hits]
    return {"query": query, "answer": answer, "sources": sources}
