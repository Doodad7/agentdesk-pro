# services/api/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

app = FastAPI()
MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)
qdrant = QdrantClient(url="http://localhost:6333")
COLLECTION_NAME = "agentdesk_docs"

class QueryIn(BaseModel):
    q: str

@app.post("/retrieve")
def retrieve(inp: QueryIn):
    qvec = model.encode(inp.q).tolist()
    hits = qdrant.search(collection_name=COLLECTION_NAME, query_vector=qvec, limit=5)
    return {"query": inp.q, "hits": [{"payload": h.payload, "score": h.score} for h in hits]}
