"""
Тесты для модуля validators.
"""

import pytest
from bot_assistant.validators import (
    normalize_phone,
    validate_phone,
    validate_name,
    validate_car,
    validate_service,
    validate_datetime,
    validate_comment,
    validate_lead_data,
    ValidationError,
)


class TestNormalizePhone:
    """Тесты для normalize_phone."""

    def test_russian_number_with_plus(self):
        assert normalize_phone("+7 999 123-45-67") == "+79991234567"

    def test_russian_number_with_8(self):
        assert normalize_phone("8 999 123-45-67") == "+79991234567"

    def test_russian_number_without_prefix(self):
        assert normalize_phone("9991234567") == "+79991234567"

    def test_already_normalized(self):
        assert normalize_phone("+79991234567") == "+79991234567"

    def test_with_letters_and_symbols(self):
        assert normalize_phone("+7 (999) 123-45-67 доб. 101") == "+79991234567101"


class TestValidatePhone:
    """Тесты для validate_phone."""

    def test_valid_phone(self):
        assert validate_phone("+7 999 123-45-67") == "+79991234567"

    def test_invalid_phone_too_short(self):
        with pytest.raises(ValidationError):
            validate_phone("123")

    def test_invalid_phone_empty(self):
        with pytest.raises(ValidationError):
            validate_phone("")


class TestValidateName:
    """Тесты для validate_name."""

    def test_valid_name(self):
        assert validate_name("Иван") == "Иван"

    def test_valid_name_with_spaces(self):
        assert validate_name("  Иван Петров  ") == "Иван Петров"

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            validate_name("И")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            validate_name("А" * 101)

    def test_name_with_numbers(self):
        with pytest.raises(ValidationError):
            validate_name("Иван123")


class TestValidateCar:
    """Тесты для validate_car."""

    def test_valid_car(self):
        assert validate_car("Toyota Camry") == "Toyota Camry"

    def test_valid_car_cyrillic(self):
        assert validate_car("Лада Веста") == "Лада Веста"

    def test_car_too_short(self):
        with pytest.raises(ValidationError):
            validate_car("A")

    def test_car_empty(self):
        with pytest.raises(ValidationError):
            validate_car("")


class TestValidateService:
    """Тесты для validate_service."""

    def test_valid_service(self):
        assert validate_service("Замена масла") == "Замена масла"

    def test_service_too_short(self):
        with pytest.raises(ValidationError):
            validate_service("Т")


class TestValidateDatetime:
    """Тесты для validate_datetime."""

    def test_valid_datetime_iso(self):
        result = validate_datetime("2026-12-25 14:00")
        assert result == "2026-12-25 14:00"

    def test_valid_datetime_russian(self):
        result = validate_datetime("25.12.2026 14:00")
        assert result == "2026-12-25 14:00"

    def test_invalid_format(self):
        with pytest.raises(ValidationError):
            validate_datetime("неправильная дата")

    def test_empty_datetime(self):
        with pytest.raises(ValidationError):
            validate_datetime("")


class TestValidateComment:
    """Тесты для validate_comment."""

    def test_valid_comment(self):
        assert validate_comment("Позвонить после 18:00") == "Позвонить после 18:00"

    def test_no_comment(self):
        assert validate_comment("нет") == ""
        assert validate_comment("Нет") == ""
        assert validate_comment("no") == ""
        assert validate_comment("-") == ""

    def test_comment_too_long(self):
        with pytest.raises(ValidationError):
            validate_comment("А" * 1001)


class TestValidateLeadData:
    """Тесты для validate_lead_data."""

    def test_valid_lead(self):
        data = {
            "name": "Иван",
            "phone": "+7 999 123-45-67",
            "car": "Toyota Camry",
            "service": "Замена масла",
            "desired_datetime": "2026-12-25 14:00",
            "comment": "нет",
        }
        result = validate_lead_data(data)
        assert result["name"] == "Иван"
        assert result["phone"] == "+79991234567"
        assert result["comment"] == ""

    def test_empty_lead(self):
        result = validate_lead_data({})
        assert result == {}