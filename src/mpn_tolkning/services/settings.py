from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


REQUIRED_PROVIDERS = [
    "CALR-ETdb",
    "MTBP",
    "Franklin",
    "ClinVar",
    "OncoKB",
    "COSMIC",
]


@dataclass
class AppSettings:
    selected_providers: list[str] = field(default_factory=lambda: list(REQUIRED_PROVIDERS))
    browser_background: bool = True
    request_delay_min_ms: int = 10_000
    request_delay_max_ms: int = 20_000
    navigation_timeout_ms: int = 45_000
    analysis_timeout_ms: int = 1_200_000
    reference_build: str = "GRCh37"
    output_directory: str = ""
    cosmic_email: str = ""
    oncokb_email: str = ""
    franklin_email: str = ""
    mtbp_email: str = ""
    artifact_rules: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def default_path() -> Path:
        profile = Path(os.environ.get("USERPROFILE") or Path.home())
        return profile / ".mpn-tolkning" / "config.json"

    @classmethod
    def load(cls, path: Path | None = None) -> AppSettings:
        target = Path(path) if path is not None else cls.default_path()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return cls()
        if not isinstance(payload, dict):
            return cls()
        allowed = {item.name for item in fields(cls)}
        values = {key: value for key, value in payload.items() if key in allowed}
        try:
            settings = cls(**values)
        except TypeError:
            return cls()
        settings._normalize()
        return settings

    def save(self, path: Path | None = None) -> Path:
        target = Path(path) if path is not None else self.default_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._normalize()
        payload = {
            key: value
            for key, value in asdict(self).items()
            if not key.lower().endswith("_password")
        }
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def _normalize(self) -> None:
        self.selected_providers = [
            str(provider)
            for provider in self.selected_providers
            if str(provider).strip()
        ]
        self.request_delay_min_ms = max(0, int(self.request_delay_min_ms))
        self.request_delay_max_ms = max(
            self.request_delay_min_ms,
            int(self.request_delay_max_ms),
        )
        self.reference_build = "GRCh37"
