from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.quiz import Quiz


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # nullable for OAuth users
    
    # OAuth fields
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="email")  # "email", "google", "phone"
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)  # Google sub, phone number
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    quizzes: Mapped[list["Quiz"]] = relationship(
        back_populates="creator", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r} provider={self.auth_provider}>"