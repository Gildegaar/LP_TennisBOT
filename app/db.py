from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import DATABASE_URL

def normalize_db_url(url: str) -> str:
    # Railway spesso usa postgresql:// ; SQLAlchemy preferisce postgresql+psycopg://
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

engine = create_engine(normalize_db_url(DATABASE_URL), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_session():
    return SessionLocal()