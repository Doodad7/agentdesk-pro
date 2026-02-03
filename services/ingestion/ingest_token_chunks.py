# services/ingestion/ingest_token_chunks.py
"""
Improved token-based ingestion with:
- PII redaction
- Chunk source labeling
- Better metadata for RAG accuracy
- Environment-driven Postgres + Qdrant config
"""

import os
import glob
import uuid
import re
from dotenv import load_dotenv

# ------------------------
# Load environment
# ------------------------
try:
    load_dotenv()
except Exception:
    pass

import psycopg2
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance

# ------------------------
# Try tiktoken
# ------------------------
try:
    import tiktoken
    TOKTI = True
    enc = tiktoken.get_encoding("cl100k_base")
except Exception:
    TOKTI = False
    enc = None

# ------------------------
# Config
# ------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "agentdesk_docs")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

PG = dict(
    dbname=os.getenv("POSTGRES_DB", "agentdesk"),
    user=os.getenv("POSTGRES_USER", "agentdesk"),
    password=os.getenv("POSTGRES_PASSWORD", "example"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
)

# ------------------------
# PII Redaction
# ------------------------
EMAIL_RE = re.compile(r'\b[\w\.-]+@[\w\.-]+\.\w+\b')
PHONE_RE = re.compile(r'\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b')

def redact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return text

# ------------------------
# Token Helpers
# ------------------------
def tokenize_text(text):
    if TOKTI and enc:
        return enc.encode(text)
    return text.split()

def decode_tokens(tokens):
    if TOKTI and enc:
        return enc.decode(tokens)
    return " ".join(tokens)

# ------------------------
# Init models
# ------------------------
print("Loading embedding model...")
embed_model = SentenceTransformer(EMBED_MODEL)

print("Connecting to Qdrant...")
qdrant = QdrantClient(url=QDRANT_URL, check_compatibility=False)

# ------------------------
# Ensure collection exists
# ------------------------
try:
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=embed_model.get_sentence_embedding_dimension(),
                distance=Distance.COSINE
            )
        )
        print(f"Created collection {COLLECTION_NAME}")
    else:
        print(f"Collection {COLLECTION_NAME} exists.")
except Exception as e:
    print("Collection check error:", e)

# ------------------------
# Postgres
# ------------------------
print("Connecting to Postgres...")
conn = psycopg2.connect(**PG)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
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

# ------------------------
# Ingest Files
# ------------------------
files = sorted(glob.glob("sample_docs/*.md"))
print(f"Found {len(files)} markdown files.")

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        raw_text = f.read().strip()

    redacted_text = redact_pii(raw_text)
    filename = os.path.basename(fpath)

    # Store document
    cur.execute("SELECT id FROM documents WHERE source=%s", (filename,))
    row = cur.fetchone()

    if row:
        doc_db_id = row[0]
    else:
        cur.execute(
            "INSERT INTO documents (source, full_text) VALUES (%s,%s) RETURNING id",
            (filename, redacted_text)
        )
        doc_db_id = cur.fetchone()[0]
        conn.commit()

    print(f"Ingesting {filename}")

    tokens = tokenize_text(redacted_text)
    total_tokens = len(tokens)

    step = CHUNK_TOKENS - CHUNK_OVERLAP
    points = []
    chunk_id = 0

    for start in range(0, total_tokens, step):
        chunk_tokens = tokens[start:start + CHUNK_TOKENS]
        chunk_body = decode_tokens(chunk_tokens)

        # ⭐ Add document context
        chunk_text = f"Source: {filename}\n\n{chunk_body}"

        embedding = embed_model.encode(chunk_text).tolist()

        payload = {
            "doc_id": filename,
            "chunk_id": chunk_id,
            "source": filename,
            "text": chunk_body
        }

        points.append({
            "id": str(uuid.uuid4()),
            "vector": embedding,
            "payload": payload
        })

        cur.execute(
            "INSERT INTO chunks (doc_id, chunk_id, text, token_count, char_start, char_end) VALUES (%s,%s,%s,%s,%s,%s)",
            (filename, chunk_id, chunk_body, len(chunk_tokens), 0, 0)
        )

        chunk_id += 1

        if len(points) >= 100:
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            points = []
            conn.commit()

    if points:
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
        conn.commit()

    print(f"Finished {filename} ({chunk_id} chunks)")

print("✅ Ingestion complete.")

cur.close()
conn.close()
