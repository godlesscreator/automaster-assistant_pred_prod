"""
SQLAlchemy модели для PostgreSQL.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from bot_assistant.database import Base


class LeadModel(Base):
    """SQLAlchemy модель для заявки клиента."""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), default="", index=True)
    timestamp = Column(String(50), default="")
    name = Column(String(255), default="", index=True)
    phone = Column(String(50), default="", index=True)
    car = Column(String(255), default="")
    service = Column(String(255), default="")
    desired_datetime = Column(String(50), default="")
    comment = Column(Text, default="")
    user_id = Column(String(255), default="", index=True)
    status = Column(String(50), default="new", index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        """Преобразует модель в словарь."""
        return {
            "id": self.id,
            "source": self.source,
            "timestamp": self.timestamp,
            "name": self.name,
            "phone": self.phone,
            "car": self.car,
            "service": self.service,
            "desired_datetime": self.desired_datetime,
            "comment": self.comment,
            "user_id": self.user_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }


class WebSessionModel(Base):
    """SQLAlchemy модель для веб-сессии чата."""
    __tablename__ = "web_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), default="")
    phone = Column(String(50), default="")
    car = Column(String(255), default="")
    service = Column(String(255), default="")
    desired_datetime = Column(String(50), default="")
    comment = Column(Text, default="")
    awaiting = Column(String(50), nullable=True)
    messages = Column(Text, default="[]")  # JSON строка
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        """Преобразует модель в словарь для WebSession."""
        import json
        return {
            "name": self.name,
            "phone": self.phone,
            "car": self.car,
            "service": self.service,
            "desired_datetime": self.desired_datetime,
            "comment": self.comment,
            "awaiting": self.awaiting,
        }