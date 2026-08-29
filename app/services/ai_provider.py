from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Protocol

import httpx

from app.core.config import settings


class AIProviderError(RuntimeError):
    pass


class AIProvider(Protocol):
    provider: str
    model: str

    def create_ride_draft(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]: ...


class MockAIProvider:
    provider = "mock"
    model = "mock-ride-assistant-v1"

    def create_ride_draft(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
        text = " ".join(prompt.split())
        origin, destination = self._extract_route(text)
        seats = self._extract_seats(text)
        price = self._extract_price(text)
        departure_time = self._extract_departure_time(text)
        vehicle = self._extract_vehicle(text)
        missing_fields = [
            field
            for field, value in {
                "origin": origin,
                "destination": destination,
                "departure_time": departure_time,
                "available_seats": seats,
                "price_per_seat": price,
                "vehicle_details": vehicle,
            }.items()
            if value is None
        ]

        return {
            "origin": origin,
            "destination": destination,
            "departure_time": departure_time.isoformat() if departure_time else None,
            "available_seats": seats,
            "price_per_seat": str(price) if price is not None else None,
            "vehicle_details": vehicle,
            "notes": self._build_notes(text),
            "missing_fields": missing_fields,
            "confidence": max(0.35, 1 - (len(missing_fields) * 0.1)),
            "safety_notes": [
                "Confirm exact pickup point before publishing.",
                "Avoid sharing private payment details in notes.",
            ],
        }

    def _extract_route(self, text: str) -> tuple[str | None, str | None]:
        match = re.search(
            r"\bfrom\s+([A-Za-z\s,.-]{2,80}?)\s+to\s+([A-Za-z\s,.-]{2,80}?)(?:\s+(?:on|at|by|with|in|for|tomorrow|today)\b|[,.;]|$)",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None, None
        return self._clean_place(match.group(1)), self._clean_place(match.group(2))

    def _extract_seats(self, text: str) -> int | None:
        match = re.search(r"\b([1-9]|10)\s*(?:seat|seats|passenger|passengers)\b", text, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _extract_price(self, text: str) -> Decimal | None:
        match = re.search(r"(?:₹|rs\.?|inr)\s*([0-9]{1,6})(?:\s*(?:per seat|each))?", text, flags=re.IGNORECASE)
        if not match:
            match = re.search(r"\b([0-9]{2,6})\s*(?:per seat|each)\b", text, flags=re.IGNORECASE)
        return Decimal(match.group(1)) if match else None

    def _extract_departure_time(self, text: str) -> datetime | None:
        now = datetime.now(timezone.utc)
        if re.search(r"\btomorrow\b", text, flags=re.IGNORECASE):
            date_value = now.date() + timedelta(days=1)
        elif re.search(r"\btoday\b", text, flags=re.IGNORECASE):
            date_value = now.date()
        else:
            date_value = None

        time_match = re.search(r"\b([0-1]?[0-9]|2[0-3])(?::([0-5][0-9]))?\s*(am|pm)?\b", text, flags=re.IGNORECASE)
        if not date_value and not time_match:
            return None

        hour = 9
        minute = 0
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            meridiem = time_match.group(3)
            if meridiem:
                meridiem = meridiem.lower()
                if meridiem == "pm" and hour < 12:
                    hour += 12
                if meridiem == "am" and hour == 12:
                    hour = 0

        return datetime.combine(date_value or now.date(), time(hour, minute), tzinfo=timezone.utc)

    def _extract_vehicle(self, text: str) -> str | None:
        vehicle_match = re.search(
            r"\b(swift|ertiga|innova|sedan|hatchback|suv|dzire|baleno|creta|wagonr|wagon r)\b",
            text,
            flags=re.IGNORECASE,
        )
        if not vehicle_match:
            return None
        return vehicle_match.group(1).title()

    def _build_notes(self, text: str) -> str:
        clipped = text[:220]
        return f"AI draft from driver note: {clipped}"

    def _clean_place(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip(" ,.-")).title()


class OpenAICompatibleProvider:
    provider = "openai"

    def __init__(self) -> None:
        if not settings.AI_API_KEY:
            raise RuntimeError("AI_API_KEY is not configured")
        self.model = settings.AI_MODEL
        self.base_url = settings.AI_BASE_URL.rstrip("/")

    def create_ride_draft(self, *, prompt: str, locale: str, timezone_name: str) -> dict[str, object]:
        system_prompt = (
            "You convert ride-sharing driver text into a strict JSON ride draft. "
            "Return only JSON with keys: origin, destination, departure_time, available_seats, "
            "price_per_seat, vehicle_details, notes, missing_fields, confidence, safety_notes. "
            "Use ISO 8601 for departure_time, null for unknown fields, and do not invent exact data."
        )
        user_prompt = (
            f"Locale: {locale}\n"
            f"Timezone: {timezone_name}\n"
            f"Current UTC time: {datetime.now(timezone.utc).isoformat()}\n"
            f"Driver text: {prompt}"
        )
        payload = {
            "model": self.model,
            "temperature": settings.AI_TEMPERATURE,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
                json=payload,
                timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise AIProviderError("AI provider returned non-object JSON")
            return parsed
        except (KeyError, json.JSONDecodeError, httpx.HTTPError) as exc:
            raise AIProviderError("AI provider failed to return a valid ride draft") from exc


def get_ai_provider() -> AIProvider:
    if settings.AI_PROVIDER == "openai":
        return OpenAICompatibleProvider()
    return MockAIProvider()
