"""The engine: single owner of the tune, the device connection and history.

UI, HTTP API and MCP tools all call into one Engine instance, so a person and an
agent always see and change the same state.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from . import afpx, autotune, equipment, mapping, measurements, safety, targets
from .proposals import Proposal, ProposalConflict, ProposalContext, fingerprint
from .devicefile import ParamMap
from .model import Tune
from .protocol import commands
from .protocol.client import Client


class EngineError(RuntimeError):
    pass


class SnapshotExists(EngineError):
    def __init__(self, name: str):
        super().__init__(f"a scene named {name!r} already exists; choose another name (the owner may overwrite)")
        self.name = name


class NoTrustedAnchor(EngineError):
    """A solver needs a trustworthy reference and none exists; refuse instead of guessing."""


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
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "snapshots").mkdir(exist_ok=True)
        cur = self.data_dir / "current.json"
        if cur.exists():
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
        self.protections = (safety.OutputProtections.model_validate_json(protection_file.read_text())
                            if protection_file.exists() else safety.OutputProtections())
        # Migrate current tune + equipment conservatively; snapshots never own these floors.
        self._persist_protections(self.tune)

    @classmethod
    def from_param_map(cls, pm: ParamMap, data_dir: Path) -> "Engine":
        return cls(mapping=mapping.DeviceMapping(pm), data_dir=data_dir)

    # ---- device -------------------------------------------------------------------

    def attach(self, client: Client, kind: str, port: str | None = None) -> DeviceState:
        with self._lock:
            info = client.identify()
            if info.model_type != commands.PRO_MK2:
                raise EngineError(f"connected device is {info.model_string!r}, not a HELIX DSP PRO MK2")
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
            self.client = None
            self.device = DeviceState()
            self.applied_image = None

    def push_full(self, confirm: str) -> int:
        """Overwrite every managed parameter on the device with the current tune.

        Destroys whatever tune is on the device. Requires confirm == "OVERWRITE".
        """
        with self._lock:
            if confirm != "OVERWRITE":
                raise EngineError('full push overwrites the tune on the DSP; pass confirm="OVERWRITE"')
            self._require_writable()
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
            res = self._adopt(prev, source, "undo")
            self.history.pop()
            self.redo_stack.append(cur)
            return res

    def _adopt(self, t: Tune, source: str, summary: str) -> dict:
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
            previous = self.tune
            result = self._adopt(t, source, f"loaded snapshot {name}")
            self.history.append(previous)
            return result

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
        m = self.measurements.get(mid)
        grid = measurements.GRID
        measured = np.interp(np.log(grid), np.log(m.freqs), m.spl)
        predicted = measurements.predict(m, self.tune, grid)
        measured = measurements.smooth(measured, grid, smoothing)
        predicted = measurements.smooth(predicted, grid, smoothing)
        idx = np.linspace(0, len(grid) - 1, min(points, len(grid))).round().astype(int)
        return {"id": m.id, "name": m.name, "channels": m.channels, "has_tune": m.tune is not None,
                "freqs": grid[idx].round(2).tolist(), "measured": measured[idx].round(2).tolist(),
                "predicted": predicted[idx].round(2).tolist()}

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
        """Everything the main graph needs in one call.

        Uses the latest measurement per channel set for the seat. System curves are power
        sums (phase-blind) until sweep data with phase is available."""
        grid = measurements.GRID
        idx = np.linspace(0, len(grid) - 1, min(points, len(grid))).round().astype(int)
        latest: dict[tuple, measurements.Measurement] = {}
        for info in self.measurements.list():
            if info["seat"] != seat or not info["channels"]:
                continue
            latest[tuple(info["channels"])] = self.measurements.get(info["id"])
        groups: dict[str, list[np.ndarray]] = {}
        meas_p, pred_p = [], []
        per_channel: dict[str, list[float]] = {}
        for chans, m in latest.items():
            meas = measurements.smooth(np.interp(np.log(grid), np.log(m.freqs), m.spl), grid, smoothing)
            pred = measurements.smooth(measurements.predict(m, tune or self.tune, grid), grid, smoothing)
            meas_p.append(10 ** (meas / 10))
            pred_p.append(10 ** (pred / 10))
            role = (m.tune or tune or self.tune).channel(chans[0]).role.value
            groups.setdefault(role, []).append(10 ** (pred / 10))
            for c in chans:
                per_channel[c] = pred[idx].round(2).tolist()
        out = {"seat": seat, "freqs": grid[idx].round(2).tolist(), "target_name": target or self.target_name,
               "measurement_count": len(latest)}
        if not latest:
            return out | {"measured": None, "predicted": None, "target": None, "groups": {}, "channels": {}}
        meas_sum = 10 * np.log10(sum(meas_p))
        pred_sum = 10 * np.log10(sum(pred_p))
        # anchor the target at the predicted level around 1 kHz (300 Hz - 3 kHz mean)
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

    SOLVER_INPUT_FIELDS = {"role", "hp", "lp", "eq", "gain_db", "mute", "mix"}

    def channel_inputs(self, tune: Tune, channel: str) -> str:
        """Fingerprint of the channel settings the magnitude solvers consume (not names/colours)."""
        return fingerprint(tune.channel(channel).model_dump(include=self.SOLVER_INPUT_FIELDS))

    def _anchor_measurements(self, seat: str) -> list[measurements.Measurement]:
        """Trusted measurements for level anchoring: current provenance, no channel counted twice.
        Single-channel and newer measurements win."""
        candidates = []
        for info in self.measurements.list():
            if info["seat"] == seat and info["channels"]:
                m = self.measurements.get(info["id"])
                if self.measurement_status(m)[0] == "current":
                    candidates.append(m)
        candidates.sort(key=lambda m: (len(m.channels) != 1, -m.taken_at))
        chosen, covered = [], set()
        for m in candidates:
            if covered.isdisjoint(m.channels):
                chosen.append(m)
                covered.update(m.channels)
        return chosen

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

    def attest_measurement(self, mid: str, source: str) -> measurements.Measurement:
        """Owner statement: this measurement was taken with the drivers recorded now."""
        m = self.measurements.get(mid)
        m = m.model_copy(update={"drivers": {ch: self.driver_identity(ch) for ch in m.channels},
                                 "drivers_source": f"attested by {source} at {time.strftime('%Y-%m-%d %H:%M')}"})
        self.measurements.save(m)
        self.revision += 1
        self._log(source, f"attested drivers for measurement {m.name}")
        return m

    def _usable_measurements(self, seat: str) -> tuple[dict[str, measurements.Measurement], list[str]]:
        usable, notes = {}, []
        for ch, m in self._seat_measurements(seat).items():
            state, why = self.measurement_status(m)
            if state == "current":
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
        t = self.snapshot_tune(snapshot) if snapshot else self.tune.model_copy(deep=True)
        self.ab[slot] = t
        if self.ab["active"] is None:
            self.ab["active"] = slot if snapshot is None else None
        self.revision += 1
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
            previous = self.tune
            self._adopt(t.model_copy(deep=True), source, f"A/B → {nxt} ({t.name})")
            self.history.append(previous)
            if self.ab["active"]:
                self.ab[cur] = previous.model_copy(deep=True)  # retain edits only after a successful switch
            self.ab["active"] = nxt
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
            "device": self.device.__dict__,
            "tune_name": self.tune.name,
            "revision": self.revision,
            "ab": self.ab_state(),
            "proposals": [{"id": p.id, "title": p.title, "kind": p.kind, "changes": len(p.edits), "source": p.source}
                          for p in self.proposals.values()],
            "undo_depth": len(self.history),
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
                protections = safety.tighten_outputs(self.tune, self.policy, self.protections,
                                                      equipment.channel_driver_limits(proposed))
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
            updated = safety.tighten_outputs(t, self.policy, self.protections,
                                             equipment.channel_driver_limits(self.design))
            self._save_protections(updated)

    def _save_protections(self, value: safety.OutputProtections) -> None:
        path = self.data_dir / "protections.json"
        encoded = value.model_dump_json(indent=2)
        if not path.exists() or path.read_text() != encoded:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(encoded)
            temporary.replace(path)
        self.protections = value

    def configure_output_protection(self, cid: str, value: safety.OutputProtection, confirm: str) -> dict:
        """Deliberate owner configuration; HTTP authorization is enforced separately."""
        with self._lock:
            cid = self.tune.channel(cid).id
            if self.client is not None:
                raise EngineError("disconnect the device before changing physical output protections")
            if confirm != "RECONFIGURE":
                raise EngineError('physical output reconfiguration requires confirm="RECONFIGURE"')
            updated = self.protections.model_copy(deep=True)
            updated.outputs[cid] = safety.OutputProtection.model_validate(value.model_dump())
            # Current roles/specifications still impose their own floors. Change stale
            # metadata first, then explicitly reconfigure after physical equipment changes.
            updated = safety.tighten_outputs(self.tune, self.policy, updated,
                                             equipment.channel_driver_limits(self.design))
            self._save_protections(updated)
            self.revision += 1
            self._log("owner", f"reconfigured physical output protection {cid}")
            return self.protections.outputs[cid].model_dump()

    # ---- internals ------------------------------------------------------------------

    def _autosave(self):
        self.revision += 1
        (self.data_dir / "current.json").write_text(self.tune.model_dump_json(indent=2))

    def _log(self, source: str, summary: str, writes: int = 0):
        self.events.append(Event(time.time(), source, summary, writes))
        self.events = self.events[-500:]
        with open(self.data_dir / "events.jsonl", "a") as fh:
            fh.write(json.dumps(self.events[-1].__dict__) + "\n")
