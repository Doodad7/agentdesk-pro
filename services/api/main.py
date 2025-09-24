# services/api/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from typing import List

# NEW IMPORT
from services.rag.rag_runner import answer_query

app = FastAPI(title="AgentDesk Pro - Retrieval API")

# Config
EMBED_MODEL = "all-MiniLM-L6-v2"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # small cross-encoder
QDRANT_URL = "http://localhost:6333"
COLLECTION = "agentdesk_docs"

# Init models & client
embed_model = SentenceTransformer(EMBED_MODEL)
# CrossEncoder is heavier — if torch isn't installed or GPU not available, this might be slower.
try:
    reranker = CrossEncoder(RERANKER_MODEL)
except Exception as e:
    reranker = None
    print("Reranker not available:", e)

qdrant = QdrantClient(url=QDRANT_URL)


class QueryIn(BaseModel):
    q: str
    top_k: int = 5


@app.post("/retrieve")
def retrieve(inp: QueryIn):
    query = inp.q
    top_k = inp.top_k
    # 1) embed query
    qvec = embed_model.encode(query).tolist()

    # 2) coarse search in Qdrant (top 50)
    coarse = qdrant.search(collection_name=COLLECTION, query_vector=qvec, limit=50)
    # each item has .payload and .score

    # 3) re-rank with cross-encoder if available
    hits = []
    if reranker is not None and len(coarse) > 0:
        pairs = [(query, item.payload.get("text", "")) for item in coarse]
        scores = reranker.predict(pairs)  # higher -> more relevant
        # attach scores to coarse
        scored = []
        for item, s in zip(coarse, scores):
            scored.append((float(s), item))
        # sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        # take top_k
        top_items = [it for _, it in scored[:top_k]]
        for it in top_items:
            hits.append({
                "doc_id": it.payload.get("doc_id"),
                "chunk_id": it.payload.get("chunk_id"),
                "char_start": it.payload.get("char_start"),
                "char_end": it.payload.get("char_end"),
                "token_count": it.payload.get("token_count"),
                "text": it.payload.get("text"),
                "score": it.score
            })
    else:
        # fallback: use coarse top-k by qdrant score
        for it in coarse[:top_k]:
            hits.append({
                "doc_id": it.payload.get("doc_id"),
                "chunk_id": it.payload.get("chunk_id"),
                "char_start": it.payload.get("char_start"),
                "char_end": it.payload.get("char_end"),
                "token_count": it.payload.get("token_count"),
                "text": it.payload.get("text"),
                "score": it.score
            })

    return {"query": query, "hits": hits}


# NEW ENDPOINT
@app.post("/query")
def query_endpoint(inp: QueryIn):
    res = answer_query(inp.q, top_k=inp.top_k)
    return res
