"""Stable public API errors that never expose provider or server internals."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    message: str = Field(min_length=2, max_length=300)
    needs_retry: bool | None = None
    issues: list[dict[str, Any]] | None = None


class ErrorEnvelope(BaseModel):
    detail: ErrorDetail


class RouteError(Exception):
    """An intentional learner-safe error returned by a route."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}
        self.extra = extra or {}

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}
