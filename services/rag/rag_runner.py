# services/rag/rag_runner.py
import os, requests, json
from typing import List, Dict
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

# optional LLMs
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
HF_KEY = os.getenv("HUGGINGFACE_API_KEY")

# fallback local HF model
try:
    from transformers import pipeline
    HF_PIPE = None
except Exception:
    HF_PIPE = None

EMBED_MODEL = "all-MiniLM-L6-v2"
embed_model = SentenceTransformer(EMBED_MODEL)
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
qdrant = QdrantClient(url=QDRANT_URL, check_compatibility=False)
COLLECTION = "agentdesk_docs"

def retrieve_docs(query: str, top_k: int = 5):
    qvec = embed_model.encode(query).tolist()
    # don't pass vector_name if your qdrant-client version doesn't accept it
    hits = qdrant.search(
        collection_name=COLLECTION,
        query_vector=qvec,
        limit=50
    )
    return hits[:top_k]

def build_prompt(query: str, hits) -> str:
    context = []
    for i, h in enumerate(hits):
        payload = h.payload
        context.append(
            f"[S-{i}] ({payload.get('doc_id')} chunk:{payload.get('chunk_id')})\n{payload.get('text')}\n"
        )
    context_block = "\n---\n".join(context)
    prompt = (
        "You are a helpful assistant. Use the context to answer. "
        "Cite sources inline using [S-i] where appropriate.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {query}\n\n"
        "Answer (be concise, and include citations like [S-0] when you use a source):"
    )
    return prompt

def call_llm(prompt: str, max_tokens: int = 256):
    # quick test stub
    use_stub = os.getenv("USE_LOCAL_STUB", "").lower() in ("1", "true", "yes")
    if use_stub:
        return "LOCAL-STUB: LLM disabled for tests."

    # 0) local pipeline (no network)
    if HF_PIPE is not None:
        try:
            out = HF_PIPE(prompt, max_length=min(256, max_tokens))
            if isinstance(out, list) and len(out) > 0:
                cand = out[0]
                if isinstance(cand, dict) and "generated_text" in cand:
                    return cand["generated_text"].strip()
                if isinstance(cand, str):
                    return cand.strip()
            if isinstance(out, dict) and "generated_text" in out:
                return out["generated_text"].strip()
            if isinstance(out, str):
                return out.strip()
        except Exception as e:
            print("Local HF_PIPE failed:", e)

    # 1) OpenAI path
    if OPENAI_KEY:
        try:
            import openai
            client = openai.OpenAI(api_key=OPENAI_KEY)
            model = "gpt-4o-mini" if os.getenv("OPENAI_USE_GPT4O") else "gpt-3.5-turbo"
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            try:
                return resp.choices[0].message.content.strip()
            except Exception:
                msg = getattr(resp.choices[0], "message", None)
                if isinstance(msg, dict) and "content" in msg:
                    c = msg["content"]
                    if isinstance(c, dict) and "text" in c:
                        return c["text"].strip()
                    return str(c).strip()
                return str(resp).strip()
        except Exception as e:
            print("OpenAI call failed, falling back to Hugging Face:", e)

    # 2) Hugging Face remote
    if HF_KEY:
        hf_model = os.getenv("HUGGINGFACE_MODEL", "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai")
        url = "https://router.huggingface.co/v1/chat/completions"
        headers = {"Authorization": f"Bearer {HF_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": hf_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": min(256, max_tokens),
            "stream": False
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            out = r.json()
            # router returns OpenAI-like chat shape: choices[0].message.content
            if isinstance(out, dict):
                choices = out.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    content = msg.get("content")
                    if isinstance(content, str):
                        return content.strip()
                    if isinstance(content, dict) and "text" in content:
                        return content["text"].strip()
                # fallback older shapes
                if "generated_text" in out:
                    return out["generated_text"].strip()
            if isinstance(out, list) and len(out) > 0 and isinstance(out[0], dict):
                if "generated_text" in out[0]:
                    return out[0]["generated_text"].strip()
            return str(out)
        except Exception as e:
            print(f"Hugging Face router call failed: {e}")
            return "Sorry — the LLM service is currently unavailable."

    # 3) nothing configured
    raise RuntimeError("No LLM configured. Set HUGGINGFACE_API_KEY or OPENAI_API_KEY or install local HF_PIPE.")

def answer_query(query: str, top_k: int = 5):
    print("Received query:", query)
    hits = retrieve_docs(query, top_k=top_k)
    print(f"Retrieved {len(hits)} hits from Qdrant")
    prompt = build_prompt(query, hits)
    print("Built prompt")
    answer = call_llm(prompt)
    print("LLM call finished")
    sources = [
        {"doc_id": h.payload.get("doc_id"), "chunk_id": h.payload.get("chunk_id")}
        for h in hits
    ]
    return {"query": query, "answer": answer, "sources": sources}
