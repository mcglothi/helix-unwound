"""The whole audio system: equipment inventory, specs, and wiring.

Specs are free-form name -> value maps with a source, so an agent (or the user) can
record exactly what the manufacturer publishes. Known fields (below) get units, labels
and calculations; unknown ones are kept as-is.
"""

from __future__ import annotations

import math
import uuid
from enum import Enum

from pydantic import BaseModel, Field


class Kind(str, Enum):
    VEHICLE_SOURCE = "source"         # head unit, OEM radio, streamer
    DSP = "dsp"
    AMPLIFIER = "amplifier"
    SPEAKER = "speaker"
    SUBWOOFER = "subwoofer"
    ENCLOSURE = "enclosure"
    MICROPHONE = "microphone"
    POWER = "power"                   # battery, fuse block, distribution, capacitor
    COMPUTER = "computer"             # in-truck controller (e.g. Raspberry Pi)
    INTERFACE = "interface"           # OEM integration (e.g. PAC AmpPRO), converters
    CONTROLLER = "controller"         # remote / display (e.g. HELIX Director)
    OTHER = "other"


class Signal(str, Enum):
    SPEAKER = "speaker"               # amplified speaker-level
    LINE = "line"                     # RCA / low-level
    HIGH_LEVEL = "high_level"         # OEM speaker-level into a DSP's high-level input
    OPTICAL = "optical"
    COAX = "coax"
    USB = "usb"
    POWER = "power"
    GROUND = "ground"
    REMOTE = "remote"                 # remote turn-on
    DATA = "data"                     # vehicle bus / control cable (CAN, controller link)
    OTHER = "other"


class Spec(BaseModel):
    value: float | str
    unit: str = ""
    source: str = ""                  # URL or "manual" / "measured"


class Point(BaseModel):
    x: float
    y: float


class Component(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    kind: Kind
    name: str = ""                    # what you call it, e.g. "Front left tweeter"
    make: str = ""
    model: str = ""
    serial: str = ""
    location: str = ""                # e.g. "driver door, sail panel"
    channels: list[str] = Field(default_factory=list)   # DSP output channels feeding it (speakers)
    enclosure: str | None = None      # enclosure component id (drivers)
    specs: dict[str, Spec] = Field(default_factory=dict)
    spec_source: str = ""             # main datasheet URL
    notes: str = ""
    image: str | None = None          # primary picture: media id or an external (stock) image URL
    media: list[str] = Field(default_factory=list)  # more photos (media ids / URLs)
    flow_pos: Point | None = None     # position on the signal-flow canvas
    cab_pos: Point | None = None      # position on the vehicle layout (over the cab photo)

    @property
    def label(self) -> str:
        mm = " ".join(x for x in (self.make, self.model) if x)
        return self.name or mm or self.kind.value


class Connection(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    src: str                          # component id
    src_port: str = ""                # e.g. "Out A", "CH1", "+12V"
    dst: str
    dst_port: str = ""
    signal: Signal
    cable: str = ""                   # e.g. "12 AWG OFC", "4 AWG power"
    notes: str = ""


class Vehicle(BaseModel):
    year: str = ""
    make: str = ""
    model: str = ""
    trim: str = ""
    notes: str = ""
    layout_image: str | None = None   # cab photo / top-down image used as the vehicle-view backdrop
    media: list[str] = Field(default_factory=list)


class SystemDesign(BaseModel):
    vehicle: Vehicle = Field(default_factory=Vehicle)
    components: list[Component] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)

    def get(self, cid: str) -> Component:
        for c in self.components:
            if c.id == cid:
                return c
        raise KeyError(f"no component {cid!r}")


# ---- known spec fields -----------------------------------------------------------------

DRIVER_SPECS = {
    "size": ("Nominal size", "in"), "impedance": ("Nominal impedance", "Ω"), "re": ("Re (DC resistance)", "Ω"),
    "fs": ("Fs (resonance)", "Hz"), "qts": ("Qts", ""), "qes": ("Qes", ""), "qms": ("Qms", ""),
    "vas": ("Vas", "L"), "xmax": ("Xmax (one way)", "mm"), "sd": ("Sd (cone area)", "cm²"),
    "le": ("Le", "mH"), "bl": ("Bl", "T·m"), "mms": ("Mms", "g"), "sensitivity": ("Sensitivity (1 W/1 m)", "dB"),
    "power_rms": ("Power handling (RMS)", "W"), "freq_low": ("Usable range low", "Hz"), "freq_high": ("Usable range high", "Hz"),
    "hp_min": ("Manufacturer min. high-pass", "Hz"), "hp_min_slope": ("Min. high-pass slope", "dB/oct"),
    "lp_max": ("Manufacturer max. low-pass", "Hz"),
}
ENCLOSURE_SPECS = {"type": ("Type (sealed / ported / infinite baffle / door)", ""), "volume": ("Net volume", "L"),
                   "port_tuning": ("Port tuning (Fb)", "Hz")}
AMP_SPECS = {"channels": ("Channels", ""), "power_4ohm": ("Power per channel @ 4 Ω", "W"),
             "power_2ohm": ("Power per channel @ 2 Ω", "W"), "power_1ohm": ("Power per channel @ 1 Ω", "W"),
             "power_bridged": ("Bridged power", "W"), "max_voltage": ("Max supply voltage", "V"),
             "mode": ("Mode (stereo / bridged)", ""),
             "input_sensitivity": ("Input sensitivity range", "V"), "class": ("Class", "")}
KNOWN_SPECS = {Kind.SPEAKER: DRIVER_SPECS, Kind.SUBWOOFER: DRIVER_SPECS, Kind.ENCLOSURE: ENCLOSURE_SPECS,
               Kind.AMPLIFIER: AMP_SPECS}


def _num(c: Component, key: str) -> float | None:
    s = c.specs.get(key)
    if s is None:
        return None
    try:
        return float(s.value)
    except (TypeError, ValueError):
        return None


def analyze(design: SystemDesign, cid: str) -> dict:
    """Derived numbers and recommendations for one component, from its recorded specs."""
    c = design.get(cid)
    out: dict = {"id": c.id, "label": c.label, "findings": [], "derived": {}}
    if c.kind not in (Kind.SPEAKER, Kind.SUBWOOFER):
        return out
    fs, qts, vas, xmax, sd = (_num(c, k) for k in ("fs", "qts", "vas", "xmax", "sd"))
    if fs:
        out["derived"]["fs_hz"] = fs
        if c.kind is Kind.SUBWOOFER:
            out["findings"].append(f"Fs {fs:g} Hz. Subwoofers are protected by the subsonic high-pass rule; "
                                   "the box result below matters more than Fs alone.")
        else:
            out["findings"].append(f"Fs {fs:g} Hz. The safety policy sets the minimum high-pass from this by role "
                                   f"(defaults: tweeter 2×Fs = {2 * fs:.0f} Hz, midrange 1.5×Fs = {1.5 * fs:.0f} Hz, "
                                   f"midbass/woofer ≥ Fs).")
    if xmax and sd:
        vd = sd * xmax / 10  # cm² * mm -> cm³
        out["derived"]["vd_cm3"] = round(vd, 1)
    if qts is not None:
        kind = "sealed" if qts > 0.5 else "ported" if qts < 0.4 else "sealed or ported"
        out["findings"].append(f"Qts {qts:g} suits a {kind} enclosure (rule of thumb).")
    enc = None
    if c.enclosure:
        try:
            enc = design.get(c.enclosure)
        except KeyError:
            enc = None
    if enc and fs and qts and vas:
        vb_total = _num(enc, "volume")
        sharing = sum(1 for x in design.components if x.enclosure == enc.id) or 1
        vb = vb_total / sharing if vb_total else None  # a shared box gives each driver its share
        if vb and sharing > 1:
            out["findings"].append(f"Shared enclosure: {vb_total:g} L across {sharing} drivers → {vb:.1f} L each.")
        etype = str(enc.specs.get("type").value).lower() if enc.specs.get("type") else ""
        if vb and "seal" in etype:
            alpha = vas / vb
            qtc = qts * math.sqrt(1 + alpha)
            fc = fs * math.sqrt(1 + alpha)
            # -3 dB point of a 2nd-order high-pass with Q=qtc
            k = 1 / (2 * qtc ** 2) - 1
            f3 = fc * math.sqrt(k + math.sqrt(k * k + 1))
            out["derived"].update({"qtc": round(qtc, 3), "fc_hz": round(fc, 1), "f3_hz": round(f3, 1)})
            out["findings"].append(f"Sealed {vb:g} L: Qtc {qtc:.2f}, Fc {fc:.0f} Hz, F3 ≈ {f3:.0f} Hz "
                                   "(before cabin gain, which lifts the low end in a vehicle).")
        if vb and "port" in etype:
            fb = _num(enc, "port_tuning")
            if fb:
                sub = round(fb * 0.7)
                out["derived"]["recommended_subsonic_hz"] = sub
                out["findings"].append(f"Ported, tuned to {fb:g} Hz → subsonic high-pass around {sub} Hz protects "
                                       "the driver below tuning where the box stops controlling the cone.")
    return out


class DriverLimits(BaseModel):
    label: str
    fs: float | None = None
    hp_min: float | None = None        # manufacturer's recommended minimum high-pass
    hp_min_slope: float | None = None
    lp_max: float | None = None        # manufacturer's recommended maximum low-pass


def channel_driver_limits(design: SystemDesign) -> dict[str, DriverLimits]:
    """DSP channel -> the strictest recorded limits among the drivers it feeds."""
    out: dict[str, DriverLimits] = {}
    for c in design.components:
        if c.kind not in (Kind.SPEAKER, Kind.SUBWOOFER):
            continue
        lim = DriverLimits(label=c.label, fs=_num(c, "fs"), hp_min=_num(c, "hp_min"),
                           hp_min_slope=_num(c, "hp_min_slope"), lp_max=_num(c, "lp_max"))
        if lim.fs is None and lim.hp_min is None and lim.lp_max is None:
            continue
        for ch in c.channels:
            cur = out.get(ch)
            if cur is None:
                out[ch] = lim
                continue
            cur.fs = max(x for x in (cur.fs, lim.fs) if x is not None) if (cur.fs or lim.fs) else None
            cur.hp_min = max(x for x in (cur.hp_min, lim.hp_min) if x is not None) if (cur.hp_min or lim.hp_min) else None
            cur.lp_max = min(x for x in (cur.lp_max, lim.lp_max) if x is not None) if (cur.lp_max or lim.lp_max) else None
    return out


def normalize_ports(d: SystemDesign) -> bool:
    """Upgrade wires saved before ports had ids ("Out A" -> "outA"). Returns True if changed."""
    kinds = {c.id: c.kind for c in d.components}
    changed = False
    for cn in d.connections:
        sk, dk = kinds.get(cn.src), kinds.get(cn.dst)
        new_src, new_dst = cn.src_port, cn.dst_port
        if sk is Kind.DSP and cn.src_port.startswith("Out "):
            new_src = "out" + cn.src_port[4:].strip()
        if sk is Kind.VEHICLE_SOURCE and not cn.src_port and cn.signal is Signal.HIGH_LEVEL:
            new_src = "spk"
        if dk is Kind.DSP and not cn.dst_port and cn.signal is Signal.HIGH_LEVEL:
            new_dst = "hl"
        if dk in (Kind.SPEAKER, Kind.SUBWOOFER) and not cn.dst_port:
            new_dst = "in"
        if (new_src, new_dst) != (cn.src_port, cn.dst_port):
            cn.src_port, cn.dst_port = new_src, new_dst
            changed = True
    return changed


def seed(tune) -> SystemDesign:
    """Initial design from what we already know (the tune's channels, the DSP, the mic)."""
    from .model import Role

    d = SystemDesign()
    src = Component(kind=Kind.VEHICLE_SOURCE, name="Head unit / source")
    dsp = Component(kind=Kind.DSP, name="DSP", make="Audiotec Fischer", model="HELIX DSP PRO MK2",
                    spec_source="https://www.audiotec-fischer.de/",
                    specs={"outputs": Spec(value=10, source="parameter map (DSPPro2.at01)"),
                           "usb": Spec(value="FTDI USB-serial", source="PC-Tool 4.80b analysis")})
    mic = Component(kind=Kind.MICROPHONE, name="Measurement mic", make="miniDSP", model="UMIK-1", serial="7015199",
                    notes="90° calibration file used in 2018 measurements (7015199_90deg.txt)")
    d.components += [src, dsp, mic]
    d.connections.append(Connection(src=src.id, src_port="spk", dst=dsp.id, dst_port="hl", signal=Signal.HIGH_LEVEL,
                                    notes="input type not recorded yet"))
    for ch in tune.channels:
        if ch.role is Role.UNUSED:
            continue
        kind = Kind.SUBWOOFER if ch.role is Role.SUBWOOFER else Kind.SPEAKER
        spk = Component(kind=kind, name=ch.name or f"Channel {ch.id}", channels=[ch.id],
                        notes="model not recorded yet")
        d.components.append(spk)
        d.connections.append(Connection(src=dsp.id, src_port=f"out{ch.id}", dst=spk.id, dst_port="in", signal=Signal.LINE,
                                        notes="amplifier not recorded yet"))
    return d
