"""
Модели данных для заявок и сессий.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Lead:
    """Модель заявки клиента."""
    source: str = ""  # telegram, tilda_web_widget, admin
    timestamp: str = ""
    name: str = ""
    phone: str = ""
    car: str = ""
    service: str = ""
    desired_datetime: str = ""
    comment: str = ""
    user_id: str = ""
    status: str = "new"  # new, contacted, completed, cancelled
    created_at: str = ""

    def to_dict(self) -> dict:
        """Преобразует заявку в словарь."""
        return {
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
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        """Создаёт заявку из словаря."""
        return cls(
            source=data.get("source", ""),
            timestamp=data.get("timestamp", ""),
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            car=data.get("car", ""),
            service=data.get("service", ""),
            desired_datetime=data.get("desired_datetime", ""),
            comment=data.get("comment", ""),
            user_id=data.get("user_id", ""),
            status=data.get("status", "new"),
            created_at=data.get("created_at", ""),
        )

    def is_complete(self) -> bool:
        """Проверяет, заполнены ли все обязательные поля."""
        return all([
            self.name,
            self.phone,
            self.car,
            self.service,
            self.desired_datetime,
        ])

    def missing_fields(self) -> list:
        """Возвращает список незаполненных обязательных полей."""
        fields = {
            "name": self.name,
            "phone": self.phone,
            "car": self.car,
            "service": self.service,
            "desired_datetime": self.desired_datetime,
        }
        return [k for k, v in fields.items() if not v]


@dataclass
class WebSession:
    """Модель веб-сессии для чата."""
    session_id: str
    name: str = ""
    phone: str = ""
    car: str = ""
    service: str = ""
    desired_datetime: str = ""
    comment: str = ""
    awaiting: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    messages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "phone": self.phone,
            "car": self.car,
            "service": self.service,
            "desired_datetime": self.desired_datetime,
            "comment": self.comment,
            "awaiting": self.awaiting,
        }

    def to_lead(self, source: str = "tilda_web_widget") -> Lead:
        """Преобразует сессию в заявку."""
        return Lead(
            source=source,
            name=self.name,
            phone=self.phone,
            car=self.car,
            service=self.service,
            desired_datetime=self.desired_datetime,
            comment=self.comment,
            user_id=self.session_id,
        )


@dataclass
class ServiceRecord:
    """Модель услуги автосервиса."""
    id: str
    name: str
    description: str
    price: float = 0.0
    duration_minutes: int = 60
    category: str = "other"  # to, repair, diagnostics, painting, other


@dataclass
class Appointment:
    """Модель записи на сервис."""
    id: str
    lead_id: str
    datetime: str
    service: str
    status: str = "scheduled"  # scheduled, confirmed, in_progress, completed, cancelled
    notes: str = ""
    created_at: str = ""