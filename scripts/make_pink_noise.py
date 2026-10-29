"""Write a loopable pink-noise test WAV for "Measure this seat" and time alignment.

Usage: python scripts/make_pink_noise.py [out.wav] [--level -20] [--seconds 120]

Built in the frequency domain (random phase, 1/sqrt(f) amplitude, band 20 Hz-20 kHz), so the
file is exactly periodic and loops with no seam. Mono, 48 kHz, 16-bit. Prints its own checks
(RMS, peak, power per octave, seam step) from the file as written.
"""
import argparse, wave
import numpy as np

FS = 48000

def make(seconds, level_dbfs, seed=7):
    n = FS * seconds
    f = np.fft.rfftfreq(n, 1 / FS)
    rng = np.random.default_rng(seed)
    spec = rng.standard_normal(f.size) + 1j * rng.standard_normal(f.size)
    band = (f >= 20) & (f <= 20000)
    spec[~band] = 0
    spec[band] /= np.sqrt(f[band])
    x = np.fft.irfft(spec, n)
    return x * 10 ** (level_dbfs / 20) / np.sqrt(np.mean(x ** 2))

def check(path):
    with wave.open(path, "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, FS)
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32767
    f = np.fft.rfftfreq(x.size, 1 / FS)
    p = np.abs(np.fft.rfft(x)) ** 2
    octaves = [10 * np.log10(p[(f >= lo) & (f < 2 * lo)].sum()) for lo in (31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000)]
    steps = np.abs(np.diff(x))
    return {
        "seconds": x.size / FS,
        "rms_dbfs": 20 * np.log10(np.sqrt(np.mean(x ** 2))),
        "peak_dbfs": 20 * np.log10(np.abs(x).max()),
        "octave_spread_db": max(octaves) - min(octaves),
        "seam_step": abs(x[0] - x[-1]),
        "p99_step": float(np.percentile(steps, 99)),
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="helixtune-pink-noise-20dBFS.wav")
    ap.add_argument("--level", type=float, default=-20.0)
    ap.add_argument("--seconds", type=int, default=120)
    a = ap.parse_args()
    x = make(a.seconds, a.level)
    assert np.abs(x).max() < 1, "clips; lower --level"
    with wave.open(a.out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes(np.round(x * 32767).astype("<i2").tobytes())
    for k, v in check(a.out).items():
        print(f"{k}: {v:.4f}")
