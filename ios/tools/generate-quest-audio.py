#!/usr/bin/env python3
"""Bounded frozen-line generation. Adapted from Nghe's Realtime generator.
One attempt per line, persist paid output before validation/packaging, never reroll.
Run with uv run --with websocket-client python ios/tools/generate-quest-audio.py.
Reads the existing Nghe audio credential without printing or storing it.
"""
import base64, hashlib, json, os, subprocess, wave
from pathlib import Path
from datetime import datetime, timezone
import websocket
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'art/Generation/vietquest-v1/audio'
MAX_OUTPUT_TOKENS = 512
def request_audio(api_key: str, model: str, voice: str, prompt: str, line: str) -> tuple[bytes, str, dict]:
    ws = websocket.create_connection(
        f"wss://api.openai.com/v1/realtime?model={model}",
        header=[f"Authorization: Bearer {api_key}"],
        timeout=180,
    )
    audio = bytearray()
    transcript = ""
    usage: dict = {}
    try:
        ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": model,
                "output_modalities": ["audio"],
                "instructions": prompt,
                "audio": {
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": voice,
                    }
                },
                "reasoning": {"effort": "low"},
                "max_output_tokens": MAX_OUTPUT_TOKENS,
            },
        }))
        while True:
            event = json.loads(ws.recv())
            if event["type"] == "error":
                raise RuntimeError(f"OpenAI Realtime error: {event.get('error', event)}")
            if event["type"] == "session.updated":
                break
        ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "conversation": "none",
                "output_modalities": ["audio"],
                "instructions": f"{prompt}\n\nSpeak exactly this line:\n{line}",
            },
        }))
        while True:
            event = json.loads(ws.recv())
            event_type = event["type"]
            if event_type == "error":
                raise RuntimeError(f"OpenAI Realtime error: {event.get('error', event)}")
            if event_type == "response.output_audio.delta":
                audio.extend(base64.b64decode(event["delta"], validate=True))
            elif event_type == "response.output_audio_transcript.delta":
                transcript += event["delta"]
            elif event_type == "response.output_audio_transcript.done":
                transcript = event.get("transcript", transcript)
            elif event_type == "response.done":
                response = event["response"]
                if response.get("status") != "completed":
                    raise RuntimeError(f"Incomplete Realtime response: {response.get('status_details')}")
                usage = response.get("usage", {})
                break
    finally:
        ws.close()
    if not audio:
        raise RuntimeError("OpenAI Realtime returned no audio.")
    return bytes(audio), transcript, usage


def normalize(value):
    return ' '.join(''.join(c.lower() if c.isalnum() else ' ' for c in value).split())

def main():
    profile = json.loads((ROOT / 'art/Generation/vietquest-v1/voice-profile.json').read_text())
    jobs = json.loads((ROOT / 'art/Generation/vietquest-v1/audio-lines.json').read_text())
    assert len(jobs) <= 4, 'Four request hard ceiling'
    OUT.mkdir(parents=True, exist_ok=True)
    for job in jobs:
        raw = OUT / (job['id'] + '.wav')
        receipt = OUT / (job['id'] + '.json')
        if not receipt.exists():
            # A request marker prevents automatic re-generation after uncertain failure.
            marker = OUT / (job['id'] + '.requested')
            if marker.exists():
                raise RuntimeError('Prior request needs diagnosis: ' + job['id'])
            key = os.environ.get('OPENAI_API_KEY') or (Path.home()/'.nghe/openai-key').read_text().strip()
            persona = profile['personas'][job['persona']]
            prompt = '\n\n'.join([profile['accent'], persona['prompt'], profile['exactLineInstruction']])
            marker.write_text(datetime.now(timezone.utc).isoformat())
            print('Request ' + job['id'], flush=True)
            pcm, transcript, usage = request_audio(key, profile['model'], persona['voice'], prompt, job['text'])
            with wave.open(str(raw), 'wb') as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(pcm)
            record = dict(job, provider='openai', model=profile['model'], voice=persona['voice'], prompt=prompt, transcript=transcript, usage=usage, date=datetime.now(timezone.utc).isoformat(), raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
            receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
        record = json.loads(receipt.read_text())
        if normalize(record['transcript']) != normalize(job['text']):
            raise RuntimeError('Transcript mismatch: ' + job['id'] + ': ' + record['transcript'])
        dest = ROOT / 'ios/Resources/Content/quest/audio' / (job['id'] + '.caf')
        subprocess.run(['afconvert','-f','caff','-d','LEI16@24000','-c','1',str(raw),str(dest)],check=True)
        record['runtime_sha256'] = hashlib.sha256(dest.read_bytes()).hexdigest()
        record['validation'] = 'Normalized returned transcript matched; CAF conversion passed. Independent listening review separate.'
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
        print('Packaged ' + job['id'], flush=True)
if __name__ == '__main__': main()
