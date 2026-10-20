import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.db import engine

def main():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            if result == 1:
                print("Database connection successful: SELECT 1 returned 1.")
                return 0
            else:
                print(f"Unexpected result from SELECT 1: {result}", file=sys.stderr)
                return 1
    except Exception as e:
        print(f"Database connection failed: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

