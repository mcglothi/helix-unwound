"""Read-only REW adapter. Only fixed loopback GET endpoints are available."""
from __future__ import annotations
import base64
from collections import Counter
import binascii
import math
import re
from uuid import UUID
import httpx
import numpy as np
from .proposals import fingerprint


class RewError(ValueError):
    pass


class RewClient:
    def __init__(self, port: int = 4735, *, transport=None):
        if not 1024 <= port <= 65535:
            raise RewError('REW port must be between 1024 and 65535')
        self.port = port
        self.transport = transport

    def _get(self, path: str, params: dict | None = None):
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{self.port}', timeout=3,
                              follow_redirects=False, trust_env=False, transport=self.transport) as client:
                with client.stream('GET', path, params=params) as response:
                    if response.status_code != 200:
                        raise RewError(f'REW returned HTTP {response.status_code}; check its API and selected measurement')
                    raw = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        raw.extend(chunk)
                        if len(raw) > 8 * 1024 * 1024:
                            raise RewError('REW response is too large')
                    import json
                    return json.loads(raw)
        except (httpx.HTTPError, UnicodeError) as exc:
            raise RewError('Cannot reach REW. Start its local API in REW preferences and check the port.') from exc
        except (ValueError, TypeError) as exc:
            if isinstance(exc, RewError): raise
            raise RewError('REW returned an unsupported or invalid response') from exc

    def discover(self) -> dict:
        doc = self._get('/doc.json')
        paths = doc.get('paths', {}) if isinstance(doc, dict) else {}
        if not isinstance(paths, dict):
            raise RewError('Unsupported REW API description')
        frequency_paths = [p for p in paths if re.fullmatch(r'/measurements/\{[^}]+\}/frequency-response', p)]
        if '/measurements' not in paths or not frequency_paths:
            raise RewError('This REW API does not advertise measurement listing and frequency-response reads')
        records = self._get('/measurements')
        if isinstance(records, dict) and all(str(key).isdigit() for key in records):
            records = list(records.values())
        if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
            raise RewError('Unsupported REW measurement list format')
        measurements = []
        for row in records:
            try: uid = str(UUID(row.get('uuid', '')))
            except (ValueError, TypeError, AttributeError):
                raise RewError('REW measurement is missing a stable UUID') from None
            measurements.append({'uuid': uid, 'title': str(row.get('title') or 'Untitled'),
                                 'date': str(row.get('date') or ''), 'notes': str(row.get('notes') or '')})
        counts = Counter(row['uuid'] for row in measurements)
        for row in measurements:
            row['ambiguous'] = counts[row['uuid']] > 1
            row['fingerprint'] = fingerprint(row)
        return {'port': self.port, 'api_version': str(doc['info'].get('version', 'unknown') if isinstance(doc.get('info'), dict) else 'unknown'),
                'read_only': True, 'measurements': measurements}

    @staticmethod
    def _array(encoded) -> np.ndarray:
        try:
            if not isinstance(encoded, str) or len(encoded) > 1100000:
                raise ValueError()
            raw = base64.b64decode(encoded, validate=True)
            if not raw or len(raw) % 4 or len(raw) > 800000:
                raise ValueError()
            values = np.frombuffer(raw, dtype='>f4').astype(float)
            if not np.isfinite(values).all(): raise ValueError()
            return values
        except (ValueError, binascii.Error):
            raise RewError('REW returned an invalid Base64 float array') from None

    def capture(self, uid: str) -> tuple[dict, dict]:
        try: uid = str(UUID(uid))
        except (ValueError, TypeError, AttributeError): raise RewError('Use a REW measurement UUID') from None
        listing = self.discover()
        matches = [m for m in listing['measurements'] if m['uuid'] == uid]
        if len(matches) != 1 or matches[0]['ambiguous']:
            raise RewError('REW measurement is missing or its UUID is duplicated; keep one copy loaded in REW')
        summary = matches[0]
        data = self._get(f'/measurements/{uid}/frequency-response', {'unit': 'SPL'})
        if not isinstance(data, dict): raise RewError('Unsupported REW frequency response')
        if data.get('unit', 'SPL') not in ('SPL', 'dB SPL'):
            raise RewError('REW did not return SPL magnitude data')
        magnitude = self._array(data.get('magnitude'))
        phase = self._array(data['phase']) if data.get('phase') else None
        if len(magnitude) < 2 or np.max(np.abs(magnitude)) > 300 or (phase is not None and len(phase) != len(magnitude)):
            raise RewError('REW response has invalid magnitudes or mismatched phase data')
        try:
            start, ppo, step = float(data['startFreq']), float(data.get('ppo', 0) or 0), float(data.get('freqStep', 0) or 0)
            if not all(math.isfinite(v) for v in (start, ppo, step)) or start < 0:
                raise ValueError()
            if ppo > 0 and step <= 0:
                with np.errstate(over='raise', invalid='raise'):
                    freqs = start * np.exp2(np.arange(len(magnitude)) / ppo)
            elif step > 0 and ppo <= 0:
                freqs = start + step * np.arange(len(magnitude))
            else: raise ValueError()
            if not np.isfinite(freqs).all() or np.any(np.diff(freqs) <= 0): raise ValueError()
        except (ValueError, KeyError, TypeError, FloatingPointError):
            raise RewError('REW frequency spacing is invalid or unsupported') from None
        positive = freqs > 0
        if not positive.all():
            freqs, magnitude = freqs[positive], magnitude[positive]
            phase = phase[positive] if phase is not None else None
        if len(freqs) < 2:
            raise RewError('REW capture has too few positive-frequency points')
        # Refuse source changes during the multi-request read; never silently switch rows.
        after = self.discover()['measurements']
        same = [row for row in after if row['uuid'] == uid]
        if len(same) != 1 or same[0] != summary:
            raise RewError('REW measurement changed while reading; refresh and try again')
        payload = {'port': self.port, 'summary': summary, 'response': data}
        preview = {'port': self.port, 'summary': summary, 'fingerprint': fingerprint(payload), 'points': len(freqs),
                   'frequency_range_hz': [float(freqs[0]), float(freqs[-1])], 'has_phase': phase is not None,
                   'smoothing': data.get('smoothing', 'unknown'), 'unit': 'SPL'}
        arrays = {'freqs': freqs.tolist(), 'spl': magnitude.tolist(), 'phase': phase.tolist() if phase is not None else None}
        return preview, arrays
