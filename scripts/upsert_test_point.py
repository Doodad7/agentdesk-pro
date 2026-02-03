# scripts/upsert_test_point.py
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models
import os, uuid

EMBED_MODEL = "all-MiniLM-L6-v2"
embed = SentenceTransformer(EMBED_MODEL)
q = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))

COLL = "agentdesk_docs"

texts = [
    ("doc1.md", 0, "AgentDesk stores docs as chunks in Qdrant and uses embeddings to search."),
    ("doc2.md", 0, "We embed user queries with all-MiniLM and search Qdrant for similar chunks.")
]

points = []
for i, (doc_id, chunk_id, txt) in enumerate(texts, start=1):
    vec = embed.encode(txt).tolist()
    payload = {"doc_id": doc_id, "chunk_id": chunk_id, "text": txt}
    points.append(models.PointStruct(id=i, vector=vec, payload=payload))

# make sure collection exists with correct size
try:
    q.recreate_collection(
        collection_name=COLL,
        vectors_config=models.VectorParams(size=len(points[0].vector), distance="Cosine")
    )
except Exception as e:
    print("create/recreate collection warning:", e)

res = q.upsert(collection_name=COLL, points=points)
print("Upsert response:", res)
