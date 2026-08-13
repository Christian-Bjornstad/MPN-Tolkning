from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus


class AuditStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, result: EvidenceResult) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        path = self.root / f"{digest}.json"
        temporary = path.with_suffix(".json.tmp")
        payload = {
            "key": key,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "result": self._serialize(result),
        }
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def load_all(self) -> dict[str, EvidenceResult]:
        results: dict[str, EvidenceResult] = {}
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                results[str(payload["key"])] = self._deserialize(payload["result"])
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return results

    @staticmethod
    def _serialize(result: EvidenceResult) -> dict[str, Any]:
        return {
            "provider": result.provider,
            "status": result.status.value,
            "summary": result.summary,
            "url": result.url,
            "retryable": result.retryable,
            "expected_identity": result.expected_identity,
            "observed_identity": result.observed_identity,
            "screenshots": [str(path) for path in result.screenshots],
            "metadata": result.metadata,
        }

    @staticmethod
    def _deserialize(payload: dict[str, Any]) -> EvidenceResult:
        return EvidenceResult(
            provider=str(payload["provider"]),
            status=EvidenceStatus(str(payload["status"])),
            summary=str(payload.get("summary") or ""),
            url=str(payload.get("url") or ""),
            retryable=bool(payload.get("retryable", False)),
            expected_identity=str(payload.get("expected_identity") or ""),
            observed_identity=str(payload.get("observed_identity") or ""),
            screenshots=tuple(
                Path(value) for value in payload.get("screenshots") or []
            ),
            metadata=dict(payload.get("metadata") or {}),
        )
