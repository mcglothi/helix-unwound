"""Bounded, explicit stored-memory reads. No session, baud, slot or write commands."""
from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass

from .protocol.client import Client

MEMORY_END = 0x10000
BLOB_START = 18
MAX_XML = 4 * 1024 * 1024


class StoredPresetError(ValueError):
    pass


@dataclass(frozen=True)
class StoredPreset:
    name_bytes: bytes
    blob: bytes
    xml: bytes

    @property
    def xml_sha256(self) -> str:
        return hashlib.sha256(self.xml).hexdigest()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.blob).hexdigest()


def _read_once(client: Client, deadline: float) -> StoredPreset:
    def read(address, length):
        if time.monotonic() >= deadline:
            raise StoredPresetError('Stored-preset read exceeded its time limit')
        return client.read_stored(address, length)

    name = read(0, BLOB_START)
    raw = bytearray()
    xml = bytearray()
    expected = None
    decoder = zlib.decompressobj()
    address = BLOB_START
    while address < MEMORY_END:
        chunk = read(address, min(128, MEMORY_END - address))
        raw.extend(chunk)
        address += len(chunk)
        if expected is None:
            expected = int.from_bytes(chunk[:4], 'big')
            if not 0 < expected <= MAX_XML:
                raise StoredPresetError('Stored-preset XML length is missing or exceeds the supported limit')
            chunk = chunk[4:]
        try:
            xml.extend(decoder.decompress(chunk, expected - len(xml) + 1))
        except zlib.error as exc:
            raise StoredPresetError('Stored preset contains invalid compressed data') from exc
        if len(xml) > expected:
            raise StoredPresetError('Stored-preset XML exceeds its declared length')
        if decoder.eof:
            if len(xml) != expected:
                raise StoredPresetError('Stored-preset XML length does not match its header')
            blob = bytes(raw[:len(raw) - len(decoder.unused_data)])
            content = bytes(xml)
            try:
                text = content.decode('utf-8-sig')
            except UnicodeDecodeError as exc:
                raise StoredPresetError('Stored preset XML must use supported UTF-8 encoding') from exc
            if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
                raise StoredPresetError('Stored-preset XML declarations are not supported')
            try:
                root = ET.fromstring(text)
            except ET.ParseError as exc:
                raise StoredPresetError('Stored preset is not valid XML') from exc
            if root.tag != 'ATF' or root.get('Dev') != '15':
                raise StoredPresetError('Stored XML is not a supported DSP PRO MK2 preset')
            return StoredPreset(name, blob, content)
    raise StoredPresetError('Stored preset has no complete compressed stream within memory bounds')


def read(client: Client, *, timeout: float = 60) -> StoredPreset:
    """Require two identical reads. This detects changes, not an atomic RAM snapshot."""
    deadline = time.monotonic() + timeout
    first = _read_once(client, deadline)
    second = _read_once(client, deadline)
    if first.name_bytes != second.name_bytes or first.blob != second.blob:
        raise StoredPresetError('Stored preset changed while reading; no backup was accepted. Retry when preset selection is stable.')
    return first


def save(path, preset: StoredPreset) -> None:
    """Publish a complete backup without replacing an existing file."""
    import os
    import tempfile
    from pathlib import Path
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.stored-preset-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(preset.blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # atomic create, fails if destination already exists
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
    finally:
        os.unlink(temporary)
