#!/usr/bin/env python3
"""contact_sheet.py <video> <candidates.json> <out.jpg> [clip_len]
One row per candidate start (seconds): frames at +0.5s, middle, end, each with a yellow 9:16 centre-crop guide."""
import json, subprocess, sys, os, tempfile
studio = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); FF = os.path.join(studio, "bin", "ffmpeg")
video, cand, out = sys.argv[1:4]; L = float(sys.argv[4]) if len(sys.argv) > 4 else 20
font = "/System/Library/Fonts/Supplemental/Arial.ttf"; tmp = tempfile.mkdtemp(); rows = []
for i, s in enumerate(json.load(open(cand)), 1):
    cells = []
    for j, o in enumerate((0.5, L / 2, L - 1)):
        label = f"C{i}  {int(s)//60:02d}m{int(s)%60:02d}s +{o:g}s"
        p = os.path.join(tmp, f"{i}_{j}.png"); cells.append(p)
        vf = ("scale=480:270,drawbox=x=164:y=0:w=152:h=270:color=yellow@0.9:t=2,"
              f"drawtext=fontfile={font}:text='{label}':x=6:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6")
        subprocess.run([FF, "-loglevel", "error", "-y", "-ss", str(s + o), "-i", video, "-frames:v", "1", "-vf", vf, p], check=True)
    r = os.path.join(tmp, f"row{i}.png"); rows.append(r)
    subprocess.run([FF, "-loglevel", "error", "-y", *sum([["-i", c] for c in cells], []), "-filter_complex", "hstack=3", r], check=True)
subprocess.run([FF, "-loglevel", "error", "-y", *sum([["-i", r] for r in rows], []), "-filter_complex", f"vstack={len(rows)}", "-q:v", "3", out], check=True)
print("wrote", out)
