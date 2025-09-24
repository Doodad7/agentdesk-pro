# tests/test_retrieval.py
from fastapi.testclient import TestClient
from services.api.main import app

client = TestClient(app)

def test_retrieve_docs():
    # Use a query that should match doc1.md (edit this string to match your doc contents)
    q = "solar system has eight planets"
    resp = client.post("/retrieve", json={"q": q, "top_k": 3})
    assert resp.status_code == 200
    js = resp.json()
    hits = js.get("hits", [])
    assert len(hits) > 0
    # verify at least one hit is from doc1.md
    assert any(h.get("doc_id") == "doc1.md" for h in hits), "doc1.md not in top hits"