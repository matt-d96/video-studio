#!/usr/bin/env python3
"""beat_snap.py: cut an edit on the beat (added 11 Nov 2026: "make sure the
clips are beat matched to the music").

  beat_snap.py EDL.json [--out SNAPPED.json] [--render OUT.mp4] [--grid beat|bar|half]
EDL.json:
  {"music": "<audio or video file>", "music_start": 30.0,         # where the bed starts in that file
   "grid": "beat",                                               # beat | bar (every 4th beat) | half (every 2nd)
   "client": "<slug>", "look": "night_moody",                       # look optional; else the client's default (grade.py)
   "fade": 0.3,
   "clips": [{"src": "<file>", "in": 12.5, "dur": 2.0, "crop_x": 600}, ...]}   # dur = the length you want
Each cut moves to the nearest grid point after the previous one (never shorter than 1 beat), so the first
frame of every shot lands on a beat. Writes the snapped EDL (with "bpm", "beats" and real "dur"s) and, with
--render, a 1080x1920 30fps H.264 file: graded footage, music bed only (source audio dropped), -14 LUFS.
Bar lines assume bar 1 starts on the first detected beat: check by ear, and shift with "bar_offset": 1-3.
Released songs (where a client's rules say so) go in with the platform's audio picker, never baked in (CLAUDE.md): for those, use
the render as a guide cut only, or render with "mute": true.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import beats as B  # noqa: E402
import grade as G  # noqa: E402

FF = os.path.join(STUDIO, "bin", "ffmpeg")


def snap(edl, grid=None):
    grid = grid or edl.get("grid", "beat")
    want = sum(c["dur"] for c in edl["clips"])
    bpm, bt = B.track(edl["music"], float(edl.get("music_start", 0)), want + 8)
    step = {"beat": 1, "half": 2, "bar": 4}[grid]
    if grid == "beat":
        off = 0
    elif "bar_offset" in edl:
        off = int(edl["bar_offset"])
    else:  # beat 1 = the beat phase with the most low-end (kick) energy (Matt, 13 Nov 2026: cut on the 1st beat of the bar)
        import numpy as np
        s0 = float(edl.get("music_start", 0)); x = B.load(edl["music"], s0, want + 8)
        lp = np.convolve(x, np.ones(64) / 64, "same"); sr = B.SR
        en = [float(np.sum(lp[int(t * sr):int((t + .1) * sr)] ** 2)) for t in bt]
        off = int(np.argmax([np.mean(en[p::step]) for p in range(step)]))
    pts = bt[off::step]
    if not pts:
        sys.exit("No beats found in that part of the track.")
    origin = pts[0]  # first shot starts on the first grid point
    pts = [p - origin for p in pts]
    period = 60 / bpm
    t, out = 0.0, []
    for c in edl["clips"]:
        target = t + c["dur"]
        later = [p for p in pts if p >= t + period * 0.99]
        if not later:
            sys.exit("Track segment too short for these clips: lower the durations or move music_start.")
        cut = min(later, key=lambda p: abs(p - target))
        cut = round(cut * 30) / 30  # frame-exact (30 fps), so per-clip rounding never adds up across cuts
        out.append({**c, "want": c["dur"], "dur": round(cut - t, 6)})
        t = cut
    return {**edl, "grid": grid, "bpm": round(bpm, 2), "music_start": round(float(edl.get("music_start", 0)) + origin, 3),
            "beats": [round(p, 3) for p in pts if p <= t + 0.01], "clips": out, "length": round(t, 3)}


PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff", ".gif"}


def is_photo(p):
    return os.path.splitext(p)[1].lower() in PHOTO_EXT


def has_audio(p):
    try:
        out = subprocess.run([os.path.join(STUDIO, "bin", "ffprobe"), "-v", "error", "-select_streams", "a", "-show_entries",
                              "stream=index", "-of", "csv=p=0", p], capture_output=True, text=True, timeout=20).stdout
        return bool(out.strip())
    except Exception:
        return False


def photo_src(p):
    """ffmpeg can't read HEIC: convert once to a JPEG beside the render (sips, macOS)."""
    if os.path.splitext(p)[1].lower() != ".heic":
        return p
    out = os.path.join(STUDIO, "tools", "models", ".heic-cache", str(abs(hash(p))) + ".jpg")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["sips", "-s", "format", "jpeg", p, "--out", out], capture_output=True, timeout=60)
    return out


def plain(edl):
    """No beat snapping: keep the lengths as asked (photos-only edits, or beat matching switched off)."""
    t = sum(c["dur"] for c in edl["clips"])
    return {**edl, "grid": "none", "bpm": None, "beats": [], "length": round(t, 3),
            "music_start": float(edl.get("music_start", 0)), "clips": [{**c, "want": c["dur"]} for c in edl["clips"]]}


def render(s, out):
    look = s.get("look")
    vf_look = (G.chain(look) if look else G.chain(G.client_default(s["client"])[0])) if (look or s.get("client")) else None
    args, parts = [FF, "-hide_banner", "-loglevel", "error", "-y"], []
    n = len(s["clips"])
    music = s.get("music")
    for i, c in enumerate(s["clips"]):
        photo = is_photo(c["src"])
        if photo:
            args += ["-loop", "1", "-framerate", "30", "-t", str(c["dur"]), "-i", photo_src(c["src"])]
        else:
            args += ["-ss", str(c.get("in", 0)), "-t", str(c["dur"]), "-i", c["src"]]
        crop = (f"crop=trunc(ih*9/16/2)*2:ih:{c['crop_x']}:0,scale=1080:1920:flags=lanczos" if c.get("crop_x") is not None
                else "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
        parts.append(f"[{i}:v]{crop},setsar=1,fps=30" + (f",{vf_look}" if vf_look else "") +
                     f",format=yuv420p,trim=duration={c['dur']},setpts=PTS-STARTPTS[v{i}]")
        if not music:  # no music bed: keep each clip's own sound, silence under photos
            if not photo and has_audio(c["src"]):
                parts.append(f"[{i}:a]atrim=0:{c['dur']},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]")
            else:
                parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{c['dur']}[a{i}]")
    parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]")
    fade = min(float(s.get("fade", 0.3)), s["length"] / 4)
    tail = f"afade=t=in:d={fade},afade=t=out:st={max(0, s['length'] - fade)}:d={fade},loudnorm=I=-14:TP=-1.5:LRA=11"
    if music:
        args += ["-ss", str(s["music_start"]), "-t", str(s["length"]), "-i", music]
        a = f"[{n}:a]atrim=0:{s['length']},asetpts=PTS-STARTPTS,{tail}" + (",volume=0" if s.get("mute") else "")
        parts.append(a + "[a]")
    else:
        parts.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1,{tail}[a]")
    args += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-dn", "-map_metadata", "-1",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", out]
    subprocess.run(args, check=True)
    print(f"wrote {out} ({s['length']}s, {s.get('bpm')} BPM, grid {s['grid']}, look {look or 'client default'}"
          f"{', music muted (guide only)' if music and s.get('mute') else ''})", flush=True)
    subprocess.run([os.path.join(STUDIO, "scripts", "release-check"), out])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl"); ap.add_argument("--out"); ap.add_argument("--render"); ap.add_argument("--grid", choices=["beat", "half", "bar"])
    a = ap.parse_args()
    edl = json.load(open(a.edl))
    s = snap(edl, a.grid) if edl.get("music") and edl.get("snap", True) else plain(edl)
    out = a.out or os.path.splitext(a.edl)[0] + ".snapped.json"
    json.dump(s, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"{s['bpm']} BPM · grid {s['grid']} · {len(s['clips'])} cuts · {s['length']}s · wrote {out}", flush=True)
    for c in s["clips"]:
        print(f"  {os.path.basename(c['src'])[:30]:30} in {c.get('in', 0):>6}  wanted {c['want']:>5}s  -> {c['dur']:>5}s", flush=True)
    if a.render:
        render(s, a.render)


if __name__ == "__main__":
    main()
