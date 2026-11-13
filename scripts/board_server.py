#!/usr/bin/env python3
"""board_server.py <folder> <slug> [port]
Serves a board page (grade board from grade.py, or any page in templates/ that rates things) on 127.0.0.1
and saves every rating into the one store, clients/<slug>/feedback/ratings.jsonl, via ratings.py.
  GET  /api/rate?batch=B[&kind=K]  -> latest rating per item for that batch (JSON object keyed by item)
  POST /api/rate                   -> {kind, item, batch, overall, scores, verdict, note, ...}; appended, never overwritten
Video and image files are served with byte ranges so they seek. Never posts or uploads anything."""
import functools, http.server, json, os, sys
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ratings

root, slug = os.path.abspath(sys.argv[1]), sys.argv[2]
port = int(sys.argv[3]) if len(sys.argv) > 3 else 8772


class H(http.server.SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/rate":
            q = parse_qs(u.query)
            rows = ratings.latest(slug, q.get("kind", [None])[0], q.get("batch", [None])[0])
            return self._json(200, {str(e.get("item")): e for e in rows})
        f = self.translate_path(u.path)
        rng = self.headers.get("Range")
        if rng and os.path.isfile(f):
            size = os.path.getsize(f); a, b = rng.replace("bytes=", "").split("-")
            a = int(a or 0); b = min(int(b) if b else size - 1, size - 1)
            self.send_response(206); self.send_header("Content-Type", self.guess_type(f))
            self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
            self.send_header("Content-Length", str(b - a + 1)); self.end_headers()
            with open(f, "rb") as fh:
                fh.seek(a); left = b - a + 1
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk: break
                    try: self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError): break
                    left -= len(chunk)
            return
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/rate":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", 0))
        if n > 200_000: return self._json(413, {"error": "too large"})
        try:
            e = json.loads(self.rfile.read(n))
            e.setdefault("v", 2); e.setdefault("by", "matt"); e.setdefault("source", "board")
            return self._json(200, {"ok": True, **ratings.add(slug, e)})
        except Exception as err:
            return self._json(400, {"error": str(err)})

    def log_message(self, *a): pass


print(f"board for {slug}: http://127.0.0.1:{port}/  (ratings -> {ratings.store(slug)})")
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=root)).serve_forever()
