"""
Тесты для Repository Pattern.
"""

from unittest.mock import MagicMock, patch

import pytest

from bot_assistant.models import Lead
from bot_assistant.repository import (
    GoogleSheetsLeadRepository,
    PostgresLeadRepository,
    create_lead_repository,
    get_lead_repository,
    reset_repository,
)


class TestGoogleSheetsLeadRepository:
    """Тесты для GoogleSheetsLeadRepository."""

    def test_add_lead(self):
        """Проверка сохранения заявки через Google Sheets."""
        mock_sheets = MagicMock()
        mock_sheets.append_lead.return_value = {"updatedRange": "Leads!A2:J2"}

        repo = GoogleSheetsLeadRepository(sheets_service=mock_sheets)
        lead = Lead(name="Иван", phone="+79991234567", car="Toyota", service="Ремонт")

        result = repo.add(lead)
        assert result.name == "Иван"

    def test_get_all(self):
        """Проверка получения списка заявок."""
        mock_sheets = MagicMock()
        mock_sheets.get_leads.return_value = [
            Lead(name="Иван", phone="+79991234567"),
            Lead(name="Петр", phone="+79991112233"),
        ]

        repo = GoogleSheetsLeadRepository(sheets_service=mock_sheets)
        leads = repo.get_all(limit=10)

        assert len(leads) == 2
        assert leads[0].name == "Иван"
        assert leads[1].name == "Петр"

    def test_get_by_id_not_supported(self):
        """Проверка, что get_by_id не поддерживается для Google Sheets."""
        mock_sheets = MagicMock()
        repo = GoogleSheetsLeadRepository(sheets_service=mock_sheets)
        result = repo.get_by_id(1)
        assert result is None

    def test_update_status_not_supported(self):
        """Проверка, что update_status не поддерживается для Google Sheets."""
        mock_sheets = MagicMock()
        repo = GoogleSheetsLeadRepository(sheets_service=mock_sheets)
        result = repo.update_status(1, "contacted")
        assert result is False


class TestCreateRepository:
    """Тесты для фабрики репозиториев."""

    def test_create_postgres_repo(self):
        """Проверка создания PostgreSQL репозитория."""
        mock_cfg = MagicMock()
        mock_cfg.database.enabled = True

        repo = create_lead_repository(config=mock_cfg)
        assert isinstance(repo, PostgresLeadRepository)

    def test_create_google_sheets_repo(self):
        """Проверка создания Google Sheets репозитория (fallback)."""
        mock_cfg = MagicMock()
        mock_cfg.database.enabled = False

        repo = create_lead_repository(config=mock_cfg)
        assert isinstance(repo, GoogleSheetsLeadRepository)

    def test_get_lead_repository_singleton(self):
        """Проверка, что get_lead_repository возвращает singleton."""
        reset_repository()
        r1 = get_lead_repository()
        r2 = get_lead_repository()
        assert r1 is r2

    def test_reset_repository(self):
        """Проверка сброса репозитория."""
        reset_repository()
        r1 = get_lead_repository()
        reset_repository()
        r2 = get_lead_repository()
        assert r1 is not r2