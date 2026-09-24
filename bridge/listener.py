#!/usr/bin/env python3
"""GOLD DESK VPS listener — HMAC gates, ticket drop, optional GitHub poll.

Never stores a broker password. Point GOLD_DESK_TICKET_DIR at MT5 Common\\Files.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from emit_ticket import build_ticket, classify, load_pulse, to_ini, verify

SECRET = os.environ.get("GOLD_DESK_SECRET", "")
TICKET_DIR = Path(os.environ.get("GOLD_DESK_TICKET_DIR", str(Path.home() / "gold-desk-tickets")))
HOST = os.environ.get("GOLD_DESK_HOST", "127.0.0.1")
PORT = int(os.environ.get("GOLD_DESK_PORT", "8788"))
PULSE_URL = os.environ.get(
    "GOLD_DESK_PULSE_URL",
    "https://raw.githubusercontent.com/joekays11/ai-forex-analysis/main/feed/pulse.json",
)
POLL_SECS = int(os.environ.get("GOLD_DESK_POLL_SECS", "30"))
MAX_AGE_MIN = int(os.environ.get("GOLD_DESK_MAX_AGE_MIN", "15"))


def _seen_path() -> Path:
    return TICKET_DIR / "gold_desk_seen.json"


def load_seen() -> set[str]:
    p = _seen_path()
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data if isinstance(data, list) else data.get("keys", []))
    except json.JSONDecodeError:
        return set()


def save_seen(keys: set[str]) -> None:
    TICKET_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = sorted(keys)[-200:]
    _seen_path().write_text(json.dumps(trimmed, indent=2), encoding="utf-8")


def write_ticket(ticket: dict, mode: str) -> None:
    TICKET_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(ticket)
    payload["mode"] = mode
    (TICKET_DIR / "gold_desk_ticket.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (TICKET_DIR / "gold_desk_ticket.ini").write_text(to_ini(ticket, mode), encoding="utf-8")


def accept(ticket: dict, mode: str) -> tuple[bool, str]:
    if mode != "execute":
        write_ticket(ticket, mode)
        return False, mode
    key = ticket.get("idempotency_key") or ""
    seen = load_seen()
    if key in seen:
        return False, "duplicate"
    seen.add(key)
    save_seen(seen)
    write_ticket(ticket, mode)
    return True, "armed-file"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[gold-desk] " + fmt % args + "\n")

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path in ("/health", "/gold-desk/health"):
            self._send(200, {"ok": True, "dir": str(TICKET_DIR)})
            return
        self._send(404, {"ok": False})

    def do_POST(self) -> None:
        if self.path not in ("/gold-desk/order", "/order"):
            self._send(404, {"ok": False})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 200_000:
            self._send(400, {"ok": False, "error": "bad-length"})
            return
        body = self.rfile.read(length)
        sig = self.headers.get("X-Gold-Desk-Signature")
        if not SECRET or not verify(body, SECRET, sig):
            self._send(401, {"ok": False, "error": "bad-signature"})
            return
        try:
            ticket = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"ok": False, "error": "bad-json"})
            return
        mode = ticket.get("mode") or classify(ticket)
        if mode == "silent":
            self._send(202, {"ok": True, "action": "silent"})
            return
        if mode == "notify":
            write_ticket(ticket, "notify")
            self._send(202, {"ok": True, "action": "notify"})
            return
        ok, why = accept(ticket, "execute")
        self._send(200 if ok else 202, {"ok": True, "action": why})


def poll_loop() -> None:
    print(f"[gold-desk] poll {PULSE_URL} every {POLL_SECS}s → {TICKET_DIR}", flush=True)
    last_hash = ""
    while True:
        try:
            with urllib.request.urlopen(PULSE_URL, timeout=20) as resp:
                raw = resp.read()
            digest = str(hash(raw))
            if digest != last_hash:
                last_hash = digest
                pulse = json.loads(raw.decode("utf-8"))
                ticket = build_ticket(pulse)
                mode = classify(ticket)
                if mode == "execute":
                    ok, why = accept(ticket, mode)
                    print(f"[gold-desk] {why} {ticket.get('idempotency_key')}", flush=True)
                elif mode == "notify":
                    write_ticket(ticket, mode)
                    print(f"[gold-desk] notify {ticket.get('status')} {ticket.get('idempotency_key')}", flush=True)
                else:
                    print(f"[gold-desk] silent {ticket.get('status')}", flush=True)
        except Exception as exc:  # noqa: BLE001 — keep poller alive
            print(f"[gold-desk] poll error {exc}", flush=True)
        time.sleep(POLL_SECS)


def main() -> None:
    TICKET_DIR.mkdir(parents=True, exist_ok=True)
    if "--poll" in sys.argv:
        poll_loop()
        return
    if not SECRET:
        print("Set GOLD_DESK_SECRET before serving inbound webhooks.", file=sys.stderr)
        sys.exit(1)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[gold-desk] listen {HOST}:{PORT} tickets → {TICKET_DIR}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
