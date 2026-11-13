#!/usr/bin/env python3
"""ratings.py: the one rating store for a client (added 11 Nov 2026).

Every rating Matt gives, from any page, lands in ONE file: clients/<slug>/feedback/ratings.jsonl.
Before this there were three: catalog stars (library/tags.json), review-page scores (ratings.jsonl)
and one-off pick files (feedback/picks-*.json, grade-pick-*.json). Those old files are kept, untouched.

One record shape (every line, append-only, the latest line per (kind, batch, item) wins):
  {"v": 2, "kind": "clip|edit|look|pick", "item": "<library id, clip id or look name>",
   "batch": "<batch or set name, or null>", "file": "<file name>",
   "overall": 1-5 | null,
   "scores": {"moment": 1-5, "look": 1-5, "sound": 1-5, "pacing": 1-5},   # any subset
   "verdict": "Keep|Swap|Cut|" , "note": "...", "tags": [...], "timed_notes": [{"t": s, "text": ...}],
   "better_hook": "...", "by": "matt|claude", "source": "catalog|review|grade|pick|cli",
   "saved_at": ISO time}
  - kind "clip": a library item (raw or edited), rated in the catalog. item = library id.
  - kind "edit": a clip in a review batch. item = clip id (C1, A2 ...).
  - kind "look": a colour-grade look in a grade board. overall 5 = the picked look.
  - kind "pick": a clip picked for a set (in/out points). Kept here so picks are evidence too.
Old review-page lines (7 scores) are read through normalise(), so nothing needs rewriting.
The 7 old scores map to 4: moment, look = mean(framing, hook_look), sound, pacing. hook_text stays
in legacy_scores (Matt's hook rewrite, better_hook, is the stronger hook signal).

  ratings.py add SLUG --kind K --item ID [--batch B] [--overall N] [--moment N --look N --sound N --pacing N]
                 [--verdict V] [--note TEXT] [--by matt|claude]
  ratings.py latest SLUG [--kind K] [--batch B] [--json]
  ratings.py migrate SLUG      rewrite old lines to v2 (keeps a .bak copy) and import catalog stars + pick files
Stdlib only.
"""
import argparse, datetime as dt, glob, json, os, statistics, sys

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBS = ("moment", "look", "sound", "pacing")


def store(slug):
    d = os.path.join(STUDIO, "clients", slug, "feedback")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "ratings.jsonl")


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _n(v):
    try:
        v = int(v)
        return v if 1 <= v <= 5 else None
    except (TypeError, ValueError):
        return None


def normalise(e):
    """Any old or new record -> v2 fields (old fields are kept alongside, so old pages still load)."""
    if e.get("v") == 2:
        return e
    old = e.get("scores") or {}
    out = dict(e)
    out["v"] = 2
    out.setdefault("kind", "edit")
    out.setdefault("item", e.get("clip"))
    out["overall"] = _n(old.get("overall"))
    looks = [x for x in (_n(old.get("framing")), _n(old.get("hook_look")), _n(old.get("look"))) if x]
    out["legacy_scores"] = old
    out["scores"] = {k: v for k, v in {
        "moment": _n(old.get("moment")),
        "look": round(statistics.mean(looks)) if looks else None,
        "sound": _n(old.get("sound")),
        "pacing": _n(old.get("pacing")),
    }.items() if v}
    notes = e.get("notes") or {}
    parts = [e.get("general") or ""] + [f"{k}: {v}" for k, v in notes.items() if v]
    out.setdefault("note", " | ".join(p for p in parts if p))
    out.setdefault("by", "matt")
    out.setdefault("source", "review")
    return out


def read(slug):
    p = store(slug)
    rows = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            try:
                rows.append(normalise(json.loads(line)))
            except Exception:
                pass
    return rows


def latest(slug, kind=None, batch=None):
    last = {}
    for e in read(slug):
        if kind and e.get("kind") != kind:
            continue
        if batch is not None and e.get("batch") != batch:
            continue
        last[(e.get("kind"), e.get("batch"), e.get("item"))] = e
    return list(last.values())


def add(slug, rec):
    """Append one record. rec may be old-shape (review page) or v2; it is normalised and timestamped."""
    if not isinstance(rec, dict) or not (rec.get("item") or rec.get("clip")):
        raise ValueError("item (or clip) required")
    e = normalise(rec)
    for k in ("overall",):
        if k in rec:
            e[k] = _n(rec[k])
    if isinstance(rec.get("scores"), dict) and rec.get("v") == 2:
        e["scores"] = {k: _n(v) for k, v in rec["scores"].items() if k in SUBS and _n(v)}
    e["saved_at"] = now()
    with open(store(slug), "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def item_ratings(slug):
    """Latest catalog star per library id (kind clip), for the catalog and list --sort rating."""
    return {e["item"]: e.get("overall") for e in latest(slug, kind="clip")}


def cmd_add(a):
    rec = {"v": 2, "kind": a.kind, "item": a.item, "batch": a.batch, "overall": a.overall,
           "scores": {k: getattr(a, k) for k in SUBS if getattr(a, k)}, "verdict": a.verdict or "",
           "note": a.note or "", "by": a.by, "source": "cli"}
    print(json.dumps(add(a.slug, rec), ensure_ascii=False))


def cmd_latest(a):
    rows = latest(a.slug, a.kind, a.batch)
    if a.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False)); return
    for e in sorted(rows, key=lambda e: (e.get("kind") or "", e.get("batch") or "", str(e.get("item")))):
        sc = " ".join(f"{k[0]}{v}" for k, v in (e.get("scores") or {}).items())
        print(f"{e.get('kind'):5} {str(e.get('batch') or '-'):28.28} {str(e.get('item')):14.14} "
              f"overall {e.get('overall') or '-'}  {sc:14} {e.get('verdict') or '':5} by {e.get('by')}  {(e.get('note') or '')[:60]}")
    print(f"\n{len(rows)} rating(s) in {store(a.slug)}")


def cmd_migrate(a):
    p = store(a.slug)
    lib = os.path.join(STUDIO, "clients", a.slug, "library")
    fb = os.path.dirname(p)
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    if lines:
        bak = p + ".bak-" + dt.date.today().isoformat()
        if not os.path.exists(bak):
            open(bak, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    out, n_old = [], 0
    for line in lines:
        try:
            e = json.loads(line)
        except Exception:
            continue
        n_old += e.get("v") != 2
        out.append(normalise(e))
    have = {(e.get("kind"), e.get("batch"), e.get("item")) for e in out}
    # catalog stars
    tags = json.load(open(os.path.join(lib, "tags.json"))) if os.path.exists(os.path.join(lib, "tags.json")) else {}
    n_star = 0
    for iid, t in tags.items():
        if t.get("rating") and ("clip", None, iid) not in have:
            out.append({"v": 2, "kind": "clip", "item": iid, "batch": None, "overall": _n(t["rating"]), "scores": {},
                        "note": t.get("notes", ""), "tags": t.get("tags", []), "by": "matt", "source": "catalog",
                        "saved_at": t.get("updated") or now()}); n_star += 1
    # one-off pick files
    n_pick = 0
    for f in sorted(glob.glob(os.path.join(fb, "picks-*.json"))):
        batch = "picks " + os.path.basename(f)[6:-5]
        for cid, pk in json.load(open(f)).items():
            if ("pick", batch, cid) in have:
                continue
            out.append({"v": 2, "kind": "pick", "item": cid, "batch": batch, "file": pk.get("file"), "overall": None,
                        "scores": {}, "verdict": "Keep" if pk.get("pick") else "Cut", "note": pk.get("note", ""),
                        "in": pk.get("in"), "out": pk.get("out"), "by": "matt", "source": "pick",
                        "saved_at": dt.datetime.fromtimestamp(os.path.getmtime(f)).astimezone().isoformat(timespec="seconds")}); n_pick += 1
    for f in sorted(glob.glob(os.path.join(fb, "grade-pick-*.json"))):
        batch = "grade " + os.path.basename(f)[11:-5]
        j = json.load(open(f))
        if j.get("look") and ("look", batch, j["look"]) not in have:
            out.append({"v": 2, "kind": "look", "item": j["look"], "batch": batch, "overall": 5, "scores": {},
                        "verdict": "Keep", "note": j.get("note", ""), "by": "matt", "source": "grade",
                        "saved_at": dt.datetime.fromtimestamp(os.path.getmtime(f)).astimezone().isoformat(timespec="seconds")}); n_pick += 1
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for e in out:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, p)
    print(f"{a.slug}: {n_old} old line(s) normalised, {n_star} catalog star(s) and {n_pick} pick record(s) imported. "
          f"{len(out)} line(s) in {p}. Old files kept.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("add"); s.add_argument("slug"); s.add_argument("--kind", required=True, choices=["clip", "edit", "look", "pick"])
    s.add_argument("--item", required=True); s.add_argument("--batch"); s.add_argument("--overall", type=int)
    for k in SUBS: s.add_argument("--" + k, type=int)
    s.add_argument("--verdict"); s.add_argument("--note"); s.add_argument("--by", default="claude", choices=["matt", "claude"])
    s.set_defaults(f=cmd_add)
    s = sp.add_parser("latest"); s.add_argument("slug"); s.add_argument("--kind"); s.add_argument("--batch"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_latest)
    s = sp.add_parser("migrate"); s.add_argument("slug"); s.set_defaults(f=cmd_migrate)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
