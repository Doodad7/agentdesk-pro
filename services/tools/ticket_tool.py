# services/tools/ticket_tool.py
"""
Small tool to create a ticket in Postgres.
Reads Postgres connection info from environment for safety.
"""
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

# load .env if available (dev convenience)
try:
    load_dotenv()
except Exception:
    pass

import psycopg2

PG = dict(
    dbname=os.getenv("POSTGRES_DB", "agentdesk"),
    user=os.getenv("POSTGRES_USER", "agentdesk"),
    password=os.getenv("POSTGRES_PASSWORD", "example"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
)

def create_ticket(payload: dict):
    conn = psycopg2.connect(**PG)
    cur = conn.cursor()
    ticket_id = str(uuid.uuid4())
    title = payload.get("title", "")[:200]
    description = payload.get("description", "")[:4000]
    priority = payload.get("priority", "medium")
    created_at = datetime.utcnow()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS tickets (
        id SERIAL PRIMARY KEY,
        ticket_id TEXT,
        title TEXT,
        description TEXT,
        priority TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    """)
    cur.execute("INSERT INTO tickets (ticket_id, title, description, priority, created_at) VALUES (%s,%s,%s,%s,%s)",
                (ticket_id, title, description, priority, created_at))
    conn.commit()
    cur.close()
    conn.close()
    return {"ticket_id": ticket_id, "status": "created", "title": title}