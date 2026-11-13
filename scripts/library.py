#!/usr/bin/env python3
"""library.py: the per-project content library behind /video-studio.

Every command takes a project slug from projects.json and touches ONLY that project's
sources. Items posted in the last N days (projects.json "exclude_posted_days", default 30)
are left out of every list, search and catalog view.

  library.py resolve [--cwd PATH]            which project this folder belongs to (JSON)
  library.py scan SLUG [--no-thumbs]         index local folders + imported Drive/Dropbox listings
  library.py add-remote SLUG drive|dropbox FILE.json [--stage raw|ready]
                                             import a connector listing (list of file entries)
  library.py posted SLUG NAME_OR_ID DATE [--platform ig] [--derived-from NAME ...]
                                             record that something went out (YYYY-MM-DD)
  library.py list SLUG [--category C] [--type video|photo|audio] [--stage S] [--source S]
                  [--search TEXT] [--sort date|duration|name|rating] [--limit N] [--json]
  library.py tag SLUG ID [--category C] [--tags a,b] [--rating 1-5] [--notes TEXT]
  library.py pick SLUG ID --set NAME [--in S] [--out S] [--note T] [--unpick]
  library.py picks SLUG [--set NAME] [--json]  the clip selection for a set, with paths and in/out
                                             (feeds beat_snap.py / make_fcpxml.py)
  library.py timeline SLUG --set S [--order id,id] [--music ID --start S] [--grid beat|half|bar] [--look L]
  library.py prompts SLUG [--all]            prompts Matt typed in the editor that wait for Claude
  library.py answer SLUG PID --reply T [--actions JSON]
  library.py path SLUG ID                    local path of an item (for editing)
  library.py excluded SLUG                   what is hidden by the posted rule, and why
  library.py serve SLUG [--port 8780]        catalog page: http://127.0.0.1:8780/
Ratings (stars) go to the one store, clients/<slug>/feedback/ratings.jsonl (ratings.py, 11 Nov 2026).
Picks for a set live in clients/<slug>/library/picks.json and are also logged there as kind "pick".
Stdlib only. Never posts, uploads or deletes anything.
"""
import argparse, datetime as dt, functools, hashlib, http.server, json, os, re, subprocess, sys, threading

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(STUDIO, "scripts"))
import ratings  # noqa: E402
import studio_media  # noqa: E402
REGISTRY = os.path.join(STUDIO, "projects.json")
BIN = os.path.join(STUDIO, "bin")
VIDEO = {".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm", ".mts"}
PHOTO = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".tif", ".tiff"}
AUDIO = {".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac"}
INDEX_LOCK = threading.Lock()


def load_registry():
    with open(REGISTRY) as f:
        return json.load(f)


def project(slug):
    reg = load_registry()
    if slug not in reg["projects"]:
        sys.exit(f"Unknown project '{slug}'. Registered: {', '.join(reg['projects'])}")
    return reg, reg["projects"][slug]


def libdir(slug):
    d = os.path.join(STUDIO, "clients", slug, "library")
    os.makedirs(os.path.join(d, "thumbs"), exist_ok=True)
    return d


def jload(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def jsave(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def kind(name):
    ext = os.path.splitext(name)[1].lower()
    return "video" if ext in VIDEO else "photo" if ext in PHOTO else "audio" if ext in AUDIO else None


def item_id(source, key):
    return hashlib.sha1(f"{source}:{key}".encode()).hexdigest()[:12]


# ---------- resolve ----------
def cmd_resolve(a):
    cwd = os.path.realpath(a.cwd or os.getcwd())
    reg = load_registry()
    best = None
    for slug, p in reg["projects"].items():
        root = os.path.realpath(p["project_dir"])
        if cwd == root or cwd.startswith(root + os.sep):
            if not best or len(root) > len(best[1]):
                best = (slug, root)
    if not best:
        print(json.dumps({"slug": None, "cwd": cwd, "registered": {s: p["project_dir"] for s, p in reg["projects"].items()}}, indent=1))
        sys.exit(2)
    p = reg["projects"][best[0]]
    print(json.dumps({"slug": best[0], "name": p["name"], "project_dir": p["project_dir"],
                      "library": libdir(best[0]), "exclude_posted_days": reg.get("exclude_posted_days", 30)}, indent=1))


# ---------- metadata ----------
def probe(path):
    try:
        out = subprocess.run([os.path.join(BIN, "ffprobe"), "-v", "error", "-show_entries",
                              "format=duration:stream=width,height,codec_type,codec_name,pix_fmt:stream_tags=rotate:format_tags=creation_time",
                              "-of", "json", path], capture_output=True, text=True, timeout=30).stdout
        j = json.loads(out or "{}")
    except Exception:
        return {}
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    w, h = v.get("width"), v.get("height")
    if str(v.get("tags", {}).get("rotate", "0")) in ("90", "270", "-90") and w and h:
        w, h = h, w
    dur = j.get("format", {}).get("duration")
    created = j.get("format", {}).get("tags", {}).get("creation_time")
    return {"width": w, "height": h, "duration": round(float(dur), 1) if dur else None, "created": created,
            "vcodec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt")}


def thumb(path, k, out):
    if os.path.exists(out):
        return True
    try:
        if k == "video":
            subprocess.run([os.path.join(BIN, "ffmpeg"), "-v", "error", "-y", "-ss", "1", "-i", path, "-frames:v", "1",
                            "-vf", "scale=360:-2", out], timeout=60, capture_output=True)
            if not os.path.exists(out):  # very short clip: grab the first frame
                subprocess.run([os.path.join(BIN, "ffmpeg"), "-v", "error", "-y", "-i", path, "-frames:v", "1",
                                "-vf", "scale=360:-2", out], timeout=60, capture_output=True)
        elif k == "photo":
            subprocess.run(["sips", "-s", "format", "jpeg", "-Z", "360", path, "--out", out], timeout=60, capture_output=True)
    except Exception:
        pass
    return os.path.exists(out)


def orientation(w, h):
    if not w or not h:
        return "unknown"
    r = w / h
    return "vertical" if r < 0.9 else "horizontal" if r > 1.1 else "square"


def length_bucket(d):
    if d is None:
        return None
    return "<15s" if d < 15 else "15–60s" if d <= 60 else "1–3 min" if d <= 180 else ">3 min"


def stage_of(path_lower, default):
    if any(s in path_lower for s in ("/exports/", "ready to post", "/finals/", "final")):
        return "ready"
    if any(s in path_lower for s in ("/edited/", "/reels 9x16/", "_v2", "_v3", "/social posts/")):
        return "edited"
    return default or "raw"


def auto_category(p, path_lower, k):
    for cat, words in p.get("category_rules", {}).items():
        if any(w in path_lower for w in words):
            return cat
    if k == "audio":
        return "audio"
    if k == "photo":
        return next((c for c in p.get("categories", []) if c.startswith("photo")), "photo")
    return "uncategorised"


# ---------- posted rule ----------
DATE = re.compile(r"(20\d\d-\d\d-\d\d)")


def norm(s):
    return os.path.basename(s.strip().strip("`\"'")).lower()


def posted_records(slug, p):
    """Every known 'this went out on <date>' record: (name_or_id_lower, date, where)."""
    recs = []
    for log in p.get("posted_logs", []):
        path = log["path"]
        if not os.path.exists(path):
            continue
        if log["type"] == "markdown_table":
            for line in open(path, encoding="utf-8", errors="ignore"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 2 or not DATE.match(cells[0]):
                    continue
                low = line.lower()
                if "never posted" in low or "not posted" in low:
                    continue
                date = DATE.match(cells[0]).group(1)
                for tok in re.findall(r"`([^`]+)`|\"([^\"]+\.[A-Za-z0-9]{2,4})\"", " | ".join(cells[1:])):
                    t = tok[0] or tok[1]
                    if kind(t):
                        recs.append((norm(t), date, os.path.basename(path)))
        elif log["type"] == "week_sheet_csv":  # week-plan sheets: Media + "Posted? (date)" columns
            import csv, glob
            for f in glob.glob(path):
                for row in csv.DictReader(open(f, encoding="utf-8", errors="ignore")):
                    m = DATE.search(row.get("Posted? (date)") or "")
                    if m:
                        for media in (row.get("Media") or "").split(";"):
                            if media.strip():
                                recs.append((norm(media), m.group(1), os.path.basename(os.path.dirname(f))))
        elif log["type"] == "path_date_json":
            for k, v in jload(path, {}).items():
                m = DATE.search(str(v))
                if m:
                    recs.append((norm(k), m.group(1), os.path.basename(path)))
    ledger = os.path.join(libdir(slug), "posted.jsonl")
    if os.path.exists(ledger):
        for line in open(ledger):
            try:
                e = json.loads(line)
            except Exception:
                continue
            for key in [e["key"]] + e.get("derived_from", []):
                recs.append((norm(key), e["date"], "posted.jsonl"))
    return recs


def posted_index(slug, p, days):
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    latest = {}
    for key, date, where in posted_records(slug, p):
        if key not in latest or date > latest[key][0]:
            latest[key] = (date, where)
    return {k: v for k, v in latest.items() if v[0] >= cutoff}, latest


def local_item(p, root, full, old=None):
    """One index entry for a local file (probe + metadata). Used by scan and by uploads."""
    fn, k = os.path.basename(full), kind(full)
    st = os.stat(full)
    iid = item_id("local", os.path.realpath(full))
    prev = (old or {}).get(iid, {})
    if prev.get("size") == st.st_size and prev.get("mtime") == int(st.st_mtime) and (k != "video" or "vcodec" in prev):
        meta = {x: prev.get(x) for x in ("width", "height", "duration", "created", "vcodec", "pix_fmt")}
    else:
        meta = probe(full) if k in ("video", "audio") else {}
        if k == "photo":
            try:
                out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", full], capture_output=True, text=True, timeout=20).stdout
                meta = {"width": int(re.search(r"pixelWidth: (\d+)", out).group(1)), "height": int(re.search(r"pixelHeight: (\d+)", out).group(1))}
            except Exception:
                meta = {}
    rel = os.path.relpath(full, root)
    low = "/" + full.lower()
    return {
        "id": iid, "source": "local", "name": fn, "path": full, "folder": os.path.dirname(rel) or os.path.basename(root),
        "root": root, "type": k, "size": st.st_size, "mtime": int(st.st_mtime),
        "date": (meta.get("created") or dt.datetime.fromtimestamp(st.st_mtime).isoformat())[:10],
        **meta, "orientation": orientation(meta.get("width"), meta.get("height")),
        "length": length_bucket(meta.get("duration")), "stage": stage_of(low, None),
        "auto_category": auto_category(p, low, k),
    }


def index_add(slug, full):
    """Add (or refresh) one local file in the index without a full rescan. Returns the item."""
    reg, p = project(slug)
    d = libdir(slug)
    root = next((r for r in p.get("local_folders", []) if os.path.realpath(full).startswith(os.path.realpath(r) + os.sep)), os.path.dirname(full))
    it = local_item(p, root, full)
    it["posted"] = None; it["posted_via"] = None
    it["thumb"] = thumb(full, it["type"], os.path.join(d, "thumbs", it["id"] + ".jpg"))
    with INDEX_LOCK:
        idx = jload(os.path.join(d, "index.json"), {"project": slug, "items": [], "excluded": [], "exclude_posted_days": reg.get("exclude_posted_days", 30)})
        idx.setdefault("scanned_at", dt.datetime.now().isoformat(timespec="seconds"))
        idx["items"] = [i for i in idx["items"] if i["id"] != it["id"]] + [it]
        jsave(os.path.join(d, "index.json"), idx)
    return it


# ---------- scan ----------
def cmd_scan(a):
    reg, p = project(a.slug)
    days = reg.get("exclude_posted_days", 30)
    d = libdir(a.slug)
    old = {i["id"]: i for i in jload(os.path.join(d, "index.json"), {}).get("items", [])}
    items, seen_paths = [], set()
    skip = set(p.get("local_skip", []))
    for root in p.get("local_folders", []):
        if not os.path.isdir(root):
            print(f"  missing local folder: {root}")
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in skip and not x.startswith(".")]
            for fn in files:
                k = kind(fn)
                full = os.path.join(dirpath, fn)
                if not k or fn.startswith(".") or os.path.realpath(full) in seen_paths:
                    continue
                seen_paths.add(os.path.realpath(full))
                items.append(local_item(p, root, full, old))
    # remote listings imported with add-remote
    for r in jload(os.path.join(d, "remote.json"), {"items": []})["items"]:
        low = ("/" + r.get("folder", "") + "/" + r["name"]).lower()
        r.update({"orientation": orientation(r.get("width"), r.get("height")), "length": length_bucket(r.get("duration")),
                  "stage": r.get("stage") or stage_of(low, None), "auto_category": auto_category(p, low, r["type"])})
        items.append(r)
    # posted rule
    recent, _ = posted_index(a.slug, p, days)
    kept, hidden = [], []
    for it in items:
        hit = recent.get(it["name"].lower()) or recent.get(str(it.get("remote_id", "")).lower())
        (hidden if hit else kept).append({**it, "posted": hit[0] if hit else None, "posted_via": hit[1] if hit else None})
    # thumbnails for local items
    for it in kept:
        if it["source"] == "local":
            tp = os.path.join(d, "thumbs", it["id"] + ".jpg")
            it["thumb"] = os.path.exists(tp) if a.no_thumbs else thumb(it["path"], it["type"], tp)
    jsave(os.path.join(d, "index.json"), {"project": a.slug, "scanned_at": dt.datetime.now().isoformat(timespec="seconds"),
                                          "exclude_posted_days": days, "items": kept, "excluded": hidden})
    by = {}
    for it in kept:
        by[it["source"]] = by.get(it["source"], 0) + 1
    print(f"{p['name']}: {len(kept)} items indexed ({', '.join(f'{v} {k}' for k, v in by.items()) or 'none'}); "
          f"{len(hidden)} hidden (posted in the last {days} days).")
    if not jload(os.path.join(d, "remote.json"), {"items": []})["items"] and (p.get("drive_folders") or p.get("dropbox_folders")):
        print("  Drive/Dropbox not imported yet: list the folders with the connectors, then run add-remote.")


# ---------- remote import ----------
def cmd_add_remote(a):
    reg, p = project(a.slug)
    d = libdir(a.slug)
    raw = jload(a.file, None)
    if raw is None:
        sys.exit(f"Can't read {a.file}")
    if isinstance(raw, dict):
        raw = raw.get("files") or raw.get("entries") or raw.get("items") or []
    store = jload(os.path.join(d, "remote.json"), {"items": []})
    keep = [i for i in store["items"] if not (i["source"] == a.source and (a.stage is None or i.get("stage") == a.stage) and a.replace)]
    have = {i["id"] for i in keep}
    added = 0
    for e in raw:
        name = e.get("title") or e.get("name")
        if not name:
            continue
        mime = e.get("mimeType") or e.get("mime_type") or ""
        k = kind(name) or ("video" if mime.startswith("video/") else "photo" if mime.startswith("image/") else "audio" if mime.startswith("audio/") else None)
        if not k:
            continue
        rid = (e.get("path") or e.get("file_id")) if a.source == "dropbox" else (e.get("id") or e.get("file_id") or e.get("path"))
        iid = item_id(a.source, rid)
        if iid in have:
            continue
        have.add(iid)
        keep.append({
            "id": iid, "source": a.source, "remote_id": rid, "name": name, "type": k, "size": e.get("size") or e.get("fileSize") or e.get("file", {}).get("size"),
            "folder": e.get("folder") or a.folder or os.path.dirname(e.get("path_display") or re.sub(r"^ns:\d+//", "", e.get("path") or "")) or "", "path": e.get("path") or e.get("path_display"),
            "url": e.get("viewUrl") or e.get("url") or e.get("webViewLink"),
            "date": (e.get("createdTime") or e.get("client_modified") or e.get("modifiedTime") or e.get("modified_time") or "")[:10],
            "width": e.get("width"), "height": e.get("height"), "duration": e.get("duration"), "stage": e.get("stage") or a.stage,
        })
        added += 1
    jsave(os.path.join(d, "remote.json"), {"items": keep})
    print(f"Added {added} {a.source} items to {p['name']} ({len(keep)} remote in total). Run: library.py scan {a.slug}")


# ---------- posted ledger ----------
def cmd_posted(a):
    reg, p = project(a.slug)
    if not DATE.fullmatch(a.date):
        sys.exit("DATE must be YYYY-MM-DD")
    e = {"key": a.key, "date": a.date, "platform": a.platform, "derived_from": a.derived_from or [],
         "logged_at": dt.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(libdir(a.slug), "posted.jsonl"), "a") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Logged: {a.key} posted {a.date} ({a.platform}). Re-run scan to apply.")


# ---------- list / tag ----------
def merged(slug):
    d = libdir(slug)
    idx = jload(os.path.join(d, "index.json"), None)
    if idx is None:
        sys.exit(f"No index yet. Run: library.py scan {slug}")
    tags = jload(os.path.join(d, "tags.json"), {})
    stars = ratings.item_ratings(slug)
    picks = jload(os.path.join(d, "picks.json"), {})
    auto = jload(os.path.join(d, "autotags.json"), {})
    for it in idx["items"]:
        t = tags.get(it["id"], {})
        it["category"] = t.get("category") or it.get("auto_category")
        it["tags"], it["notes"] = t.get("tags", []), t.get("notes", "")
        it["rating"] = stars[it["id"]] if it["id"] in stars else t.get("rating")
        it["picked_in"] = sorted(k for k, v in picks.items() if v.get(it["id"], {}).get("pick"))
        au = auto.get(it["id"])
        if au: it["auto"] = au
        if it["source"] == "local":
            it["play"] = (f"/proxy/{it['id']}.mp4" if studio_media.needs_proxy(it) else f"/file/{it['id']}") if it["type"] != "photo" else f"/img/{it['id']}.jpg"
    return idx


def cmd_list(a):
    idx = merged(a.slug)
    rows = idx["items"]
    if a.category: rows = [r for r in rows if (r["category"] or "").lower() == a.category.lower()]
    if a.type: rows = [r for r in rows if r["type"] == a.type]
    if a.stage: rows = [r for r in rows if r.get("stage") == a.stage]
    if a.source: rows = [r for r in rows if r["source"] == a.source]
    if a.search:
        q = a.search.lower()
        rows = [r for r in rows if q in (r["name"] + " " + r.get("folder", "") + " " + " ".join(r["tags"]) + " " + r["notes"]).lower()]
    key = {"date": lambda r: r.get("date") or "", "duration": lambda r: r.get("duration") or 0,
           "name": lambda r: r["name"].lower(), "rating": lambda r: r.get("rating") or 0}[a.sort]
    rows.sort(key=key, reverse=a.sort != "name")
    rows = rows[: a.limit] if a.limit else rows
    if a.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False)); return
    for r in rows:
        dur = f"{r['duration']:.0f}s" if r.get("duration") else "  -"
        print(f"{r['id']}  {r.get('date') or '':10}  {r['type']:5} {r['orientation']:10} {dur:>5}  {r['source']:7} "
              f"{(r['category'] or ''):18.18} {('★' * (r['rating'] or 0)):5}  {r['folder'][:28]:28}  {r['name']}")
    print(f"\n{len(rows)} shown · {len(idx['excluded'])} hidden (posted in the last {idx['exclude_posted_days']} days) · scanned {idx['scanned_at']}")


def save_tag(slug, iid, category=None, tags=None, rating=None, notes=None):
    d = libdir(slug)
    allt = jload(os.path.join(d, "tags.json"), {})
    t = allt.get(iid, {})
    if category is not None: t["category"] = category
    if tags is not None: t["tags"] = [x.strip() for x in tags if x.strip()]
    if rating is not None: t["rating"] = int(rating) if rating else None
    if notes is not None: t["notes"] = notes
    t["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    allt[iid] = t
    jsave(os.path.join(d, "tags.json"), allt)
    if rating is not None:  # the one rating store; tags.json keeps a copy for old readers
        ratings.add(slug, {"v": 2, "kind": "clip", "item": iid, "batch": None, "overall": int(rating) if rating else None,
                           "scores": {}, "note": t.get("notes", ""), "tags": t.get("tags", []), "by": "matt", "source": "catalog"})
    return t


def save_pick(slug, iid, setname, pick=True, tin=None, tout=None, note=None):
    if not setname:
        raise ValueError("set name required")
    d = libdir(slug)
    allp = jload(os.path.join(d, "picks.json"), {})
    p = allp.setdefault(setname, {}).get(iid, {})
    p["pick"] = bool(pick)
    if tin is not None: p["in"] = float(tin) if tin != "" else None
    if tout is not None: p["out"] = float(tout) if tout != "" else None
    if note is not None: p["note"] = note
    p["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    allp[setname][iid] = p
    jsave(os.path.join(d, "picks.json"), allp)
    ratings.add(slug, {"v": 2, "kind": "pick", "item": iid, "batch": setname, "overall": None, "scores": {},
                       "verdict": "Keep" if p["pick"] else "Cut", "note": p.get("note", ""), "in": p.get("in"), "out": p.get("out"),
                       "by": "matt", "source": "pick"})
    return p


def cmd_pick(a):
    find(a.slug, a.id)
    print(json.dumps(save_pick(a.slug, a.id, a.set, not a.unpick, a.tin, a.tout, a.note)))


def cmd_picks(a):
    idx = merged(a.slug)
    byid = {i["id"]: i for i in idx["items"]}
    allp = jload(os.path.join(libdir(a.slug), "picks.json"), {})
    sets = [a.set] if a.set else sorted(allp)
    out = []
    for s in sets:
        for iid, p in allp.get(s, {}).items():
            if not p.get("pick"):
                continue
            it = byid.get(iid)
            out.append({"set": s, "id": iid, "name": it["name"] if it else None, "path": it.get("path") if it else None,
                        "source": it["source"] if it else None, "in": p.get("in"), "out": p.get("out"), "note": p.get("note", ""),
                        "available": bool(it)})
    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False)); return
    for r in out:
        io = f"{r['in'] if r['in'] is not None else '-'} -> {r['out'] if r['out'] is not None else '-'}"
        print(f"{r['set'][:20]:20} {r['id']}  {io:16} {'' if r['available'] else '(hidden or gone) '}{r['name']}  {r['note']}")
    print(f"\n{len(out)} picked" + (f" in {a.set}" if a.set else f" across {len(sets)} set(s)"))


def cmd_tag(a):
    print(json.dumps(save_tag(a.slug, a.id, a.category, a.tags.split(",") if a.tags is not None else None, a.rating, a.notes)))


def find(slug, iid):
    idx = merged(slug)
    it = next((i for i in idx["items"] if i["id"] == iid), None)
    if not it and any(i["id"] == iid for i in idx["excluded"]):
        sys.exit("That item was posted in the last 30 days, so it's excluded.")
    if not it:
        sys.exit("No such item. Run list to see ids.")
    return it


def cmd_timeline(a):
    kw = {}
    if a.order is not None: kw["order"] = [x for x in a.order.split(",") if x]
    if a.music: kw["music"] = {"id": a.music, "start": a.start or 0.0}
    if a.grid: kw["grid"] = a.grid
    if a.look is not None: kw["look"] = a.look or None
    m = set_update(a.slug, a.set, **kw) if kw else sets_load(a.slug).get(a.set, {})
    print(json.dumps({**m, "timeline": timeline(a.slug, a.set)}, indent=1, ensure_ascii=False))


def cmd_prompts(a):
    import studio_ai
    q = studio_ai.queue(a.slug)
    rows = [e for e in q.values() if a.all or e["status"] == "queued"]
    for e in sorted(rows, key=lambda e: e["asked_at"]):
        print(json.dumps(e, ensure_ascii=False))
    print(f"# {len(rows)} prompt(s){'' if a.all else ' waiting'}. Answer: library.py answer {a.slug} <id> --reply \"...\" [--actions '[...]']")


def cmd_answer(a):
    import studio_ai
    acts = json.loads(a.actions) if a.actions else []
    print(json.dumps(studio_ai.answer(a.slug, a.id, a.reply, acts), ensure_ascii=False))


def cmd_path(a):
    it = find(a.slug, a.id)
    print(it["path"] if it["source"] == "local" else json.dumps({"source": it["source"], "remote_id": it["remote_id"], "url": it.get("url")}))


def cmd_excluded(a):
    idx = merged(a.slug)
    for r in idx["excluded"]:
        print(f"{r['posted']}  via {r['posted_via']:22}  {r['source']:7}  {r['name']}")
    print(f"\n{len(idx['excluded'])} hidden (posted in the last {idx['exclude_posted_days']} days)")


# ---------- sets (the editor's timelines) ----------
# library/sets.json: {set: {"order": [ids], "music": {"id": .., "start": s} | null, "look": name | null,
#                           "grid": "beat|half|bar", "snapped": {...} | null}}
DEFAULT_DUR = 2.5


def sets_load(slug):
    return jload(os.path.join(libdir(slug), "sets.json"), {})


def set_update(slug, name, **kw):
    allm = sets_load(slug)
    m = allm.setdefault(name, {"order": [], "music": None, "look": None, "grid": "beat", "snapped": None})
    for k, v in kw.items():
        if k in ("order", "music", "look", "grid", "snapped", "rights", "beat"):
            m[k] = v
    if any(k in kw for k in ("order", "music", "grid", "beat")) and "snapped" not in kw:
        m["snapped"] = None  # timeline changed: the old beat snap no longer applies
    jsave(os.path.join(libdir(slug), "sets.json"), allm)
    return m


def timeline(slug, name):
    """Picked clips of a set in timeline order, with in/out and planned length."""
    picks = {k: v for k, v in jload(os.path.join(libdir(slug), "picks.json"), {}).get(name, {}).items() if v.get("pick")}
    order = [i for i in sets_load(slug).get(name, {}).get("order", []) if i in picks]
    order += sorted((i for i in picks if i not in order), key=lambda i: picks[i].get("updated", ""))
    out = []
    for i in order:
        pk = picks[i]
        tin = pk.get("in") or 0.0
        dur = (pk["out"] - tin) if pk.get("out") is not None and pk["out"] > tin else DEFAULT_DUR
        out.append({"id": i, "in": round(tin, 3), "dur": round(dur, 3), "note": pk.get("note", "")})
    return out


def build_edl(slug, name, need_music=False):
    m = sets_load(slug).get(name) or {}
    byid = {i["id"]: i for i in merged(slug)["items"]}
    tl = timeline(slug, name)
    if not tl:
        raise ValueError("No clips in this set's timeline yet.")
    bad = [c["id"] for c in tl if c["id"] not in byid or byid[c["id"]]["source"] != "local"]
    if bad:
        raise ValueError(f"{len(bad)} clip(s) aren't local (or were posted in the last 30 days): bring them into the inbox first.")
    mu = m.get("music")
    edl = {"grid": m.get("grid") or "beat", "client": slug, "look": m.get("look"), "set": name,
           "snap": m.get("beat", True) is not False, "mute": not m.get("rights"),
           "clips": [{"id": c["id"], "src": byid[c["id"]]["path"], "in": c["in"], "dur": c["dur"]} for c in tl]}
    if mu and mu.get("id") in byid and byid[mu["id"]]["source"] == "local":
        edl.update(music=byid[mu["id"]]["path"], music_start=float(mu.get("start") or 0))
    elif need_music:
        raise ValueError("Add a song first: beat matching needs music.")
    return edl


RENDERS = {}
UPLOAD_DIRS = {"clip": "", "reference": "references", "music": "music"}
MAX_UPLOAD = 8 * 1024 ** 3


def safe_name(n):
    n = os.path.basename(n or "").strip().replace("\x00", "")
    n = re.sub(r"[^\w.\- ()&+,@]", "_", n)[:120]
    return n if n and not n.startswith(".") else "upload"


def wave_png(slug, it):
    out = os.path.join(libdir(slug), "waves", it["id"] + ".png")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        w = max(400, min(8000, int((it.get("duration") or 60) * 20)))
        subprocess.run([os.path.join(BIN, "ffmpeg"), "-v", "error", "-y", "-i", it["path"], "-filter_complex",
                        f"[0:a]aformat=channel_layouts=mono,compand,showwavespic=s={w}x80:colors=#bff2d6[w]", "-map", "[w]",
                        "-frames:v", "1", out], capture_output=True, timeout=120)
    return out if os.path.exists(out) else None


def ai_context(slug, name, sel):
    import studio_ai
    idx = merged(slug)
    tl = timeline(slug, name) if name else []
    m = sets_load(slug).get(name, {}) if name else {}
    refs = [i for i in idx["items"] if (i.get("category") or "") == "reference"]
    try:
        import grade
        looks = ", ".join(grade.looks()); dflt = grade.client_default(slug)[0]
    except Exception:
        looks, dflt = "", None
    selit = next((i for i in idx["items"] if i["id"] == sel), None)
    return (f"PROJECT: {idx.get('project')}  TODAY: {dt.date.today().isoformat()}\n"
            f"CURRENT TIMELINE: {name or '(none: use new_timeline first)'}  grid={m.get('grid')} look={m.get('look') or 'client default ' + str(dflt)}\n"
            f"  music: {m.get('music')}\n  clips in order: {json.dumps(tl)}\n"
            f"SELECTED: {selit['id'] + ' ' + selit['name'] if selit else 'none'}\n"
            f"LOOKS: {looks}\n"
            f"REFERENCE VIDEOS (Matt's examples of what he wants): {json.dumps([{'id': r['id'], 'name': r['name'], 'notes': r.get('notes', '')} for r in refs])}\n"
            f"LIBRARY (id | type | name | length | shape | category | stars | stage | source | folder | tags | notes):\n"
            + studio_ai.listing(idx["items"]))


# ---------- catalog / editor server ----------
def cmd_serve(a):
    reg, p = project(a.slug)
    d = libdir(a.slug)
    page = os.path.join(STUDIO, "scripts", "simple.html")
    pro_page = os.path.join(STUDIO, "scripts", "studio.html")
    catalog_page = os.path.join(STUDIO, "scripts", "library.html")
    try:
        n = studio_media.warm_proxies(d, [i for i in jload(os.path.join(d, "index.json"), {}).get("items", []) if i.get("source") == "local"])
        if n: print(f"  making {n} browser-playable preview(s) in the background")
    except Exception:
        pass
    AUTOTAG = {"state": "idle", "done": 0, "total": 0, "error": ""}

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json", extra=None):
            if isinstance(body, (dict, list)): body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                return self._send(200, open(page, "rb").read(), "text/html; charset=utf-8")
            if path == "/pro":
                return self._send(200, open(pro_page, "rb").read(), "text/html; charset=utf-8")
            if path == "/catalog":
                return self._send(200, open(catalog_page, "rb").read(), "text/html; charset=utf-8")
            if path == "/api/picks":
                return self._send(200, jload(os.path.join(d, "picks.json"), {}))
            if path == "/api/sets":
                allm = sets_load(a.slug)
                names = set(allm) | set(jload(os.path.join(d, "picks.json"), {}))
                return self._send(200, {n: {**allm.get(n, {}), "timeline": timeline(a.slug, n)} for n in names})
            if path == "/api/looks":
                try:
                    import grade
                    L = grade.looks(); dflt = grade.client_default(a.slug)
                except Exception as err:
                    return self._send(200, {"looks": {}, "default": None, "error": str(err)})
                return self._send(200, {"looks": {k: {"label": v["label"], "desc": v["desc"]} for k, v in L.items()},
                                        "default": dflt[0], "default_from": dflt[1]})
            m = re.fullmatch(r"/(proxy|img)/([0-9a-f]{12})\.(mp4|jpg)", path)
            if m:
                it = next((i for i in merged(a.slug)["items"] if i["id"] == m.group(2) and i["source"] == "local"), None)
                if not it: return self._send(404, {"error": "not a local, non-excluded item"})
                f = studio_media.proxy(d, it) if m.group(1) == "proxy" else studio_media.view_image(d, it)
                return self._file(f) if f else self._send(500, {"error": "couldn't make a preview of this file"})
            m = re.fullmatch(r"/look/([0-9a-f]{12})/([a-z_]+)\.jpg", path)
            if m:
                from urllib.parse import urlparse, parse_qs
                import grade
                it = next((i for i in merged(a.slug)["items"] if i["id"] == m.group(1) and i["source"] == "local"), None)
                L = grade.looks()
                if not it or m.group(2) not in L: return self._send(404, {"error": "no such clip or look"})
                try: t = float(parse_qs(urlparse(self.path).query).get("t", ["0"])[0])
                except ValueError: t = 0.0
                f = studio_media.look_frame(d, it, m.group(2), L[m.group(2)]["filter"], t)
                return self._send(200, open(f, "rb").read(), "image/jpeg", {"Cache-Control": "max-age=86400"}) if f else self._send(500, {"error": "no frame"})
            if path == "/api/job":
                from urllib.parse import urlparse, parse_qs
                j = studio_media.JOBS.get(parse_qs(urlparse(self.path).query).get("id", [""])[0])
                if not j: return self._send(404, {"error": "no such job"})
                if j["state"] == "done" and "item" not in j:
                    it = index_add(a.slug, j["file"]); save_tag(a.slug, it["id"], category="music"); j["item"] = it["id"]
                return self._send(200, {k: v for k, v in j.items() if k != "file"})
            if path == "/api/autotag":
                au = jload(os.path.join(d, "autotags.json"), {})
                loc = [i for i in merged(a.slug)["items"] if i["source"] == "local" and i["type"] != "audio" and i.get("thumb")]
                return self._send(200, {**AUTOTAG, "tagged": sum(1 for i in loc if i["id"] in au), "taggable": len(loc)})
            m = re.fullmatch(r"/wave/([0-9a-f]{12})\.png", path)
            if m:
                it = next((i for i in merged(a.slug)["items"] if i["id"] == m.group(1) and i["source"] == "local"), None)
                f = wave_png(a.slug, it) if it and it["type"] in ("audio", "video") else None
                return self._send(200, open(f, "rb").read(), "image/png") if f else self._send(404, {"error": "no waveform"})
            if path == "/api/ai":
                import studio_ai
                from urllib.parse import urlparse, parse_qs
                pid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
                if not pid:
                    return self._send(200, {"cli": bool(studio_ai.cli()), "signed_in": studio_ai._cli["ok"], "why": studio_ai._cli["why"],
                                            "queued": sum(1 for e in studio_ai.queue(a.slug).values() if e["status"] == "queued")})
                e = studio_ai.queue(a.slug).get(pid)
                return self._send(200, e or {"error": "no such prompt"})
            if path == "/api/render":
                from urllib.parse import urlparse, parse_qs
                name = parse_qs(urlparse(self.path).query).get("set", [""])[0]
                j = RENDERS.get(name)
                if not j: return self._send(200, {"state": "none"})
                code = j["proc"].poll()
                tail = open(j["log"]).read()[-1500:] if os.path.exists(j["log"]) else ""
                if code == 0 and "item" not in j and os.path.exists(j["out"]):
                    try: j["item"] = index_add(a.slug, j["out"])["id"]
                    except Exception: j["item"] = None
                return self._send(200, {"state": "running" if code is None else "done" if code == 0 else "failed",
                                        "out": j["out"], "log": tail, "item": j.get("item")})
            if path == "/api/index":
                idx = merged(a.slug)
                return self._send(200, {**idx, "project": p["name"], "categories": p.get("categories", []),
                                        "excluded": [{"name": x["name"], "posted": x["posted"]} for x in idx["excluded"]]})
            m = re.fullmatch(r"/thumb/([0-9a-f]{12})\.jpg", path)
            if m:
                f = os.path.join(d, "thumbs", m.group(1) + ".jpg")
                return self._send(200, open(f, "rb").read(), "image/jpeg") if os.path.exists(f) else self._send(404, {"error": "no thumb"})
            m = re.fullmatch(r"/file/([0-9a-f]{12})", path)
            if m:
                it = next((i for i in merged(a.slug)["items"] if i["id"] == m.group(1) and i["source"] == "local"), None)
                if not it: return self._send(404, {"error": "not a local, non-excluded item"})
                return self._file(it["path"])
            return self._send(404, {"error": "not found"})

        def _file(self, f):
            size = os.path.getsize(f)
            ext = os.path.splitext(f)[1].lower()
            ctype = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}.get(ext, "application/octet-stream")
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
                if m.group(1): start = int(m.group(1))
                if m.group(2): end = min(int(m.group(2)), size - 1)
            length = end - start + 1
            self.send_response(206 if rng else 200)
            self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(length))
            if rng: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(f, "rb") as fh:
                fh.seek(start); left = length
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk: break
                    try: self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError): return
                    left -= len(chunk)

        def do_POST(self):
            if self.path.startswith("/api/upload"):
                return self._upload()
            if self.path.startswith("/api/transcribe"):
                n = int(self.headers.get("Content-Length", 0))
                if n <= 0 or n > 40_000_000: return self._send(413, {"error": "recording empty or too long"})
                try: return self._send(200, {"text": studio_media.transcribe(self.rfile.read(n))})
                except Exception as err: return self._send(500, {"error": f"Couldn't transcribe: {err}"})
            if self.path not in ("/api/tag", "/api/pick", "/api/set", "/api/snap", "/api/render", "/api/ai", "/api/music", "/api/autotag"): return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length", 0))
            if n > 100_000: return self._send(413, {"error": "too large"})
            try: e = json.loads(self.rfile.read(n))
            except Exception: return self._send(400, {"error": "bad json"})
            if self.path == "/api/music":
                try: jid = studio_media.music_import(str(e.get("url") or ""), os.path.join(STUDIO, "clients", a.slug, "inbox", "music"))
                except ValueError as err: return self._send(400, {"error": str(err)})
                return self._send(200, {"ok": True, "job": jid})
            if self.path == "/api/autotag":
                import studio_ai
                if AUTOTAG["state"] == "running": return self._send(200, AUTOTAG)
                if not studio_ai.cli(): return self._send(400, {"error": "Claude Code isn't installed on this Mac."})
                ids = [i["id"] for i in merged(a.slug)["items"] if i["source"] == "local" and i["type"] != "audio" and i.get("thumb")]
                AUTOTAG.update(state="running", done=0, total=0, error="")
                def run():
                    try:
                        r = studio_media.autotag(studio_ai.cli(), d, ids, lambda dn, tot, er: AUTOTAG.update(done=dn, total=tot, error=er))
                        AUTOTAG.update(state="done", error="; ".join(r["errors"]))
                    except Exception as err:
                        AUTOTAG.update(state="failed", error=str(err))
                threading.Thread(target=run, daemon=True).start()
                return self._send(200, AUTOTAG)
            if self.path == "/api/ai":
                import studio_ai
                prompt = str(e.get("prompt") or "").strip()[:4000]
                if not prompt: return self._send(400, {"error": "prompt required"})
                name = str(e.get("set") or "").strip()
                ctx = ai_context(a.slug, name, e.get("sel"))
                res, why = (None, "queued by request") if e.get("queue") else studio_ai.ask_live(ctx, prompt)
                if res is not None:
                    ids = {i["id"] for i in merged(a.slug)["items"]}
                    acts = [x for x in (res.get("actions") or []) if isinstance(x, dict) and
                            all(v in ids for v in ([x["id"]] if x.get("id") else []) + list(x.get("ids") or []))]
                    return self._send(200, {"mode": "live", "reply": res.get("reply", ""), "actions": acts,
                                            "dropped": len(res.get("actions") or []) - len(acts)})
                q = studio_ai.enqueue(a.slug, prompt, {"set": name, "sel": e.get("sel")})
                return self._send(200, {"mode": "queued", "id": q["id"], "why": why})
            if self.path in ("/api/set", "/api/snap", "/api/render"):
                name = str(e.get("set") or "").strip()
                if not name or "/" in name or name.startswith("."): return self._send(400, {"error": "set name required"})
                if self.path == "/api/set":
                    kw = {k: e[k] for k in ("order", "music", "look", "grid", "rights", "beat") if k in e}
                    if "music" in kw and kw["music"] and not re.fullmatch(r"[0-9a-f]{12}", str(kw["music"].get("id", ""))):
                        return self._send(400, {"error": "bad music id"})
                    return self._send(200, {"ok": True, **set_update(a.slug, name, **kw), "timeline": timeline(a.slug, name)})
                try:
                    edl = build_edl(a.slug, name)
                except ValueError as err:
                    return self._send(400, {"error": str(err)})
                pdir = os.path.join(STUDIO, "clients", a.slug, "projects", name)
                os.makedirs(pdir, exist_ok=True)
                jsave(os.path.join(pdir, "edl.json"), edl)
                if self.path == "/api/snap":
                    try:
                        import beat_snap
                        edl = build_edl(a.slug, name, need_music=True)
                        s = beat_snap.snap(edl)
                    except ValueError as err:
                        return self._send(400, {"error": str(err)})
                    except ImportError:
                        return self._send(500, {"error": "Beat snap needs numpy: run serve with the studio .venv python."})
                    except SystemExit as err:
                        return self._send(400, {"error": str(err)})
                    jsave(os.path.join(pdir, "edl.snapped.json"), s)
                    snapped = {"bpm": s["bpm"], "grid": s["grid"], "music_start": s["music_start"], "beats": s["beats"],
                               "length": s["length"], "durs": {c["id"]: c["dur"] for c in s["clips"]}}
                    set_update(a.slug, name, snapped=snapped)
                    return self._send(200, {"ok": True, **snapped})
                if name in RENDERS and RENDERS[name]["proc"].poll() is None:
                    return self._send(409, {"error": "A render of this set is already running."})
                ex = os.path.join(STUDIO, "clients", a.slug, "exports", name if re.match(r"\d{4}-\d{2}-\d{2}", name) else f"{dt.date.today().isoformat()}_{name}")
                os.makedirs(ex, exist_ok=True)
                out = os.path.join(ex, f"{name}.mp4")
                log = os.path.join(pdir, "render.log")
                py = os.path.join(STUDIO, ".venv", "bin", "python")
                proc = subprocess.Popen([py if os.path.exists(py) else sys.executable, "-u", os.path.join(STUDIO, "scripts", "beat_snap.py"),
                                         os.path.join(pdir, "edl.json"), "--render", out], stdout=open(log, "w"), stderr=subprocess.STDOUT)
                RENDERS[name] = {"proc": proc, "out": out, "log": log}
                return self._send(200, {"ok": True, "state": "running", "out": out})
            if not re.fullmatch(r"[0-9a-f]{12}", str(e.get("id", ""))): return self._send(400, {"error": "id required"})
            if self.path == "/api/pick":
                try: pk = save_pick(a.slug, e["id"], str(e.get("set") or "").strip(), e.get("pick", True), e.get("in"), e.get("out"), e.get("note"))
                except ValueError as err: return self._send(400, {"error": str(err)})
                return self._send(200, {"ok": True, **pk})
            t = save_tag(a.slug, e["id"], e.get("category"), e.get("tags"), e.get("rating"), e.get("notes"))
            return self._send(200, {"ok": True, **t})

        def _upload(self):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            kind_ = q.get("kind", ["clip"])[0]
            if kind_ not in UPLOAD_DIRS: return self._send(400, {"error": "kind must be clip, reference or music"})
            name = safe_name(q.get("name", [""])[0])
            if not kind(name): return self._send(400, {"error": "Only video, audio or photo files."})
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > MAX_UPLOAD: return self._send(413, {"error": "empty or over 8 GB"})
            inbox = os.path.join(STUDIO, "clients", a.slug, "inbox", UPLOAD_DIRS[kind_])
            os.makedirs(inbox, exist_ok=True)
            base, ext = os.path.splitext(name)
            dest = os.path.join(inbox, f"{dt.date.today().isoformat()}_{base}{ext}")
            k2 = 1
            while os.path.exists(dest):
                k2 += 1; dest = os.path.join(inbox, f"{dt.date.today().isoformat()}_{base}-{k2}{ext}")
            left = n
            with open(dest + ".part", "wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk: break
                    fh.write(chunk); left -= len(chunk)
            if left:
                os.remove(dest + ".part"); return self._send(400, {"error": "upload cut off"})
            os.replace(dest + ".part", dest)
            it = index_add(a.slug, dest)
            if kind_ == "reference":
                save_tag(a.slug, it["id"], category="reference")
            elif kind_ == "music":
                save_tag(a.slug, it["id"], category="music")
            return self._send(200, {"ok": True, "item": {**it, "category": "reference" if kind_ == "reference" else "music" if kind_ == "music" else it.get("auto_category")}})

        def log_message(self, *x): pass

    print(f"{p['name']} studio: http://127.0.0.1:{a.port}/  (simple catalog: /catalog)  (Ctrl-C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("resolve"); s.add_argument("--cwd"); s.set_defaults(f=cmd_resolve)
    s = sp.add_parser("scan"); s.add_argument("slug"); s.add_argument("--no-thumbs", action="store_true"); s.set_defaults(f=cmd_scan)
    s = sp.add_parser("add-remote"); s.add_argument("slug"); s.add_argument("source", choices=["drive", "dropbox"]); s.add_argument("file")
    s.add_argument("--stage"); s.add_argument("--folder", help="folder name to record (Drive listings have no path)"); s.add_argument("--replace", action="store_true", help="drop this source's earlier listing first"); s.set_defaults(f=cmd_add_remote)
    s = sp.add_parser("posted"); s.add_argument("slug"); s.add_argument("key"); s.add_argument("date"); s.add_argument("--platform", default="instagram")
    s.add_argument("--derived-from", nargs="*"); s.set_defaults(f=cmd_posted)
    s = sp.add_parser("list"); s.add_argument("slug")
    for o in ("--category", "--type", "--stage", "--source", "--search"): s.add_argument(o)
    s.add_argument("--sort", default="date", choices=["date", "duration", "name", "rating"]); s.add_argument("--limit", type=int); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_list)
    s = sp.add_parser("tag"); s.add_argument("slug"); s.add_argument("id")
    for o in ("--category", "--tags", "--rating", "--notes"): s.add_argument(o)
    s.set_defaults(f=cmd_tag)
    s = sp.add_parser("pick"); s.add_argument("slug"); s.add_argument("id"); s.add_argument("--set", required=True)
    s.add_argument("--in", dest="tin"); s.add_argument("--out", dest="tout"); s.add_argument("--note"); s.add_argument("--unpick", action="store_true"); s.set_defaults(f=cmd_pick)
    s = sp.add_parser("picks"); s.add_argument("slug"); s.add_argument("--set"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_picks)
    s = sp.add_parser("timeline"); s.add_argument("slug"); s.add_argument("--set", required=True); s.add_argument("--order")
    s.add_argument("--music"); s.add_argument("--start", type=float); s.add_argument("--grid", choices=["beat", "half", "bar"]); s.add_argument("--look"); s.set_defaults(f=cmd_timeline)
    s = sp.add_parser("prompts"); s.add_argument("slug"); s.add_argument("--all", action="store_true"); s.set_defaults(f=cmd_prompts)
    s = sp.add_parser("answer"); s.add_argument("slug"); s.add_argument("id"); s.add_argument("--reply", required=True); s.add_argument("--actions"); s.set_defaults(f=cmd_answer)
    s = sp.add_parser("path"); s.add_argument("slug"); s.add_argument("id"); s.set_defaults(f=cmd_path)
    s = sp.add_parser("excluded"); s.add_argument("slug"); s.set_defaults(f=cmd_excluded)
    s = sp.add_parser("serve"); s.add_argument("slug"); s.add_argument("--port", type=int, default=8780); s.set_defaults(f=cmd_serve)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
