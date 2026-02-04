# services/api/main.py

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from typing import List
import os
from dotenv import load_dotenv
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status

# NEW: Prometheus instrumentator + custom metric
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Histogram

from services.tools.ticket_tool import create_ticket

from fastapi import UploadFile, File
from services.vision.ocr_ingest import extract_text_from_image
import shutil, tempfile, os

from services.vision.clip_embed import embed_image, embed_texts

import tempfile
import uuid
from qdrant_client.http import models

# load .env for local dev
try:
    load_dotenv()
except Exception:
    pass

_auth_scheme = HTTPBearer(auto_error=False)

# Optional: OpenTelemetry (tracing). Wrapped in try/except so the app still runs if not configured.
try:
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    OTEL_AVAILABLE = True
except Exception:
    OTEL_AVAILABLE = False

# NEW: helper to estimate tokens (tiktoken if available, else whitespace count)
try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    TOKTI_AVAILABLE = True
except Exception:
    _ENC = None
    TOKTI_AVAILABLE = False

# App init
app = FastAPI(title="AgentDesk Pro - Retrieval API")

# -------------------------
# Observability setup
# -------------------------
# 1) Prometheus Instrumentator: collects HTTP metrics (counts, latencies) and exposes /metrics
Instrumentator().instrument(app).expose(app, include_in_schema=False, should_gzip=True)

# 2) Custom metric: tokens per request (Histogram)
# This will appear in the /metrics output and can be used in Grafana dashboards.
tokens_per_request = Histogram(
    "agentdesk_tokens_per_request",
    "Histogram of number of tokens processed per API request (approx.)"
)

# 3) Optional OpenTelemetry basic setup (Console exporter)
# This is a minimal local setup that exports spans to the console for development.
if OTEL_AVAILABLE:
    resource = Resource(attributes={SERVICE_NAME: "agentdesk-pro"})
    provider = TracerProvider(resource=resource)
    span_processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(span_processor)
    TracerProvider()  # safe-guard (no-op) — provider configured above
    # Connect FastAPI to OpenTelemetry instrumentation
    try:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    except Exception as e:
        # If instrumentation fails, app still runs; print helpful debug info
        print("OpenTelemetry instrumentor failed to attach:", e)

# -------------------------
# Config + models (unchanged)
# -------------------------
# Config
EMBED_MODEL = "all-MiniLM-L6-v2"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION = "agentdesk_docs"

# Init models & client (these are heavier and may take > a few seconds)
embed_model = SentenceTransformer(EMBED_MODEL)

try:
    reranker = CrossEncoder(RERANKER_MODEL)
except Exception as e:
    reranker = None
    print("Reranker not available:", e)

qdrant = QdrantClient(url=QDRANT_URL, check_compatibility=False)


# -------------------------
# Helpers
# -------------------------
def estimate_token_count(text: str) -> int:
    """Estimate token count for a string.
    Uses tiktoken if available (preferred), otherwise falls back to simple whitespace word count.
    """
    if TOKTI_AVAILABLE and _ENC:
        try:
            return len(_ENC.encode(text))
        except Exception:
            pass
    # fallback: approximate by words
    return max(1, len(text.split()))


# -------------------------
# API models
# -------------------------
class QueryIn(BaseModel):
    q: str
    top_k: int = 5


# -------------------------
# Endpoints
# -------------------------
@app.get("/ping")
def ping():
    """Simple health endpoint. Useful for liveness checks & Grafana/Prometheus dashboards."""
    return {"message": "pong"}


@app.post("/retrieve")
def retrieve(inp: QueryIn):
    """
    Lightweight retrieval endpoint:
    - embeds the query
    - coarse-searches Qdrant
    - optional reranking
    Returns top chunks and scores.
    We observe tokens_per_request here for observability.
    """
    query = inp.q
    top_k = inp.top_k

    # Observability: estimate tokens used by request and record
    tok_count = estimate_token_count(query)
    tokens_per_request.observe(tok_count)

    # 1) embed query
    qvec = embed_model.encode(query).tolist()

    # 2) coarse search in Qdrant (top 50)
    coarse = qdrant.search(collection_name=COLLECTION, query_vector=qvec, limit=50)

    # 3) re-rank with cross-encoder if available
    hits = []
    if reranker is not None and len(coarse) > 0:
        pairs = [(query, item.payload.get("text", "")) for item in coarse]
        scores = reranker.predict(pairs)  # higher -> more relevant
        scored = []
        for item, s in zip(coarse, scores):
            scored.append((float(s), item))
        scored.sort(key=lambda x: x[0], reverse=True)
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

@app.post("/query")
def query_endpoint(inp: QueryIn):

    from services.agents.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator()
    result = orchestrator.run(inp.q, inp.top_k)

    return result


def get_current_role(credentials: HTTPAuthorizationCredentials = Depends(_auth_scheme)):
    """
    Resolve role from a simple Bearer token.
    - Bearer <ADMIN_TOKEN> => "admin"
    - Bearer <USER_TOKEN> => "user"
    Raises 401 if missing/invalid.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")
    token = credentials.credentials
    admin_token = os.getenv("ADMIN_TOKEN", "admin123")
    user_token = os.getenv("USER_TOKEN", "user123")
    if token == admin_token:
        return "admin"
    if token == user_token:
        return "user"
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
# --------------------------
# Tool orchestration endpoint (unchanged)
# --------------------------
class ToolCall(BaseModel):
    name: str
    args: dict
    run_id: str = None


@app.post("/execute_tool")
def execute_tool(call: ToolCall, role: str = Depends(get_current_role)):
    # Only admin may run tools (example)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: admin role required")
    if call.name == "create_ticket":
        res = create_ticket(call.args)
        return {"ok": True, "result": res}
    else:
        return {"ok": False, "error": "Unknown tool"}


@app.post("/ingest_image")
async def ingest_image(file: UploadFile = File(...)):
    # Save upload to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
    try:
        with open(tmp.name, "wb") as f:
            shutil.copyfileobj(file.file, f)
        text = extract_text_from_image(tmp.name)
        return {"ok": True, "extracted_chars": len(text), "preview": text[:300]}
    finally:
        try: os.unlink(tmp.name)
        except: pass
        


@app.post("/embed_image")
async def embed_image_endpoint(file: UploadFile = File(...), tenant: str = "default"):
    # Save the uploaded file temporarily
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, file.filename)
    with open(tmp_path, "wb") as f:
        f.write(await file.read())

    # Generate embedding for the image
    vec = embed_image(tmp_path)

    # Use per-tenant collection name (for multi-user support)
    coll = f"user_{tenant}"

    # Ensure collection exists with correct vector size and distance metric
    try:
        qdrant.recreate_collection(
            collection_name=coll,
            vectors_config=models.VectorParams(size=len(vec), distance="Cosine")
        )
    except Exception:
        pass

    # Upsert single image embedding
    point = models.PointStruct(
        id=str(uuid.uuid4()),  # valid UUID for Qdrant
        vector=vec,            # correct variable name
        payload={"path": tmp_path}
    )

    qdrant.upsert(collection_name=coll, points=[point])

    # Clean up temporary file
    os.remove(tmp_path)

    return {"ok": True, "message": "Image embedded successfully"}


@app.post("/search_images")
async def search_images_endpoint(query: str, tenant: str = "default"):
    # Embed the text query
    vec = embed_texts([query])[0]

    # Collection name for this tenant
    coll = f"user_{tenant}"

    # Search top 3 results
    results = qdrant.search(
        collection_name=coll,
        query_vector=vec,
        limit=3
    )

    return {
        "ok": True,
        "query": query,
        "results": [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload
            }
            for r in results
        ]
    }
