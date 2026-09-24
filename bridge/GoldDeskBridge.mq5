//+------------------------------------------------------------------+
//| GoldDeskBridge.mq5                                               |
//| Reads gold_desk_ticket.ini dropped by the VPS listener.          |
//| Broker login stays in this terminal. Do not put it in GitHub.    |
//+------------------------------------------------------------------+
#property copyright "THE SMART Ai / GOLD DESK"
#property version   "1.00"
#property strict

input string TicketFile        = "gold_desk_ticket.ini";
input bool   UseCommonFolder   = true;
input double RiskPercent       = 0.5;
input double FixedLots         = 0.0;      // >0 overrides risk %
input int    Magic             = 260924;
input int    MaxSpreadPoints   = 80;
input int    DeviationPoints   = 40;
input int    PollMs            = 1000;
input bool   AllowMarketFill   = false;    // pending only unless true

string g_last_key = "";
datetime g_last_poll = 0;

string ReadFile()
  {
   int flags = FILE_TXT | FILE_READ | FILE_ANSI | FILE_SHARE_READ;
   if(UseCommonFolder)
      flags |= FILE_COMMON;
   int h = FileOpen(TicketFile, flags);
   if(h == INVALID_HANDLE)
      return "";
   string body = "";
   while(!FileIsEnding(h))
      body += FileReadString(h) + "\n";
   FileClose(h);
   return body;
  }

string IniVal(const string body, const string key)
  {
   string lines[];
   int n = StringSplit(body, '\n', lines);
   for(int i = 0; i < n; i++)
     {
      string line = lines[i];
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringFind(line, key + "=") == 0)
         return StringSubstr(line, StringLen(key) + 1);
     }
   return "";
  }

bool KeyUsed(const string key)
  {
   if(key == "" || key == g_last_key)
      return true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionGetTicket(i) && PositionGetInteger(POSITION_MAGIC) == Magic)
         if(PositionGetString(POSITION_COMMENT) == key)
            return true;
     }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0 && OrderGetInteger(ORDER_MAGIC) == Magic)
         if(OrderGetString(ORDER_COMMENT) == key)
            return true;
     }
   return false;
  }

double LotsFor(const string symbol, const double entry, const double sl)
  {
   if(FixedLots > 0)
      return NormalizeDouble(FixedLots, 2);
   double risk_money = AccountInfoDouble(ACCOUNT_EQUITY) * RiskPercent / 100.0;
   double tick_val = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_sz  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double point    = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(tick_val <= 0 || tick_sz <= 0 || point <= 0)
      return 0;
   double sl_dist = MathAbs(entry - sl);
   if(sl_dist <= 0)
      return 0;
   double money_per_lot = sl_dist / tick_sz * tick_val;
   if(money_per_lot <= 0)
      return 0;
   double lots = risk_money / money_per_lot;
   double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0)
      step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < vmin)
      lots = 0;
   if(lots > vmax)
      lots = vmax;
   return NormalizeDouble(lots, 2);
  }

bool Place(const string symbol, const string side, const double entry, const double sl, const double tp, const string key)
  {
   if(!SymbolSelect(symbol, true))
     {
      Print("GOLD DESK: unknown symbol ", symbol);
      return false;
     }
   long spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   if(spread > MaxSpreadPoints)
     {
      Print("GOLD DESK: spread too wide ", spread);
      return false;
     }
   double lots = LotsFor(symbol, entry, sl);
   if(lots <= 0)
     {
      Print("GOLD DESK: lots=0, check risk / SL distance");
      return false;
     }
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   ENUM_ORDER_TYPE type;
   bool market = false;
   if(side == "SELL")
     {
      if(bid > entry)
         type = ORDER_TYPE_SELL_LIMIT;
      else if(AllowMarketFill)
        {
         type = ORDER_TYPE_SELL;
         market = true;
        }
      else
        {
         Print("GOLD DESK: SELL limit invalid, bid already through entry");
         return false;
        }
     }
   else if(side == "BUY")
     {
      if(ask < entry)
         type = ORDER_TYPE_BUY_LIMIT;
      else if(AllowMarketFill)
        {
         type = ORDER_TYPE_BUY;
         market = true;
        }
      else
        {
         Print("GOLD DESK: BUY limit invalid, ask already through entry");
         return false;
        }
     }
   else
      return false;

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.symbol   = symbol;
   req.volume   = lots;
   req.type     = type;
   req.sl       = sl;
   req.tp       = tp;
   req.magic    = Magic;
   req.comment  = key;
   req.deviation = DeviationPoints;
   req.type_time = ORDER_TIME_GTC;
   if(market)
     {
      req.action = TRADE_ACTION_DEAL;
      req.price  = (side == "SELL" ? bid : ask);
      req.type_filling = ORDER_FILLING_IOC;
     }
   else
     {
      req.action = TRADE_ACTION_PENDING;
      req.price  = entry;
      req.type_filling = ORDER_FILLING_RETURN;
     }
   if(!OrderSend(req, res))
     {
      Print("GOLD DESK OrderSend fail retcode=", res.retcode, " ", res.comment);
      return false;
     }
   Print("GOLD DESK placed ", side, " ", lots, " @ ", req.price, " key=", key, " ticket=", res.order);
   return true;
  }

void ProcessTicket()
  {
   string body = ReadFile();
   if(body == "")
      return;
   string mode   = IniVal(body, "MODE");
   string status = IniVal(body, "STATUS");
   string symbol = IniVal(body, "SYMBOL");
   string side   = IniVal(body, "SIDE");
   string key    = IniVal(body, "KEY");
   double entry  = StringToDouble(IniVal(body, "ENTRY"));
   double sl     = StringToDouble(IniVal(body, "SL"));
   double tp     = StringToDouble(IniVal(body, "TP1"));
   if(mode != "execute" || status != "LIVE")
      return;
   if(symbol == "")
      symbol = _Symbol;
   if(KeyUsed(key))
      return;
   if(entry <= 0 || sl <= 0 || tp <= 0)
      return;
   if(Place(symbol, side, entry, sl, tp, key))
      g_last_key = key;
  }

int OnInit()
  {
   EventSetMillisecondTimer(PollMs);
   Print("GOLD DESK bridge on ", _Symbol, " file=", TicketFile);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   ProcessTicket();
  }

void OnTick()
  {
   if(TimeCurrent() != g_last_poll)
     {
      g_last_poll = TimeCurrent();
      ProcessTicket();
     }
  }
