#!/usr/bin/env python3
"""Build a GOLD DESK ticket from feed/pulse.json. Shared by Action and poller."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from typing import Any

EAT = timezone(timedelta(hours=3))
ALLOW = {"XAUUSD", "XAUUSDm", "GOLD"}
MIN_RR = 1.4


def load_pulse(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _rr(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(":", " ")
    parts = text.replace("1 ", "", 1).split()
    try:
        if len(parts) == 2:
            a, b = float(parts[0]), float(parts[1])
            return b / a if a else None
        return float(text)
    except ValueError:
        return None


def build_ticket(pulse: dict[str, Any]) -> dict[str, Any]:
    sotd = pulse.get("sotd") or {}
    symbol = str(sotd.get("symbol") or "XAUUSD").upper()
    side = str(sotd.get("side") or "").upper()
    status = str(sotd.get("status") or "WAIT").upper()
    entry = sotd.get("entry")
    sl = sotd.get("sl")
    tp1 = sotd.get("tp1")
    rr = _rr(sotd.get("rr"))
    updated = pulse.get("updated_at") or datetime.now(EAT).isoformat()
    day = updated[:10] if isinstance(updated, str) else datetime.now(EAT).date().isoformat()
    key = f"{symbol}-{day}-{side}-{entry}"
    return {
        "desk": "GOLD DESK",
        "source": pulse.get("source") or "Grok",
        "timezone": pulse.get("timezone") or "Africa/Nairobi",
        "session": pulse.get("session"),
        "updated_at": updated,
        "symbol": symbol,
        "side": side,
        "status": status,
        "grade": sotd.get("grade"),
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "rr": rr,
        "reason": sotd.get("reason"),
        "idempotency_key": key,
    }


def sl_ok(side: str, entry: Any, sl: Any) -> bool:
    try:
        e, s = float(entry), float(sl)
    except (TypeError, ValueError):
        return False
    if side == "SELL":
        return s > e
    if side == "BUY":
        return s < e
    return False


def classify(ticket: dict[str, Any]) -> str:
    """execute | notify | silent"""
    status = ticket.get("status")
    rr = ticket.get("rr")
    if status == "LIVE" and ticket.get("symbol") in ALLOW and ticket.get("side") in {"BUY", "SELL"}:
        if sl_ok(ticket["side"], ticket.get("entry"), ticket.get("sl")) and rr is not None and rr >= MIN_RR:
            if ticket.get("tp1") is not None:
                return "execute"
    if status in {"LIVE", "ARMED"}:
        return "notify"
    return "silent"


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify(body: bytes, secret: str, header: str | None) -> bool:
    if not header or not secret:
        return False
    expect = sign(body, secret)
    return hmac.compare_digest(expect, header.strip())


def to_ini(ticket: dict[str, Any], mode: str) -> str:
    lines = [
        f"MODE={mode}",
        f"STATUS={ticket.get('status')}",
        f"SYMBOL={ticket.get('symbol')}",
        f"SIDE={ticket.get('side')}",
        f"GRADE={ticket.get('grade') or ''}",
        f"ENTRY={ticket.get('entry')}",
        f"SL={ticket.get('sl')}",
        f"TP1={ticket.get('tp1')}",
        f"RR={ticket.get('rr')}",
        f"KEY={ticket.get('idempotency_key')}",
        f"UPDATED={ticket.get('updated_at')}",
    ]
    return "\n".join(lines) + "\n"
