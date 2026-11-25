"""Raw response envelope: what was requested + the untouched JSON body. Saved to <run>/raw/."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_NAME = 140


def _short_hash(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def _saved_url(path: Path):
    try:
        with path.open(encoding="utf-8") as f:
            head = f.read(4096)
        m = re.search(r'"url":\s*"([^"]+)"', head)
        return m.group(1) if m else None
    except OSError:
        return None


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
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", "__".join(parts))
        if len(name) > MAX_NAME:                     # long cursors/ids: keep it readable + unique (Windows path limit)
            name = f"{name[:MAX_NAME - 12]}__{_short_hash(self.url)}"
        return name + ".json"

    def provenance(self) -> dict[str, Any]:
        return {"endpoint": self.endpoint, "url": self.url, "params": dict(self.params),
                "fetched_at": self.fetched_at.isoformat()}

    def to_dict(self) -> dict[str, Any]:
        return {"meta": {**self.provenance(), "status": self.status}, "body": self.body}

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / self.filename
        if path.exists() and _saved_url(path) not in (None, self.url):
            # same endpoint+params but a different URL (e.g. /items/{id} details): never overwrite another response
            path = path.with_name(f"{path.stem}__{_short_hash(self.url)}.json")
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=4), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Envelope":
        d = json.loads(path.read_text(encoding="utf-8"))
        m = d["meta"]
        return cls(endpoint=m["endpoint"], url=m["url"], status=m["status"], body=d["body"],
                   params=m.get("params") or {}, fetched_at=datetime.fromisoformat(m["fetched_at"]))
