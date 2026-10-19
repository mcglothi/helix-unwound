"""HTTP API + static web UI. The UI uses exactly these endpoints, as do MCP tools."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .dsp.filters import EqType
from .emulator import EmulatedDevice
from .engine import Engine, EngineError, MeasurementConflict, OutputSetupConflict, SafetyRejected, SnapshotExists
from .mapping import MappingError
from .model import EQ_BANDS, Crossover, Role, Tune
from .protocol.client import Client
from .targets import Target
from . import equipment as eq
from .media import Library
from .access import AccessControl, COOKIE, SessionLimit
from .proposals import ProposalConflict
from .safety import OutputProtection
from .measurements import CaptureDriver, Measurement
from .durable import atomic_write
from .measurements import normalise_seat
from .rew import RewClient, RewError

WEB = Path(__file__).parent / "web"


# Channel fields a link group shares (captured: gain, mute, polarity). Name, role,
# routing and delay stay per channel.
LINKED_CHANNEL_FIELDS = frozenset({"gain_db", "mute", "invert"})


class RecoveryAck(BaseModel):
    reason: str = Field(..., min_length=8, max_length=2000)


class UnmuteAtZero(BaseModel):
    # The gains the user reviewed, per affected output. A mismatch means the review is stale.
    reviewed_gain_db: dict[str, float]


class ChannelPatch(BaseModel):
    mix: dict[str, float] | None = None
    name: str | None = None
    role: Role | None = None
    gain_db: float | None = None
    mute: bool | None = None
    invert: bool | None = None
    delay_ms: float | None = None
    link_group: int | None = Field(None, ge=0, le=99)


class OutputSetup(BaseModel):
    name: str = Field(max_length=120)
    role: Role
    mix: dict[str, float]
    expected_context: str = Field(min_length=16, max_length=16)


class BandPatch(BaseModel):
    enabled: bool | None = None
    type: EqType | None = None
    freq_hz: float | None = None
    gain_db: float | None = None
    q: float | None = None


class MasterPatch(BaseModel):
    gain_db: float


class Connect(BaseModel):
    port: str = Field(..., description='serial device path, or "emulator"')
    allow_writes: bool = False


class Confirm(BaseModel):
    confirm: str
    expected_context: str | None = Field(None, min_length=16, max_length=64)


class SessionToken(BaseModel):
    token: str = Field(..., min_length=1, max_length=512, repr=False)


class ProtectionUpdate(BaseModel):
    protection: OutputProtection
    confirm: str


class ProtectionReview(BaseModel):
    action: Literal['confirm', 'clear']
    reason: str = Field(min_length=1, max_length=2000)
    expected_fingerprint: str = Field(min_length=64, max_length=64)


class RewImport(BaseModel):
    port: int = Field(4735, ge=1024, le=65535)
    uuid: str
    expected_fingerprint: str
    channels: list[str] = Field(default_factory=list)
    seat: str = Field('driver', min_length=1, max_length=100)
    tune_snapshot: str | None = None
    # One step for a measurement taken just now: the capture-time tune is the tune on the
    # connected, synchronized DSP and the drivers are the ones currently installed.
    captured_now: bool = False
    expected_revision: int | None = None
    expected_connection_epoch: int | None = None
    # Explicit owner statement that these outputs played the synchronized tune through the
    # currently recorded drivers. Not hardware verification (master excluded, Director/input
    # state can change outside the workstation, no readback).
    owner_confirmed: bool = False


class SnapshotName(BaseModel):
    name: str


class SnapshotSave(BaseModel):
    name: str
    overwrite: bool = False  # owner only


class MeasPatch(BaseModel):
    name: str | None = None
    channels: list[str] | None = None
    seat: str | None = None
    notes: str | None = None
    tune_snapshot: str | None = Field(None, description="attach the tune that was active when measured")
    clear_tune: bool = False


class MeasurementAttestation(BaseModel):
    model_config = {"str_strip_whitespace": True}

    drivers: dict[str, list[CaptureDriver]]
    reason: str = Field(..., min_length=8, max_length=2000)
    expected_fingerprint: str = Field(..., pattern=r"^[a-f0-9]{16}$")
    correct_existing: bool = False


class AutoEqReq(BaseModel):
    channels: list[str] | None = None
    seat: str = "driver"
    max_bands: int = Field(8, ge=1, le=30)
    max_freq: float = Field(8000, ge=100, le=20000)
    replace: bool = True


class AlignReq(BaseModel):
    distances_cm: dict[str, float]


class SlotReq(BaseModel):
    snapshot: str | None = None


class PositionsIn(BaseModel):
    view: Literal["flow", "cab"]
    positions: dict[str, eq.Point]


class MediaPatch(BaseModel):
    caption: str | None = None
    tags: list[str] | None = None


class ComponentPatch(BaseModel):
    kind: eq.Kind | None = None
    name: str | None = None
    make: str | None = None
    model: str | None = None
    serial: str | None = None
    location: str | None = None
    channels: list[str] | None = None
    enclosure: str | None = None
    spec_source: str | None = None
    notes: str | None = None
    specs: dict[str, eq.Spec | None] | None = Field(None, description="merge; null value deletes a spec")
    image: str | None = None
    media: list[str] | None = None


class ThemeIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    author: str | None = None
    variant: Literal["dark", "light"]
    palette: dict[str, str]
    accent: str | None = None


def _fmt(d: dict) -> str:
    return ", ".join(f"{k}={v.value if hasattr(v, 'value') else v}" for k, v in d.items())


def _may_overwrite(request: Request, requested: bool) -> bool:
    """Only the owner may replace an existing scene; agents get a conflict instead."""
    if requested and request.state.principal != "owner":
        raise HTTPException(403, "Only the owner can overwrite an existing scene")
    return requested


def _src(request: Request) -> str:
    if request.state.principal == "agent":
        return "agent"
    return request.headers.get("x-helixtune-source", "ui")


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def agent_allowed(endpoint):
    """Opt a mutating route in for agent credentials. Undecorated mutating routes are owner-only."""
    endpoint.__helixtune_agent__ = True
    return endpoint


PUBLIC_UI_PATHS = {"/", "/legacy", "/manifest.json"}
PUBLIC_STATIC_PREFIXES = ("/assets/", "/static/")


def _is_public(method: str, path: str) -> bool:
    if method in SAFE_METHODS and (path in PUBLIC_UI_PATHS or path.startswith(PUBLIC_STATIC_PREFIXES)):
        return True
    return method == "POST" and path == "/api/session"


def public_route(endpoint):
    """Mark an endpoint that may be reached without credentials (must also be on the public list)."""
    endpoint.__helixtune_public__ = True
    return endpoint


async def authorize_route(request: Request) -> None:
    """Route-level capability check (runs after routing, so it sees the matched endpoint)."""
    endpoint = getattr(request.scope.get("route"), "endpoint", None)
    principal = getattr(request.state, "principal", None)
    if principal is None:
        # reached only via the middleware's public list; the endpoint must agree it is public
        if not getattr(endpoint, "__helixtune_public__", False):
            raise HTTPException(401, "Authentication required")
        return
    if principal == "owner" or request.method in SAFE_METHODS:
        return
    if not getattr(endpoint, "__helixtune_agent__", False):
        raise HTTPException(403, "Owner capability required")


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="helixtune", version="0.0.1", dependencies=[Depends(authorize_route)])
    access = AccessControl(engine.data_dir)
    app.state.access = access
    app.state.rew_factory = RewClient

    @app.exception_handler(MeasurementConflict)
    async def _measurement_conflict(_, exc: MeasurementConflict):
        return JSONResponse({"error": "measurement_conflict", "detail": str(exc)}, status_code=409)

    @app.middleware("http")
    async def authorize(request: Request, call_next):
        path = request.url.path
        # A same-site cookie alone does not protect against another local port.
        origin = request.headers.get("origin")
        if request.method not in SAFE_METHODS and origin is not None:
            if origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin mutations are not allowed"}, status_code=403)
        # Everything requires a principal except an explicit public surface: the static UI
        # shell (no live state) and the owner-session bootstrap exchange.
        if _is_public(request.method, path):
            request.state.principal = None
            return await call_next(request)
        authorization = request.headers.get("authorization")
        if authorization is not None:
            scheme, _, token = authorization.partition(" ")
            principal = access.authenticate(token) if scheme.lower() == "bearer" else None
        else:
            principal = access.authenticate_session(request.cookies.get(COOKIE, ""))
        if principal is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})
        if authorization is None and request.method not in ("GET", "HEAD", "OPTIONS"):
            if origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Browser mutations require a same-origin request"}, status_code=403)
        request.state.principal = principal
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/session")
    @public_route
    def start_session(value: SessionToken, request: Request):
        try:
            session_id = access.start_session(value.token, request.cookies.get(COOKIE, ""))
        except SessionLimit as exc:
            raise HTTPException(429, str(exc), headers={"Cache-Control": "no-store"}) from None
        if session_id is None:
            raise HTTPException(401, "Valid owner credential required", headers={"Cache-Control": "no-store"})
        response = JSONResponse({"ok": True, "expires_in": access.session_ttl},
                                headers={"Cache-Control": "no-store"})
        response.set_cookie(COOKIE, session_id, max_age=access.session_ttl, path="/",
                            secure=request.url.scheme == "https", httponly=True, samesite="strict")
        return response

    @app.delete("/api/session")
    def end_session(request: Request):
        access.revoke_session(request.cookies.get(COOKIE, ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/", secure=request.url.scheme == "https",
                               httponly=True, samesite="strict")
        return response

    @app.exception_handler(SnapshotExists)
    async def _exists(_, e: SnapshotExists):
        return JSONResponse({"error": "exists", "name": e.name, "detail": str(e)}, status_code=409)

    @app.exception_handler(ProposalConflict)
    async def _conflict(_, e: ProposalConflict):
        return JSONResponse({"error": "conflict", "conflicts": e.conflicts,
                             "detail": "Recompute the proposal; nothing was changed."}, status_code=409)

    @app.exception_handler(SafetyRejected)
    async def _safety(_, e: SafetyRejected):
        return JSONResponse({"error": "safety", "problems": e.problems}, status_code=409)

    @app.exception_handler(MappingError)
    async def _mapping(_, e: MappingError):
        return JSONResponse({"error": "unrepresentable", "detail": str(e)}, status_code=422)

    @app.exception_handler(ValidationError)
    async def _validation(_, e: ValidationError):
        return JSONResponse({"error": "invalid", "detail": e.errors(include_url=False, include_context=False, include_input=False)}, status_code=422)

    @app.exception_handler(EngineError)
    async def _engine(_, e: EngineError):
        return JSONResponse({"error": "engine", "detail": str(e)}, status_code=400)

    @app.exception_handler(KeyError)
    async def _key(_, e: KeyError):
        return JSONResponse({"error": "not_found", "detail": str(e)}, status_code=404)

    # ---- read ---------------------------------------------------------------------

    @app.get("/api/status")
    def status():
        return engine.status()

    @app.get("/api/tune", response_model=Tune)
    def get_tune():
        return engine.tune

    @app.get("/api/channels/{cid}")
    def get_channel(cid: str):
        return engine.tune.channel(cid)

    @app.get("/api/outputs/{cid}/setup")
    def output_setup_review(cid: str):
        return engine.output_setup_review(cid)

    @app.put("/api/outputs/{cid}/setup")
    def save_output_setup(cid: str, p: OutputSetup, request: Request):
        try:
            return engine.save_output_setup(cid, source=_src(request), **p.model_dump())
        except OutputSetupConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/response")
    def response(channels: str | None = None, points: int = 200):
        ids = [c.strip().upper() for c in channels.split(",")] if channels else None
        return engine.response(ids, max(16, min(points, 1000)))

    @app.get("/api/safety")
    def get_safety():
        return engine.policy

    @app.get("/api/protections")
    def get_protections():
        return engine.protection_view()

    @app.post("/api/state/acknowledge-recovery")
    def acknowledge_recovery(value: RecoveryAck):
        """Owner-only: confirms state restored from backups was reviewed; re-enables DSP writes."""
        return engine.acknowledge_recovery(value.reason)

    @app.post("/api/protections/constraints/{key}/review")
    def review_protection(key: str, review: ProtectionReview):
        return engine.review_protection(key, review.action, review.reason, review.expected_fingerprint)

    @app.put("/api/protections/{cid}")
    def configure_protection(cid: str, update: ProtectionUpdate):
        return engine.configure_output_protection(cid, update.protection, update.confirm)

    @app.get("/api/safety/check")
    def check_safety(snapshot: str | None = None):
        """Problems the current tune (or a saved snapshot) has under the policy and recorded driver specs."""
        t = engine.snapshot_tune(snapshot) if snapshot else engine.tune
        return {"tune": t.name, "problems": engine._check(t), "advisories": engine._advisories(t)}

    @app.get("/api/events")
    def events(limit: int = 50):
        return [e.__dict__ for e in engine.events[-limit:]]

    # ---- edit ---------------------------------------------------------------------

    @app.put("/api/tune")
    @agent_allowed
    def put_tune(t: Tune, request: Request):
        return engine.apply(t, _src(request), "replaced whole tune")

    # Link groups (PC-Tool LG): the edited item is copied to every linked channel, as the
    # 2026-10-17 captures show. ?link=false edits one channel only (e.g. callers that
    # already address each channel of a group themselves).
    def _partners(t, cid: str, link: bool) -> list[str]:
        return [c for c in t.linked(cid) if c != cid.upper()] if link else []

    def _linked_note(cid: str, link: bool) -> str:
        others = _partners(engine.tune, cid, link)
        return f" (linked: {', '.join(others)})" if others else ""

    @app.patch("/api/channels/{cid}")
    @agent_allowed
    def patch_channel(cid: str, p: ChannelPatch, request: Request, link: bool = True):
        fields = p.model_dump(exclude_none=True)
        engine.tune.channel(cid)  # 404 early
        shared = {k: v for k, v in fields.items() if k in LINKED_CHANNEL_FIELDS}

        def f(t):
            ch = t.channel(cid)
            for k, v in fields.items():
                setattr(ch, k, v)
            for other in _partners(t, cid, link):
                for k, v in shared.items():
                    setattr(t.channel(other), k, v)
        note = _linked_note(cid, link) if shared else ""
        return engine.edit(_src(request), f"{cid.upper()}: {_fmt(fields)}{note}", f)

    @app.post("/api/channels/{cid}/unmute-at-zero")
    @agent_allowed
    def unmute_at_zero(cid: str, body: UnmuteAtZero, request: Request, link: bool = True):
        """One reviewed edit: unmute an output (and its linked partners) with any positive gain
        lowered to 0 dB. Never raises gain; every safety check still runs."""
        engine.tune.channel(cid)
        reviewed = {k.upper(): v for k, v in body.reviewed_gain_db.items()}

        def f(t):
            targets = [cid.upper()] + _partners(t, cid, link)
            if reviewed != {c: t.channel(c).gain_db for c in targets}:
                raise EngineError("Output levels or links changed since the review; review again. Nothing was changed.")
            for c in targets:
                ch = t.channel(c)
                ch.gain_db = min(ch.gain_db, 0.0)
                ch.mute = False
        return engine.edit(_src(request), f"{cid.upper()}: unmute at 0 dB{_linked_note(cid, link)}", f)

    @app.put("/api/channels/{cid}/{which}")
    @agent_allowed
    async def put_crossover(cid: str, which: Literal["hp", "lp"], request: Request, xo: Crossover | None = None,
                            link: bool = True):
        if not await request.body():
            raise HTTPException(422, "Supply a crossover object or explicit JSON null to bypass")
        engine.tune.channel(cid)

        def f(t):
            for c in [cid] + _partners(t, cid, link):
                setattr(t.channel(c), which, xo.model_copy() if xo else None)
        return await run_in_threadpool(engine.edit, _src(request),
                                       f"{cid.upper()} {which}: {_fmt(xo.model_dump(mode='json')) if xo else 'off'}"
                                       f"{_linked_note(cid, link)}", f)

    @app.patch("/api/channels/{cid}/eq/{band}")
    @agent_allowed
    def patch_band(cid: str, band: int, p: BandPatch, request: Request, link: bool = True):
        if not 1 <= band <= EQ_BANDS:
            raise HTTPException(404, f"band must be 1..{EQ_BANDS}")
        fields = p.model_dump(exclude_none=True)
        engine.tune.channel(cid)

        def f(t):
            b = t.channel(cid).eq[band - 1]
            for k, v in fields.items():
                setattr(b, k, v)
            for other in _partners(t, cid, link):  # PC-Tool copies the whole edited band
                t.channel(other).eq[band - 1] = b.model_copy()
        return engine.edit(_src(request), f"{cid.upper()} band {band}: {_fmt(fields)}{_linked_note(cid, link)}", f)

    @app.post("/api/channels/{cid}/eq/reset")
    @agent_allowed
    def reset_eq(cid: str, request: Request, link: bool = True):
        engine.tune.channel(cid)

        def f(t):
            for c in [cid] + _partners(t, cid, link):
                for b in t.channel(c).eq:
                    b.enabled, b.gain_db = False, 0.0
        return engine.edit(_src(request), f"{cid.upper()}: EQ reset{_linked_note(cid, link)}", f)

    @app.patch("/api/master")
    @agent_allowed
    def patch_master(p: MasterPatch, request: Request):
        return engine.edit(_src(request), f"master {p.gain_db} dB",
                           lambda t: setattr(t, "master_gain_db", p.gain_db))

    @app.post("/api/undo")
    @agent_allowed
    def undo(request: Request):
        return engine.undo(_src(request))

    @app.post("/api/redo")
    @agent_allowed
    def redo(request: Request):
        return engine.redo(_src(request))

    @app.post("/api/session/save")
    def retry_save():
        return engine.retry_save()

    # ---- snapshots ------------------------------------------------------------------

    @app.get("/api/snapshots")
    def snapshots():
        return engine.list_snapshots()

    @app.post("/api/snapshots")
    @agent_allowed
    def save_snapshot(s: SnapshotSave, request: Request):
        return {"saved": engine.save_snapshot(s.name, overwrite=_may_overwrite(request, s.overwrite))}

    @app.post("/api/snapshots/{name}/load")
    @agent_allowed
    def load_snapshot(name: str, request: Request):
        return engine.load_snapshot(name, _src(request))

    # ---- import & measurements -----------------------------------------------------

    def _spool(upload: UploadFile, suffix: str) -> Path:
        tmp = Path(tempfile.mkdtemp()) / (Path(upload.filename or "upload").stem + suffix)
        with open(tmp, "wb") as fh:
            shutil.copyfileobj(upload.file, fh)
        return tmp

    @app.post("/api/import/afpx")
    @agent_allowed
    def import_afpx(request: Request, file: UploadFile = File(...), overwrite: bool = Form(False)):
        return engine.import_afpx(_spool(file, ".afpx"), overwrite=_may_overwrite(request, overwrite))

    @app.post("/api/import/mdat")
    @agent_allowed
    def import_mdat(file: UploadFile = File(...), tune_snapshot: str | None = Form(None)):
        return engine.import_mdat(_spool(file, ".mdat"), tune_snapshot)

    @app.get("/api/measurements")
    def list_measurements():
        return engine.list_measurements()

    @app.get("/api/measurements/{mid}")
    def measurement_metadata(mid: str):
        return engine.measurement_metadata(mid)

    @app.get("/api/measurements/{mid}/curves")
    def measurement_curves(mid: str, smoothing: float = 6, points: int = 240):
        return engine.measurement_curves(mid, smoothing, points)


    @app.patch("/api/measurements/{mid}")
    @agent_allowed
    def patch_measurement(mid: str, p: MeasPatch, request: Request):
        upd = p.model_dump(exclude_none=True, exclude={"tune_snapshot", "clear_tune"})
        return engine.update_measurement(mid, upd, p.tune_snapshot, p.clear_tune, _src(request))

    @app.post("/api/measurements/{mid}/attest")
    def attest_measurement(mid: str, value: MeasurementAttestation):
        """Explicit capture-time identities and owner evidence; historical hardware stays historical."""
        engine.attest_measurement(mid, "owner", **value.model_dump())
        return engine.measurement_metadata(mid)

    @app.delete("/api/measurements/{mid}")
    def delete_measurement(mid: str):
        engine.delete_measurement(mid)
        return {"ok": True}

    # REW network access is owner-only, including GETs; agents cannot probe local services.
    def rew_owner(request: Request):
        if request.state.principal != 'owner':
            raise HTTPException(403, 'Owner capability required')

    @app.exception_handler(RewError)
    async def rew_error(_, exc: RewError):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.get('/api/rew', dependencies=[Depends(rew_owner)])
    def rew_discover(port: int = 4735):
        return app.state.rew_factory(port).discover()

    @app.get('/api/rew/measurements/{uid}', dependencies=[Depends(rew_owner)])
    def rew_preview(uid: str, port: int = 4735):
        return app.state.rew_factory(port).capture(uid)[0]

    @app.post('/api/rew/import', dependencies=[Depends(rew_owner)])
    def rew_import(value: RewImport):
        preview, arrays = app.state.rew_factory(value.port).capture(value.uuid)
        if preview['fingerprint'] != value.expected_fingerprint:
            raise HTTPException(409, 'REW capture changed; refresh the preview before importing')
        seat = normalise_seat(value.seat)
        if not seat:
            raise HTTPException(422, 'Choose the listening position')
        with engine._lock:
            channels = sorted({engine.tune.channel(cid).id for cid in value.channels})
            if value.captured_now:
                if value.tune_snapshot:
                    raise HTTPException(422, 'Choose either "captured just now" or a capture-time scene, not both')
                if not channels:
                    raise HTTPException(422, 'Tag the outputs that were playing')
                dev = engine.device
                if engine.client is None or not dev.baselined or dev.sync_state != 'synchronized':
                    raise HTTPException(409, '"Captured just now" needs a connected DSP that is synchronized with this '
                                             'workstation; otherwise choose the capture-time scene')
                if not value.owner_confirmed:
                    raise HTTPException(422, 'Confirm that these outputs played the synchronized tune through the drivers currently recorded')
                if value.expected_revision != engine.revision or value.expected_connection_epoch != engine._connection_epoch:
                    raise HTTPException(409, 'The tune or connection changed after you started this import; confirm what was playing and import again')
                missing = [c for c in channels if not engine.driver_identity(c)]
                if missing:
                    raise HTTPException(409, f'Record the drivers on output(s) {", ".join(missing)} in Setup first')
                tune = Tune.model_validate(engine.tune.model_dump())
            else:
                tune = engine.snapshot_tune(value.tune_snapshot) if value.tune_snapshot else None
            provenance = {'provider': 'REW', 'port': value.port, **preview}
            if value.captured_now:
                from .proposals import fingerprint as _fp
                provenance['capture_context'] = {
                    'kind': 'captured_now', 'connection_epoch': engine._connection_epoch, 'revision': engine.revision,
                    'applied_image': _fp(sorted((a, w.hex()) for a, w in (engine.applied_image or {}).items())),
                    'design': _fp(engine.design.model_dump(mode='json')),
                    'limits': 'acknowledged managed writes only; master excluded on hardware; Director/input state '
                              'may change outside the workstation; no hardware readback'}
            for info in engine.measurements.list():
                existing = engine.measurements.get(info['id'])
                if (existing.import_provenance == provenance and existing.channels == channels and
                        existing.seat == seat and existing.tune == tune):
                    return {'id': existing.id, 'created': False}
            measurement = Measurement(name=preview['summary']['title'], kind='rew-import', channels=channels,
                seat=seat, taken_at=0, source="Imported from REW",
                notes=preview['summary']['notes'], tune=tune, import_provenance=provenance, **arrays)
            engine.measurements.save(measurement)
            if value.captured_now:
                engine.attest_measurement(measurement.id, 'owner',
                                          reason='Captured just now: drivers as currently installed (owner import)')
            engine.revision += 1
            engine._log('owner', f'Imported REW capture {measurement.name}' + (' (captured just now)' if value.captured_now else ''))
            return {'id': measurement.id, 'created': True}

    # ---- targets & system view -----------------------------------------------------

    @app.get("/api/targets")
    def list_targets():
        return {"current": engine.target_name, "targets": engine.all_targets()}

    @app.put("/api/targets/current")
    @agent_allowed
    def set_target(s: SnapshotName):
        engine.target(s.name)
        engine.target_name = s.name
        engine.revision += 1
        return {"current": s.name}

    @app.post("/api/targets")
    @agent_allowed
    def save_target(t: Target):
        engine.save_target(t)
        return {"saved": t.name}

    @app.get("/api/system")
    def system(seat: str = "driver", smoothing: float = 6, points: int = 200, target: str | None = None):
        return engine.system_view(seat, smoothing, max(32, min(points, 480)), target)

    # ---- proposals & A/B -------------------------------------------------------------




    @app.post("/api/propose/auto-eq")
    @agent_allowed
    def propose_auto_eq(r: AutoEqReq, request: Request):
        return engine.propose_auto_eq(r.channels, r.seat, r.max_bands, r.max_freq, r.replace, _src(request))

    @app.post("/api/propose/levels")
    @agent_allowed
    def propose_levels(request: Request, seat: str = "driver"):
        return engine.propose_levels(seat, _src(request))

    @app.post("/api/propose/alignment")
    @agent_allowed
    def propose_alignment(r: AlignReq, request: Request):
        return engine.propose_alignment(r.distances_cm, _src(request))

    @app.get("/api/proposals/{pid}")
    def get_proposal(pid: str):
        return engine.proposal(pid).model_dump(exclude={"edits": {"__all__": {"value", "before"}}})

    @app.get("/api/proposals/{pid}/preview")
    def preview_proposal(pid: str, seat: str = "driver", smoothing: float = 6, points: int = 200):
        return engine.preview_proposal(pid, seat, smoothing, max(32, min(points, 480)))

    @app.post("/api/proposals/{pid}/apply")
    @agent_allowed
    def apply_proposal(pid: str, request: Request):
        return engine.apply_proposal(pid, _src(request))

    @app.delete("/api/proposals/{pid}")
    @agent_allowed
    def discard_proposal(pid: str):
        engine.proposals.pop(pid, None)
        engine.revision += 1
        return {"ok": True}

    @app.put("/api/ab/{slot}")
    @agent_allowed
    def ab_set(slot: str, r: SlotReq):
        return engine.ab_set(slot, r.snapshot)

    @app.post("/api/ab/toggle")
    @agent_allowed
    def ab_toggle(request: Request):
        return engine.ab_toggle(_src(request))

    # ---- system design: equipment + wiring --------------------------------------------

    @app.get("/api/design")
    def get_design():
        return engine.design

    @app.put("/api/design/vehicle")
    @agent_allowed
    def put_vehicle(v: eq.Vehicle):
        engine.design.vehicle = v
        engine.save_design()
        return v

    @app.get("/api/design/spec-fields")
    def spec_fields():
        return {k.value: {f: {"label": l, "unit": u} for f, (l, u) in fields.items()}
                for k, fields in eq.KNOWN_SPECS.items()}

    @app.post("/api/equipment")
    @agent_allowed
    def add_component(c: eq.Component):
        if any(x.id == c.id for x in engine.design.components):
            raise HTTPException(409, f"component {c.id} exists")
        engine.design.components.append(c)
        engine.save_design()
        return c

    @app.patch("/api/equipment/{cid}")
    @agent_allowed
    def patch_component(cid: str, p: ComponentPatch):
        c = engine.design.get(cid)
        upd = p.model_dump(exclude_none=True, exclude={"specs"})
        if p.image == "":
            upd["image"] = None
        if "channels" in upd:
            upd["channels"] = [x.upper() for x in upd["channels"]]
            for x in upd["channels"]:
                engine.tune.channel(x)
        specs = dict(c.specs)
        for k, v in (p.specs or {}).items():
            if v is None:
                specs.pop(k, None)
            else:
                specs[k] = v
        new = c.model_copy(update=upd | {"specs": specs})
        engine.design.components = [new if x.id == cid else x for x in engine.design.components]
        engine.save_design()
        return new

    @app.delete("/api/equipment/{cid}")
    def delete_component(cid: str):
        engine.design.get(cid)
        engine.design.components = [x for x in engine.design.components if x.id != cid]
        engine.design.connections = [x for x in engine.design.connections if cid not in (x.src, x.dst)]
        engine.save_design()
        return {"ok": True}

    @app.put("/api/design/positions")
    @agent_allowed
    def put_positions(p: PositionsIn):
        field_name = "flow_pos" if p.view == "flow" else "cab_pos"
        comps = []
        for c in engine.design.components:
            pos = p.positions.get(c.id)
            comps.append(c.model_copy(update={field_name: pos}) if pos else c)
        engine.design.components = comps
        engine.save_design()
        return {"ok": True, "updated": len(p.positions)}

    @app.get("/api/equipment/{cid}/analysis")
    def analyze_component(cid: str):
        return eq.analyze(engine.design, cid)

    @app.post("/api/connections")
    @agent_allowed
    def add_connection(cn: eq.Connection):
        engine.design.get(cn.src)
        engine.design.get(cn.dst)
        engine.design.connections.append(cn)
        engine.save_design()
        return cn

    @app.delete("/api/connections/{cnid}")
    def delete_connection(cnid: str):
        engine.design.connections = [x for x in engine.design.connections if x.id != cnid]
        engine.save_design()
        return {"ok": True}

    # ---- media library -------------------------------------------------------------------

    lib = Library(engine.data_dir)

    @app.get("/api/media")
    def list_media():
        return lib.list()

    @app.post("/api/media")
    @agent_allowed
    async def upload_media(file: UploadFile = File(...), caption: str = Form("")):
        data = await file.read()
        try:
            return lib.add(data, file.filename or "image", file.content_type or "", caption)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    @app.get("/api/media/{mid}")
    def get_media(mid: str):
        path, ctype = lib.path(mid)
        return FileResponse(path, media_type=ctype, headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})

    @app.patch("/api/media/{mid}")
    @agent_allowed
    def patch_media(mid: str, p: MediaPatch):
        return lib.update(mid, p.caption, p.tags)

    @app.delete("/api/media/{mid}")
    def delete_media(mid: str):
        lib.delete(mid)
        # drop references so nothing points at a missing file
        comps = []
        for c in engine.design.components:
            comps.append(c.model_copy(update={"image": None if c.image == mid else c.image,
                                              "media": [m for m in c.media if m != mid]}))
        engine.design.components = comps
        v = engine.design.vehicle
        engine.design.vehicle = v.model_copy(update={"layout_image": None if v.layout_image == mid else v.layout_image,
                                                     "media": [m for m in v.media if m != mid]})
        engine.save_design()
        return {"ok": True}

    # ---- themes (custom base16 schemes, shared by every device) ------------------------

    themes_file = engine.data_dir / "themes.json"

    def _themes() -> list[dict]:
        import json
        return json.loads(themes_file.read_text()) if themes_file.exists() else []

    @app.get("/api/themes")
    def list_themes():
        return _themes()

    @app.post("/api/themes")
    @agent_allowed
    def save_theme(t: ThemeIn):
        import json
        import re
        keys = [f"base0{i:X}" for i in range(16)]
        if sorted(t.palette) != sorted(keys) or not all(re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in t.palette.values()):
            raise HTTPException(422, "palette needs base00..base0F as #rrggbb")
        rest = [x for x in _themes() if x["name"] != t.name]
        atomic_write(themes_file, json.dumps(rest + [t.model_dump()], indent=2))
        return {"saved": t.name}

    @app.delete("/api/themes/{name}")
    def delete_theme(name: str):
        import json
        atomic_write(themes_file, json.dumps([x for x in _themes() if x["name"] != name], indent=2))
        return {"ok": True}

    # ---- device -----------------------------------------------------------------------

    @app.get("/api/ports")
    def ports():
        if engine.demo:
            return []
        from serial.tools import list_ports

        return [{"device": p.device, "vid": p.vid, "pid": p.pid, "description": p.description}
                for p in list_ports.comports() if not p.device.startswith("/dev/tty.")]

    @app.post("/api/device/connect")
    def connect(c: Connect):
        with engine._lock:
            if engine.demo and c.port != "emulator":
                raise EngineError("Demo mode cannot open physical ports; select emulator")
            if c.port != "emulator" and c.allow_writes and not engine.physical_writes_allowed:
                raise EngineError("Physical writes are disabled; start the server with --allow-physical-writes "
                                  "for a supervised session, or connect read-only")
            engine.detach()
            if c.port == "emulator":
                client = Client(EmulatedDevice(), allow_writes=c.allow_writes)
                return engine.attach(client, "emulator").__dict__
            import serial

            from .protocol.commands import LOW_HOST_BAUD

            ser = serial.Serial(c.port, LOW_HOST_BAUD, bytesize=8, parity="N", stopbits=1, timeout=0.05)
            try:
                return engine.attach(Client(ser, allow_writes=c.allow_writes, timeout=1.0,
                                            physical_session=c.allow_writes), "serial", c.port).__dict__
            except Exception:
                ser.close()
                raise

    @app.post("/api/device/stored-preset/backup")
    def backup_stored_preset():
        return engine.backup_stored_preset()

    @app.get("/api/backups/stored/{backup_id}", dependencies=[Depends(rew_owner)])
    def download_stored_preset(backup_id: str):
        return FileResponse(engine.stored_backup_path(backup_id), media_type="application/octet-stream",
                            filename=f"stored-{backup_id}.afpx", headers={"Cache-Control": "no-store"})

    @app.post("/api/backups/stored/{backup_id}/import")
    def import_stored_preset(backup_id: str, value: SnapshotSave):
        # Copy to a named scene only; never load/adopt it or relax output protections.
        with engine._lock:
            return engine.import_afpx(engine.stored_backup_path(backup_id), name=value.name, overwrite=False)

    @app.post("/api/device/disconnect")
    def disconnect():
        engine.detach()
        return {"ok": True}

    @app.get("/api/device/review")
    def review_overwrite():
        return engine.overwrite_review()

    @app.post("/api/device/push-full")
    def push_full(c: Confirm, request: Request):
        return {"writes": engine.push_full(c.confirm, c.expected_context)}

    # ---- UI -----------------------------------------------------------------------------

    dist = WEB / "dist"

    @app.get("/")
    @public_route
    def index():
        return FileResponse(dist / "index.html" if (dist / "index.html").exists() else WEB / "index.html")

    @app.get("/legacy")
    @public_route
    def legacy():
        return FileResponse(WEB / "index.html")

    @app.get("/manifest.json")
    @public_route
    def manifest():
        return FileResponse(dist / "manifest.json" if (dist / "manifest.json").exists() else WEB / "manifest.json")

    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
