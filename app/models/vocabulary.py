from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.setting import utc_now


class Vocabulary(Base):
    __tablename__ = "vocabularies"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_empty"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255))
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    entries: Mapped[list[Entry]] = relationship(
        back_populates="vocabulary",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint(
            "vocabulary_id",
            "normalized_term",
            name="uq_entries_vocabulary_normalized_term",
        ),
        CheckConstraint("length(trim(term)) > 0", name="term_not_empty"),
        CheckConstraint(
            "length(trim(normalized_term)) > 0",
            name="normalized_term_not_empty",
        ),
        CheckConstraint("length(trim(meaning)) > 0", name="meaning_not_empty"),
        CheckConstraint(
            "entry_type IN ('word', 'phrase')",
            name="entry_type_allowed",
        ),
        Index("ix_entries_vocabulary_created_at", "vocabulary_id", "created_at"),
        Index("ix_entries_vocabulary_term", "vocabulary_id", "term"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vocabulary_id: Mapped[int] = mapped_column(
        ForeignKey("vocabularies.id", ondelete="CASCADE"),
        nullable=False,
    )
    term: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(500), nullable=False)
    entry_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="word",
    )
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    part_of_speech: Mapped[str | None] = mapped_column(String(100))
    phonetic: Mapped[str | None] = mapped_column(String(255))
    example: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    vocabulary: Mapped[Vocabulary] = relationship(back_populates="entries")
