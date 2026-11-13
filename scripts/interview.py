#!/usr/bin/env python3
"""interview.py: "watch" an industry interview for a client (ported from a client project, 11 Nov 2026).

Pulls a long-form interview's captions (no video download) and writes a timestamped transcript the
agent then turns into summary.md with verbatim quote candidates (method: templates/interview-summary.md).
Per-project settings live in projects.json -> projects.<slug>.interviews:
  {"topics": ["flow state", ...], "out_dir": "<abs path>", "repeat_weeks": 6, "langs": "en,en-US,en-GB,en-orig"}
out_dir defaults to clients/<slug>/interviews.

  interview.py topics SLUG                       the project's topics and where interviews go
  interview.py check SLUG "<speaker>"            was this speaker watched in the last repeat_weeks? (exit 1 if so)
  interview.py fetch SLUG <url> <speaker-topic-slug> [--out DIR]
                                                 -> <out_dir>/<YYYY-MM-DD>-<slug>/{transcript.md, info.json, src.*.vtt}
  interview.py index SLUG <folder> --speaker S --topics "a, b"
                                                 add the row to <out_dir>/_index.md after summary.md is written
Uses tools/vendor/claude-watch/scripts/transcribe.py (MIT) and the studio's bin/yt-dlp. Only public
interviews, quoted briefly with credit: transcripts stay in the folder and are never published.
"""
import argparse, datetime as dt, json, os, re, subprocess, sys
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STUDIO / "tools" / "vendor" / "claude-watch" / "scripts"))


def cfg(slug):
    reg = json.load(open(STUDIO / "projects.json"))
    p = reg["projects"].get(slug) or sys.exit(f"Unknown project {slug}. Registered: {', '.join(reg['projects'])}")
    c = dict(p.get("interviews") or {})
    c.setdefault("topics", [])
    c["out_dir"] = Path(c.get("out_dir") or STUDIO / "clients" / slug / "interviews")
    c.setdefault("repeat_weeks", 6)
    c.setdefault("langs", "en,en-US,en-GB,en-orig")
    return p, c


def index_rows(out_dir):
    f = out_dir / "_index.md"
    if not f.exists():
        return []
    rows = []
    for line in f.read_text().splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.fullmatch(r"20\d\d-\d\d-\d\d", cells[0]):
            rows.append(cells)
    return rows


def cmd_topics(a):
    p, c = cfg(a.slug)
    print(f"{p['name']}: interviews go to {c['out_dir']}")
    print("topics: " + ("; ".join(c["topics"]) if c["topics"] else "none set (ask Matt, then add projects.<slug>.interviews.topics)"))
    print(f"no repeat speaker within {c['repeat_weeks']} weeks · {len(index_rows(c['out_dir']))} watched so far")


def cmd_check(a):
    _, c = cfg(a.slug)
    cutoff = (dt.date.today() - dt.timedelta(weeks=c["repeat_weeks"])).isoformat()
    who = a.speaker.lower()
    hits = [r for r in index_rows(c["out_dir"]) if who in r[1].lower() and r[0] >= cutoff]
    if hits:
        print(f"Watched {hits[-1][0]} ({hits[-1][2]}): inside {c['repeat_weeks']} weeks, pick someone else."); sys.exit(1)
    print("OK: not watched recently.")


def cmd_fetch(a):
    from transcribe import parse_vtt, format_transcript
    _, c = cfg(a.slug)
    base = Path(a.out) if a.out else c["out_dir"]
    out = base / f"{dt.date.today():%Y-%m-%d}-{a.name}"
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    try:
        import certifi
        env.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass
    subprocess.run([str(STUDIO / "bin" / "yt-dlp"), "--skip-download", "--write-info-json", "--write-subs", "--write-auto-subs",
                    "--sub-langs", c["langs"], "--sub-format", "vtt", "-o", str(out / "src.%(ext)s"), a.url], check=False, env=env)
    # prefer the original-language track: on some videos "en" is a garbled re-translation (Gilmour, 9 Nov 2026)
    vtts = sorted(out.glob("src*.vtt"), key=lambda p: (".en-orig." not in p.name, ".en." not in p.name, p.name))
    if not vtts:
        sys.exit(f"no captions in {c['langs']} for {a.url}")
    segs = parse_vtt(str(vtts[0]))
    info_f = out / "src.info.json"
    info = json.loads(info_f.read_text()) if info_f.exists() else {}
    meta = {k: info.get(k) for k in ("title", "channel", "uploader", "upload_date", "duration", "webpage_url")}
    (out / "info.json").write_text(json.dumps(meta, indent=2))
    info_f.unlink(missing_ok=True)
    head = (f"# Transcript: {meta['title']}\n"
            f"Channel: {meta['channel']} · Uploaded: {meta['upload_date']} · Length: {round((meta['duration'] or 0) / 60)} min\n"
            f"URL: {meta['webpage_url']}\nCaptions file: {vtts[0].name} (auto captions can mishear words: check a quote against the video before it ships)\n\n")
    (out / "transcript.md").write_text(head + format_transcript(segs))
    print(out)


def cmd_index(a):
    _, c = cfg(a.slug)
    folder = Path(a.folder)
    meta = json.loads((folder / "info.json").read_text())
    f = c["out_dir"] / "_index.md"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# Industry interviews index\nOne row per interview watched. Don't repeat a speaker within "
                     f"{c['repeat_weeks']} weeks.\n\n| Watched | Speaker | Title | URL | Topics | Folder |\n|---|---|---|---|---|---|\n")
    row = f"| {folder.name[:10]} | {a.speaker} | {meta.get('title')} | {meta.get('webpage_url')} | {a.topics} | {folder.name}/ |\n"
    with open(f, "a") as fh:
        fh.write(row)
    print(f"added to {f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("topics"); s.add_argument("slug"); s.set_defaults(f=cmd_topics)
    s = sp.add_parser("check"); s.add_argument("slug"); s.add_argument("speaker"); s.set_defaults(f=cmd_check)
    s = sp.add_parser("fetch"); s.add_argument("slug"); s.add_argument("url"); s.add_argument("name"); s.add_argument("--out"); s.set_defaults(f=cmd_fetch)
    s = sp.add_parser("index"); s.add_argument("slug"); s.add_argument("folder"); s.add_argument("--speaker", required=True)
    s.add_argument("--topics", required=True); s.set_defaults(f=cmd_index)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
