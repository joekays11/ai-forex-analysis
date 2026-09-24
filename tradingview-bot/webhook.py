#!/usr/bin/env python3
"""THE SMART Ai — TradingView signal webhook (notify only).

Receives the JSON that SMART_AI_TV_Signal_Desk.pine posts from an alert.
Forwards to Telegram / Discord. Never talks to a broker.

  export TV_BOT_SECRET='same-tag-or-a-header-secret'
  export TELEGRAM_BOT_TOKEN='...'
  export TELEGRAM_CHAT_ID='...'          # @kayzfxking notify channel id
  export DISCORD_WEBHOOK_URL='...'       # optional
  python3 webhook.py                     # :8789
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EAT = timezone(timedelta(hours=3))
HOST = os.environ.get("TV_BOT_HOST", "0.0.0.0")
PORT = int(os.environ.get("TV_BOT_PORT", "8789"))
SECRET = os.environ.get("TV_BOT_SECRET", "")
EXPECT_TAG = os.environ.get("TV_BOT_TAG", "smart-ai")
LOG_DIR = Path(os.environ.get("TV_BOT_LOG_DIR", str(Path.home() / "smart-ai-tv-signals")))
ALLOW = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "XAUUSDm", "GOLD"}


def _post(url: str, payload: dict) -> None:
    raw = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    _post(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": text, "disable_web_page_preview": True})


def discord(text: str) -> None:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return
    _post(url, {"content": text})


def pretty(sig: dict) -> str:
    pair = sig.get("pair") or sig.get("symbol") or "?"
    side = str(sig.get("side") or "WAIT").upper()
    state = str(sig.get("state") or sig.get("status") or "WAIT").upper()
    return (
        f"SMART Ai TV  {state}  {side}  {pair}\n"
        f"tf {sig.get('tf')}  entry {sig.get('entry')}  sl {sig.get('sl')}  tp1 {sig.get('tp1')}  {sig.get('rr')}\n"
        f"{sig.get('thesis') or ''}\n"
        f"{sig.get('sessionNote') or 'educational only'}"
    )


def valid(sig: dict) -> tuple[bool, str]:
    if EXPECT_TAG and str(sig.get("tag") or "") != EXPECT_TAG:
        return False, "bad-tag"
    pair = str(sig.get("pair") or sig.get("symbol") or "").upper()
    if pair not in ALLOW:
        return False, f"pair-blocked:{pair}"
    side = str(sig.get("side") or "").upper()
    if side not in {"BUY", "SELL"}:
        return False, "not-a-signal"
    if sig.get("entry") is None or sig.get("sl") is None:
        return False, "missing-levels"
    return True, "ok"


def persist(sig: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(EAT).strftime("%Y%m%d")
    path = LOG_DIR / f"signals-{stamp}.jsonl"
    row = dict(sig)
    row["received_at"] = datetime.now(EAT).isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    (LOG_DIR / "last-signal.json").write_text(json.dumps(row, indent=2), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[tv-bot] " + fmt % args + "\n")

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path in ("/health", "/tv/health"):
            self._send(200, {"ok": True, "desk": "THE SMART Ai", "mode": "signals-only"})
            return
        self._send(404, {"ok": False})

    def do_POST(self) -> None:
        if self.path not in ("/tv/signal", "/signal", "/"):
            self._send(404, {"ok": False})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 50_000:
            self._send(400, {"ok": False, "error": "bad-length"})
            return
        raw = self.rfile.read(length)
        try:
            text = raw.decode("utf-8").strip()
            sig = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"ok": False, "error": "bad-json"})
            return
        ok, why = valid(sig)
        if not ok:
            self._send(202, {"ok": True, "action": "ignored", "why": why})
            return
        persist(sig)
        note = pretty(sig)
        try:
            telegram(note)
            discord(note)
        except Exception as exc:  # keep listener up
            sys.stderr.write(f"[tv-bot] notify fail {exc}\n")
        self._send(200, {"ok": True, "action": "notified", "pair": sig.get("pair"), "side": sig.get("side")})


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[tv-bot] signals-only listen {HOST}:{PORT}  log → {LOG_DIR}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
