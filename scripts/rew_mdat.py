"""Extract measurements from a legacy REW .mdat (Java serialization) file."""
import sys, json
import javaobj.v2 as j

def fields(o):
    out = {}
    for cd, fs in getattr(o, "field_data", {}).items():
        for fd, v in fs.items():
            out[fd.name] = v
    return out

def arr(v):
    if v is None: return None
    if hasattr(v, "data"): return list(v.data)
    if isinstance(v, (list, tuple)): return list(v)
    return None

def extract(path):
    with open(path, "rb") as f:
        objs = j.load(f)
    meas = []
    for o in objs:
        cd = getattr(o, "classdesc", None)
        if cd is None or cd.name != "roomeqwizard.MeasData":
            continue
        F = fields(o)
        rec = {k: F[k] for k in ("sampleRate", "startFreq", "freqStep", "dataLength", "octaveFrac", "isLogSpaced", "measNotes") if k in F}
        for k in ("title", "measTitle", "name", "measName", "fullTitle"):
            if k in F: rec[k] = str(F[k])
        rec["arrays"] = {k: len(arr(v)) for k, v in F.items() if arr(v) is not None and len(arr(v)) > 16}
        rec["_fields"] = sorted(F)
        meas.append((rec, F))
    return meas

if __name__ == "__main__":
    for rec, F in extract(sys.argv[1]):
        r = dict(rec); flds = r.pop("_fields")
        print(json.dumps(r, default=str))
    print("fields:", flds)
