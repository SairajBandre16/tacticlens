"""Keyless (Entra ID) REST calls to the AI Services resource: Translator and Speech TTS.

One custom-domain endpoint serves both (AZURE_AI_SERVICES_ENDPOINT). Every response is cached on disk by input
hash, so a second run makes no calls.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "cache"
SCOPE = "https://cognitiveservices.azure.com/.default"
ENDPOINT_ENV = "AZURE_AI_SERVICES_ENDPOINT"


def digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


class AzureRest:
    def __init__(self, endpoint: str | None = None, cache_dir: Path = CACHE_DIR):
        from azure.identity import DefaultAzureCredential  # optional extra: pip install .[azure]

        self.endpoint = (endpoint or os.environ[ENDPOINT_ENV]).rstrip("/")
        self.credential = DefaultAzureCredential()
        self.cache_dir = cache_dir
        self._token, self._expires = "", 0.0

    def _bearer(self) -> str:
        if time.time() > self._expires - 120:
            tok = self.credential.get_token(SCOPE)
            self._token, self._expires = tok.token, tok.expires_on
        return f"Bearer {self._token}"

    def _post(self, path: str, body: bytes, headers: dict, tries: int = 3) -> bytes:
        for attempt in range(tries):
            req = urllib.request.Request(f"{self.endpoint}{path}", data=body, method="POST", headers={
                "Authorization": self._bearer(), "User-Agent": "tacticlens", **headers})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.read()
            except (urllib.error.URLError, TimeoutError):  # transient network errors: back off and retry
                if attempt == tries - 1:
                    raise
                time.sleep(2 ** attempt)

    async def translate(self, texts: list[str], to: str, frm: str = "en") -> list[str]:
        """Translator v3 (custom domain). Supports <mstrans:dictionary> markup to force entity renderings."""
        path = self.cache_dir / "translate" / f"{digest(frm, to, *texts)}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        body = json.dumps([{"Text": t} for t in texts], ensure_ascii=False).encode()
        raw = await asyncio.to_thread(self._post, f"/translator/text/v3.0/translate?api-version=3.0&from={frm}&to={to}",
                                      body, {"Content-Type": "application/json; charset=UTF-8"})
        out = [item["translations"][0]["text"] for item in json.loads(raw)]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        return out

    async def speak(self, ssml: str, out_path: Path) -> Path:
        """Speech TTS REST (custom domain) to a 16 kHz mono mp3. Skips the call when out_path exists."""
        if not out_path.exists():
            audio = await asyncio.to_thread(self._post, "/tts/cognitiveservices/v1", ssml.encode(), {
                "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3"})
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(audio)
        return out_path
