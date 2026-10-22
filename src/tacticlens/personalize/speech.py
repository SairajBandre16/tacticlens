"""Audio description: Azure AI Speech TTS for the audio persona, cached as mp3 next to the golden match."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from .azure_rest import digest

VOICES = {"en": ("en-GB", "en-GB-SoniaNeural"), "hi": ("hi-IN", "hi-IN-SwaraNeural"),
          "es": ("es-ES", "es-ES-ElviraNeural")}


def ssml(text: str, lang: str) -> str:
    locale, voice = VOICES[lang]
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
            f'<voice name="{voice}"><prosody rate="-5%">{escape(text)}</prosody></voice></speak>')


def audio_text(explanation: dict) -> str:
    return " ".join(s["text"] for s in explanation["sentences"])


def audio_name(text: str, lang: str) -> str:
    return f"audio/{lang}-{digest(VOICES[lang][1], text)[:16]}.mp3"


async def synthesize(match_dir: Path, explanations: list[dict], moment_ids: list[str], rest) -> dict:
    """mp3 for every audio-persona explanation of the given moments. Returns {moment_id: {lang: relative path}}."""
    index: dict[str, dict[str, str]] = {}
    for e in explanations:
        if e["persona_key"] != "audio" or e["moment_id"] not in moment_ids or e["lang"] not in VOICES:
            continue
        text = audio_text(e)
        rel = audio_name(text, e["lang"])
        await rest.speak(ssml(text, e["lang"]), match_dir / rel)
        index.setdefault(e["moment_id"], {})[e["lang"]] = rel
    return index
