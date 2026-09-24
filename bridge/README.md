# GOLD DESK execution bridge

Three pieces. Grok never holds the broker login.

```
pulse.json  →  GitHub Action  →  POST signed ticket
                              →  VPS listener (gates + HMAC)
                              →  gold_desk_ticket.ini
                              →  MT5 EA OrderSend
```

`WAIT` and `ARMED` never send an order. Only `sotd.status == LIVE` with `rr >= 1.4`.

## 1. GitHub Action

File: `.github/workflows/gold-desk-webhook.yml`

Repo → Settings → Secrets and variables → Actions. Add:

| Secret | Required | Purpose |
|---|---|---|
| `WEBHOOK_URL` | yes (for execute) | `https://YOUR_VPS:8788/gold-desk/order` |
| `WEBHOOK_SECRET` | yes | same string the listener uses |
| `TELEGRAM_BOT_TOKEN` | no | notify |
| `TELEGRAM_CHAT_ID` | no | notify |
| `DISCORD_WEBHOOK_URL` | no | notify |

Action fires on every change to `feed/pulse.json`. It posts an **execute** body only when LIVE. ARMED posts notify-only.

If the VPS has no public IP, skip `WEBHOOK_URL` and run the listener in `--poll` mode instead. The Action can still hit Telegram/Discord.

## 2. VPS listener

Python 3.10+, stdlib only.

```bash
export GOLD_DESK_SECRET='paste-same-secret-as-github'
export GOLD_DESK_TICKET_DIR="$HOME/gold-desk-tickets"
# Windows MT5 Common Files (adjust terminal path):
# export GOLD_DESK_TICKET_DIR="C:/Users/YOU/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
export GOLD_DESK_MAX_RISK_PCT=0.5
python3 bridge/listener.py          # inbound webhook
python3 bridge/listener.py --poll   # pull GitHub raw every 30s, no public port
```

Writes:

- `gold_desk_ticket.json` — full ticket
- `gold_desk_ticket.ini` — flat file the EA reads
- `gold_desk_seen.json` — idempotency keys

## 3. MT5 EA

Copy `bridge/GoldDeskBridge.mq5` into `MQL5/Experts/`, compile, attach to an XAUUSD chart.

Inputs:

- `TicketFile` = `gold_desk_ticket.ini` (must sit in **Common Files** if the listener writes there — enable `FILE_COMMON`)
- `RiskPercent` = 0.5
- `Magic` = 260924
- `MaxSpreadPoints` = 80 (gold)

EA places a **pending** (BUY LIMIT / SELL LIMIT) at `entry`. It will not chase if price has already run through. It will not open a second ticket with the same `KEY`.

## Ticket contract

```json
{
  "desk": "GOLD DESK",
  "source": "Grok",
  "mode": "execute",
  "symbol": "XAUUSD",
  "side": "SELL",
  "status": "LIVE",
  "grade": "B",
  "entry": 4300,
  "sl": 4318,
  "tp1": 4250,
  "rr": 2.78,
  "idempotency_key": "XAUUSD-2026-09-24-SELL-4300",
  "updated_at": "2026-09-24T16:16:00+03:00"
}
```

Header: `X-Gold-Desk-Signature: sha256=<hmac_hex>`

## Do not

- Put broker server, account, or password in this repo or in chat
- Set `WEBHOOK_SECRET` in a committed file
- Treat ARMED as an order
