"""
Repository Pattern для работы с заявками.
Абстрагирует слой хранения данных от бизнес-логики.

Поддерживаемые реализации:
- PostgreSQL (основная, через SQLAlchemy)
- Google Sheets (для обратной совместимости)
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from bot_assistant.config import AppConfig
from bot_assistant.database import DatabaseManager
from bot_assistant.db_models import LeadModel
from bot_assistant.errors import LeadSaveError
from bot_assistant.logger import get_logger
from bot_assistant.models import Lead

logger = get_logger(__name__)


class LeadRepository(ABC):
    """Абстрактный репозиторий для заявок."""

    @abstractmethod
    def add(self, lead: Lead) -> Lead:
        """Сохраняет новую заявку."""
        ...

    @abstractmethod
    def get_all(self, limit: int = 100, offset: int = 0) -> List[Lead]:
        """Возвращает список заявок."""
        ...

    @abstractmethod
    def get_by_id(self, lead_id: int) -> Optional[Lead]:
        """Возвращает заявку по ID."""
        ...

    @abstractmethod
    def update_status(self, lead_id: int, status: str) -> bool:
        """Обновляет статус заявки."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Возвращает общее количество заявок."""
        ...


class PostgresLeadRepository(LeadRepository):
    """Репозиторий заявок на PostgreSQL через SQLAlchemy."""

    def __init__(self, db_manager: DatabaseManager):
        self._db = db_manager

    def _lead_from_model(self, model: LeadModel) -> Lead:
        """Преобразует SQLAlchemy модель в доменную модель Lead."""
        return Lead(
            source=model.source or "",
            timestamp=model.timestamp or "",
            name=model.name or "",
            phone=model.phone or "",
            car=model.car or "",
            service=model.service or "",
            desired_datetime=model.desired_datetime or "",
            comment=model.comment or "",
            user_id=model.user_id or "",
            status=model.status or "new",
            created_at=model.created_at.isoformat() if model.created_at else "",
        )

    def add(self, lead: Lead) -> Lead:
        """Сохраняет заявку в PostgreSQL."""
        with self._db.get_db() as db:
            if db is None:
                raise LeadSaveError("Database is not configured")

            model = LeadModel(
                source=lead.source,
                timestamp=lead.timestamp,
                name=lead.name,
                phone=lead.phone,
                car=lead.car,
                service=lead.service,
                desired_datetime=lead.desired_datetime,
                comment=lead.comment,
                user_id=lead.user_id,
                status=lead.status or "new",
            )
            db.add(model)
            db.flush()  # Чтобы получить id
            logger.info(
                "Lead saved to PostgreSQL: id=%d, name=%s",
                model.id, lead.name,
            )
            return self._lead_from_model(model)

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Lead]:
        """Возвращает список заявок из PostgreSQL."""
        with self._db.get_db() as db:
            if db is None:
                logger.warning("Database not configured, returning empty list")
                return []

            models = (
                db.query(LeadModel)
                .order_by(LeadModel.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self._lead_from_model(m) for m in models]

    def get_by_id(self, lead_id: int) -> Optional[Lead]:
        """Возвращает заявку по ID."""
        with self._db.get_db() as db:
            if db is None:
                return None

            model = db.query(LeadModel).filter(LeadModel.id == lead_id).first()
            if model is None:
                return None
            return self._lead_from_model(model)

    def update_status(self, lead_id: int, status: str) -> bool:
        """Обновляет статус заявки."""
        with self._db.get_db() as db:
            if db is None:
                return False

            rows = (
                db.query(LeadModel)
                .filter(LeadModel.id == lead_id)
                .update({"status": status})
            )
            if rows:
                logger.info("Lead %d status updated to %s", lead_id, status)
                return True
            logger.warning("Lead %d not found for status update", lead_id)
            return False

    def count(self) -> int:
        """Возвращает общее количество заявок."""
        with self._db.get_db() as db:
            if db is None:
                return 0
            return db.query(LeadModel).count()


class InMemoryLeadRepository(LeadRepository):
    """
    In-memory репозиторий заявок для тестирования и разработки.
    Используется, когда PostgreSQL и Google Sheets отключены.
    """

    def __init__(self):
        self._leads: List[Lead] = []
        self._next_id = 1

    def add(self, lead: Lead) -> Lead:
        """Сохраняет заявку в памяти."""
        from datetime import datetime
        lead.created_at = datetime.now().isoformat()
        lead.timestamp = lead.created_at
        self._leads.append(lead)
        logger.info("Lead saved to in-memory storage: name=%s", lead.name)
        return lead

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Lead]:
        """Возвращает список заявок из памяти."""
        return list(reversed(self._leads))[offset:offset + limit]

    def get_by_id(self, lead_id: int) -> Optional[Lead]:
        """Возвращает заявку по ID (индексу в списке)."""
        if 0 <= lead_id - 1 < len(self._leads):
            return self._leads[lead_id - 1]
        return None

    def update_status(self, lead_id: int, status: str) -> bool:
        """Обновляет статус заявки."""
        lead = self.get_by_id(lead_id)
        if lead:
            lead.status = status
            logger.info("Lead %d status updated to %s (in-memory)", lead_id, status)
            return True
        return False

    def count(self) -> int:
        """Возвращает общее количество заявок."""
        return len(self._leads)


class GoogleSheetsLeadRepository(LeadRepository):
    """
    Репозиторий заявок на Google Sheets (для обратной совместимости).
    Используется, когда PostgreSQL отключён.
    """

    def __init__(self, sheets_service=None):
        if sheets_service is None:
            from bot_assistant.services.google_sheets import GoogleSheetsService
            from bot_assistant.config import get_config
            sheets_service = GoogleSheetsService(get_config())
        self._sheets = sheets_service

    def add(self, lead: Lead) -> Lead:
        """Сохраняет заявку в Google Sheets."""
        result = self._sheets.append_lead(lead)
        logger.info("Lead saved to Google Sheets: %s", result.get("updatedRange", ""))
        return lead

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Lead]:
        """Возвращает список заявок из Google Sheets."""
        all_leads = self._sheets.get_leads(limit=limit + offset)
        return all_leads[offset:]

    def get_by_id(self, lead_id: int) -> Optional[Lead]:
        """Google Sheets не поддерживает поиск по ID."""
        logger.warning("get_by_id not supported for Google Sheets")
        return None

    def update_status(self, lead_id: int, status: str) -> bool:
        """Google Sheets не поддерживает обновление статуса."""
        logger.warning("update_status not supported for Google Sheets")
        return False

    def count(self) -> int:
        """Возвращает количество заявок."""
        return len(self._sheets.get_leads(limit=1000))


def create_lead_repository(
    config: Optional[AppConfig] = None,
    db_manager: Optional[DatabaseManager] = None,
) -> LeadRepository:
    """
    Фабрика: создаёт подходящий репозиторий в зависимости от конфигурации.
    Приоритет: PostgreSQL > Google Sheets > In-Memory.
    """
    if config is None:
        from bot_assistant.config import get_config
        config = get_config()

    if config.database.enabled:
        if db_manager is None:
            db_manager = DatabaseManager(config)
        logger.info("Using PostgreSQL lead repository")
        return PostgresLeadRepository(db_manager)

    if config.google_sheets.sheets_id:
        logger.info("Using Google Sheets lead repository (fallback)")
        return GoogleSheetsLeadRepository()

    logger.info("Using in-memory lead repository (for testing/development)")
    return InMemoryLeadRepository()


# Для обратной совместимости — функции-прокси
_repository: Optional[LeadRepository] = None


def get_lead_repository() -> LeadRepository:
    """Прокси для обратной совместимости. Использует DI контейнер."""
    global _repository
    if _repository is None:
        from bot_assistant.di import get_container
        container = get_container()
        _repository = container.get_lead_repository()
    return _repository


def reset_repository():
    """Сбрасывает глобальный репозиторий (для тестов)."""
    global _repository
    _repository = None
    # Также сбрасываем в DI контейнере
    from bot_assistant.di import get_container
    container = get_container()
    container.reset_repository()