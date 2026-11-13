#!/usr/bin/env python3
"""feedback_summary.py <client> : what Matt's ratings say, for the agent to read before the next edit.
Reads the one rating store, clients/<client>/feedback/ratings.jsonl, through ratings.py (latest save per
item per batch counts; old 7-score lines are mapped to the 4 scores). Prints, for Matt's ratings only:
average overall and per score (moment, look, sound, pacing), issue tags, verdicts, picked grade looks,
catalog favourites and rejects, hook rewrites, and every note. Claude's own scores are counted apart."""
import collections, os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ratings

if len(sys.argv) < 2: sys.exit("usage: feedback_summary.py <slug>")
client = sys.argv[1]
rows = ratings.latest(client)
if not rows:
    print("No ratings yet."); sys.exit(0)
matt = [e for e in rows if e.get("by", "matt") == "matt"]
mine = len(rows) - len(matt)
print(f"{len(matt)} rating(s) by Matt in {ratings.store(client)}" + (f" ({mine} by Claude, not counted)" if mine else ""))

edits = [e for e in matt if e.get("kind") == "edit"]
dims = collections.defaultdict(list)
for e in edits:
    if e.get("overall"): dims["overall"].append(e["overall"])
    for k, v in (e.get("scores") or {}).items():
        if v: dims[k].append(v)
print("\nEDITS: AVERAGE SCORE (1-5), weakest first")
for k, v in sorted(dims.items(), key=lambda kv: statistics.mean(kv[1])):
    print(f"  {k:<8} {statistics.mean(v):.1f}  (n={len(v)})")
legacy = [v for e in edits if (v := (e.get("legacy_scores") or {}).get("hook_text"))]
if legacy:
    print(f"  (old pages) hook words {statistics.mean(legacy):.1f} (n={len(legacy)})")

tags = collections.Counter(t for e in matt for t in (e.get("tags") or []))
print("\nISSUE TAGS"); [print(f"  {t}: {n}") for t, n in tags.most_common()]
print("\nVERDICTS", dict(collections.Counter(e.get("verdict") or "none" for e in edits)))

looks = [e for e in matt if e.get("kind") == "look" and (e.get("overall") or 0) >= 4]
if looks:
    print("\nGRADE LOOKS PICKED")
    for e in sorted(looks, key=lambda e: e.get("saved_at") or ""):
        print(f"  {e.get('batch')}: {e['item']}" + (f" ({e['note']})" if e.get("note") else ""))

clips = [e for e in matt if e.get("kind") == "clip" and e.get("overall")]
if clips:
    fav = [e for e in clips if e["overall"] >= 4]; rej = [e for e in clips if e["overall"] <= 2]
    print(f"\nCATALOG STARS: {len(clips)} rated, {len(fav)} at 4-5, {len(rej)} at 1-2")
    for e in rej:
        if e.get("note"): print(f"  low [{e['item']}] {e['note']}")

picks = [e for e in matt if e.get("kind") == "pick" and e.get("verdict") == "Keep"]
if picks:
    print("\nPICK SETS", dict(collections.Counter(e.get("batch") for e in picks)))

print("\nNOTES")
for e in sorted(matt, key=lambda e: (e.get("batch") or "", str(e.get("item")))):
    if e.get("kind") not in ("edit", "look"):
        continue
    bits = [e["note"]] if e.get("note") else []
    bits += [f"@{n['t']}s {n['text']}" for n in e.get("timed_notes") or []]
    if e.get("better_hook"): bits.append(f"better hook: \"{e['better_hook']}\" (was \"{e.get('hook')}\")")
    if bits: print(f"  [{e.get('batch')} {e.get('item')}] " + " | ".join(bits))
