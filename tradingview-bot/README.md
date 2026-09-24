# THE SMART Ai — TradingView signal bot

Signals only. You still place the trade.

```
XAUUSD / EURUSD / GBPUSD / USDJPY / BTCUSD chart
        ↓  Pine (this folder)
TradingView alert on bar close
        ↓  webhook JSON
Telegram / Discord  +  last-signal.json
        ↓
You execute on the desk
```

Does **not** call MT5. The existing GOLD DESK bridge stays gated on `sotd.status=LIVE`.

## 1. Pine script

File: `SMART_AI_TV_Signal_Desk.pine`

1. TradingView → Pine Editor → paste → Add to chart.
2. Same script on every pair. It remaps the ticker to desk names (`XAUUSD`, `EURUSD`, …).
3. Suggested timeframes: gold **M5 / M15**, FX **M15 / H1**, BTC **M15 / H1**.
4. HUD top-right shows STATE / HTF / ADX / session.

Logic (v1):

- 4H EMA 50 vs 200 = higher-timeframe bias
- Chart EMA 21 / 50 stack
- ADX chop filter
- Liquidity sweep of prior swing **or** close through that swing (BOS)
- ATR stop, TP1 at 1.8R
- London–NY session on FX/gold (exchange time). BTC can run 24h.

WAIT is the default. No mid-range MA-cross spam.

## 2. Create the alert

On each chart:

1. Alert button → Condition = **THE SMART Ai · TV Signal Desk**
2. Trigger = **Once per bar close**
3. Also tick **alert() function calls only**
4. Notifications:
   - App + email always
   - Webhook URL (Essential plan+): `https://YOUR_VPS:8789/tv/signal`
5. Message box can stay empty — the script already builds the JSON.

Payload shape (matches the desk pulse ticket):

```json
{
  "version": 1,
  "source": "tv-bot",
  "desk": "THE SMART Ai",
  "tag": "smart-ai",
  "pair": "XAUUSD",
  "ticker": "XAUUSD",
  "tf": "15",
  "side": "SELL",
  "state": "ARMED",
  "entry": 4274.10,
  "sl": 4291.40,
  "tp1": 4242.96,
  "rr": "1:1.8",
  "confluence": { "sweep": true, "bos": false, "fvg": false, "ob": false, "mtf": true },
  "thesis": "SELL XAUUSD · HTF bear · ADX 21.4 · sweep · 15",
  "sessionNote": "TV signal · educational only"
}
```

Repeat the alert on EURUSD, GBPUSD, USDJPY, BTCUSD.

## 3. Optional notify webhook

TradingView will not talk to Telegram by itself unless you add a public HTTPS URL.

```bash
export TELEGRAM_BOT_TOKEN='...'
export TELEGRAM_CHAT_ID='...'          # notify channel
export TV_BOT_TAG='smart-ai'
python3 tradingview-bot/webhook.py
```

Put nginx / caddy in front with TLS. Point the TradingView webhook at `https://desk.example/tv/signal`.

Writes:

- `~/smart-ai-tv-signals/last-signal.json`
- `~/smart-ai-tv-signals/signals-YYYYMMDD.jsonl`

`WAIT` rows are dropped. Only BUY/SELL with entry + SL notify.

## 4. Hook later

When you want TV signals on THE SMART Ai blotter, merge `last-signal.json` into `desk-feed.json` pulse rows (`source: tv-bot`). Do not flip GOLD DESK `sotd.status` to LIVE from this script.

## 5. What this is not

- Not a broker connection
- Not a guarantee
- Not the Alchemist 10-pip book or SLK master levels yet — say if you want those gates next
