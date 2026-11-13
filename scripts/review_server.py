#!/usr/bin/env python3
"""review_server.py <folder-to-serve> <feedback.jsonl> [port]
Serves the review page and videos on 127.0.0.1, and stores ratings:
  GET  /api/feedback[?batch=X]  -> latest entry per clip, optionally for one batch (JSON)
  POST /api/feedback  -> appends one JSON line (every save is kept, so the history shows how opinions change).
Since 11 Nov 2026 every line is normalised to the one rating shape in ratings.py (kind "edit"), old fields kept."""
import http.server, json, os, sys, datetime, functools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ratings
root, store = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]); port = int(sys.argv[3]) if len(sys.argv) > 3 else 8771
os.makedirs(os.path.dirname(store), exist_ok=True)
class H(http.server.SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/api/feedback"):
            from urllib.parse import urlparse, parse_qs
            want = parse_qs(urlparse(self.path).query).get("batch", [None])[0]
            latest = {}
            if os.path.exists(store):
                for line in open(store):
                    try:
                        e = json.loads(line)
                        if e.get("legacy_scores"): e = {**e, "scores": e["legacy_scores"]}  # pages read their own score keys back
                        if (want is None or e.get("batch") == want) and e.get("clip"): latest[e["clip"]] = e
                    except Exception: pass
            return self._json(200, latest)
        return super().do_GET()
    def do_POST(self):
        if not self.path.startswith("/api/feedback"): return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", 0))
        if n > 200_000: return self._json(413, {"error": "too large"})
        try: e = json.loads(self.rfile.read(n))
        except Exception: return self._json(400, {"error": "bad json"})
        if not isinstance(e, dict) or "clip" not in e: return self._json(400, {"error": "clip required"})
        e.setdefault("source", "review"); e.setdefault("by", "matt"); e = ratings.normalise(e)
        e["saved_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        with open(store, "a") as f: f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return self._json(200, {"ok": True, "saved_at": e["saved_at"]})
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=root)).serve_forever()
