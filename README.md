# THE SMART Ai — Grok desk feed

Live desk: https://ai-forex-analysis.surge.sh

Hook URL (paste in Desk → Settings → Public feed URL):
https://raw.githubusercontent.com/joekays11/ai-forex-analysis/main/desk-feed.json

The running site already reads `version: 1` feeds with `source: grok-bot`.
Default built-in URL is still `https://ai-forex-analysis.surge.sh/desk-feed.json` (last Surge publish).
Until Surge is redeployed, use the GitHub raw URL above so auto-refresh pulls Grok.

## GOLD DESK webhook / MT5 bridge

Execution path lives in [`bridge/`](bridge/README.md). Grok writes `feed/pulse.json`. A GitHub Action can notify Telegram/Discord and POST a signed ticket to your VPS. An MT5 EA reads the dropped `gold_desk_ticket.ini`. Broker login stays on your terminal — never in this repo.

`WAIT` does not trade. Only `sotd.status=LIVE` with RR ≥ 1.4 can hit OrderSend.
