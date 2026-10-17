"""The engine: single owner of the tune, the device connection and history.

UI, HTTP API and MCP tools all call into one Engine instance, so a person and an
agent always see and change the same state.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from . import afpx, autotune, equipment, mapping, measurements, safety, targets
from . import protection_provenance as provenance
from . import workstation
from .proposals import Proposal, ProposalConflict, ProposalContext, fingerprint
from .devicefile import ParamMap
from .model import Tune, Role
from .protocol import commands
from .protocol.client import Client


class EngineError(RuntimeError):
    pass


class OutputSetupConflict(EngineError):
    pass


class SnapshotExists(EngineError):
    def __init__(self, name: str):
        super().__init__(f"a scene named {name!r} already exists; choose another name (the owner may overwrite)")
        self.name = name


class NoTrustedAnchor(EngineError):
    """A solver needs a trustworthy reference and none exists; refuse instead of guessing."""


class MeasurementConflict(EngineError):
    pass


class SafetyRejected(EngineError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Event:
    ts: float
    source: str
    summary: str
    writes: int = 0


@dataclass
class DeviceState:
    kind: str = "none"              # none | emulator | serial
    port: str | None = None
    model: str | None = None
    model_type: int | None = None
    writes_enabled: bool = False
    baselined: bool = False         # completed writes acknowledged; not hardware readback verification
    sync_state: Literal["disconnected", "unsynchronized", "applying", "synchronized", "uncertain"] = "disconnected"
    last_error: str | None = None


@dataclass
class Engine:
    mapping: mapping.DeviceMapping
    data_dir: Path
    policy: safety.SafetyPolicy = field(default_factory=safety.SafetyPolicy)
    tune: Tune = field(default_factory=Tune)
    client: Client | None = None
    device: DeviceState = field(default_factory=DeviceState)
    applied_image: dict[int, bytes] | None = None
    history: list[Tune] = field(default_factory=list)
    redo_stack: list[Tune] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    pending_writes: int = 0
    revision: int = 0
    proposals: dict = field(default_factory=dict)
    ab: dict = field(default_factory=lambda: {"A": None, "B": None, "active": None})

    def __post_init__(self):
        self._lock = threading.RLock()
        self._connection_epoch = 0
        self._connection_nonce = secrets.token_hex(16)
        if not self.demo and (self.data_dir / '.helix-unwound-demo.json').exists():
            raise EngineError('Demo state cannot be opened by a hardware engine; use the demo command or a different directory')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "snapshots").mkdir(exist_ok=True)
        self.save_error = None
        try:
            saved, self.recovery_notice = workstation.load(self.data_dir)
        except workstation.RecoveryError as exc:
            raise EngineError(str(exc)) from exc
        cur = self.data_dir / "current.json"
        if saved:
            self.tune = saved.tune
            self.history = saved.history
            self.redo_stack = saved.redo
            self.ab = {"A": saved.ab.A, "B": saved.ab.B, "active": saved.ab.active}
        elif cur.exists():
            self.tune = Tune.model_validate_json(cur.read_text())
        self.measurements = measurements.Store(self.data_dir)
        tf = self.data_dir / "targets.json"
        self.user_targets: list[targets.Target] = (
            [targets.Target.model_validate(t) for t in json.loads(tf.read_text())] if tf.exists() else [])
        self.target_name = "Car preference"
        df = self.data_dir / "system.json"
        if df.exists():
            self.design = equipment.SystemDesign.model_validate_json(df.read_text())
            if equipment.normalize_ports(self.design):
                df.write_text(self.design.model_dump_json(indent=2))
        else:
            self.design = equipment.seed(self.tune)
            df.write_text(self.design.model_dump_json(indent=2))
        pol = self.data_dir / "safety.json"
        if pol.exists():
            raw = json.loads(pol.read_text())
            # fill settings added after this policy file was written, keeping the user's values
            for role, defaults in safety.DEFAULT_ROLES.items():
                r = raw.setdefault("roles", {}).setdefault(role.value, {})
                for k, v in defaults.model_dump().items():
                    r.setdefault(k, v)
            self.policy = safety.SafetyPolicy.model_validate(raw)
            pol.write_text(self.policy.model_dump_json(indent=2))
        else:
            pol.write_text(self.policy.model_dump_json(indent=2))
        protection_file = self.data_dir / "protections.json"
        self.protection_book = provenance.load(protection_file.read_text() if protection_file.exists() else None)
        self.protections = self.protection_book.effective()
        # Migrate current tune + equipment conservatively; snapshots never own these floors.
        self._persist_protections(self.tune)

    @classmethod
    def from_param_map(cls, pm: ParamMap, data_dir: Path) -> "Engine":
        return cls(mapping=mapping.DeviceMapping(pm), data_dir=data_dir)

    # ---- device -------------------------------------------------------------------

    @property
    def demo(self) -> bool:
        return bool(getattr(self.mapping, 'synthetic', False))

    def attach(self, client: Client, kind: str, port: str | None = None) -> DeviceState:
        with self._lock:
            if self.demo:
                from .emulator import EmulatedDevice
                if kind != 'emulator' or not isinstance(client.t, EmulatedDevice):
                    raise EngineError('Demo mode only connects to its in-memory emulator')
            from .emulator import EmulatedDevice
            if client.allow_writes and not isinstance(client.t, EmulatedDevice):
                raise EngineError("Physical writes are disabled pending captured-protocol validation; connect read-only or use the emulator")
            info = client.identify()
            if info.model_type != commands.PRO_MK2:
                raise EngineError(f"connected device is {info.model_string!r}, not a HELIX DSP PRO MK2")
            self._connection_epoch += 1
            self.client = client
            self.device = DeviceState(kind=kind, port=port, model=info.model_string,
                                      model_type=info.model_type, writes_enabled=client.allow_writes,
                                      sync_state="unsynchronized")
            self.applied_image = None
            self.pending_writes = 0
            self._log("engine", f"attached {kind} {port or ''} ({info.model_string})")
            return self.device

    def detach(self) -> None:
        with self._lock:
            client = self.client
            self.client = None
            self._connection_epoch += 1
            self.device = DeviceState()
            self.applied_image = None
            if client is not None:
                close = getattr(client.t, 'close', None)
                if callable(close):
                    try:
                        close()
                    except Exception as exc:
                        raise EngineError('Device detached, but closing the transport failed') from exc

    def overwrite_review(self) -> dict:
        with self._lock:
            return {'context': fingerprint({'tune': self.tune.model_dump(mode='json'),
                                            'device': self.device.__dict__, 'connection_epoch': self._connection_epoch,
                                            'boot': self._connection_nonce}),
                    'revision': self.revision, 'connection_epoch': self._connection_epoch,
                    'tune_name': self.tune.name, 'device': dict(self.device.__dict__),
                    'problems': self._check(self.tune), 'parameter_count': len(self.mapping.render(self.tune))}

    def push_full(self, confirm: str, expected_context: str | None = None) -> int:
        """Overwrite every managed parameter on the device with the current tune.

        Destroys whatever tune is on the device. Requires confirm == "OVERWRITE".
        """
        with self._lock:
            if confirm != "OVERWRITE":
                raise EngineError('full push overwrites the tune on the DSP; pass confirm="OVERWRITE"')
            self._require_writable()
            if expected_context is not None and expected_context != self.overwrite_review()['context']:
                raise EngineError('Tune or connection changed; review the overwrite again')
            tune = Tune.model_validate(self.tune.model_dump())
            problems = self._check(tune)
            if problems:
                raise SafetyRejected(problems)
            img = self.mapping.render(tune)
            self._persist_protections(tune)
            n = self._write_image(img, full=True)
            self._log("engine", "full push to device", n)
            return n

    def _require_writable(self):
        if self.client is None:
            raise EngineError("no device attached")
        if not self.device.writes_enabled:
            raise EngineError("device attached read-only; writes are disabled")

    def _write(self, changes: dict[int, bytes]) -> int:
        ops = mapping.coalesce(changes)
        for addr, data in ops:
            self.client.write_ram(addr, data)
        return len(ops)

    def _write_image(self, img: dict[int, bytes], *, full: bool = False) -> int:
        """Only a completely acknowledged update establishes a software baseline.

        A timeout may mean a write landed but its reply was lost. Do not retry a
        partial diff or claim rollback: stop incremental writes until a person
        deliberately overwrites the managed parameters again.
        """
        self._require_writable()
        if not full and not self.device.baselined:
            raise EngineError("device has no baseline; a confirmed full overwrite is required")
        changes = mapping.diff(None if full else self.applied_image, img)
        self.device.sync_state = "applying"
        self.device.baselined = False
        try:
            n = self._write(changes)
        except Exception as exc:
            self.applied_image = None
            self.pending_writes = len(img)
            self.device.sync_state = "uncertain"
            self.device.last_error = (
                "DSP update failed; device state is unknown. Incremental writes are paused. "
                "Review the tune and perform a confirmed full overwrite to resynchronize."
            )
            self.revision += 1
            self._log("engine", self.device.last_error)
            raise EngineError(self.device.last_error) from exc
        self.applied_image = img
        self.device.baselined = True
        self.device.sync_state = "synchronized"
        self.device.last_error = None
        self.pending_writes = 0
        return n

    # ---- tune changes ---------------------------------------------------------------

    def apply(self, new: Tune, source: str, summary: str) -> dict:
        """Validate and adopt a new tune; push the diff if the device is live."""
        with self._lock:
            new = Tune.model_validate(new.model_dump())  # re-run field validation
            problems = self._check(new, previous=self.tune)
            if problems:
                self._log(source, f"REJECTED: {summary}: {'; '.join(problems)}")
                raise SafetyRejected(problems)
            img = self.mapping.render(new)  # raises MappingError if unrepresentable
            self._persist_protections(new)
            writes = 0
            if self.client is not None and self.device.writes_enabled and self.device.baselined:
                writes = self._write_image(img)
            else:
                self.pending_writes = len(mapping.diff(self.applied_image, img))
            self.history.append(self.tune)
            self.history = self.history[-200:]
            self.redo_stack.clear()
            self.tune = new
            self._autosave()
            self._log(source, summary, writes)
            return {"ok": True, "writes": writes, "live": writes > 0}

    def output_setup_review(self, cid: str) -> dict:
        """Bind an output-assignment edit to current settings, equipment and send state."""
        with self._lock:
            channel = self.tune.channel(cid)
            context = fingerprint({
                "channel": channel, "design": self.design, "policy": self.policy,
                "protections": self.protections, "device": self.device.__dict__,
                "connection": self._connection_epoch, "boot": self._connection_nonce,
            })
            return {"channel": channel.model_dump(mode="json"), "context": context,
                    "live": bool(self.client and self.device.writes_enabled and self.device.baselined)}

    def save_output_setup(self, cid: str, *, name: str, role: Role, mix: dict[str, float],
                          expected_context: str, source: str) -> dict:
        with self._lock:
            if self.output_setup_review(cid)["context"] != expected_context:
                raise OutputSetupConflict("Output, equipment, protection rules or connection changed. Reopen the output editor and review the current settings.")
            def update(t):
                channel = t.channel(cid)
                channel.name, channel.role, channel.mix = name, role, mix
            return self.edit(source, f"{cid.upper()}: updated output name, role and input route", update)

    def edit(self, source: str, summary: str, fn) -> dict:
        """Copy the tune, let fn mutate the copy, then apply it."""
        with self._lock:
            draft = self.tune.model_copy(deep=True)
            fn(draft)
            return self.apply(draft, source, summary)

    def undo(self, source: str = "user") -> dict:
        with self._lock:
            if not self.history:
                raise EngineError("nothing to undo")
            prev = self.history[-1]
            cur = self.tune
            # undo is allowed to lower or restore; still safety-checked without step limits
            problems = self._check(prev)
            if problems:
                raise SafetyRejected(problems)
            return self._adopt(prev, source, "undo",
                               history=self.history[:-1], redo=(self.redo_stack + [cur])[-200:])

    def redo(self, source: str = "user") -> dict:
        with self._lock:
            if not self.redo_stack:
                raise EngineError("nothing to redo")
            return self._adopt(self.redo_stack[-1], source, "redo",
                               history=(self.history + [self.tune])[-200:], redo=self.redo_stack[:-1])

    def _adopt(self, t: Tune, source: str, summary: str, *, history=None, redo=None, ab=None) -> dict:
        t = Tune.model_validate(t.model_dump())
        problems = self._check(t)
        if problems:
            raise SafetyRejected(problems)
        img = self.mapping.render(t)
        self._persist_protections(t)
        writes = 0
        if self.client is not None and self.device.writes_enabled and self.device.baselined:
            writes = self._write_image(img)
        else:
            self.pending_writes = len(mapping.diff(self.applied_image, img))
        self.history = (self.history + [self.tune])[-200:] if history is None else history
        self.redo_stack = [] if redo is None else redo
        if ab is not None:
            self.ab = ab
        self.tune = t
        self._autosave()
        self._log(source, summary, writes)
        return {"ok": True, "writes": writes}

    # ---- snapshots ----------------------------------------------------------------

    @staticmethod
    def snapshot_name(name: str, default: str = "snapshot") -> str:
        return "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or default

    def _write_snapshot(self, safe: str, text: str, overwrite: bool) -> None:
        """Create a scene file atomically. Without overwrite, O_EXCL guarantees that exactly one
        of several concurrent writers wins; with overwrite, a temp file replaces the old one."""
        path = self.data_dir / "snapshots" / f"{safe}.json"
        if overwrite:
            tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(text)
            os.replace(tmp, path)
            return
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            raise SnapshotExists(safe) from None
        with os.fdopen(fd, "w") as fh:
            fh.write(text)

    def save_snapshot(self, name: str, overwrite: bool = False) -> str:
        safe = self.snapshot_name(name)
        t = self.tune.model_copy(update={"name": safe})
        self._write_snapshot(safe, t.model_dump_json(indent=2), overwrite)
        self._log("engine", f"saved snapshot {safe}")
        return safe

    def list_snapshots(self) -> list[str]:
        return sorted(p.stem for p in (self.data_dir / "snapshots").glob("*.json"))

    def load_snapshot(self, name: str, source: str) -> dict:
        path = self.data_dir / "snapshots" / f"{name}.json"
        if not path.exists():
            raise EngineError(f"no snapshot {name!r}")
        t = Tune.model_validate_json(path.read_text())
        with self._lock:
            problems = self._check(t)
            if problems:
                raise SafetyRejected(problems)
            return self._adopt(t, source, f"loaded snapshot {name}")

    def snapshot_tune(self, name: str) -> Tune:
        path = self.data_dir / "snapshots" / f"{name}.json"
        if not path.exists():
            raise EngineError(f"no snapshot {name!r}")
        return Tune.model_validate_json(path.read_text())

    # ---- import -------------------------------------------------------------------

    def import_afpx(self, path: Path, name: str | None = None, overwrite: bool = False) -> dict:
        tune, rep = afpx.load(path)
        tune.name = name or tune.name
        tune.notes = f"imported from {rep.source} (PC-Tool {rep.version}, saved {rep.date})"
        safe = self.snapshot_name(tune.name, "imported")
        self._write_snapshot(safe, tune.model_dump_json(indent=2), overwrite)
        problems = self._check(tune)
        self._log("engine", f"imported preset {safe}" + (f" ({len(problems)} safety issues)" if problems else ""))
        return {"snapshot": safe, "warnings": rep.warnings, "safety_problems": problems}

    def import_mdat(self, path: Path, tune_snapshot: str | None) -> list[dict]:
        tune = self.snapshot_tune(tune_snapshot) if tune_snapshot else None
        ms = measurements.import_mdat(path, tune)
        for m in ms:
            self.measurements.save(m)
        self._log("engine", f"imported {len(ms)} measurements from {path.name}")
        return [{"id": m.id, "name": m.name, "channels": m.channels} for m in ms]

    def measurement_curves(self, mid: str, smoothing: float = 6, points: int = 240) -> dict:
        with self._lock:
            m = self.measurements.get(mid)
            grid = measurements.GRID
            measured = measurements.smooth(np.interp(np.log(grid), np.log(m.freqs), m.spl), grid, smoothing)
            state, why = self.measurement_status(m)
            issues = ([why] if state != "current" else []) + measurements.prediction_issues(m, self.tune)
            predicted = None if issues else measurements.smooth(measurements.predict(m, self.tune, grid), grid, smoothing)
            idx = np.linspace(0, len(grid) - 1, min(points, len(grid))).round().astype(int)
            return {"id": m.id, "name": m.name, "channels": m.channels, "has_tune": m.tune is not None,
                    "freqs": grid[idx].round(2).tolist(), "measured": measured[idx].round(2).tolist(),
                    "predicted": predicted[idx].round(2).tolist() if predicted is not None else None,
                    "prediction_issues": issues, "hardware_status": state,
                    "prediction_method": "magnitude_delta" if len(m.channels) == 1 else "combined_power_ratio",
                    "phase_verified": False}

    # ---- targets & system view -------------------------------------------------------

    def all_targets(self) -> list[targets.Target]:
        return targets.BUILTINS + self.user_targets

    def target(self, name: str | None = None) -> targets.Target:
        name = name or self.target_name
        for t in self.all_targets():
            if t.name == name:
                return t
        raise KeyError(f"no target {name!r}")

    def save_target(self, t: targets.Target) -> None:
        if any(b.name == t.name for b in targets.BUILTINS):
            raise EngineError(f"{t.name!r} is a built-in target; save under another name")
        self.user_targets = [u for u in self.user_targets if u.name != t.name] + [t.model_copy(update={"builtin": False})]
        (self.data_dir / "targets.json").write_text(json.dumps([u.model_dump() for u in self.user_targets], indent=2))

    def system_view(self, seat: str = "driver", smoothing: float = 6, points: int = 200,
                    target: str | None = None, tune: Tune | None = None) -> dict:
        """Magnitude estimate from current nonoverlapping captures, with explicit coverage."""
        with self._lock:
            now = tune or self.tune
            chosen, excluded, available = self._prediction_selection(seat, now)
            grid = measurements.GRID
            idx = np.linspace(0, len(grid) - 1, min(points, len(grid))).round().astype(int)
            groups: dict[str, list[np.ndarray]] = {}
            meas_p, pred_p, per_channel = [], [], {}
            covered = sorted({c for m in chosen for c in m.channels})
            active = {ch.id for ch in now.channels if ch.role != Role.UNUSED and not ch.mute}
            limitations = ["Magnitude-only estimate; phase, delay and polarity effects between outputs are not verified.",
                           "Capture and playback levels must be comparable; absolute SPL and clipping/headroom are not verified.",
                           "Deep filter attenuation and mute use numerical floors; remeasurement is required to verify the result.",
                           "Outside each capture frequency range, edge values are extended; inspect contributor bandwidths before interpreting the curve."]
            if len(chosen) > 1:
                limitations.append("Separate captures are combined as a power sum, not a measured acoustic system response.")
            if any(len(m.channels) > 1 for m in chosen):
                limitations.append("Combined captures use an approximate power-ratio change and cannot identify individual output responses.")
            out = {"seat": seat, "freqs": grid[idx].round(2).tolist(), "target_name": target or self.target_name,
                   "measurement_count": len(chosen), "available_measurement_count": available,
                   "coverage": {"outputs": covered, "missing_outputs": sorted(active - set(covered))},
                   "contributors": [{"id": m.id, "name": m.name, "channels": m.channels,
                                     "fingerprint": self._measurement_fp(m), "taken_at": m.taken_at,
                                     "frequency_range_hz": [m.freqs[0], m.freqs[-1]]} for m in chosen],
                   "excluded": excluded, "limitations": limitations, "phase_verified": False,
                   "aggregation": "power_sum" if len(chosen) > 1 else "single_capture" if chosen else "none"}
            for m in chosen:
                meas = measurements.smooth(np.interp(np.log(grid), np.log(m.freqs), m.spl), grid, smoothing)
                pred = measurements.smooth(measurements.predict(m, now, grid), grid, smoothing)
                meas_p.append(10 ** (meas / 10))
                pred_p.append(10 ** (pred / 10))
                roles = {now.channel(c).role.value for c in m.channels}
                role = next(iter(roles)) if len(roles) == 1 else "mixed"
                groups.setdefault(role, []).append(10 ** (pred / 10))
                # A combined capture is never presented as each driver's individual response.
                if len(m.channels) == 1:
                    per_channel[m.channels[0]] = pred[idx].round(2).tolist()
            if not chosen:
                return out | {"measured": None, "predicted": None, "target": None, "groups": {}, "channels": {}}
            meas_sum = 10 * np.log10(sum(meas_p))
            pred_sum = 10 * np.log10(sum(pred_p))
            band = (grid > 300) & (grid < 3000)
            tgt = self.target(target).at(grid)
            tgt = tgt - tgt[band].mean() + pred_sum[band].mean()
            return out | {
                "measured": meas_sum[idx].round(2).tolist(),
                "predicted": pred_sum[idx].round(2).tolist(),
                "target": tgt[idx].round(2).tolist(),
                "groups": {r: (10 * np.log10(sum(v)))[idx].round(2).tolist() for r, v in groups.items()},
                "channels": per_channel,
            }

    def _prediction_selection(self, seat: str, tune: Tune | None = None) -> tuple[list, list[dict], int]:
        """Prefer isolated, newest captures; report every refusal and overlap."""
        candidates, excluded, available = [], [], 0
        for info in self.measurements.list():
            if info["seat"] != seat:
                continue
            available += 1
            m = self.measurements.get(info["id"])
            state, why = self.measurement_status(m)
            issues = ([why] if state != "current" else []) + measurements.prediction_issues(m, tune or self.tune)
            if issues:
                excluded.append({"id": m.id, "name": m.name, "reason": "; ".join(issues)})
            else:
                candidates.append(m)
        candidates.sort(key=lambda m: (len(m.channels) != 1, -m.taken_at, m.id))
        chosen, covered = [], set()
        for m in candidates:
            overlap = covered.intersection(m.channels)
            if overlap:
                excluded.append({"id": m.id, "name": m.name,
                                 "reason": "Overlaps selected outputs " + ", ".join(sorted(overlap))})
            else:
                chosen.append(m)
                covered.update(m.channels)
        return chosen, excluded, available

    # ---- proposals ------------------------------------------------------------------------

    def _seat_measurements(self, seat: str) -> dict[str, measurements.Measurement]:
        """Latest measurement covering each channel at a seat (single-channel preferred)."""
        out, single = {}, set()
        for info in self.measurements.list():
            if info["seat"] != seat or not info["channels"]:
                continue
            m = None
            for c in info["channels"]:
                if len(info["channels"]) == 1 or c not in single:
                    m = m or self.measurements.get(info["id"])
                    out[c] = m
                    if len(info["channels"]) == 1:
                        single.add(c)
        return out

    # -- solver targets: built only from trusted, non-overlapping measurements --

    SOLVER_INPUT_FIELDS = {"role", "hp", "lp", "eq", "gain_db", "mute", "mix", "delay_ms", "invert"}

    def channel_inputs(self, tune: Tune, channel: str) -> str:
        """Fingerprint of the channel settings the magnitude solvers consume (not names/colours)."""
        return fingerprint(tune.channel(channel).model_dump(include=self.SOLVER_INPUT_FIELDS))

    def _anchor_measurements(self, seat: str) -> list[measurements.Measurement]:
        """Use the same current, eligible, nonoverlapping captures as the displayed estimate."""
        return self._prediction_selection(seat)[0]

    def solver_target(self, seat: str, mode: str) -> tuple[np.ndarray, dict[str, str]]:
        """Target array a solver uses, plus the anchor measurements it depends on.

        shape: the target curve itself (auto-EQ fits shape and levels it internally).
        level: the target placed at the level of the trusted, predicted system (300 Hz-3 kHz).
        Raises NoTrustedAnchor rather than inventing a reference from untrusted data."""
        grid = measurements.GRID
        tgt = self.target().at(grid)
        if mode == "shape":
            return tgt, {}
        anchor = self._anchor_measurements(seat)
        band = (grid > 300) & (grid < 3000)
        if not anchor:
            raise NoTrustedAnchor(f"no trusted measurement at the {seat} seat to set a level reference "
                                  "(measurements with unknown or outdated drivers are not used)")
        power = sum(10 ** (measurements.smooth(measurements.predict(m, self.tune, grid), grid, 6) / 10) for m in anchor)
        pred = 10 * np.log10(power)
        return tgt - tgt[band].mean() + pred[band].mean(), {m.id: self._measurement_fp(m) for m in anchor}

    @staticmethod
    def _target_fp(arr: np.ndarray) -> str:
        return fingerprint(np.round(arr, 3).tolist())

    # -- provenance: which physical drivers a measurement / proposal is about --

    def driver_identity(self, channel: str) -> list[dict[str, str]]:
        """Recorded drivers fed by a DSP output (component id + make/model), sorted."""
        refs = [{"id": c.id, "make": c.make, "model": c.model} for c in self.design.components
                if c.kind in (equipment.Kind.SPEAKER, equipment.Kind.SUBWOOFER) and channel in c.channels]
        return sorted(refs, key=lambda r: r["id"])

    def measurement_status(self, m: measurements.Measurement) -> tuple[str, str]:
        """('current' | 'unknown' | 'stale', reason) for using m to optimise today's drivers."""
        if m.drivers is None:
            return "unknown", f"{m.name}: drivers at measurement time are unknown (attest them to use it)"
        for ch in m.channels:
            then, now = m.drivers.get(ch), self.driver_identity(ch)
            if then != now:
                was = ", ".join(f"{r['make']} {r['model']}".strip() or r["id"] for r in then or []) or "none"
                cur = ", ".join(f"{r['make']} {r['model']}".strip() or r["id"] for r in now) or "none"
                return "stale", f"{m.name}: channel {ch} was measured with {was}; now {cur}"
        return "current", ""

    @staticmethod
    def _measurement_fp(m: measurements.Measurement) -> str:
        return fingerprint(m.model_dump(include={"freqs", "spl", "phase", "channels", "seat", "tune", "drivers"}))

    def attest_measurement(self, mid: str, source: str, *, drivers: dict | None = None,
                           reason: str = "Trusted local owner statement of current hardware",
                           expected_fingerprint: str | None = None, correct_existing: bool = False) -> measurements.Measurement:
        """Record capture-time hardware; HTTP callers must supply explicit identities/evidence.

        Current-design shorthand is only for trusted in-process callers. Raw data,
        current equipment and the captured tune are never rewritten here.
        """
        with self._lock:
            m = self.measurements.get(mid)
            before = self._measurement_fp(m)
            if expected_fingerprint is not None and expected_fingerprint != before:
                raise MeasurementConflict("The measurement changed while it was being reviewed; reload it first")
            if not m.channels:
                raise EngineError("Tag the measured outputs before recording their capture-time hardware")
            if drivers is None:
                drivers = {ch: self.driver_identity(ch) for ch in m.channels}
            else:
                if set(drivers) != set(m.channels):
                    raise EngineError("Capture hardware must identify every measured output, and no others")
                clean = {}
                for ch, refs in drivers.items():
                    values = [measurements.CaptureDriver.model_validate(ref).model_dump() for ref in refs]
                    if not values or len({v["id"] for v in values}) != len(values):
                        raise EngineError(f"{ch}: record at least one distinct capture-time driver")
                    if any(not v["make"].strip() or not v["model"].strip() for v in values):
                        raise EngineError(f"{ch}: driver make and model are required")
                    clean[ch] = sorted(values, key=lambda v: v["id"])
                drivers = clean
            changed = m.drivers is not None and m.drivers != drivers
            if changed and not correct_existing:
                raise MeasurementConflict("Capture hardware is already recorded; explicitly confirm a correction with its reason")
            history = m.driver_history + [measurements.DriverProvenanceEvent(
                action="correct" if changed else "attest", source=source, reason=reason,
                drivers=drivers, previous_drivers=m.drivers, capture_fingerprint=before)]
            m = m.model_copy(update={"drivers": drivers, "drivers_source": f"owner record: {reason}",
                                     "driver_history": history})
            self.measurements.save(m)
            self.revision += 1
            self._log(source, f"recorded capture hardware for measurement {m.name}")
            return m

    def measurement_metadata(self, mid: str) -> dict:
        with self._lock:
            m = self.measurements.get(mid)
            state, why = self.measurement_status(m)
            if not m.channels:
                state, why = "unknown", "Tag the measured outputs before reviewing capture hardware"
            return m.model_dump(mode="json", exclude={"freqs", "spl", "phase", "tune"}) | {
                "status": state, "status_reason": why, "has_tune": m.tune is not None,
                "tune_name": m.tune.name if m.tune else None, "has_phase": m.phase is not None,
                "optimizable": state == "current" and m.tune is not None and bool(m.channels),
                "capture_fingerprint": self._measurement_fp(m),
                "current_drivers": {ch: self.driver_identity(ch) for ch in m.channels}}

    def list_measurements(self) -> list[dict]:
        with self._lock:
            return [self.measurement_metadata(info["id"]) for info in self.measurements.list()]

    def update_measurement(self, mid: str, fields: dict, tune_snapshot: str | None = None,
                           clear_tune: bool = False, source: str = "ui") -> dict:
        with self._lock:
            m = self.measurements.get(mid)
            fields = dict(fields)
            if "channels" in fields:
                fields["channels"] = sorted({self.tune.channel(ch).id for ch in fields["channels"]})
            if clear_tune and tune_snapshot:
                raise EngineError("Choose a capture-time tune or clear it, not both")
            if tune_snapshot:
                fields["tune"] = self.snapshot_tune(tune_snapshot)
            elif clear_tune:
                fields["tune"] = None
            context_changed = any(key in fields and fingerprint(fields[key]) != fingerprint(getattr(m, key))
                                  for key in ("channels", "seat", "tune"))
            if context_changed and m.drivers is not None:
                fields.update(drivers=None, drivers_source="Capture details changed; hardware requires review",
                              driver_history=m.driver_history + [measurements.DriverProvenanceEvent(
                                  action="invalidate", source=source, reason="Capture output, seat or tune changed",
                                  previous_drivers=m.drivers, capture_fingerprint=self._measurement_fp(m))])
            self.measurements.save(measurements.Measurement.model_validate(m.model_dump() | fields))
            self.revision += 1
            self._log(source, f"updated capture details for measurement {m.name}")
            return self.measurement_metadata(mid)

    def delete_measurement(self, mid: str) -> None:
        with self._lock:
            self.measurements.delete(mid)
            self.revision += 1

    def _usable_measurements(self, seat: str) -> tuple[dict[str, measurements.Measurement], list[str]]:
        usable, notes = {}, []
        for ch, m in self._seat_measurements(seat).items():
            state, why = self.measurement_status(m)
            if state == "current" and m.tune is None:
                notes.append(f"refused {m.name}: capture-time tune is unknown")
            elif state == "current":
                issues = measurements.prediction_issues(m, self.tune)
                if issues:
                    notes.append(f"refused {m.name}: {'; '.join(issues)}")
                else:
                    usable[ch] = m
            elif why not in notes:
                notes.append(f"refused {why}")
        return usable, notes

    def _context(self, seat: str | None, used: dict[str, measurements.Measurement], channels: list[str],
                 target_mode: str | None = None, target_arr: np.ndarray | None = None,
                 anchor: dict[str, str] | None = None, driver_channels: list[str] | None = None) -> ProposalContext:
        chans = sorted(set(channels) | {c for m in used.values() for c in m.channels})
        return ProposalContext(
            seat=seat, target_mode=target_mode,
            target=self._target_fp(target_arr) if target_arr is not None else None,
            anchor=anchor or {},
            measurements={m.id: self._measurement_fp(m) for m in used.values()},
            drivers={ch: fingerprint(self.driver_identity(ch)) for ch in sorted(set(driver_channels or chans))},
            inputs={ch: self.channel_inputs(self.tune, ch) for ch in chans})

    def proposal_conflicts(self, p: Proposal) -> list[str]:
        out = p.field_conflicts(self.tune)
        ctx = p.context
        for ch, fp in ctx.inputs.items():
            if self.channel_inputs(self.tune, ch) != fp:
                out.append(f"channel {ch} processing (role/filters/EQ/level/mute/routing) changed since this proposal")
        if ctx.target_mode is not None:
            try:
                arr, _ = self.solver_target(ctx.seat or "driver", ctx.target_mode)
                if self._target_fp(arr) != ctx.target:
                    out.append("the solver target (curve or its trusted level reference) changed since this proposal")
            except NoTrustedAnchor as e:
                out.append(str(e))
        for mid, fp in ctx.measurements.items():
            try:
                if self._measurement_fp(self.measurements.get(mid)) != fp:
                    out.append(f"measurement {mid} changed since this proposal was computed")
            except KeyError:
                out.append(f"measurement {mid} no longer exists")
        for ch, fp in ctx.drivers.items():
            if fingerprint(self.driver_identity(ch)) != fp:
                out.append(f"drivers recorded on channel {ch} changed since this proposal was computed")
        return out

    def _store_proposal(self, p: Proposal, source: str) -> dict:
        p.source = source
        self.proposals[p.id] = p
        self.proposals = dict(list(self.proposals.items())[-20:])
        self._log(source, f"proposed: {p.title} ({len(p.edits)} changes)")
        self.revision += 1
        return p.model_dump(exclude={"edits": {"__all__": {"value", "before"}}})

    def propose_auto_eq(self, channels: list[str] | None, seat: str = "driver", max_bands: int = 8,
                        max_freq: float = 8000, replace: bool = True, source: str = "engine") -> dict:
        meas, refused = self._usable_measurements(seat)
        chans = [c.upper() for c in channels] if channels else sorted(meas)
        max_boost = min(3.0, self.policy.max_eq_boost_db, self.policy.max_boost_step_db)
        tgt, _ = self.solver_target(seat, "shape")
        p = autotune.propose_auto_eq(self.tune, meas, tgt, chans, max_bands, max_freq, max_boost, replace)
        p.notes = refused + p.notes
        used = {ch: meas[ch] for ch in chans if ch in meas}
        p.context = self._context(seat, used, [e.channel for e in p.edits if e.channel], "shape", tgt)
        return self._store_proposal(p, source)

    def propose_levels(self, seat: str = "driver", source: str = "engine") -> dict:
        meas, refused = self._usable_measurements(seat)
        try:
            tgt, anchor = self.solver_target(seat, "level")
        except NoTrustedAnchor as e:
            return self._store_proposal(Proposal(kind="levels", title="Match driver levels to target", edits=[],
                                           notes=refused + [f"refused: {e}"]), source)
        p = autotune.propose_levels(self.tune, meas, tgt, self.policy.max_boost_step_db)
        p.notes = refused + p.notes
        anchor_meas = [self.measurements.get(mid) for mid in anchor]
        anchor_chans = [c for m in anchor_meas for c in m.channels]
        p.context = self._context(seat, meas, [e.channel for e in p.edits if e.channel] + anchor_chans,
                                  "level", tgt, anchor)
        return self._store_proposal(p, source)

    def propose_alignment(self, distances_cm: dict[str, float], source: str = "engine") -> dict:
        p = autotune.propose_alignment(self.tune, distances_cm)
        # distances describe physical drivers: bind which drivers were on every measured channel
        measured = [c.upper() for c, d in distances_cm.items() if d]
        p.context = self._context(None, {}, [], driver_channels=measured)
        p.context.inputs = {}  # delays only; the edited fields' before-values cover the rest
        return self._store_proposal(p, source)

    def proposal(self, pid: str) -> Proposal:
        if pid not in self.proposals:
            raise KeyError(f"no proposal {pid!r} (proposals are kept in memory for this session)")
        return self.proposals[pid]

    def preview_proposal(self, pid: str, seat: str = "driver", smoothing: float = 6, points: int = 200) -> dict:
        with self._lock:
            p = self.proposal(pid)
            conflicts = self.proposal_conflicts(p)
            if conflicts:
                raise ProposalConflict(conflicts)
            draft = p.apply_to(self.tune)
        return self.system_view(p.context.seat or seat, smoothing, points, tune=draft)

    def apply_proposal(self, pid: str, source: str) -> dict:
        with self._lock:
            p = self.proposal(pid)
            conflicts = self.proposal_conflicts(p)
            if conflicts:
                self._log(source, f"CONFLICT applying {p.title}: {'; '.join(conflicts)}")
                raise ProposalConflict(conflicts)  # accepted tune and proposal left unchanged
            res = self.apply(p.apply_to(self.tune), source, f"applied proposal: {p.title}")
            self.proposals.pop(pid, None)
            return res

    # ---- A/B -----------------------------------------------------------------------------

    def ab_set(self, slot: str, snapshot: str | None) -> dict:
        slot = slot.upper()
        if slot not in ("A", "B"):
            raise EngineError("slot must be A or B")
        with self._lock:
            t = self.snapshot_tune(snapshot) if snapshot else self.tune.model_copy(deep=True)
            self.ab[slot] = t
            if self.ab["active"] is None:
                self.ab["active"] = slot if snapshot is None else None
            self._autosave()
            return self.ab_state()

    def ab_toggle(self, source: str) -> dict:
        with self._lock:
            if not (self.ab["A"] and self.ab["B"]):
                raise EngineError("set both A and B first")
            cur = self.ab["active"] or "A"
            nxt = "B" if cur == "A" else "A"
            t = self.ab[nxt]
            problems = self._check(t)
            if problems:
                raise SafetyRejected(problems)
            slots = dict(self.ab)
            if slots["active"]:
                slots[cur] = self.tune.model_copy(deep=True)
            slots["active"] = nxt
            self._adopt(t.model_copy(deep=True), source, f"A/B → {nxt} ({t.name})", ab=slots)
            return self.ab_state()

    def ab_state(self) -> dict:
        return {"A": self.ab["A"].name if self.ab["A"] else None, "B": self.ab["B"].name if self.ab["B"] else None,
                "active": self.ab["active"]}

    # ---- analysis -----------------------------------------------------------------

    def response(self, channel_ids: list[str] | None = None, points: int = 200) -> dict:
        from .dsp.filters import log_freqs

        f = log_freqs(points)
        out = {"freqs": [round(x, 2) for x in f.tolist()], "channels": {}}
        for ch in self.tune.channels:
            if channel_ids and ch.id not in channel_ids:
                continue
            db = mapping.channel_response(ch, self.tune.sample_rate, f)
            out["channels"][ch.id] = [round(x, 2) for x in np.clip(db, -120, 40).tolist()]
        return out

    def status(self) -> dict:
        return {
            "demo": self.demo,
            "connection_epoch": self._connection_epoch,
            "device": self.device.__dict__,
            "tune_name": self.tune.name,
            "revision": self.revision,
            "ab": self.ab_state(),
            "proposals": [{"id": p.id, "title": p.title, "kind": p.kind, "changes": len(p.edits), "source": p.source}
                          for p in self.proposals.values()],
            "undo_depth": len(self.history),
            "redo_depth": len(self.redo_stack),
            "save_error": self.save_error,
            "recovery_notice": self.recovery_notice,
            "pending_writes": None if self.device.baselined else self.pending_writes,
            "recent_events": [e.__dict__ for e in self.events[-20:]],
        }

    # ---- equipment / system design ---------------------------------------------------------

    def save_design(self, d: equipment.SystemDesign | None = None) -> None:
        with self._lock:
            path = self.data_dir / "system.json"
            proposed = d if d is not None else self.design
            try:
                ids = {c.id for c in proposed.components}
                for component in proposed.components:
                    for cid in component.channels:
                        self.tune.channel(cid)
                for cn in proposed.connections:
                    if cn.src not in ids or cn.dst not in ids:
                        raise ValueError(f"connection {cn.id} references a missing component")
                protections = provenance.reconcile(self.protection_book, self.tune, self.policy, proposed)
            except (ValueError, KeyError) as exc:
                # Existing endpoints edit in-memory design objects before saving.
                # Restore the accepted design if protection-driving metadata is invalid.
                self.design = equipment.SystemDesign.model_validate_json(path.read_text())
                raise EngineError("Invalid system design or physical output protection specifications") from exc
            self._save_protections(protections)
            path.write_text(proposed.model_dump_json(indent=2))
            self.design = proposed
            self.revision += 1

    def _check(self, t: Tune, previous: Tune | None = None) -> list[str]:
        return safety.check(t, self.policy, previous=previous,
                            driver_limits=equipment.channel_driver_limits(self.design),
                            protections=self.protections)

    def _persist_protections(self, t: Tune) -> None:
        with self._lock:
            updated = provenance.reconcile(self.protection_book, t, self.policy, self.design)
            self._save_protections(updated)

    def _save_protections(self, value: provenance.ProtectionBook) -> None:
        path = self.data_dir / "protections.json"
        encoded = value.model_dump_json(indent=2)
        if not path.exists() or path.read_text() != encoded:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(encoded)
            temporary.replace(path)
        self.protection_book = value
        self.protections = value.effective()

    def configure_output_protection(self, cid: str, value: safety.OutputProtection, confirm: str) -> dict:
        """Retired bulk operation; retain an explicit error for older clients."""
        with self._lock:
            cid = self.tune.channel(cid).id
            if self.client is not None:
                raise EngineError("disconnect the device before changing physical output protections")
            if confirm != "RECONFIGURE":
                raise EngineError('physical output reconfiguration requires confirm="RECONFIGURE"')
            raise EngineError("Bulk protection replacement is retired; review and clear each retained constraint with a reason")

    def protection_view(self) -> dict:
        with self._lock:
            return self.protection_book.view()

    def review_protection(self, key: str, action: Literal["confirm", "clear"], reason: str,
                          expected_fingerprint: str) -> dict:
        with self._lock:
            if action == "clear" and self.client is not None:
                raise EngineError("disconnect the device before clearing a physical output constraint; disconnect does not silence the DSP")
            try:
                updated = provenance.reconcile(self.protection_book, self.tune, self.policy, self.design)
                updated = provenance.review(updated, key, action, reason, expected_fingerprint)
            except (KeyError, ValueError) as exc:
                raise EngineError(str(exc)) from exc
            self._save_protections(updated)
            self.revision += 1
            self._log("owner", f"{action} physical output constraint {key}: {reason.strip()}")
            return self.protection_book.view()

    # ---- internals ------------------------------------------------------------------

    def _autosave(self):
        self.revision += 1
        self._save_workstation()

    def _save_workstation(self):
        try:
            workstation.save(self.data_dir, workstation.Checkpoint(
                tune=self.tune, history=self.history, redo=self.redo_stack, ab=workstation.Slots(**self.ab)))
        except (OSError, workstation.RecoveryError):
            # The accepted tune may already have reached the DSP. Do not report a
            # rejected edit or roll back memory; make unsaved work explicit instead.
            self.save_error = "Session changes are not saved. Keep the app open, check available disk space and permissions, then retry saving."
            return
        self.save_error = None
        try:
            workstation.atomic_write(self.data_dir / "current.json", self.tune.model_dump_json(indent=2))
        except OSError:
            self.save_error = "Session saved, but the current.json compatibility export failed. Retry saving after checking disk space and permissions."

    def retry_save(self):
        with self._lock:
            self._save_workstation()
            self._log("owner", "retried session save")
            return {"ok": self.save_error is None}

    def _log(self, source: str, summary: str, writes: int = 0):
        self.events.append(Event(time.time(), source, summary, writes))
        self.events = self.events[-500:]
        try:
            with open(self.data_dir / "events.jsonl", "a") as fh:
                fh.write(json.dumps(self.events[-1].__dict__) + "\n")
        except OSError:
            self.save_error = self.save_error or "The activity log could not be saved. Check disk space and permissions, then retry saving the session."
