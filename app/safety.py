"""TrustyAI Guardrails — PII check via Orchestrator."""

from __future__ import annotations

import json
import logging
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import TRUSTYAI_ORCHESTRATOR_URL, TRUSTYAI_SHIELD_ID
from tracing import span

log = logging.getLogger(__name__)

_PII = {
    "email": {},
    "us-social-security-number": {},
    "credit-card": {},
}


def check_prompt(text: str) -> dict[str, Any]:
    """Return {ok, blocked, detail}. Blocks when PII detectors fire."""
    detector = TRUSTYAI_SHIELD_ID or "built-in-detector"
    with span("trustyai-shield", "TOOL", {"detector": detector, "chars": len(text)}):
        if not TRUSTYAI_ORCHESTRATOR_URL:
            return {"ok": True, "blocked": False, "skipped": True, "detail": "No orchestrator URL"}
        try:
            payload = {
                "content": text,
                "detectors": {detector: {"regex": dict(_PII)}},
            }
            data = json.dumps(payload).encode()
            req = Request(
                TRUSTYAI_ORCHESTRATOR_URL.rstrip("/") + "/api/v2/text/detection/content",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            ctx = ssl._create_unverified_context()
            with urlopen(req, timeout=60, context=ctx) as resp:
                result = json.loads(resp.read() or b"{}")
            detections = list(result.get("detections") or [])
            blocked = len(detections) > 0
            return {
                "ok": not blocked,
                "blocked": blocked,
                "skipped": False,
                "shield_id": detector,
                "detail": result,
            }
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            log.warning("TrustyAI check failed: %s", exc)
            return {"ok": True, "blocked": False, "skipped": True, "detail": str(exc)}
