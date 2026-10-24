"""Moment / evidence store: Cosmos DB (NoSQL, Entra ID auth) when AZURE_COSMOS_ENDPOINT is set, else local JSON.

Moments (with their evidence packs and counterfactuals) live in container `moments`, explanations from live agent
runs in `explanations`; both are partitioned by /match_id. The Cosmos store seeds itself from data/golden on first
read of a match, and any Cosmos failure falls back to the JSON store, so golden mode never depends on Azure.
"""
from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from ..sim.golden import GOLDEN_DIR

log = logging.getLogger("tacticlens.store")
ENDPOINT_ENV, DB_ENV = "AZURE_COSMOS_ENDPOINT", "AZURE_COSMOS_DATABASE"
LOCAL_DIR = GOLDEN_DIR.parents[1] / "data" / "cache" / "store"


def _doc_id(*parts: str) -> str:
    return re.sub(r"[/\\?#]", "_", ":".join(parts))  # characters Cosmos forbids in ids


class JsonStore:
    name = "json"

    def __init__(self, golden_dir: Path = GOLDEN_DIR, local_dir: Path = LOCAL_DIR):
        self.golden_dir, self.local_dir = golden_dir, local_dir

    def moments(self, mid: str) -> list[dict]:
        return json.loads((self.golden_dir / mid / "moments.json").read_text(encoding="utf-8"))

    def save_explanation(self, mid: str, explanation: dict, trace: list[dict], backend: str) -> str:
        doc_id = _doc_id(explanation["moment_id"], explanation["persona_key"], backend)
        path = self.local_dir / mid / f"{doc_id.replace(':', '_')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"id": doc_id, "match_id": mid, "backend": backend, "explanation": explanation,
                                    "trace": trace}, ensure_ascii=False), encoding="utf-8")
        return doc_id


class CosmosStore:
    name = "cosmos"

    def __init__(self, endpoint: str, database: str = "tacticlens", fallback: JsonStore | None = None):
        from azure.cosmos import CosmosClient  # optional extra: pip install .[azure]
        from azure.identity import DefaultAzureCredential

        db = CosmosClient(endpoint, credential=DefaultAzureCredential()).get_database_client(database)
        self.moments_c, self.expl_c = db.get_container_client("moments"), db.get_container_client("explanations")
        self.fallback = fallback or JsonStore()

    def moments(self, mid: str) -> list[dict]:
        try:
            rows = list(self.moments_c.query_items("SELECT * FROM c WHERE c.match_id = @m",
                                                   parameters=[{"name": "@m", "value": mid}], partition_key=mid))
            if not rows:  # first read of this match: seed from golden
                rows = self.fallback.moments(mid)
                for m in rows:
                    self.moments_c.upsert_item(m)
                log.info("seeded %d moments for %s into Cosmos", len(rows), mid)
            return sorted(({k: v for k, v in r.items() if not k.startswith("_")} for r in rows),
                          key=lambda m: (m["t_start"], m["id"]))
        except Exception as exc:  # noqa: BLE001 - any Cosmos failure: serve golden JSON
            log.warning("Cosmos read failed for %s, using JSON: %s", mid, exc)
            return self.fallback.moments(mid)

    def save_explanation(self, mid: str, explanation: dict, trace: list[dict], backend: str) -> str:
        doc_id = _doc_id(explanation["moment_id"], explanation["persona_key"], backend)
        try:
            self.expl_c.upsert_item({"id": doc_id, "match_id": mid, "backend": backend,
                                     "explanation": explanation, "trace": trace})
            return doc_id
        except Exception as exc:  # noqa: BLE001
            log.warning("Cosmos write failed, using JSON: %s", exc)
            return self.fallback.save_explanation(mid, explanation, trace, backend)


@lru_cache(maxsize=1)
def get_store() -> JsonStore | CosmosStore:
    endpoint = os.environ.get(ENDPOINT_ENV)
    if not endpoint:
        return JsonStore()
    try:
        return CosmosStore(endpoint, os.environ.get(DB_ENV, "tacticlens"))
    except Exception as exc:  # noqa: BLE001 - missing SDK or bad config: stay on JSON
        log.warning("Cosmos store unavailable, using JSON: %s", exc)
        return JsonStore()
