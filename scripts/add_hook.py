#!/usr/bin/env python3
"""add_hook.py <in.mp4> <out.mp4> "<hook text, \\n for line break>" [--hold SECONDS] [--badge TEXT] --client <slug>
Burns a flat hook (no outline/shadow: Matt wants flat Source Sans 3), first frames then fades out; optional badge (off by default), in the client's brand font, inside the 9:16 safe zone."""
import argparse, os, subprocess, tempfile
ap = argparse.ArgumentParser(); ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("hook")
ap.add_argument("--hold", type=float, default=3.2); ap.add_argument("--badge", default=""); ap.add_argument("--client", required=True)
a = ap.parse_args(); studio = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
brand = os.path.join(studio, "brand", a.client); black = os.path.join(brand, "SourceSans3-Bold.ttf"); semi = os.path.join(brand, "SourceSans3-Semibold.ttf")
tmp = tempfile.mkdtemp(); hf = os.path.join(tmp, "hook.txt"); bf = os.path.join(tmp, "badge.txt")
open(hf, "w").write(a.hook.replace("\\n", "\n")); open(bf, "w").write(a.badge)
h, f = a.hold, 0.25
alpha = f"if(lt(t,{f}),t/{f},if(lt(t,{h}),1,if(lt(t,{h+f}),({h+f}-t)/{f},0)))"
vf = (f"drawtext=fontfile={black}:textfile={hf}:fontsize=84:fontcolor=white:line_spacing=8:text_align=C:"
      f"x=(w-text_w)/2:y=520:alpha='{alpha}'")
if a.badge:  # off by default (Matt, 2026-11-08: badge not needed)
    vf += f",drawtext=fontfile={semi}:textfile={bf}:fontsize=38:fontcolor=white@0.92:x=72:y=280"
subprocess.run([os.path.join(studio, "bin", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", a.inp, "-vf", vf,
                "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "copy",
                "-map_metadata", "-1", "-movflags", "+faststart", a.out], check=True)
print("wrote", a.out)
