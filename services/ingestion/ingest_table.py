# services/ingestion/ingest_table.py
import pandas as pd
from sqlalchemy import create_engine, text
import os

# read DB creds from env or default
PG_USER = os.getenv("POSTGRES_USER", "agentdesk")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "supersecret")
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_DB = os.getenv("POSTGRES_DB", "agentdesk")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")

engine = create_engine(f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}")

def ingest_csv_to_table(csv_path: str, table_name: str = "features"):
    df = pd.read_csv(csv_path)
    # optional: add ingestion metadata
    df['ingested_at'] = pd.Timestamp.utcnow()
    df.to_sql(table_name, con=engine, if_exists="append", index=False)
    return {"rows": len(df)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ingest_table.py example.csv [table_name]")
        sys.exit(1)
    csv = sys.argv[1]
    table = sys.argv[2] if len(sys.argv) > 2 else "features"
    print(ingest_csv_to_table(csv, table))