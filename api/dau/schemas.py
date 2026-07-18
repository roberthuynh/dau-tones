"""Pydantic contracts shared by API routes and structured model output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ToneId = Literal["ngang", "huyen", "sac", "hoi", "nga", "nang"]
ToneFamilyId = Literal["level", "falling", "rising", "dipping"]
SemanticStatus = Literal[
    "exact_correct",
    "family_correct",
    "family_ambiguous",
    "wrong_known_word",
    "wrong_no_known_word",
    "uncertain",
]


class CoachRequest(BaseModel):
    verdict: dict[str, Any]
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=24)
    accent: Literal["north", "south"] = "north"


class CoachResponse(BaseModel):
    observation: str = Field(min_length=4, max_length=180)
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
    turn_id: str | None = None
    sentence_id: str | None = None
    text: str | None = Field(default=None, max_length=220)
    accent: Literal["north", "south"] = "north"


class EchoFocus(BaseModel):
    token_index: int = Field(ge=0)
    token: str
    tone: ToneId
    word_id: str | None = None
    meaning_en: str | None = None


class EchoTurn(BaseModel):
    id: str
    scene_id: str
    speaker: Literal["minh", "learner"]
    role_label: str
    text: str
    gloss_en: str
    turn_index: int = Field(ge=0)
    learner_turn_number: int | None = None
    next_turn_id: str | None = None
    previous_turn_id: str | None = None
    focuses: list[EchoFocus]
    focus_word_ids: list[str]
    audio_urls: dict[Literal["north", "south"], str]
    literal_stakes: list[dict[str, Any]] = Field(default_factory=list)


class EchoScene(BaseModel):
    id: str
    order: int = Field(ge=1)
    title: str
    title_vi: str
    description: str
    art_url: str
    offline_demo: dict[str, Any]
    turns: list[EchoTurn]


class EchoScenesResponse(BaseModel):
    schema_version: int
    locale: str
    scenes: list[EchoScene]


class EchoDiffToken(BaseModel):
    target: str | None = None
    heard: str | None = None
    kind: Literal["match", "tone_only", "lexical", "missing", "extra"]
    target_index: int | None = None
    heard_index: int | None = None
    target_word_id: str | None = None
    heard_word_id: str | None = None
    target_tone: ToneId | None = None
    heard_tone: ToneId | None = None
    semantic_status: Literal[
        "match",
        "known_word",
        "no_known_meaning",
        "lexical_change",
        "not_applicable",
    ] = "not_applicable"
    meaning_explanation: str | None = None


class EchoDetectedTone(BaseModel):
    token_index: int
    target: str
    heard: str
    intended_tone: ToneId
    detected_tone: ToneId
    target_word_id: str | None = None
    heard_word_id: str | None = None
    semantic_status: Literal["known_word", "no_known_meaning"]


class AnalysisAlternative(BaseModel):
    tone: ToneId
    family: ToneFamilyId
    score: float
    confidence: float = Field(ge=0.0, le=1.0)


class AnalysisWord(BaseModel):
    id: str
    surface: str
    meaning_en: str
    art_url: str


class AnalysisMeaningVerdict(BaseModel):
    status: SemanticStatus
    assertion_level: Literal["exact", "family", "none"]
    detected_surface: str | None = None
    detected_meaning_en: str | None = None
    detected_word_id: str | None = None
    tone_mark_label: str


class AnalysisResponse(BaseModel):
    tone_detected: ToneId
    tone_intended: ToneId
    intended_word_id: str
    detected_word_id: str | None = None
    correct: bool
    confidence: float = Field(ge=0.0, le=0.95)
    learner_contour: list[float]
    target_contour: list[float]
    detected_contour: list[float] | None = None
    tips_features: dict[str, Any]
    grading_mode: Literal["six_tone", "four_family"]
    exact_verified: bool
    family_verified: bool
    alternatives: list[AnalysisAlternative]
    needs_retry: bool
    signal_quality: dict[str, Any]

    # Rich meaning metadata and compatibility names used by earlier API builds.
    tone_family: ToneFamilyId
    intended_family: ToneFamilyId
    exact_tone_match: bool
    family_correct: bool
    verification_level: Literal["exact", "family", "uncertain"]
    tone_alternatives: list[dict[str, Any]]
    word: str
    intended_word: AnalysisWord
    detected_word: AnalysisWord | None = None
    verdict_copy: str | None = None
    target_validated: bool
    semantic_status: SemanticStatus
    class_confidence: float = Field(ge=0.0, le=0.95)
    signal_confidence: float = Field(ge=0.0, le=1.0)
    meaning_verdict: AnalysisMeaningVerdict
    classifier_version: str
    classifier_manifest_hash: str


class EchoTranscribeResponse(BaseModel):
    sentence_id: str
    scene_id: str | None = None
    turn_id: str
    next_turn_id: str | None = None
    target_text: str
    transcript: str
    tokens: list[EchoDiffToken]
    practice_word_ids: list[str]
    detected_tones: list[EchoDetectedTone]
    meaning_status: Literal[
        "exact_match",
        "known_word_change",
        "no_known_meaning",
        "lexical_change",
        "missing_or_extra",
    ]
    explanation: str
    literal_explanation: str
    source: str
    reveal_id: str | None = None

    # The first API build exposed these names. Keeping them costs nothing and
    # lets cached clients move to target_text/tokens without a flag day.
    target: str
    diff: list[EchoDiffToken]
