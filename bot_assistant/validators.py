"""
Модуль валидации данных.
"""

import re
from datetime import datetime
from typing import Optional, Tuple

from bot_assistant.errors import ValidationError


# Константы
PHONE_REGEX = re.compile(r"^\+?7\d{10}$|^8\d{10}$|^\d{10,15}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
CAR_REGEX = re.compile(r"^[a-zA-Zа-яА-Я0-9\s\-]{2,50}$")
NAME_REGEX = re.compile(r"^[a-zA-Zа-яА-Я\s\-]{2,100}$")


def normalize_phone(phone: str) -> str:
    """
    Нормализует номер телефона: удаляет всё кроме цифр и '+'.
    Если номер начинается с 8 или 7 — приводит к формату +7XXXXXXXXXX.
    """
    clean = re.sub(r"[^\d+]", "", phone)
    if clean.startswith("8") and len(clean) == 11:
        clean = "+7" + clean[1:]
    elif clean.startswith("7") and len(clean) == 11:
        clean = "+" + clean
    elif not clean.startswith("+") and len(clean) == 10:
        clean = "+7" + clean
    return clean


def validate_phone(phone: str, field: str = "phone") -> str:
    """Проверяет и нормализует номер телефона."""
    normalized = normalize_phone(phone)
    if not PHONE_REGEX.match(normalized):
        raise ValidationError(
            field,
            "Некорректный номер телефона. Ожидается формат: +7XXXXXXXXXX"
        )
    return normalized


def validate_name(name: str, field: str = "name") -> str:
    """Проверяет имя."""
    name = name.strip()
    if len(name) < 2:
        raise ValidationError(field, "Имя должно содержать минимум 2 символа")
    if len(name) > 100:
        raise ValidationError(field, "Имя слишком длинное (макс. 100 символов)")
    if not NAME_REGEX.match(name):
        raise ValidationError(
            field, "Имя может содержать только буквы, пробелы и дефисы"
        )
    return name


def validate_car(car: str, field: str = "car") -> str:
    """Проверяет марку и модель автомобиля."""
    car = car.strip()
    if len(car) < 2:
        raise ValidationError(field, "Укажите марку и модель автомобиля")
    if len(car) > 50:
        raise ValidationError(field, "Название слишком длинное (макс. 50 символов)")
    if not CAR_REGEX.match(car):
        raise ValidationError(
            field, "Некорректное название автомобиля"
        )
    return car


def validate_service(service: str, field: str = "service") -> str:
    """Проверяет услугу."""
    service = service.strip()
    if len(service) < 2:
        raise ValidationError(field, "Укажите необходимую услугу")
    if len(service) > 200:
        raise ValidationError(field, "Описание услуги слишком длинное")
    return service


def validate_datetime(dt_str: str, field: str = "desired_datetime") -> str:
    """Проверяет и нормализует дату/время."""
    dt_str = dt_str.strip()
    if not dt_str:
        raise ValidationError(field, "Укажите желаемую дату и время")

    # Пробуем разные форматы
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            # Проверяем, что дата не в прошлом
            if dt < datetime.now():
                raise ValidationError(
                    field, "Дата не может быть в прошлом. Укажите будущую дату"
                )
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue

    raise ValidationError(
        field,
        "Некорректный формат даты. Ожидается: ГГГГ-ММ-ДД ЧЧ:ММ или ДД.ММ.ГГГГ ЧЧ:ММ"
    )


def validate_comment(comment: str, field: str = "comment") -> str:
    """Проверяет комментарий."""
    comment = comment.strip()
    if comment.lower() in ("нет", "no", "-", "нема", "не надо"):
        return ""
    if len(comment) > 1000:
        raise ValidationError(field, "Комментарий слишком длинный (макс. 1000 символов)")
    return comment


def validate_lead_data(data: dict) -> dict:
    """
    Комплексная валидация всех полей заявки.
    Возвращает словарь с валидированными и нормализованными данными.
    """
    validated = {}

    if data.get("name"):
        validated["name"] = validate_name(data["name"])

    if data.get("phone"):
        validated["phone"] = validate_phone(data["phone"])

    if data.get("car"):
        validated["car"] = validate_car(data["car"])

    if data.get("service"):
        validated["service"] = validate_service(data["service"])

    if data.get("desired_datetime"):
        validated["desired_datetime"] = validate_datetime(data["desired_datetime"])

    if "comment" in data:
        validated["comment"] = validate_comment(data.get("comment", ""))

    return validated