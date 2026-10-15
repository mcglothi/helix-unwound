"""Loaders for the per-model files shipped in PC-Tool's deviceFiles/.

*.at01  qCompress()'d SigmaStudio parameter header: 4-byte big-endian length + zlib
        of `#define NAME VALUE` lines. Gives every DSP parameter's RAM address.
*.AF1   hex text, `$VR1` header, then 2-byte register-init pairs followed by
        4-byte words (DSP program image). Parsed here only as raw bytes.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

_DEFINE = re.compile(r"^#define\s+(\S+)\s+(\S+)\s*$")
_HEX = re.compile(r"0x([0-9A-Fa-f]{2})")


def q_uncompress(data: bytes) -> bytes:
    expected = int.from_bytes(data[:4], "big")
    out = zlib.decompress(data[4:])
    if len(out) != expected:
        raise ValueError(f"qUncompress length mismatch: header {expected}, got {len(out)}")
    return out


@dataclass
class ParamMap:
    header: dict[str, str] = field(default_factory=dict)
    params: dict[str, int] = field(default_factory=dict)

    @property
    def safeload_base(self) -> int:
        return int(self.header["SLADD"])

    def addr(self, name: str) -> int:
        return self.params[name]

    def find(self, pattern: str) -> dict[str, int]:
        rx = re.compile(pattern)
        return {k: v for k, v in self.params.items() if rx.search(k)}

    def name_at(self, address: int) -> list[str]:
        return [k for k, v in self.params.items() if v == address]


def parse_param_header(text: str) -> ParamMap:
    pm = ParamMap()
    for line in text.splitlines():
        m = _DEFINE.match(line.strip())
        if not m:
            continue
        name, value = m.groups()
        if name.startswith("MOD_") and name.endswith("_ADDR"):
            pm.params[name[4:-5]] = int(value)
        else:
            pm.header[name] = value
    return pm


def load_at01(path: str | Path) -> ParamMap:
    return parse_param_header(q_uncompress(Path(path).read_bytes()).decode("ascii"))


@dataclass
class ProgramImage:
    version: str
    register_init: list[tuple[int, int]]  # (byte, byte) pairs as shipped
    words: list[bytes]                    # 4-byte words


def load_af1(path: str | Path) -> ProgramImage:
    lines = Path(path).read_text("ascii").replace("\r", "\n").split("\n")
    lines = [ln for ln in (s.strip() for s in lines) if ln]
    version = lines[0].lstrip("$")
    pairs: list[tuple[int, int]] = []
    words: list[bytes] = []
    for ln in lines[1:]:
        vals = [int(h, 16) for h in _HEX.findall(ln)]
        if len(vals) == 2:
            pairs.append((vals[0], vals[1]))
        elif len(vals) == 4:
            words.append(bytes(vals))
        elif vals:
            raise ValueError(f"unexpected AF1 line: {ln!r}")
    return ProgramImage(version=version, register_init=pairs, words=words)
