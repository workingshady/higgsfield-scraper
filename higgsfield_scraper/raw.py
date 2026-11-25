"""Raw response envelope: what was requested + the untouched JSON body. Saved to <run>/raw/."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Envelope:
    endpoint: str
    url: str
    status: int
    body: Any
    params: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def ok(self) -> bool:
        return self.status == 200 and isinstance(self.body, (dict, list))

    @property
    def filename(self) -> str:
        parts = [self.endpoint] + [f"{k}-{v}" for k, v in sorted(self.params.items()) if k not in ("with_localization",)]
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", "__".join(parts)) + ".json"

    def provenance(self) -> dict[str, Any]:
        return {"endpoint": self.endpoint, "url": self.url, "params": dict(self.params),
                "fetched_at": self.fetched_at.isoformat()}

    def to_dict(self) -> dict[str, Any]:
        return {"meta": {**self.provenance(), "status": self.status}, "body": self.body}

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / self.filename
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=4), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Envelope":
        d = json.loads(path.read_text(encoding="utf-8"))
        m = d["meta"]
        return cls(endpoint=m["endpoint"], url=m["url"], status=m["status"], body=d["body"],
                   params=m.get("params") or {}, fetched_at=datetime.fromisoformat(m["fetched_at"]))
