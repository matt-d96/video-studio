#!/usr/bin/env python3
"""make_fcpxml.py <clips.json> <out.fcpxml>
clips.json: {"source": path, "fps": 24, "src_w":1920, "src_h":1080, "event": name,
             "clips":[{"name":..,"start":sec,"dur":sec,"crop_x":px,"markers":[[sec_in_clip,"note"],...]}]}
One vertical 1080x1920 project per clip; source is spatially 'fill'-conformed, then shifted to match crop_x.
Optional "beat_markers": "beat"|"bar" adds a marker on every beat or bar of the source audio in each clip
(beats.py; needs the studio .venv python). Use them to cut on the beat in Final Cut. Added 11 Nov 2026.
UNVERIFIED on this Mac: the adjust-transform position unit (assumed % of frame height). Check C1 on first import."""
import json, sys, urllib.parse, subprocess, os
from xml.sax.saxutils import quoteattr as qa
cfg = json.load(open(sys.argv[1])); out = sys.argv[2]; fps = cfg["fps"]; W, H = cfg["src_w"], cfg["src_h"]
def t(sec): return f"{round(sec*fps)}/{fps}s"
studio = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dur = float(subprocess.check_output([os.path.join(studio,"bin","ffprobe"),"-v","error","-show_entries","format=duration","-of","csv=p=0",cfg["source"]]).decode())
src = "file://" + urllib.parse.quote(os.path.abspath(cfg["source"]))
x = ['<?xml version="1.0" encoding="UTF-8"?>','<!DOCTYPE fcpxml>','<fcpxml version="1.11">',' <resources>',
     f'  <format id="r1" name="FFVideoFormat1080p{fps}" frameDuration="1/{fps}s" width="{W}" height="{H}" colorSpace="1-1-1 (Rec. 709)"/>',
     f'  <format id="r2" frameDuration="1/{fps}s" width="1080" height="1920" colorSpace="1-1-1 (Rec. 709)"/>',
     f'  <asset id="a1" name={qa(os.path.basename(cfg["source"]))} start="0s" duration="{t(dur)}" hasVideo="1" format="r1" hasAudio="1" audioSources="1" audioChannels="2" audioRate="48000">',
     f'   <media-rep kind="original-media" src={qa(src)}/>','  </asset>',' </resources>',' <library>',f'  <event name={qa(cfg["event"])}>']
for c in cfg["clips"]:
    cx = c["crop_x"] + (H*9/16)/2; pos = round((W/2 - cx) * 100 / H, 2)   # source px offset → % of frame height after fill
    x += [f'   <project name={qa(c["name"])}>',
          f'    <sequence format="r2" duration="{t(c["dur"])}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">','     <spine>',
          f'      <asset-clip ref="a1" offset="0s" name={qa(c["name"])} start="{t(c["start"])}" duration="{t(c["dur"])}" format="r1" tcFormat="NDF">',
          '       <adjust-conform type="fill"/>', f'       <adjust-transform position="{pos} 0"/>']
    for m, note in c.get("markers", []):
        x.append(f'       <marker start="{t(c["start"]+m)}" duration="1/{fps}s" value={qa(note)}/>')
    if cfg.get("beat_markers"):
        sys.path.insert(0, os.path.join(studio, "scripts")); import beats
        bpm, bt = beats.track(cfg["source"], c["start"], c["dur"]); step = 4 if cfg["beat_markers"] == "bar" else 1
        for n, b in enumerate(bt[::step], 1):
            label = "%s %d (%.0f BPM)" % (cfg["beat_markers"], n, bpm)
            x.append(f'       <marker start="{t(c["start"]+b)}" duration="1/{fps}s" value={qa(label)}/>')
    x += ['      </asset-clip>','     </spine>','    </sequence>','   </project>']
x += ['  </event>',' </library>','</fcpxml>']
open(out, "w").write("\n".join(x) + "\n"); print("wrote", out)
