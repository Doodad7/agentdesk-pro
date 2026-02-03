# services/ingestion/ingest_sample.py
import os
import time
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
import glob
import psycopg2

# Config
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "agentdesk_docs"
MODEL_NAME = "all-MiniLM-L6-v2"  # small & fast

# init
model = SentenceTransformer(MODEL_NAME)
qdrant = QdrantClient(url=QDRANT_URL, check_compatibility=False)

# ensure collection exists
qdrant.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=model.get_sentence_embedding_dimension(), distance=Distance.COSINE)
)

# Postgres connection for metadata
conn = psycopg2.connect(dbname="agentdesk", user="agentdesk", password="example", host="localhost", port=5432)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    source TEXT,
    text TEXT,
    inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ingest
files = glob.glob("sample_docs/*.md")
points = []
metas = []
for f in files:
    with open(f, "r", encoding="utf-8") as fh:
        text = fh.read()
    # naive chunking: split by paragraph
    chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
    for i, chunk in enumerate(chunks):
        emb = model.encode(chunk).tolist()
        payload = {"source": os.path.basename(f), "chunk_index": i, "text": chunk}
        points.append({"id": i, "vector": emb, "payload": payload})
        # also insert into postgres for provenance
        cur.execute("INSERT INTO documents (source, text) VALUES (%s, %s)", (os.path.basename(f), chunk))
conn.commit()

# upsert into Qdrant
qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
print(f"Ingested {len(points)} chunks into Qdrant and Postgres.")
cur.close()
conn.close()
