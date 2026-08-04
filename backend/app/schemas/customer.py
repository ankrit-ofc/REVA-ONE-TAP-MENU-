"""
Pydantic schemas for customer contact capture.

Security notes:
- extra="forbid" — an unexpected field is rejected with 422.
- This is a WRITE-ONLY contract. There is deliberately no response schema that
  echoes a customer's email, name, or phone; the endpoint returns a bare status.
  Nothing here may be reused to build a staff-facing response body.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _blank_to_none(value: str | None) -> str | None:
    """Trim, then normalise an empty/whitespace-only string to NULL."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class CustomerContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # EmailStr rejects malformed addresses with 422 before anything touches the DB.
    # Length cap matches the customers.email column being free text.
    email: Annotated[EmailStr, Field(max_length=254)]
    name: Annotated[str | None, Field(max_length=120)] = None
    phone: Annotated[str | None, Field(max_length=32)] = None

    @field_validator("name", "phone", mode="before")
    @classmethod
    def _optional_blank_is_null(cls, v: object) -> object:
        return _blank_to_none(v) if isinstance(v, str) or v is None else v


class CustomerContactAck(BaseModel):
    """
    Deliberately contentless. The customer app only needs to know the capture
    landed; returning any stored field would turn a write-only endpoint into a
    lookup oracle for other diners' details.
    """

    status: str = "ok"
