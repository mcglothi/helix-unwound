"""Summarise decoded .afpx presets (one-off analysis helper)."""
import sys, zlib, xml.etree.ElementTree as ET
from pathlib import Path

def load(p):
    b = Path(p).read_bytes()
    return ET.fromstring(zlib.decompress(b[4:]))

for p in sys.argv[1:]:
    r = load(p)
    print(f"\n=== {Path(p).name}  V={r.get('V')} Dev={r.get('Dev')} D={r.get('D')}")
    for oc in r.findall("OC"):
        if oc.find("Fil") is None:
            continue
        fils = {int(f.get("FN")) % 100: f for f in oc.findall("Fil")}
        t = oc.find("T"); v = oc.find("Vol")
        lp, hp = fils.get(30), fils.get(31)
        xo = lambda f: f"{f.get('F')}Hz/{f.get('G')}dB T{f.get('T')} Q{f.get('Q')} I{f.get('I')}" if f is not None else "-"
        eq = [f"{f.get('F')}:{f.get('G')}@{f.get('Q')}(T{f.get('T')})" for n, f in sorted(fils.items()) if n < 30 and float(f.get("G")) != 0]
        print(f" ON{oc.get('ON'):>2} CN{oc.get('CN'):>2} DG{oc.get('DG')} LG{oc.get('LG')} MT{oc.get('MT')} INV{oc.get('CINV')} "
              f"T={t.get('T')} PM={t.get('PM')} P={t.get('P')} GD={oc.get('GD','-')[:6]} L={float(v.get('L')):.3f} "
              f"HP[{xo(hp)}] LP[{xo(lp)}] hpBy{oc.get('hpBy')} lpBy{oc.get('lpBy')} EqBy{oc.get('EqBy')}")
        if eq: print("      EQ", " ".join(eq))
