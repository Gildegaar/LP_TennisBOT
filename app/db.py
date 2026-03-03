from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .config import DATABASE_URL
from sqlalchemy import text

def normalize_db_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

engine = create_engine(normalize_db_url(DATABASE_URL), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_session():
    return SessionLocal()
    


def ensure_schema():
    """
    Migrazione 'light' per Postgres:
    - aggiunge colonne mancanti a lesson_requests
    - crea tabella payments se non esiste
    """
    with engine.begin() as conn:
        # lesson_requests: price_cents, currency
        conn.execute(text("ALTER TABLE IF EXISTS lesson_requests ADD COLUMN IF NOT EXISTS price_cents INTEGER NULL;"))
        conn.execute(text("ALTER TABLE IF EXISTS lesson_requests ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NOT NULL DEFAULT 'EUR';"))

        # payments table
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount_cents INTEGER NOT NULL,
            currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
            note TEXT NULL,
            method VARCHAR(32) NULL,
            paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payments_user_id ON payments(user_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payments_paid_at ON payments(paid_at);"))
        
def wipe_locations_hard() -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE locations RESTART IDENTITY CASCADE;"))

def wipe_all_hard() -> None:
    """
    Cancella TUTTO e resetta gli ID.
    """
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE payments RESTART IDENTITY CASCADE;"))
        conn.execute(text("TRUNCATE TABLE lesson_requests RESTART IDENTITY CASCADE;"))
        conn.execute(text("TRUNCATE TABLE locations RESTART IDENTITY CASCADE;"))
        conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE;"))