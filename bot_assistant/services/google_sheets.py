"""
Сервис для работы с Google Sheets.
"""

import os
from typing import Dict, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from bot_assistant.circuit_breaker import (
    CircuitBreakerOpenError,
    get_circuit_breaker,
)
from bot_assistant.config import AppConfig, GoogleSheetsConfig
from bot_assistant.errors import GoogleSheetsError
from bot_assistant.logger import get_logger
from bot_assistant.models import Lead
from bot_assistant.retry import retry

logger = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetsService:
    """Сервис для работы с Google Sheets API."""

    def __init__(self, config: AppConfig):
        self._config = config.google_sheets
        self._service = None
        self._circuit_breaker = get_circuit_breaker(
            name="google_sheets",
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_attempts=3,
        )

    def _get_service(self):
        """Возвращает сервис Google Sheets (с ленивой инициализацией)."""
        if self._service is None:
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    self._config.credentials_file, scopes=_SCOPES
                )
                self._service = build("sheets", "v4", credentials=credentials)
                logger.debug("Google Sheets service initialized")
            except Exception as e:
                logger.error("Failed to initialize Google Sheets: %s", e)
                raise GoogleSheetsError(f"Ошибка инициализации Google Sheets: {e}")
        return self._service

    def _build_row(self, lead: Lead) -> List[str]:
        """Формирует строку для записи в таблицу."""
        columns_config = self._config.sheets_columns
        if columns_config:
            columns = [c.strip() for c in columns_config.split(",") if c.strip()]
            lead_dict = lead.to_dict()
            return [str(lead_dict.get(col, "") or "") for col in columns]

        # Дефолтный порядок
        return [
            lead.source,
            lead.timestamp,
            lead.name,
            lead.phone,
            lead.car,
            lead.service,
            lead.desired_datetime,
            lead.comment,
            lead.user_id,
            lead.status,
        ]

    @retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(GoogleSheetsError, OSError))
    def append_lead(self, lead: Lead) -> Dict[str, str]:
        """
        Добавляет заявку в Google Sheets.

        Args:
            lead: Заявка для сохранения

        Returns:
            Словарь с информацией о результате

        Raises:
            GoogleSheetsError: При ошибке записи или если circuit breaker открыт
        """
        if not self._config.sheets_id:
            raise GoogleSheetsError("GOOGLE_SHEETS_ID не настроен")

        try:
            return self._circuit_breaker.call(self._append_lead_impl, lead)
        except CircuitBreakerOpenError as e:
            logger.warning("Google Sheets circuit breaker open: %s", e)
            raise GoogleSheetsError(
                "Сервис Google Sheets временно недоступен. Заявка будет сохранена позже."
            )

    def _append_lead_impl(self, lead: Lead) -> Dict[str, str]:
        """Внутренняя реализация добавления заявки (без circuit breaker)."""
        try:
            service = self._get_service()
            values = [self._build_row(lead)]
            body = {"values": values}

            result = (
                service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self._config.sheets_id,
                    range=self._config.sheets_range,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
                .execute()
            )

            updated_range = result.get("updates", {}).get("updatedRange", "")
            logger.info("Lead appended to Google Sheets: %s", updated_range)
            return {"updatedRange": updated_range}

        except GoogleSheetsError:
            raise
        except Exception as e:
            logger.error("Failed to append lead to Google Sheets: %s", e)
            raise GoogleSheetsError(f"Ошибка записи в Google Sheets: {e}")

    @retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(GoogleSheetsError, OSError))
    def get_leads(self, limit: int = 100) -> List[Lead]:
        """
        Получает список заявок из Google Sheets.

        Args:
            limit: Максимальное количество записей

        Returns:
            Список заявок

        Raises:
            GoogleSheetsError: При ошибке чтения или если circuit breaker открыт
        """
        if not self._config.sheets_id:
            raise GoogleSheetsError("GOOGLE_SHEETS_ID не настроен")

        try:
            return self._circuit_breaker.call(self._get_leads_impl, limit)
        except CircuitBreakerOpenError as e:
            logger.warning("Google Sheets circuit breaker open: %s", e)
            raise GoogleSheetsError(
                "Сервис Google Sheets временно недоступен. Попробуйте позже."
            )

    def _get_leads_impl(self, limit: int = 100) -> List[Lead]:
        """Внутренняя реализация получения заявок (без circuit breaker)."""
        try:
            service = self._get_service()
            result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._config.sheets_id,
                    range=self._config.sheets_range,
                )
                .execute()
            )

            rows = result.get("values", [])
            leads = []
            for row in rows[1:limit]:  # Пропускаем заголовок
                if len(row) >= 6:
                    lead = Lead(
                        name=row[0] if len(row) > 0 else "",
                        phone=row[1] if len(row) > 1 else "",
                        car=row[2] if len(row) > 2 else "",
                        service=row[3] if len(row) > 3 else "",
                        desired_datetime=row[4] if len(row) > 4 else "",
                        comment=row[5] if len(row) > 5 else "",
                    )
                    leads.append(lead)

            logger.debug("Retrieved %d leads from Google Sheets", len(leads))
            return leads

        except Exception as e:
            logger.error("Failed to get leads from Google Sheets: %s", e)
            raise GoogleSheetsError(f"Ошибка чтения из Google Sheets: {e}")


# Для обратной совместимости
_sheets_service: Optional[GoogleSheetsService] = None


def get_sheets_service() -> GoogleSheetsService:
    """Прокси для обратной совместимости."""
    global _sheets_service
    if _sheets_service is None:
        from bot_assistant.di import get_container
        container = get_container()
        _sheets_service = container.get_sheets_service()
    return _sheets_service