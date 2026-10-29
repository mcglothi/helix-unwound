"""Local media library: photos of the cab, devices, wiring, and saved stock images.

Files live in <data_dir>/media and never leave the machine unless the user shares them.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
           "image/heic": ".heic", "image/heif": ".heif"}  # no SVG: it can carry script
MAX_BYTES = 25 * 1024 * 1024


class MediaItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    filename: str
    content_type: str
    size: int
    caption: str = ""
    tags: list[str] = Field(default_factory=list)
    created: float = Field(default_factory=time.time)

    @property
    def url(self) -> str:
        return f"/api/media/{self.id}"


class Library:
    def __init__(self, data_dir: Path):
        self.root = data_dir / "media"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_file = self.root / "index.json"

    def _load(self) -> list[MediaItem]:
        if not self.index_file.exists():
            return []
        return [MediaItem.model_validate(x) for x in json.loads(self.index_file.read_text())]

    def _save(self, items: list[MediaItem]) -> None:
        from .durable import atomic_write
        atomic_write(self.index_file, json.dumps([i.model_dump() for i in items], indent=2))

    def list(self) -> list[dict]:
        return [i.model_dump() | {"url": i.url} for i in sorted(self._load(), key=lambda i: -i.created)]

    def add(self, data: bytes, filename: str, content_type: str, caption: str = "") -> dict:
        if content_type not in ALLOWED:
            raise ValueError(f"unsupported file type {content_type!r}; images only")
        if len(data) > MAX_BYTES:
            raise ValueError("file larger than 25 MB")
        item = MediaItem(filename=Path(filename).name or "image", content_type=content_type, size=len(data), caption=caption)
        (self.root / (item.id + ALLOWED[content_type])).write_bytes(data)
        self._save(self._load() + [item])
        return item.model_dump() | {"url": item.url}

    def path(self, mid: str) -> tuple[Path, str]:
        for i in self._load():
            if i.id == mid:
                return self.root / (i.id + ALLOWED[i.content_type]), i.content_type
        raise KeyError(f"no media {mid!r}")

    def update(self, mid: str, caption: str | None, tags: list[str] | None) -> dict:
        items = self._load()
        for i in items:
            if i.id == mid:
                if caption is not None:
                    i.caption = caption
                if tags is not None:
                    i.tags = tags
                self._save(items)
                return i.model_dump() | {"url": i.url}
        raise KeyError(f"no media {mid!r}")

    def delete(self, mid: str) -> None:
        items = self._load()
        keep = [i for i in items if i.id != mid]
        for i in items:
            if i.id == mid:
                (self.root / (i.id + ALLOWED[i.content_type])).unlink(missing_ok=True)
        self._save(keep)
