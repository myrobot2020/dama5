from __future__ import annotations

import os
from typing import Any, Dict

import pytest
import requests

from tests._helpers import require_no_auth_or_skip


def test_index_status_contract(http: requests.Session, base_url: str) -> None:
    r = http.get(f"{base_url}/api/index_status", timeout=15)
    require_no_auth_or_skip(r)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert "exists" in data
    assert isinstance(data["exists"], bool)
    assert data.get("mode") in ("local_chroma", "vertex")


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "what did buddha say about water?", "book": "all", "k": 3, "use_llm": False},
        {"question": "hi", "book": "all", "k": 3, "use_llm": False},
    ],
)
def test_query_contract_smoke(http: requests.Session, base_url: str, payload: Dict[str, Any]) -> None:
    # Allow a long timeout: first request may cold-load embedding models.
    timeout = 300
    if os.environ.get("SMOKE_WITH_LLM", "").strip().lower() in ("1", "true", "yes", "on"):
        payload = dict(payload)
        payload["use_llm"] = True
        timeout = 600
    r = http.post(f"{base_url}/api/query", json=payload, timeout=timeout)
    require_no_auth_or_skip(r)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict)
    assert "chunks" in data and isinstance(data["chunks"], list)
    assert "answer" in data and isinstance(data["answer"], str)
    assert "used_llm" in data and isinstance(data["used_llm"], bool)

