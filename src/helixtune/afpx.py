"""PC-Tool preset files (.afpx): qCompress()'d XML.

Structure (observed in PC-Tool 4.20b presets for Dev=15, HELIX DSP PRO MK2):
  <ATF TM OUTS=12 INS=12 Dev V D AV>
    <OC ON=out# CN=name# LG=link group DG=delay group CINV MT ...>   x12
      <Fil FN=ON*100+n T=type F=Hz G=dB Q I dF=default Hz/>     n 0..29 EQ, 30 LP, 31 HP
      <Vol T L=linear gain i/>
      <T T=delay samples PM P=unknown/>  P is not the phase shown in PC-Tool
    <IC IN CN ...> x12 with 5 input-EQ bands (FN=IN//2*200+n)
    <Route><R .../></Route>   routing matrices
    <DCM> device config </DCM>
    <PCT DL/>

Attribute meanings marked PROVISIONAL are inferred from presets, not yet from the
PC-Tool code. Unknown attributes are preserved verbatim in `raw` so export can
round-trip them.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from .dsp.filters import EqType, XoType
from .model import CHANNELS, EQ_BANDS, Channel, Crossover, EqBand, Role, Tune

PRO_MK2_DEV = "15"

# CN index -> name (PC-Tool string table, order as shipped)
CHANNEL_NAMES = [
    "Not assigned", "Front L Full", "Front R Full", "Front L High", "Front R High", "Front L Mid",
    "Front R Mid", "Front L Low", "Front R Low", "Front Center Full", "Front Center High",
    "Front Center Low", "F Sum", "Rear L Full", "Rear R Full", "Rear L High", "Rear R High", "Rear L Mid",
    "Rear R Mid", "Rear L Low", "Rear R Low", "Rear Fill Full", "Rear Fill High", "Rear Fill Low",
    "Rear Sum", "Subwoofer 1", "Subwoofer 2", "Subwoofer 3", "Subwoofer 4", "Line Out 1",
    "Line Out 2", "Line Out 3", "Line Out 4", "Line Out 5", "Line Out 6", "Line Out 7", "Line Out 8",
    "Subwoofer L", "Subwoofer R",
]

# Fil T codes (PROVISIONAL): crossover active/bypassed, EQ band types
XO_LP_ON, XO_HP_ON = 15, 16
XO_LP_OFF, XO_HP_OFF = 9, 10
EQ_TYPE_CODES = {17: EqType.PEAK, 1: EqType.PEAK}


def read_xml(path: str | Path) -> ET.Element:
    data = Path(path).read_bytes()
    n = int.from_bytes(data[:4], "big")
    xml = zlib.decompress(data[4:])
    if len(xml) != n:
        raise ValueError(f"{path}: length header {n} != {len(xml)}")
    return ET.fromstring(xml)


def write_xml(root: ET.Element, path: str | Path) -> None:
    xml = ET.tostring(root, encoding="utf-8")
    Path(path).write_bytes(len(xml).to_bytes(4, "big") + zlib.compress(xml, 9))


def role_for(name: str) -> Role:
    if name.startswith("Subwoofer"):
        return Role.SUBWOOFER
    if name.endswith("High"):
        return Role.TWEETER
    if name.endswith("Mid"):
        return Role.MIDRANGE
    if name.endswith("Low"):
        return Role.MIDBASS
    if name.endswith("Full") or name.startswith("Line Out") or name == "Rear Sum":
        return Role.FULLRANGE
    return Role.UNUSED


@dataclass
class ImportReport:
    source: str
    version: str
    date: str
    warnings: list[str] = field(default_factory=list)


def _xo(fil: ET.Element | None, on_code: int) -> Crossover | None:
    if fil is None or int(fil.get("T", -1)) != on_code:
        return None
    slope = abs(round(float(fil.get("G", "-24"))))
    slope = min(48, max(6, 6 * round(slope / 6)))
    # PROVISIONAL: characteristic not yet decoded; Q 0.7 ~ Butterworth pole Q.
    return Crossover(type=XoType.BUTTERWORTH if slope % 12 else XoType.LINKWITZ_RILEY,
                     slope_db=slope, freq_hz=float(fil.get("F")))


def to_tune(root: ET.Element, name: str, sample_rate: float = 96000.0) -> tuple[Tune, ImportReport]:
    rep = ImportReport(source=name, version=root.get("V", "?"), date=root.get("D", "?"))
    if root.get("Dev") != PRO_MK2_DEV:
        rep.warnings.append(f"preset is for device type {root.get('Dev')}, not PRO MK2 ({PRO_MK2_DEV})")
    tune = Tune(name=name)
    for oc in root.findall("OC"):
        on = int(oc.get("ON"))
        if on >= len(CHANNELS):
            continue  # aux outputs beyond A-J
        ch: Channel = tune.channels[on]
        cn = int(oc.get("CN", 0))
        cname = CHANNEL_NAMES[cn] if 0 <= cn < len(CHANNEL_NAMES) else f"CN{cn}"
        fils = {int(f.get("FN")) % 100: f for f in oc.findall("Fil")}
        ch.name = "" if cn == 0 else cname
        ch.role = role_for(cname) if cn else Role.UNUSED
        lg = oc.get("LG", "0")
        ch.link_group = int(lg) if cn and lg.isdigit() and int(lg) <= 99 else 0
        if cn and ch.link_group == 0 and lg not in ("0", ""):
            rep.warnings.append(f"{ch.id}: unsupported link group {lg!r}; imported unlinked")
        ch.invert = oc.get("CINV") == "1"
        ch.mute = oc.get("MT") == "0"  # PROVISIONAL: MT=1 active
        vol = oc.find("Vol")
        if vol is not None:
            lin = float(vol.get("L", "1"))
            ch.gain_db = round(20 * math.log10(lin), 2) if lin > 0 else -60.0
        t = oc.find("T")
        if t is not None and t.get("T") is not None:
            ch.delay_ms = round(int(t.get("T")) / sample_rate * 1000, 4)  # samples at 96 kHz; compared with PC-Tool 4.80b demo output
            if float(t.get("P", "0")) != 0:
                rep.warnings.append(f"{ch.id}: unknown preset T.P={t.get('P')} (PM={t.get('PM')}) not applied; this is not the phase displayed by PC-Tool")
        ch.hp = _xo(fils.get(31), XO_HP_ON)
        ch.lp = _xo(fils.get(30), XO_LP_ON)
        bands = []
        for n in range(EQ_BANDS):
            f = fils.get(n)
            if f is None:
                bands.append(EqBand())
                continue
            g = float(f.get("G", "0"))
            code = int(f.get("T", 17))
            if code not in EQ_TYPE_CODES:
                rep.warnings.append(f"{ch.id} band {n + 1}: unknown type code {code}, treated as peak")
            bands.append(EqBand(enabled=g != 0, type=EQ_TYPE_CODES.get(code, EqType.PEAK),
                                freq_hz=float(f.get("F")), gain_db=g,
                                q=min(30.0, max(0.1, float(f.get("Q", "1"))))))
        ch.eq = bands
    # routing: PC-Tool edits the 12-input main matrix (AOM 1, G index = out*12 + in, inputs 0/1 =
    # Digital In L/R; captures 23/24). Older/other presets: fall back to the 2-input matrix (AOM 9).
    matrices = {(R.get("INS"), R.get("AOM")): {int(k[1:]): float(v) for k, v in R.attrib.items() if k.startswith("G")}
                for R in root.findall("Route/R")}
    main, opto = matrices.get(("12", "1")), matrices.get(("2", "9"))
    if main is not None:
        for i, ch in enumerate(tune.channels):
            ch.mix = {name: main.get(i * 12 + n, 0.0) for n, name in enumerate(("L", "R")) if main.get(i * 12 + n, 0.0)}
            if any(main.get(i * 12 + n, 0.0) for n in range(2, 12)):
                rep.warnings.append(f"{ch.id}: routing from inputs other than Digital In L/R is not supported and was dropped")
            if opto is not None and any(main.get(i * 12 + n, 0.0) != opto.get(i * 2 + n, 0.0) for n in range(2)):
                rep.warnings.append(f"{ch.id}: main and digital routing matrices disagree; the main matrix was used")
    elif opto is not None:
        for i, ch in enumerate(tune.channels):
            ch.mix = {name: opto.get(i * 2 + n, 0.0) for n, name in enumerate(("L", "R")) if opto.get(i * 2 + n, 0.0)}
    else:
        rep.warnings.append("no routing matrix found; channels keep default L/R routing")
    return tune, rep


def load(path: str | Path) -> tuple[Tune, ImportReport]:
    p = Path(path)
    return to_tune(read_xml(p), p.stem)
