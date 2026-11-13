#!/usr/bin/env python3
"""beats.py <audio/video> <start_s> <dur_s> [--json]
Beat grid for a segment of a track: spectral-flux onset envelope -> tempo by autocorrelation
(70-180 BPM) -> phase fit -> beat times relative to start_s. Needs numpy (studio .venv).
Used to cut edits on the beat: snap each cut to the nearest beat (or bar, every 4th beat)."""
import subprocess, sys, json, os
import numpy as np
ST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR, HOP, NFFT = 22050, 256, 2048

def load(path, start, dur):
    raw = subprocess.run([f"{ST}/bin/ffmpeg", "-nostdin", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", path,
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)

def onset_env(x):
    win = np.hanning(NFFT).astype(np.float32)
    n = 1 + (len(x) - NFFT) // HOP
    frames = np.lib.stride_tricks.as_strided(x, (n, NFFT), (x.strides[0] * HOP, x.strides[0]))
    S = np.log1p(10 * np.abs(np.fft.rfft(frames * win, axis=1)))
    flux = np.maximum(0, np.diff(S, axis=0)).sum(1)
    flux = flux - np.convolve(flux, np.ones(16) / 16, "same")   # remove slow trend
    return np.maximum(flux, 0)

def track(path, start, dur):
    x = load(path, start, dur); env = onset_env(x); fps = SR / HOP
    ac = np.correlate(env - env.mean(), env - env.mean(), "full")[len(env) - 1:]
    lags = np.arange(len(ac)); bpm = 60 * fps / np.maximum(lags, 1)
    ok = (bpm >= 70) & (bpm <= 180)
    w = np.exp(-0.5 * (np.log2(bpm / 110) / 0.9) ** 2)          # mild prior around 110 BPM
    lag = lags[ok][np.argmax((ac * w)[ok])]
    # refine period with parabolic interpolation
    if 1 <= lag < len(ac) - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]; lag = lag + 0.5 * (a - c) / (a - 2 * b + c + 1e-9)
    period = lag / fps
    phases = np.linspace(0, period, 64, endpoint=False)
    def score(ph):
        t = np.arange(ph, dur, period); i = (t * fps).astype(int); i = i[i < len(env)]; return env[i].sum()
    ph = phases[np.argmax([score(p) for p in phases])]
    beats = np.arange(ph, dur, period)
    return 60 / period, beats.round(3).tolist()

if __name__ == "__main__":
    bpm, beats = track(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
    if "--json" in sys.argv: print(json.dumps({"bpm": round(bpm, 2), "beats": beats}))
    else: print(f"{bpm:.1f} BPM, first beats: {beats[:8]}")
