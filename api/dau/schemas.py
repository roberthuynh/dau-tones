"""Pydantic contracts shared by API routes and structured model output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CoachRequest(BaseModel):
    verdict: dict[str, Any]
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=24)
    accent: Literal["north", "south"] = "north"


class CoachResponse(BaseModel):
    coaching_sentence: str = Field(min_length=4, max_length=180)
    next_word: str
    rationale: str = Field(min_length=4, max_length=180)
    source: Literal["gpt-5.6-sol", "rules"] = "rules"


class DrillRequest(BaseModel):
    theme: Literal["food", "family", "travel"] = "family"
    size: int = Field(default=6, ge=3, le=10)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=24)


class DrillSelection(BaseModel):
    word_ids: list[str] = Field(min_length=3, max_length=10)
    rationale: str = Field(min_length=4, max_length=180)

    @field_validator("word_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class EchoSpeakRequest(BaseModel):
    sentence_id: str | None = None
    text: str | None = Field(default=None, max_length=220)
    accent: Literal["north", "south"] = "north"


class EchoDiffToken(BaseModel):
    target: str | None = None
    heard: str | None = None
    kind: Literal["match", "tone", "lexical", "missing", "extra"]
    target_word_id: str | None = None
    heard_word_id: str | None = None
    meaning_explanation: str | None = None
