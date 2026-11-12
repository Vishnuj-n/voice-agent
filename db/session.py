from __future__ import annotations

from datetime import datetime, timezone
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from config import load_config


# Base class for all ORM models.
class Base(DeclarativeBase):
    pass


class CallSession(Base):
    """Represents a single voice conversation."""

    __tablename__ = "call_sessions"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True)
    bot_name: Mapped[str]
    started_at: Mapped[str]
    ended_at: Mapped[str | None] = mapped_column(nullable=True)


class Turn(Base):
    """Stores one user ↔ bot interaction along with latency metrics."""

    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True)
    session_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False))
    turn_index: Mapped[int]

    caller_text: Mapped[str | None] = mapped_column(nullable=True)
    bot_text: Mapped[str | None] = mapped_column(nullable=True)

    # Per-stage latency metrics (milliseconds)
    stt_ms: Mapped[int | None] = mapped_column(nullable=True)
    retrieval_ms: Mapped[int | None] = mapped_column(nullable=True)
    llm_total_ms: Mapped[int | None] = mapped_column(nullable=True)
    llm_time_to_first_token_ms: Mapped[int | None] = mapped_column(nullable=True)
    tts_total_ms: Mapped[int | None] = mapped_column(nullable=True)
    tts_time_to_first_audio_ms: Mapped[int | None] = mapped_column(nullable=True)
    total_ms: Mapped[int | None] = mapped_column(nullable=True)

    was_fallback: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[str]


# Lazily initialized singleton engine and session factory.
_engine = None
_SessionLocal = None


def get_engine():
    """Return a shared SQLAlchemy engine."""

    global _engine

    if _engine is None:
        cfg = load_config()
        db_url = cfg.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        _engine = create_engine(
            db_url,
            # Validates pooled connections before reuse.
            pool_pre_ping=True,
        )

    return _engine


def get_session():
    """Create a new database session."""

    global _SessionLocal

    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())

    return _SessionLocal()


def init_db():
    """
    Initialize the database schema.

    - Creates ORM-managed tables.
    - Enables pgvector.
    - Creates RAG document tables for Finance and Legal.
    """

    engine = get_engine()

    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS finance_docs (
                    id BIGSERIAL PRIMARY KEY,
                    content TEXT,
                    embedding VECTOR,
                    metadata JSONB
                )
            """)
        )

        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS legal_docs (
                    id BIGSERIAL PRIMARY KEY,
                    content TEXT,
                    embedding VECTOR,
                    metadata JSONB
                )
            """)
        )


def record_session_start(session_id: str, bot_name: str) -> None:
    try:
        with get_session() as s:
            s.add(CallSession(id=session_id, bot_name=bot_name, started_at=datetime.now(timezone.utc).isoformat()))
            s.commit()
    except Exception:
        pass


def record_session_end(session_id: str) -> None:
    try:
        with get_session() as s:
            cs = s.get(CallSession, session_id)
            if cs:
                cs.ended_at = datetime.now(timezone.utc).isoformat()
                s.commit()
    except Exception:
        pass


def record_turn(session_id: str, turn_index: int, caller_text: str, bot_text: str, result) -> None:
    try:
        with get_session() as s:
            s.add(Turn(
                id=str(uuid.uuid4()),
                session_id=session_id,
                turn_index=turn_index,
                caller_text=caller_text,
                bot_text=bot_text,
                stt_ms=round(result.stt_ms),
                llm_total_ms=round(result.llm_total_ms),
                llm_time_to_first_token_ms=round(result.llm_time_to_first_token_ms),
                tts_total_ms=round(result.tts_total_ms),
                tts_time_to_first_audio_ms=round(result.tts_time_to_first_audio_ms),
                total_ms=round(result.total_ms),
                created_at=datetime.now(timezone.utc).isoformat(),
            ))
            s.commit()
    except Exception:
        pass
