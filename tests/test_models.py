"""
Тесты для моделей данных.
"""

import pytest
from bot_assistant.models import Lead, WebSession, Appointment


class TestLead:
    """Тесты для модели Lead."""

    def test_lead_creation(self):
        lead = Lead(
            source="telegram",
            name="Иван",
            phone="+79991234567",
            car="Toyota Camry",
            service="Замена масла",
            desired_datetime="2026-12-25 14:00",
        )
        assert lead.source == "telegram"
        assert lead.name == "Иван"
        assert lead.status == "new"

    def test_lead_to_dict(self):
        lead = Lead(name="Иван", phone="+79991234567")
        data = lead.to_dict()
        assert data["name"] == "Иван"
        assert data["phone"] == "+79991234567"
        assert data["status"] == "new"

    def test_lead_from_dict(self):
        data = {
            "name": "Петр",
            "phone": "+79991234567",
            "car": "Lada Vesta",
            "status": "contacted",
        }
        lead = Lead.from_dict(data)
        assert lead.name == "Петр"
        assert lead.car == "Lada Vesta"
        assert lead.status == "contacted"

    def test_is_complete_true(self):
        lead = Lead(
            name="Иван",
            phone="+79991234567",
            car="Toyota",
            service="Ремонт",
            desired_datetime="2026-12-25 14:00",
        )
        assert lead.is_complete() is True

    def test_is_complete_false(self):
        lead = Lead(name="Иван", phone="+79991234567")
        assert lead.is_complete() is False

    def test_missing_fields(self):
        lead = Lead(name="Иван")
        missing = lead.missing_fields()
        assert "phone" in missing
        assert "car" in missing
        assert "service" in missing
        assert "desired_datetime" in missing
        assert "name" not in missing


class TestWebSession:
    """Тесты для модели WebSession."""

    def test_session_creation(self):
        session = WebSession(session_id="test-123")
        assert session.session_id == "test-123"
        assert session.awaiting is None

    def test_session_to_dict(self):
        session = WebSession(
            session_id="test-123",
            name="Иван",
            phone="+79991234567",
        )
        data = session.to_dict()
        assert data["name"] == "Иван"
        assert data["phone"] == "+79991234567"

    def test_session_to_lead(self):
        session = WebSession(
            session_id="test-123",
            name="Иван",
            phone="+79991234567",
            car="Toyota",
        )
        lead = session.to_lead()
        assert lead.source == "tilda_web_widget"
        assert lead.name == "Иван"
        assert lead.user_id == "test-123"