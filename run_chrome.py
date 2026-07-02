#!/usr/bin/env python3
"""
run_chrome.py — интерактивный тестовый браузер для Gailery.

Запускает Chromium на Xvfb :98, открывает галерею,
собирает console/network логи и даёт HTTP API для управления.

Все вызовы Playwright выполняются из главного потока (greenlet-safe).
HTTP API только ставит задачи в очередь.

API (порт 9999):
  GET  /screenshot          — скриншот (PNG)
  GET  /logs?n=50            — console логи (JSON)
  GET  /network?n=50         — network запросы (JSON)
  GET  /dom                  — состояние DOM
  POST /scroll               — {px: 800}
  POST /goto                 — {url: "..."}
  POST /eval                 — {js: "..."}
  POST /click                — {selector: "..."}
  POST /type                 — {selector: "...", text: "..."}
  POST /keypress             — {key: "Enter"}
  GET  /metrics              — performance metrics
  GET  /status               — {ready, url, viewport}

Запуск:
  DISPLAY=:98 ./venv/bin/python3 run_chrome.py
"""

import json
import os
import queue
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

# ─── Config ────────────────────────────────────────────────────────────
GALLERY_URL = "http://localhost:8000/gallery"
API_PORT = 9999
VIEWPORT = {"width": 2560, "height": 1440}
LOG_HISTORY = 500
NETWORK_HISTORY = 500

# ─── Globals ───────────────────────────────────────────────────────────
logs = []          # [{t, level, text}]
network = []       # [{t, method, url, status, ms}]
page = None
_lock = threading.Lock()
_ready = threading.Event()
_cmd_queue = queue.Queue()


def _log_event(level, text):
    with _lock:
        logs.append({"t": time.time(), "level": level, "text": str(text)[:500]})
        if len(logs) > LOG_HISTORY:
            logs.pop(0)


def _net_event(method, url, status, ms):
    with _lock:
        network.append({
            "t": time.time(),
            "method": method,
            "url": url[:300],
            "status": status,
            "ms": round(ms, 1),
        })
        if len(network) > NETWORK_HISTORY:
            network.pop(0)


# ─── Command dispatch (called only from browser thread) ────────────────
def _dispatch(cmd, args):
    """Execute a Playwright command. Must be called from the browser thread."""
    global page
    if not page:
        return {"error": "Page not created"}

    try:
        if cmd == "screenshot":
            full = args.get("full", False)
            return {"png": page.screenshot(full_page=full)}

        if cmd == "goto":
            url = args.get("url", GALLERY_URL)
            page.goto(url, wait_until="networkidle")
            return {"url": page.url}

        if cmd == "scroll":
            px = args.get("px", 800)
            page.evaluate(f"window.scrollBy(0, {px})")
            page.wait_for_timeout(300)
            return {"scrolled": px, "scrollY": page.evaluate("window.scrollY")}

        if cmd == "eval":
            result = page.evaluate(args.get("js", ""))
            return {"result": result}

        if cmd == "click":
            page.click(args.get("selector", ""))
            return {"clicked": args.get("selector")}

        if cmd == "type":
            page.fill(args.get("selector", ""), args.get("text", ""))
            return {"typed": args.get("text"), "into": args.get("selector")}

        if cmd == "keypress":
            page.keyboard.press(args.get("key", "Enter"))
            return {"key": args.get("key")}

        if cmd == "dom":
            info = page.evaluate("""() => {
                const cards = document.querySelectorAll('.card');
                const loaded = document.querySelectorAll('.card img[src]');
                const lazy = document.querySelectorAll('.card-thumb[data-src]');
                const broken = [];
                document.querySelectorAll('.card img').forEach(img => {
                    if (img.naturalWidth === 0 && img.src && !img.src.startsWith('data:'))
                        broken.push(img.src.split('/').pop());
                });
                const grid = document.getElementById('grid');
                return {
                    cards: cards.length,
                    thumbnails_loaded: loaded.length,
                    thumbnails_lazy: lazy.length,
                    broken_images: broken,
                    scrollY: window.scrollY,
                    docHeight: document.documentElement.scrollHeight,
                    gridText: grid ? grid.innerText.substring(0, 200) : null,
                };
            }""")
            return info

        if cmd == "metrics":
            m = page.evaluate("() => JSON.stringify(performance.toJSON())")
            return json.loads(m)

        if cmd == "status":
            try:
                title = page.title()
            except Exception:
                title = ""
            return {"ready": True, "url": page.url, "viewport": VIEWPORT, "title": title}

        return {"error": f"Unknown cmd: {cmd}"}
    except Exception as e:
        return {"error": str(e)}


# ─── Browser loop (main thread) ──────────────────────────────────────
def browser_loop():
    global page

    os.environ.setdefault("DISPLAY", ":98")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
            ]
        )
        ctx = browser.new_context(viewport=VIEWPORT, locale="ru-RU")
        page = ctx.new_page()

        page.on("console", lambda msg: _log_event(msg.type, msg.text))
        page.on("pageerror", lambda err: _log_event("pageerror", str(err)))

        def _on_finished(req):
            try:
                resp = req.response
                st = resp.status if resp else 0
                t0 = getattr(req, "_start", None)
                if t0 is None:
                    t0 = time.time()
                ms = (time.time() - t0) * 1000
                _net_event(req.method, req.url, st, ms)
            except Exception:
                pass

        def _on_request(req):
            req._start = time.time()

        page.on("request", _on_request)
        page.on("requestfinished", _on_finished)

        _log_event("info", f"Browser launched {VIEWPORT['width']}x{VIEWPORT['height']}")

        page.goto(GALLERY_URL, wait_until="networkidle")
        _log_event("info", f"Page loaded: {page.url}")

        page.wait_for_timeout(500)
        _ready.set()

        while True:
            try:
                item = _cmd_queue.get(timeout=0.5)
            except queue.Empty:
                time.sleep(0.1)
                continue

            result = _dispatch(item["cmd"], item.get("args", {}))
            item["result"] = result
            item["event"].set()


# ─── HTTP API ─────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _png(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "image/png")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length).decode())
        return {}

    def _run_cmd(self, cmd, args):
        if not _ready.is_set():
            return {"error": "Browser not ready"}
        ev = threading.Event()
        item = {"cmd": cmd, "args": args, "event": ev, "result": None}
        _cmd_queue.put(item)
        if not ev.wait(timeout=30):
            return {"error": "Timeout waiting for browser"}
        return item["result"]

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path

        if path == "/status":
            if not _ready.is_set():
                self._json(200, {"ready": False})
                return
            res = self._run_cmd("status", {})
            if "error" in res:
                self._json(503, res)
            else:
                self._json(200, res)
            return

        if path == "/logs":
            n = int(qs.get("n", [50])[0])
            with _lock:
                self._json(200, logs[-n:])
            return

        if path == "/network":
            n = int(qs.get("n", [50])[0])
            with _lock:
                self._json(200, network[-n:])
            return

        if path == "/screenshot":
            full = qs.get("full", ["0"])[0] == "1"
            res = self._run_cmd("screenshot", {"full": full})
            if "error" in res:
                self._json(500, res)
                return
            self._png(200, res["png"])
            return

        if path == "/dom":
            res = self._run_cmd("dom", {})
            if "error" in res:
                self._json(500, res)
            else:
                self._json(200, res)
            return

        if path == "/metrics":
            res = self._run_cmd("metrics", {})
            if "error" in res:
                self._json(500, res)
            else:
                self._json(200, res)
            return

        self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        cmd_map = {
            "/scroll": "scroll",
            "/goto": "goto",
            "/eval": "eval",
            "/click": "click",
            "/type": "type",
            "/keypress": "keypress",
            "/screenshot": "screenshot",
        }

        if path in cmd_map:
            res = self._run_cmd(cmd_map[path], body)
            if "error" in res:
                self._json(500 if "Timeout" in res["error"] else 400, res)
                return
            if path == "/screenshot" and "png" in res:
                self._png(200, res["png"])
                return
            self._json(200, res)
            return

        self._json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def start_api():
    srv = HTTPServer(("0.0.0.0", API_PORT), Handler)  # nosec B104 — server intentionally binds all interfaces
    srv.serve_forever()


# ─── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=start_api, daemon=True).start()
    print(f"API starting on http://0.0.0.0:{API_PORT}", flush=True)
    browser_loop()
