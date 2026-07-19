from pathlib import Path

from scripts.release_guards import model_findings, secret_findings
from scripts.validate_release import validate_release

ROOT = Path(__file__).resolve().parents[2]


def test_release_validator_checks_every_committed_media_group() -> None:
    result = validate_release()

    assert result == {
        "words": 19,
        "meaning_art": 19,
        "scenes": 4,
        "scene_art": 7,
        "dialogue_audio": 52,
        "demos": 8,
        "accepted_targets": 34,
        "missing_targets": 4,
    }


def test_secret_guard_detects_provider_tokens_and_private_keys() -> None:
    fake_key = "sk-" + "x" * 24
    private_key = "-----BEGIN " + "PRIVATE KEY-----"

    findings = secret_findings({"unsafe.txt": f"{fake_key}\n{private_key}\n"})

    assert any("OpenAI API key" in finding for finding in findings)
    assert any("private key" in finding for finding in findings)


def test_model_guard_accepts_only_the_central_active_registry() -> None:
    source = (ROOT / "api/dau/models.py").read_text(encoding="utf-8")

    assert model_findings({"api/dau/models.py": source}) == []


def test_model_guard_rejects_an_unapproved_active_id() -> None:
    deprecated = "gpt-" + "old-audio-model"
    source = (ROOT / "api/dau/models.py").read_text(encoding="utf-8")

    findings = model_findings(
        {"api/dau/models.py": source, "api/dau/example.py": f'MODEL = "{deprecated}"'}
    )

    assert findings == [f"unapproved active model {deprecated!r} in api/dau/example.py"]


def test_vercel_middleware_protects_every_paid_post_and_overwrites_assertion() -> None:
    source = (ROOT / "middleware.ts").read_text(encoding="utf-8")

    for route in (
        '"/api/coach"',
        '"/api/drills/generate"',
        '"/api/echo/transcribe"',
        'pathname.startsWith("/api/echo/reveals/")',
    ):
        assert route in source
    assert 'request.method !== "POST"' in source
    assert 'checkLevel: "basic"' in source
    assert 'headers.set("x-dau-bot-verified", "1")' in source
    assert 'code: "bot_blocked"' in source
    assert 'code: "ai_guard_unavailable"' in source
