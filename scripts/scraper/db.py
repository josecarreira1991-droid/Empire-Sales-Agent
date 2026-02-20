"""Database connection and helper functions for Empire Sales Agent."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Get a PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "empire_leads"),
        user=os.getenv("DB_USER", "empire"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=RealDictCursor,
    )


def is_opted_out(phone: str) -> bool:
    """Check if a phone number is in the opt-out list."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM opt_outs WHERE phone = %s", (phone,))
            return cur.fetchone() is not None


def add_opt_out(phone: str, source: str = "manual"):
    """Add a phone number to the opt-out list."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO opt_outs (phone, source) VALUES (%s, %s) ON CONFLICT (phone) DO NOTHING",
                (phone, source),
            )
        conn.commit()


def get_daily_contact_count(lead_id: int) -> int:
    """Get number of outbound contacts in the last 24 hours (FTSA compliance)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count_daily_contacts(%s)", (lead_id,))
            row = cur.fetchone()
            return row["count_daily_contacts"] if row else 0


def insert_lead(lead: dict) -> int | None:
    """Insert a new lead, skip if phone already exists. Returns lead ID or None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Check for duplicate phone
            if lead.get("phone"):
                cur.execute("SELECT id FROM leads WHERE phone = %s", (lead["phone"],))
                existing = cur.fetchone()
                if existing:
                    return None

            columns = [k for k in lead.keys() if lead[k] is not None]
            values = [lead[k] for k in columns]
            placeholders = ", ".join(["%s"] * len(columns))
            col_names = ", ".join(columns)

            cur.execute(
                f"INSERT INTO leads ({col_names}) VALUES ({placeholders}) RETURNING id",
                values,
            )
            result = cur.fetchone()
            conn.commit()
            return result["id"] if result else None


def insert_leads_batch(leads: list[dict]) -> tuple[int, int]:
    """Batch insert leads. Returns (inserted, skipped) counts."""
    inserted = 0
    skipped = 0
    for lead in leads:
        result = insert_lead(lead)
        if result:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def insert_permit(permit: dict) -> int | None:
    """Insert a permit record. Returns permit ID or None if duplicate."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM permits WHERE permit_number = %s",
                (permit.get("permit_number"),),
            )
            if cur.fetchone():
                return None

            columns = [k for k in permit.keys() if permit[k] is not None]
            values = [permit[k] for k in columns]
            placeholders = ", ".join(["%s"] * len(columns))
            col_names = ", ".join(columns)

            cur.execute(
                f"INSERT INTO permits ({col_names}) VALUES ({placeholders}) RETURNING id",
                values,
            )
            result = cur.fetchone()
            conn.commit()
            return result["id"] if result else None


def log_scraping_run(source: str) -> int:
    """Start a scraping run log entry. Returns the run ID."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scraping_runs (source) VALUES (%s) RETURNING id",
                (source,),
            )
            result = cur.fetchone()
            conn.commit()
            return result["id"]


def complete_scraping_run(
    run_id: int,
    records_found: int = 0,
    records_new: int = 0,
    records_updated: int = 0,
    errors: int = 0,
    error_details: str = None,
    status: str = "completed",
):
    """Complete a scraping run log entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE scraping_runs
                   SET completed_at = NOW(), records_found = %s, records_new = %s,
                       records_updated = %s, errors = %s, error_details = %s, status = %s
                   WHERE id = %s""",
                (records_found, records_new, records_updated, errors, error_details, status, run_id),
            )
        conn.commit()


def get_contactable_leads(limit: int = 50) -> list[dict]:
    """Get leads ready to be contacted (respects opt-outs and daily limits)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM contactable_leads LIMIT %s", (limit,))
            return [dict(row) for row in cur.fetchall()]
