from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from dau import coach as coach_module
from dau.coach import PHYSICAL_TIPS, coach, deterministic_coach, generate_drill
from dau.schemas import CoachRequest, CoachResponse, DrillRequest, DrillSelection


def test_deterministic_coach_leads_with_a_measured_observation() -> None:
    response = deterministic_coach(
        CoachRequest(
            verdict={
                "word": "ma-mother",
                "tone_intended": "sac",
                "correct": False,
                "class_confidence": 0.78,
                "tips_features": {
                    "codes": ["started_too_high", "no_final_rise"],
                    "numeric": {"start_semitones": 1.74, "final_rise": -2.08},
                },
            },
            accent="south",
        )
    )
    assert response.observation == "Your pitch began 1.7 semitones above the target."
    assert response.coaching_sentence == PHYSICAL_TIPS["started_too_high"]
    assert response.source == "rules"


@pytest.mark.parametrize(
    ("code", "numeric"),
    [
        ("ended_too_low", {"end": -2.1}),
        ("range_too_flat", {"pitch_range": -1.8}),
        ("dip_too_early", {"dip_position": -0.21}),
        ("too_short", {"duration_s": -0.19}),
        ("weak_glottal_break", {"central_rms_dip": -0.17}),
    ],
)
def test_deterministic_observation_covers_emitted_feature_codes(
    code: str, numeric: dict[str, float]
) -> None:
    response = deterministic_coach(
        CoachRequest(
            verdict={
                "word": "ma-code",
                "tone_intended": "nga",
                "correct": False,
                "tips_features": {"codes": [code], "numeric": numeric},
            }
        )
    )
    assert response.observation
    assert response.coaching_sentence == PHYSICAL_TIPS[code]


def test_gpt_coach_receives_only_structured_classifier_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    parsed = CoachResponse(
        observation="Your ending landed 2.1 semitones below the target.",
        coaching_sentence="Keep your chin level and support the end of the vowel.",
        next_word="ma-ghost",
        rationale="because the level and falling shapes need contrast",
        source="rules",
    )

    class Responses:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(output_parsed=parsed)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        coach_module,
        "_openai_client",
        lambda _key: SimpleNamespace(responses=Responses()),
    )
    response = coach(
        CoachRequest(
            verdict={
                "word": "phuong-name",
                "tone_intended": "ngang",
                "tone_detected": "huyen",
                "semantic_status": "wrong_known_word",
                "class_confidence": 0.82,
                "signal_confidence": 0.91,
                "meaning_verdict": {
                    "assertion_level": "exact",
                    "detected_meaning_en": "urban ward",
                },
                "tips_features": {
                    "codes": ["fell_instead_of_level"],
                    "numeric": {"end_semitones": -2.1},
                },
            },
            history=[
                {
                    "tone_intended": "ngang",
                    "tone_detected": "huyen",
                    "semantic_status": "wrong_known_word",
                    "correct": False,
                }
            ],
            accent="north",
        ),
        safety_identifier="hashed-client-id",
    )

    assert captured["text_format"] is CoachResponse
    assert captured["max_output_tokens"] == 600
    assert captured["store"] is False
    assert captured["safety_identifier"] == "hashed-client-id"
    messages = captured["input"]
    assert isinstance(messages, list)
    evidence = json.loads(messages[1]["content"])
    assert evidence["intended_tone"] == "ngang"
    assert evidence["detected_tone"] == "huyen"
    assert evidence["assertion_level"] == "exact"
    assert evidence["known_meaning"] == "urban ward"
    assert evidence["feature_differences"] == {"end_semitones": -2.1}
    assert evidence["confusion_pair_history"][0]["detected_tone"] == "huyen"
    assert response.source == "gpt-5.6-sol"
    assert response.refinement_status == "complete"
    assert response.observation.startswith("Your ending")


def test_gpt_drill_drops_unneeded_history_and_disables_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Responses:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                output_parsed=DrillSelection(
                    word_ids=["ma-ghost", "ma-but", "ma-mother"],
                    rationale="Contrast three familiar shapes.",
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        coach_module,
        "_openai_client",
        lambda _key: SimpleNamespace(responses=Responses()),
    )
    result = generate_drill(
        DrillRequest(
            theme="family",
            size=3,
            history=[
                {
                    "intended_tone": "sac",
                    "detected_tone": "ngang",
                    "correct": False,
                    "raw_audio": "must-not-leave-the-server",
                }
            ],
        ),
        safety_identifier="hashed-client-id",
    )

    assert captured["store"] is False
    assert captured["safety_identifier"] == "hashed-client-id"
    messages = captured["input"]
    assert isinstance(messages, list)
    evidence = json.loads(messages[1]["content"])
    assert "raw_audio" not in evidence["history"][0]
    assert result["source"] == "gpt-5.6-sol"
