#!/usr/bin/env python3
"""grade.py: colour grading for the studio (added 11 Nov 2026).

Looks live in templates/looks.json (client-neutral ffmpeg filter chains). A client's default look is
projects.json -> projects.<slug>.grade_default; if that's unset, the look Matt picked most recently on a
grade board (ratings.jsonl, kind "look") is used.

  grade.py list                                  every look, with its description
  grade.py filter LOOK|--client SLUG             print the -vf chain (to splice into another ffmpeg chain)
  grade.py apply IN OUT (--look LOOK | --client SLUG)
                                                 grade a whole file; audio is copied untouched
  grade.py board SLUG SRC [SRC ...] --out DIR [--at SEC] [--looks a,b,c]
                                                 one frame from each source in every look, plus a page
                                                 Matt uses to pick one. Serve it with:
                                                 board_server.py DIR SLUG 8772 -> http://127.0.0.1:8772/
Grade footage only. Hooks, text, logos and end cards stay ungraded (Matt, 11 Nov 2026).
"""
import argparse, html, json, os, subprocess, sys

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(STUDIO, "bin", "ffmpeg")
FP = os.path.join(STUDIO, "bin", "ffprobe")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def looks():
    return json.load(open(os.path.join(STUDIO, "templates", "looks.json")))["looks"]


def client_default(slug):
    p = json.load(open(os.path.join(STUDIO, "projects.json")))["projects"].get(slug) or sys.exit(f"Unknown project {slug}")
    if p.get("grade_default"):
        return p["grade_default"], "projects.json grade_default"
    import ratings
    picked = sorted((e for e in ratings.latest(slug, kind="look") if (e.get("overall") or 0) >= 4 and e.get("by", "matt") == "matt"),
                    key=lambda e: e.get("saved_at") or "")
    if picked:
        name = picked[-1]["item"].split("_", 1)[1] if picked[-1]["item"][:1].isdigit() else picked[-1]["item"]
        name = "sage" if name == "oca_sage" else name
        return name, f"Matt's pick on {picked[-1].get('batch')}"
    return "original", "no default set and no pick yet"


def chain(name):
    L = looks()
    if name not in L:
        sys.exit(f"Unknown look '{name}'. Looks: {', '.join(L)}")
    return L[name]["filter"]


def resolve(a):
    if getattr(a, "look", None):
        return a.look, "--look"
    if getattr(a, "client", None):
        return client_default(a.client)
    sys.exit("Give --look LOOK or --client SLUG")


def cmd_list(a):
    for k, v in looks().items():
        print(f"{k:12} {v['desc']}")


def cmd_filter(a):
    name, why = resolve(a)
    print(chain(name) or "null")
    print(f"# {name} ({why})", file=sys.stderr)


def cmd_apply(a):
    name, why = resolve(a)
    vf = chain(name) or "null"
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", a.input, "-vf", f"{vf},format=yuv420p",
                    "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-c:a", "copy",
                    "-map_metadata", "-1", "-movflags", "+faststart", a.output], check=True)
    print(f"wrote {a.output} (look: {name}, from {why})")


def duration(f):
    try:
        return float(subprocess.check_output([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).decode())
    except Exception:
        return 0.0


def cmd_board(a):
    L = looks()
    names = a.looks.split(",") if a.looks else list(L)
    os.makedirs(a.out, exist_ok=True)
    frames = []
    for i, src in enumerate(a.sources, 1):
        at = a.at if a.at is not None else max(0.0, duration(src) / 2)
        base = os.path.join(a.out, f"_src{i}.png")
        subprocess.run([FF, "-v", "error", "-y", "-ss", str(at), "-i", src, "-frames:v", "1",
                        "-vf", "scale=720:-2", base], check=True)
        frames.append((i, os.path.basename(src), base))
    for n in names:
        vf = chain(n) or "null"
        for i, _, base in frames:
            subprocess.run([FF, "-v", "error", "-y", "-i", base, "-vf", vf, "-frames:v", "1", "-q:v", "3",
                            os.path.join(a.out, f"{n}_s{i}.jpg")], check=True)
    for _, _, base in frames:
        os.remove(base)
    batch = os.path.basename(os.path.normpath(a.out))
    page = open(os.path.join(STUDIO, "templates", "look-board.html")).read()
    data = {"batch": batch, "frames": [f for _, f, _ in frames],
            "looks": [[n, L[n]["label"], L[n]["desc"]] for n in names]}
    page = page.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False)).replace("{{TITLE}}", html.escape(f"Grade board · {batch}"))
    open(os.path.join(a.out, "index.html"), "w").write(page)
    print(f"wrote {len(names)} looks x {len(frames)} frames to {a.out}\n"
          f"serve: python3 \"{STUDIO}/scripts/board_server.py\" \"{a.out}\" {a.slug} 8772  ->  http://127.0.0.1:8772/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list").set_defaults(f=cmd_list)
    s = sp.add_parser("filter"); s.add_argument("look", nargs="?"); s.add_argument("--client"); s.set_defaults(f=cmd_filter)
    s = sp.add_parser("apply"); s.add_argument("input"); s.add_argument("output"); s.add_argument("--look"); s.add_argument("--client"); s.set_defaults(f=cmd_apply)
    s = sp.add_parser("board"); s.add_argument("slug"); s.add_argument("sources", nargs="+"); s.add_argument("--out", required=True)
    s.add_argument("--at", type=float); s.add_argument("--looks"); s.set_defaults(f=cmd_board)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
