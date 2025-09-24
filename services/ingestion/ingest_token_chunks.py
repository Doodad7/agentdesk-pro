# services/ingestion/ingest_token_chunks.py
"""
Token-based ingestion:
- Reads sample_docs/*.md
- Splits by tokens (tiktoken if available, otherwise whitespace)
- Stores doc record in Postgres
- Stores chunk metadata in Postgres
- Upserts embeddings + payload to Qdrant
"""

import os
import glob
import time
import uuid  # ✅ added for unique point IDs
import psycopg2
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance

# Try to use tiktoken for accurate tokenization; fallback to whitespace
try:
    import tiktoken
    TOKTI = True
    enc = tiktoken.get_encoding("cl100k_base")  # works for many modern tokenizers
except Exception:
    TOKTI = False
    enc = None

# Config
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "agentdesk_docs"
EMBED_MODEL = "all-MiniLM-L6-v2"  # fast & small for embeddings
CHUNK_TOKENS = 500
CHUNK_OVERLAP = 50

# Init models & clients
print("Loading embedding model...")
embed_model = SentenceTransformer(EMBED_MODEL)
qdrant = QdrantClient(url=QDRANT_URL)

# Create / reset Qdrant collection if not exists
print("Ensuring Qdrant collection exists...")
try:
    qdrant.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=embed_model.get_sentence_embedding_dimension(), distance=Distance.COSINE)
    )
except Exception as e:
    print("Warning creating collection:", e)

# Postgres connection (match docker-compose env)
print("Connecting to Postgres...")
PG = dict(dbname="agentdesk", user="agentdesk", password="example", host="localhost", port=5432)
conn = psycopg2.connect(**PG)
cur = conn.cursor()

# Create tables if needed
cur.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_id TEXT,
    source TEXT,
    full_text TEXT,
    inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    doc_id TEXT,
    chunk_id INTEGER,
    text TEXT,
    token_count INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Helper tokenization functions
def tokenize_text(text):
    if TOKTI and enc:
        token_ids = enc.encode(text)
        return token_ids
    else:
        # simple whitespace fallback (approx tokens)
        return text.split()

def decode_tokens(token_sequence):
    if TOKTI and enc:
        return enc.decode(token_sequence)
    else:
        # fallback: list of words -> join
        if isinstance(token_sequence, list):
            return " ".join(token_sequence)
        return str(token_sequence)

# Ingest documents
files = sorted(glob.glob("sample_docs/*.md"))
print(f"Found {len(files)} files to ingest.")

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as fh:
        full_text = fh.read().strip()
    doc_basename = os.path.basename(fpath)
    doc_id = doc_basename  # simple doc id

    # Insert document record
    cur.execute(
        "INSERT INTO documents (source, text) VALUES (%s, %s) RETURNING id",
        (doc_basename, full_text),
    )
    doc_db_id = cur.fetchone()[0]
    conn.commit()
    print(f"Inserted document {doc_basename} with db id {doc_db_id}")

    # Tokenize and create chunks
    tokens = tokenize_text(full_text)
    total_length = len(tokens)
    print(f"Token length: {total_length}")

    points = []
    chunk_idx = 0
    search_pos = 0  # char search start to get char ranges
    step = CHUNK_TOKENS - CHUNK_OVERLAP
    for start_tok in range(0, total_length, step):
        chunk_tokens = tokens[start_tok:start_tok + CHUNK_TOKENS]
        if not chunk_tokens:
            break
        chunk_text = decode_tokens(chunk_tokens) if TOKTI else " ".join(chunk_tokens)
        # find char range (best-effort)
        found_at = full_text.find(chunk_text, search_pos)
        if found_at == -1:
            found_at = search_pos
        char_start = found_at
        char_end = found_at + len(chunk_text)
        search_pos = char_end

        # embedding
        emb = embed_model.encode(chunk_text).tolist()

        payload = {
            "doc_id": doc_id,
            "chunk_id": chunk_idx,
            "text": chunk_text,
            "char_start": int(char_start),
            "char_end": int(char_end),
            "token_count": len(chunk_tokens)
        }

        # ✅ FIXED: use UUID instead of string id
        point = {"id": str(uuid.uuid4()), "vector": emb, "payload": payload}
        points.append(point)

        # insert chunk metadata to Postgres
        cur.execute(
            "INSERT INTO chunks (doc_id, chunk_id, text, token_count, char_start, char_end) VALUES (%s,%s,%s,%s,%s,%s)",
            (doc_id, chunk_idx, chunk_text, len(chunk_tokens), int(char_start), int(char_end))
        )
        chunk_idx += 1

        # For memory safety, flush every 100 points
        if len(points) >= 100:
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            points = []
            conn.commit()
            print(f"Upserted 100 points for {doc_id}...")

    # flush remaining points
    if points:
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
        conn.commit()
        print(f"Upserted remaining points for {doc_id} (chunks: {chunk_idx})")

print("Ingestion complete.")
cur.close()
conn.close()
