"""Automated seat measurement: one output at a time, pink noise + REW RTA averaging.

The owner starts a run for a set of outputs at a seat and moves the microphone slowly around
the head position (moving-mic method) while HelixTune, for each output in turn:

1. isolates it: one validated engine edit mutes every other output and unmutes the target
   if this run muted it earlier (no link-group propagation, no other tune changes);
2. waits a settle time, then resets REW's RTA averaging;
3. averages for the chosen time, then has REW save the RTA trace as a measurement;
4. finds that measurement by its new UUID and imports it, tagged with this output, the seat,
   the exact isolated tune and the currently recorded drivers (magnitude only).

Afterwards, and also after Stop or an error, the generator and RTA are stopped and the mute
changes the run made are undone, but only while the connection is still trustworthy. A run
record on disk lets a restart report a run that was interrupted (crash, power cut) with
outputs still muted by it.

REW control uses fixed loopback endpoints only. Starting sweeps needs REW Pro; the generator
and RTA used here do not (tested 2026-10-18, REW 5.40 beta 135).
"""
from __future__ import annotations

import json
import threading
import time
import uuid as uuidlib
from dataclasses import asdict, dataclass, field
from typing import Callable, Literal

import httpx
import numpy as np

from . import durable, measurements
from .proposals import fingerprint
from .rew import RewClient, RewError

RUN_FILE = "measure_run.json"
Phase = Literal["starting", "isolating", "settling", "averaging", "saving", "importing", "restoring", "done"]
Status = Literal["running", "done", "stopped", "failed"]


class MeasureError(RuntimeError):
    pass


class RewControl:
    """Bounded, loopback-only REW control: generator and RTA commands for this workflow only."""

    def __init__(self, port: int = 4735, *, transport=None):
        if not 1024 <= port <= 65535:
            raise RewError('REW port must be between 1024 and 65535')
        self.port = port
        self.transport = transport

    def _send(self, method: str, path: str, body=None):
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{self.port}', timeout=3, follow_redirects=False,
                              trust_env=False, transport=self.transport) as client:
                response = client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise RewError('Cannot reach REW. Start it with its API enabled and check the port.') from exc
        if response.status_code == 401:
            raise RewError(f'REW refused {path}: {response.text[:200]}')
        if response.status_code not in (200, 202):
            raise RewError(f'REW returned HTTP {response.status_code} for {path}')
        if len(response.content) > 1024 * 1024:
            raise RewError('REW response is too large')
        return response.json() if response.content else None

    def prepare(self, level_dbfs: float, play_noise: bool) -> None:
        # Live REW 5.40b135: the RTA only processes input while its window is open ("enabled");
        # otherwise "Save current" fails with "Nothing to save".
        status = self._send('GET', '/rta/status')
        if not (isinstance(status, dict) and status.get('enabled')):
            raise RewError("Open REW's RTA window (RTA button) so it can analyse the microphone, then start again")
        # RTA: average until told otherwise; a run resets averaging for each output.
        self._send('PUT', '/rta/configuration', {'averaging': 'Forever'})
        if play_noise:
            self._send('POST', '/generator/signal', {'signal': 'pinknoise'})
            self._send('PUT', '/generator/signals/pinknoise/configuration', {'type': 'full-range'})
            self._send('POST', '/generator/level', {'value': float(level_dbfs), 'unit': 'dBFS'})

    def generator(self, play: bool) -> None:
        self._send('POST', '/generator/command', {'command': 'Play' if play else 'Stop'})

    def rta(self, command: Literal['Start', 'Stop', 'Reset averaging', 'Save current']) -> None:
        self._send('POST', '/rta/command', {'command': command})

    def rta_average(self) -> tuple[np.ndarray, np.ndarray]:
        """The RTA's current average (SPL) without saving a REW measurement."""
        data = self._send('GET', '/rta/captured-data?unit=SPL')
        if not isinstance(data, dict) or 'magnitude' not in data:
            raise RewError('REW has no RTA data yet; is the RTA window open and running?')
        spl = RewClient._array(data['magnitude'])
        start, step = float(data.get('startFreq', 0)), float(data.get('freqStep', 0))
        if step <= 0 or len(spl) < 16:
            raise RewError('Unsupported REW RTA data spacing')
        return start + step * np.arange(len(spl)), spl

    def measurement_uuids(self) -> set[str]:
        rows = self._send('GET', '/measurements')
        if isinstance(rows, dict):
            rows = list(rows.values())
        if not isinstance(rows, list):
            raise RewError('Unsupported REW measurement list format')
        return {str(r.get('uuid')) for r in rows if isinstance(r, dict) and r.get('uuid')}


@dataclass
class RunState:
    id: str
    outputs: list[str]
    seat: str
    seconds: float
    settle_s: float
    level_dbfs: float
    source: Literal['rew', 'external']
    status: Status = 'running'
    phase: Phase = 'starting'
    current: str | None = None
    step: int = 0
    remaining_s: float = 0.0
    captures: list[dict] = field(default_factory=list)
    error: str | None = None
    # output -> mute state before the run; outputs whose mute the run changed (workflow-owned)
    original_mutes: dict[str, bool] = field(default_factory=dict)
    changed: list[str] = field(default_factory=list)
    restored: bool = False
    started_at: float = field(default_factory=time.time)
    kind: Literal['measure', 'align'] = 'measure'
    # delay changes the run owns (time alignment), restored like mutes
    original_delays: dict[str, float] = field(default_factory=dict)
    delay_changed: list[str] = field(default_factory=list)
    align: dict | None = None          # parameters, per-step results and the outcome

    def view(self) -> dict:
        return asdict(self)


class MeasureRun:
    """One run. execute() is synchronous (tests); start() runs it on a thread."""

    def __init__(self, engine, state: RunState, rew: RewControl, reader: RewClient, *,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.engine, self.state, self.rew, self.reader = engine, state, rew, reader
        self.sleep, self.clock = sleep, clock
        self._stop = threading.Event()
        self._expected_revision: int | None = None
        self._epoch = engine._connection_epoch
        # Admission gate: stays True until cleanup, the final record and any interrupted-run
        # publication are complete (Codex review of 2d92b31).
        self.active = True


    # -- persistence (survives process death) ---------------------------------------------
    def _save(self) -> None:
        durable.atomic_write(self.engine.data_dir / RUN_FILE, json.dumps(self.state.view(), indent=2))

    def stop(self) -> None:
        self._stop.set()

    # -- checks -----------------------------------------------------------------------------
    def _check_unchanged(self) -> None:
        e = self.engine
        if self._stop.is_set():
            raise MeasureError('Stopped')
        if e._connection_epoch != self._epoch or e.client is None:
            raise MeasureError('The DSP connection changed during the run')
        if e.device.needs_reconnect or e.device.sync_state != 'synchronized':
            raise MeasureError('The DSP is no longer synchronized')
        if self._expected_revision is not None and e.revision != self._expected_revision:
            raise MeasureError('The tune or workstation changed during the run (another edit was made)')

    def _wait(self, seconds: float, phase: Phase) -> None:
        self.state.phase = phase
        end = self.clock() + seconds
        while True:
            left = end - self.clock()
            self.state.remaining_s = max(0.0, round(left, 1))
            if left <= 0:
                return
            self._check_unchanged()
            self.sleep(min(0.1, left))

    # -- steps ------------------------------------------------------------------------------
    def _isolate(self, target: str | set[str]) -> None:
        e, st = self.engine, self.state
        playing = {target} if isinstance(target, str) else set(target)
        target = "+".join(sorted(playing))
        self.state.phase = 'isolating'
        with e._lock:
            self._check_unchanged()
            plan = {ch.id: ch.id not in playing for ch in e.tune.channels
                    if ch.mute != (ch.id not in playing) and (ch.id not in playing or ch.id in st.changed)}
            # Recovery intent first: if the process dies after the DSP write but before the next
            # save, the record already names every output this step may have changed.
            for cid in plan:
                if cid not in st.changed:
                    st.changed.append(cid)
            self._save()

            def fn(t):
                for cid, mute in plan.items():
                    t.channel(cid).mute = mute
            if plan:
                e.edit('measure', f'measure run: isolate {target}', fn)
            self._expected_revision = e.revision
        self._save()

    def _capture(self, target: str) -> None:
        e, st = self.engine, self.state
        before = self.rew.measurement_uuids()
        self.rew.rta('Reset averaging')
        self._wait(st.seconds, 'averaging')
        st.phase = 'saving'
        self._check_unchanged()
        self.rew.rta('Save current')
        new: set[str] = set()
        for _ in range(50):
            self._check_unchanged()                     # Stop/drift stay responsive while waiting
            new = self.rew.measurement_uuids() - before
            if new:
                break
            self.sleep(0.1)
        if len(new) != 1:
            raise MeasureError('REW did not save exactly one new RTA measurement')
        uid = next(iter(new))
        st.phase = 'importing'
        self._check_unchanged()
        preview, arrays = self.reader.capture(uid)
        with e._lock:
            self._check_unchanged()
            tune = e.tune.model_copy(deep=True)            # the exact isolated tune during capture
            context = {'kind': 'measure_run', 'run': st.id, 'step': st.step, 'output': target,
                       'connection_epoch': e._connection_epoch, 'revision': e.revision,
                       'applied_image': fingerprint(sorted((a, w.hex()) for a, w in (e.applied_image or {}).items())),
                       'design': fingerprint(e.design.model_dump(mode='json')),
                       'method': 'pink noise + RTA averaging (moving mic); magnitude only, no phase or timing',
                       'signal': {'source': st.source, 'level_dbfs': st.level_dbfs if st.source == 'rew' else None,
                                  'seconds': st.seconds}}
            m = measurements.Measurement(
                name=f"{target} {preview['summary']['title']}", kind='rta', channels=[target], seat=st.seat,
                taken_at=time.time(), source='Measured by HelixTune run (REW RTA)', notes='',
                tune=tune, import_provenance={'provider': 'REW', 'port': self.reader.port, **preview,
                                              'capture_context': context},
                freqs=arrays['freqs'], spl=arrays['spl'], phase=None)
            e.measurements.save(m)
            e.attest_measurement(m.id, 'owner', reason=f'Measured in run {st.id}: drivers as currently installed')
            e.revision += 1
            e._log('measure', f'captured {target} at {st.seat} (run {st.id})')
            self._expected_revision = e.revision
        st.captures.append({'output': target, 'measurement_id': m.id, 'rew_uuid': uid})
        self._save()

    def _restore(self) -> None:
        """Undo only the run's own mute changes, and only on a trustworthy connection."""
        e, st = self.engine, self.state
        st.phase = 'restoring'
        if not st.changed and not st.delay_changed:
            st.restored = True
            return
        with e._lock:
            trustworthy = (e.client is not None and e._connection_epoch == self._epoch
                           and not e.device.needs_reconnect and e.device.sync_state == 'synchronized')
            if not trustworthy:
                st.error = (st.error or '') + ' Mutes/delays were NOT restored: the connection is not trustworthy; ' \
                            f'outputs {", ".join(sorted(set(st.changed) | set(st.delay_changed)))} may still differ.'
                return
            # Another edit during the run: its mutes can no longer be told apart from the owner's.
            if self._expected_revision is not None and e.revision != self._expected_revision:
                st.error = (st.error or '') + ' Mutes were NOT restored automatically because the workstation ' \
                            'was changed during the run; review outputs ' + ", ".join(st.changed) + ' and restore or keep them.'
                return

            def fn(t):
                for cid in st.changed:
                    t.channel(cid).mute = st.original_mutes[cid]
                for cid in st.delay_changed:
                    t.channel(cid).delay_ms = st.original_delays[cid]
            e.edit('measure', f'measure run {st.id}: restore mutes/delays', fn)
        st.restored = True

    def execute(self) -> RunState:
        e, st = self.engine, self.state
        noise = st.source == 'rew'
        final: Status = 'failed'
        started_noise = False
        try:
            with e._lock:
                self._check_unchanged()
                st.original_mutes = {ch.id: ch.mute for ch in e.tune.channels}
                self._expected_revision = e.revision
            self._save()
            self.rew.prepare(st.level_dbfs, noise)

            def begin_noise():
                nonlocal started_noise
                # Noise only after the first isolation, never through every speaker.
                if noise:
                    started_noise = True                # before Play: a timed-out Play still gets a Stop
                    self.rew.generator(True)
                self.rew.rta('Start')
            self._body(begin_noise)
            final = 'done'
        except MeasureError as exc:
            final = 'stopped' if self._stop.is_set() else 'failed'
            st.error = str(exc)
        except Exception as exc:                                  # REW, engine or I/O failure
            final = 'failed'
            st.error = f'{type(exc).__name__}: {exc}'
        finally:
            for action in ((lambda: self.rew.generator(False)) if started_noise else None, lambda: self.rew.rta('Stop')):
                if action is None:
                    continue
                try:
                    action()
                except Exception as exc:
                    st.error = (st.error or '') + f' Could not stop REW cleanly ({exc}); stop it in REW.'
            try:
                self._restore()
            except Exception as exc:
                st.error = (st.error or '') + f' Restoring mutes/delays failed ({exc}).'
            if final == 'done':
                try:
                    self._finish()
                except Exception as exc:
                    st.error = (st.error or '') + f' Could not prepare the result ({exc}).'
            with e._lock:                                   # admission takes the same lock
                st.phase, st.current, st.remaining_s = 'done', None, 0.0
                st.status = final
                try:
                    self._save()
                finally:
                    if (st.changed or st.delay_changed) and not st.restored:
                        e.interrupted_run = st.view()       # owner decides: restore or keep
                    self.active = False
        return st


    def _body(self, begin_noise) -> None:
        st = self.state
        for i, target in enumerate(st.outputs):
            st.step, st.current = i, target
            self._isolate(target)
            if i == 0:
                begin_noise()
            self._wait(st.settle_s, 'settling')
            self._capture(target)

    def _finish(self) -> None:
        """Hook for results after a completed, restored run."""


def band_level_db(freqs: np.ndarray, spl: np.ndarray, lo: float, hi: float, points: int = 48) -> float:
    """Power mean (dB) of the spectrum over [lo, hi], sampled on a log grid so each octave
    counts equally regardless of the FFT's linear bin spacing."""
    grid = np.geomspace(lo, hi, points)
    level = np.interp(grid, freqs, spl)
    return float(10 * np.log10(np.mean(10 ** (level / 10))))


class AlignRun(MeasureRun):
    """Crossover summing alignment for one pair: play reference + adjusted output together, step
    the adjusted output's delay (and any carried outputs) across about one period of the crossover
    frequency, score how fully the pair sums through the crossover band, then restore everything
    and offer the best delay as a proposal. The microphone stays still at the head position."""

    def _set_delays(self, offset_ms: float) -> None:
        e, st = self.engine, self.state
        a = st.align
        with e._lock:
            self._check_unchanged()
            wanted = {cid: round(st.original_delays[cid] + offset_ms, 4) for cid in [a['adjust'], *a['carry']]}
            for cid in wanted:                                   # recovery intent before the DSP write
                if cid not in st.delay_changed:
                    st.delay_changed.append(cid)
            self._save()
            e.edit('measure', f"alignment run: {a['adjust']} {offset_ms:+.3f} ms",
                   lambda t: [setattr(t.channel(c), 'delay_ms', v) for c, v in wanted.items()])
            self._expected_revision = e.revision
        self._save()

    MIN_SIGNAL_DB = 10.0         # pair must play this far above the all-muted noise floor

    def _band(self) -> float:
        a, st = self.state.align, self.state
        self._wait(st.settle_s, 'settling')
        self.rew.rta('Reset averaging')
        self._wait(st.seconds, 'averaging')
        self._check_unchanged()
        freqs, spl = self.rew.rta_average()
        return round(band_level_db(freqs, spl, a['fc'] / 2, a['fc'] * 2), 2)

    def _body(self, begin_noise) -> None:
        st = self.state
        a = st.align
        with self.engine._lock:
            st.original_delays = {c: self.engine.tune.channel(c).delay_ms for c in [a['adjust'], *a['carry']]}
        # Noise floor first, with every output muted (a dead source or low volume must not
        # produce a "best" delay from cabin noise - found live 2026-10-19).
        st.current = 'noise floor'
        self._isolate(set())
        begin_noise()
        a['floor_db'] = self._band()
        st.current = f"{a['reference']}+{a['adjust']}"
        self._isolate({a['reference'], a['adjust']})
        for i, off in enumerate(a['offsets']):
            st.step = i
            self._set_delays(off)
            a['results'].append({'offset_ms': off, 'band_db': self._band()})
            self._save()
        # Judged on the loudest step: the sweep legitimately passes through a deep cancellation.
        loudest = max(r['band_db'] for r in a['results'])
        if loudest < a['floor_db'] + self.MIN_SIGNAL_DB:
            raise MeasureError(f"The pair was only {loudest - a['floor_db']:.1f} dB above the cabin noise "
                               f"(need {self.MIN_SIGNAL_DB:g}); is the pink noise playing and the volume up?")
        # Repeat the starting delay: the difference shows how repeatable the measurement is.
        self._set_delays(0.0)
        a['repeat_db'] = self._band()
        self._save()

    def _finish(self) -> None:
        e, st, a = self.engine, self.state, self.state.align
        if not st.restored or not a['results']:
            return
        best = max(a['results'], key=lambda r: r['band_db'])
        current = min(a['results'], key=lambda r: abs(r['offset_ms']))
        a['best_offset_ms'], a['gain_db'] = best['offset_ms'], round(best['band_db'] - current['band_db'], 2)
        a['spread_db'] = round(max(r['band_db'] for r in a['results']) - min(r['band_db'] for r in a['results']), 2)
        a['repeatability_db'] = round(abs(a.get('repeat_db', current['band_db']) - current['band_db']), 2)
        threshold = max(0.5, 2 * a['repeatability_db'])
        if abs(best['offset_ms']) < 1e-9:
            a['outcome'] = 'Already aligned: the current delay summed best. No change proposed.'
            return
        if a['gain_db'] < threshold:
            a['outcome'] = (f"Best gain {a['gain_db']} dB is within measurement noise (needs {threshold:.2f} dB: "
                            f"repeat of the starting delay differed by {a['repeatability_db']} dB). No change proposed; "
                            "try longer averaging or a quieter cabin.")
            return
        a['proposal_id'] = e.propose_measured_alignment(st, best['offset_ms'])
        a['outcome'] = (f"Best sum with {a['adjust']} {best['offset_ms']:+.3f} ms: crossover band "
                        f"+{a['gain_db']} dB vs now. Review the proposal to apply it.")


def new_align_state(reference: str, adjust: str, carry: list[str], seat: str, fc: float, offsets: list[float],
                    seconds: float, settle_s: float, level_dbfs: float, source: Literal['rew', 'external']) -> RunState:
    st = new_state([reference, adjust], seat, seconds, settle_s, level_dbfs, source)
    st.kind = 'align'
    st.align = {'reference': reference, 'adjust': adjust, 'carry': carry, 'fc': fc, 'offsets': offsets,
                'results': [], 'method': 'RTA pink-noise sum of the pair over fc/2..2fc (magnitude); mic held still'}
    return st


def new_state(outputs: list[str], seat: str, seconds: float, settle_s: float, level_dbfs: float,
              source: Literal['rew', 'external']) -> RunState:
    return RunState(id=uuidlib.uuid4().hex[:10], outputs=outputs, seat=measurements.normalise_seat(seat),
                    seconds=seconds, settle_s=settle_s, level_dbfs=level_dbfs, source=source)
