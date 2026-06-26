//+------------------------------------------------------------------+
//| FX Multi-Regime Ensemble MT5                                      |
//| Save under: MQL5/Experts/strategy/FX_MultiRegime_Ensemble_MT5.mq5 |
//|                                                                  |
//| Modules:                                                         |
//| 1. Trend Pullback H1/H4                                          |
//| 2. Asia/London Range Breakout                                    |
//| 3. Mean Reversion Range                                          |
//| 4. Volatility Breakout                                           |
//|                                                                  |
//| This EA is for research/backtesting first, not live use by default.|
//+------------------------------------------------------------------+
#property strict
#property version   "2.00"
#property description "FX Multi-Regime Ensemble strategy for MT5 research"

#include <Trade/Trade.mqh>

CTrade trade;

//----------------------------- Inputs --------------------------------
input string          InpSymbols                = "EURUSD,USDJPY,GBPUSD,AUDUSD,USDCHF,EURJPY";
input ENUM_TIMEFRAMES InpSignalTF               = PERIOD_H1;
input ENUM_TIMEFRAMES InpFilterTF               = PERIOD_H4;
input ENUM_TIMEFRAMES InpDailyTF                = PERIOD_D1;

input bool            InpUseTrendModule         = true;
input bool            InpUseAsiaBreakoutModule  = true;
input bool            InpUseMeanReversionModule = true;
input bool            InpUseVolBreakoutModule   = true;
input bool            InpUseSwapFilter          = true;

input long            InpMagicBase              = 26062026;
input int             InpDeviationPoints        = 20;
input double          InpMaxSpreadPips          = 2.0;
input int             InpMaxPositions           = 4;
input int             InpMaxPositionsPerSymbol  = 1;

input double          InpRiskTrendPct           = 0.45;
input double          InpRiskAsiaBreakoutPct    = 0.35;
input double          InpRiskMeanRevPct         = 0.25;
input double          InpRiskVolBreakoutPct     = 0.35;
input double          InpMaxTotalRiskPct        = 2.00;
input double          InpMaxUSDRiskPct          = 1.25;
input double          InpMaxDailyLossPct        = 2.00;
input double          InpMaxWeeklyLossPct       = 4.00;
input double          InpSoftDDPct              = 6.00;
input double          InpHardDDPct              = 10.00;
input double          InpStopModelDDPct         = 15.00;

input int             InpFastEMA                = 20;
input int             InpMediumEMA              = 50;
input int             InpSlowEMA                = 100;
input int             InpLongEMA                = 200;
input int             InpADXPeriod              = 14;
input int             InpATRPeriod              = 14;
input int             InpATRLongPeriod          = 100;
input int             InpBBPeriod               = 20;
input double          InpBBDeviation            = 2.0;
input int             InpRSIPeriod              = 2;
input int             InpDonchianPeriod         = 20;

input double          InpTrendADXH1Min          = 22.0;
input double          InpTrendADXH4Min          = 20.0;
input double          InpTrendATRStopMult       = 2.0;
input double          InpTrendATRTrailMult      = 3.0;
input int             InpTrendTimeStopBars      = 120;

input int             InpServerUTCOffsetHours   = 0;       // Server time = UTC + this offset
input int             InpAsiaStartHourUTC       = 0;
input int             InpAsiaEndHourUTC         = 6;
input int             InpBreakoutStartHourUTC   = 7;
input int             InpBreakoutEndHourUTC     = 11;
input int             InpFridayCutoffHourUTC    = 18;
input double          InpAsiaMinRangeATR        = 0.40;
input double          InpAsiaMaxRangeATR        = 1.20;
input double          InpAsiaBreakoutBufferATR  = 0.10;
input double          InpAsiaMaxStopATR         = 2.20;
input double          InpAsiaTrailATR           = 2.50;
input int             InpAsiaForceExitHourUTC   = 18;
input bool            InpUseAsiaPartialClose    = true;
input double          InpAsiaPartialAtR         = 1.50;
input double          InpAsiaPartialFraction    = 0.50;

input double          InpRangeADXH1Max          = 18.0;
input double          InpRangeADXH4Max          = 20.0;
input double          InpRangeNearEMAMultATR    = 1.00;
input double          InpRangeATRMaxRatio       = 1.10;
input double          InpMeanRSILongMax         = 8.0;
input double          InpMeanRSIShortMin        = 92.0;
input double          InpMeanATRStopMult        = 1.40;
input int             InpMeanTimeStopBars       = 24;
input double          InpMeanEmergencyADX       = 24.0;

input int             InpBBWidthPercentileBars  = 120;
input double          InpCompressionPercentile  = 25.0;
input double          InpAsiaWidthPercentile    = 45.0;
input double          InpVolADXMax              = 20.0;
input double          InpVolATRStopMult         = 1.80;
input double          InpVolTrailATR            = 2.80;
input int             InpVolTimeStopBars        = 96;

input double          InpBreakEvenAtR           = 1.00;
input double          InpBreakEvenLockR         = 0.10;

input bool            InpReduceRiskOnNegSwap    = true;
input double          InpSwapBlockBelow         = -999999.0; // broker-specific. Keep very low to disable blocking.
input double          InpSwapReduceBelow        = 0.0;
input double          InpSwapRiskReductionPct   = 25.0;

input bool            InpPrintDebug             = true;

//----------------------------- Enums ---------------------------------
enum EModule
{
   MODULE_NONE = 0,
   MODULE_TREND = 1,
   MODULE_ASIA_BREAKOUT = 2,
   MODULE_MEAN_REVERSION = 3,
   MODULE_VOL_BREAKOUT = 4
};

//----------------------------- Structs -------------------------------
struct SymbolContext
{
   string   symbol;
   datetime last_bar_time;

   int hEmaFastH1;
   int hEmaMediumH1;
   int hEmaSlowH1;
   int hAdxH1;
   int hAtrH1;
   int hAtrLongH1;
   int hBandsH1;
   int hRsiH1;

   int hEmaMediumH4;
   int hEmaSlowH4;
   int hEmaLongH4;
   int hAdxH4;
   int hAtrH4;

   int hEmaSlowD1;
   int hAtrD1;
   int hAtrLongD1;
};

struct Signal
{
   bool   valid;
   bool   is_buy;
   int    module;
   double risk_pct;
   double sl;
   string comment;
};

struct TicketRiskState
{
   ulong  ticket;
   double initial_r;
   bool   partial_done;
};

SymbolContext   g_ctx[];
TicketRiskState g_ticket_state[];

double g_day_start_equity  = 0.0;
double g_week_start_equity = 0.0;
double g_equity_high       = 0.0;
int    g_day_key           = 0;
int    g_week_key          = 0;

//----------------------------- Helpers -------------------------------
void DebugPrint(const string text)
{
   if(InpPrintDebug)
      Print("FXMR: ", text);
}

string TrimString(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

string ModuleName(const int module)
{
   if(module == MODULE_TREND)          return "TREND";
   if(module == MODULE_ASIA_BREAKOUT)  return "ASIA_BREAKOUT";
   if(module == MODULE_MEAN_REVERSION) return "MEAN_REVERSION";
   if(module == MODULE_VOL_BREAKOUT)   return "VOL_BREAKOUT";
   return "NONE";
}

bool IsOurMagic(const long magic)
{
   return (magic >= InpMagicBase && magic < InpMagicBase + 100);
}

int ModuleFromMagic(const long magic)
{
   if(!IsOurMagic(magic)) return MODULE_NONE;
   return (int)(magic - InpMagicBase);
}

bool IsUSDSymbol(const string symbol)
{
   return (StringFind(symbol, "USD") >= 0);
}

datetime ServerToUTC(const datetime t)
{
   return (t - InpServerUTCOffsetHours * 3600);
}

datetime UTCToServer(const datetime t)
{
   return (t + InpServerUTCOffsetHours * 3600);
}

int DayKey(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
}

int WeekKey(const datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.year * 1000 + (dt.day_of_year / 7);
}

bool IsUTCTradingWindow(const int start_hour, const int end_hour)
{
   datetime utc = ServerToUTC(TimeCurrent());
   MqlDateTime dt;
   TimeToStruct(utc, dt);

   int h = dt.hour;
   if(start_hour == end_hour) return true;
   if(start_hour < end_hour)
      return (h >= start_hour && h < end_hour);
   return (h >= start_hour || h < end_hour);
}

bool IsFridayCutoff()
{
   datetime utc = ServerToUTC(TimeCurrent());
   MqlDateTime dt;
   TimeToStruct(utc, dt);
   if(dt.day_of_week == 5 && dt.hour >= InpFridayCutoffHourUTC)
      return true;
   if(dt.day_of_week == 6)
      return true;
   return false;
}

double PipSize(const string symbol)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(digits == 3 || digits == 5)
      return point * 10.0;
   return point;
}

bool SpreadOK(const string symbol)
{
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0) return false;
   double spread_pips = (ask - bid) / PipSize(symbol);
   return (spread_pips <= InpMaxSpreadPips);
}

bool CopyBufferValue(const int handle, const int buffer, const int shift, double &value)
{
   double tmp[];
   ArrayResize(tmp, 1);
   ArraySetAsSeries(tmp, true);
   int copied = CopyBuffer(handle, buffer, shift, 1, tmp);
   if(copied < 1) return false;
   value = tmp[0];
   return true;
}

bool CopyBufferSeries(const int handle, const int buffer, const int start, const int count, double &out[])
{
   ArrayResize(out, count);
   ArraySetAsSeries(out, true);
   int copied = CopyBuffer(handle, buffer, start, count, out);
   return (copied >= count);
}

bool CopyRatesSeries(const string symbol, const ENUM_TIMEFRAMES tf, const int start, const int count, MqlRates &rates[])
{
   ArrayResize(rates, count);
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, start, count, rates);
   return (copied >= count);
}

bool GetClose(const string symbol, const ENUM_TIMEFRAMES tf, const int shift, double &close_price)
{
   MqlRates rates[];
   if(!CopyRatesSeries(symbol, tf, shift, 1, rates)) return false;
   close_price = rates[0].close;
   return true;
}

bool GetBB(const SymbolContext &ctx, const int shift, double &middle, double &upper, double &lower)
{
   if(!CopyBufferValue(ctx.hBandsH1, 0, shift, middle)) return false;
   if(!CopyBufferValue(ctx.hBandsH1, 1, shift, upper))  return false;
   if(!CopyBufferValue(ctx.hBandsH1, 2, shift, lower))  return false;
   return true;
}

bool GetBBWidth(const SymbolContext &ctx, const int shift, double &width)
{
   double middle, upper, lower;
   if(!GetBB(ctx, shift, middle, upper, lower)) return false;
   if(MathAbs(middle) < 1e-12) return false;
   width = (upper - lower) / MathAbs(middle);
   return true;
}

double PercentileFromArray(double &arr[], const int count, const double pct)
{
   if(count <= 0) return 0.0;
   double tmp[];
   ArrayResize(tmp, count);
   for(int i = 0; i < count; i++) tmp[i] = arr[i];
   ArraySort(tmp);

   double p = MathMax(0.0, MathMin(100.0, pct));
   int idx = (int)MathFloor((count - 1) * p / 100.0);
   idx = MathMax(0, MathMin(count - 1, idx));
   return tmp[idx];
}

bool BBWidthPercentile(const SymbolContext &ctx, const int start_shift, const int bars, const double pct, double &threshold)
{
   if(bars < 10) return false;

   double middle[], upper[], lower[];
   if(!CopyBufferSeries(ctx.hBandsH1, 0, start_shift, bars, middle)) return false;
   if(!CopyBufferSeries(ctx.hBandsH1, 1, start_shift, bars, upper))  return false;
   if(!CopyBufferSeries(ctx.hBandsH1, 2, start_shift, bars, lower))  return false;

   double widths[];
   ArrayResize(widths, bars);
   int n = 0;
   for(int i = 0; i < bars; i++)
   {
      if(MathAbs(middle[i]) < 1e-12) continue;
      widths[n] = (upper[i] - lower[i]) / MathAbs(middle[i]);
      n++;
   }
   if(n < 10) return false;
   threshold = PercentileFromArray(widths, n, pct);
   return true;
}

bool BBWidthAverage(const SymbolContext &ctx, const int start_shift, const int bars, double &avg)
{
   double middle[], upper[], lower[];
   if(!CopyBufferSeries(ctx.hBandsH1, 0, start_shift, bars, middle)) return false;
   if(!CopyBufferSeries(ctx.hBandsH1, 1, start_shift, bars, upper))  return false;
   if(!CopyBufferSeries(ctx.hBandsH1, 2, start_shift, bars, lower))  return false;

   double sum = 0.0;
   int n = 0;
   for(int i = 0; i < bars; i++)
   {
      if(MathAbs(middle[i]) < 1e-12) continue;
      sum += (upper[i] - lower[i]) / MathAbs(middle[i]);
      n++;
   }
   if(n <= 0) return false;
   avg = sum / n;
   return true;
}

bool Donchian(const string symbol, const ENUM_TIMEFRAMES tf, const int period, const int start_shift, double &highest, double &lowest)
{
   MqlRates rates[];
   if(!CopyRatesSeries(symbol, tf, start_shift, period, rates)) return false;

   highest = rates[0].high;
   lowest  = rates[0].low;
   for(int i = 1; i < period; i++)
   {
      if(rates[i].high > highest) highest = rates[i].high;
      if(rates[i].low  < lowest)  lowest  = rates[i].low;
   }
   return true;
}

int FindContextIndex(const string symbol)
{
   int n = ArraySize(g_ctx);
   for(int i = 0; i < n; i++)
   {
      if(g_ctx[i].symbol == symbol) return i;
   }
   return -1;
}

bool IsNewSignalBar(SymbolContext &ctx)
{
   datetime t = iTime(ctx.symbol, InpSignalTF, 0);
   if(t <= 0) return false;
   if(ctx.last_bar_time == 0)
   {
      ctx.last_bar_time = t;
      return false;
   }
   if(t != ctx.last_bar_time)
   {
      ctx.last_bar_time = t;
      return true;
   }
   return false;
}

int VolumeDigitsByStep(const double step)
{
   double x = step;
   int digits = 0;
   while(digits < 8 && MathAbs(x - MathRound(x)) > 1e-8)
   {
      x *= 10.0;
      digits++;
   }
   return digits;
}

double NormalizeVolumeDown(const string symbol, const double volume)
{
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   double minv = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxv = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) return 0.0;

   double v = MathFloor(volume / step + 1e-10) * step;
   if(v < minv) return 0.0;
   if(v > maxv) v = maxv;
   return NormalizeDouble(v, VolumeDigitsByStep(step));
}

bool IsStopDistanceValid(const string symbol, const bool is_buy, const double sl)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int stops_level = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = stops_level * point;
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

   if(is_buy)
   {
      if(sl >= bid - min_dist) return false;
   }
   else
   {
      if(sl <= ask + min_dist) return false;
   }
   return true;
}

bool IsBetterStop(const bool is_buy, const double current_sl, const double candidate_sl)
{
   if(candidate_sl <= 0.0) return false;
   if(current_sl <= 0.0) return true;
   if(is_buy) return (candidate_sl > current_sl);
   return (candidate_sl < current_sl);
}

void TrackTicket(const ulong ticket, const double initial_r)
{
   int n = ArraySize(g_ticket_state);
   for(int i = 0; i < n; i++)
   {
      if(g_ticket_state[i].ticket == ticket)
      {
         g_ticket_state[i].initial_r = initial_r;
         return;
      }
   }
   ArrayResize(g_ticket_state, n + 1);
   g_ticket_state[n].ticket = ticket;
   g_ticket_state[n].initial_r = initial_r;
   g_ticket_state[n].partial_done = false;
}

bool GetTicketInitialR(const ulong ticket, double &initial_r)
{
   int n = ArraySize(g_ticket_state);
   for(int i = 0; i < n; i++)
   {
      if(g_ticket_state[i].ticket == ticket)
      {
         initial_r = g_ticket_state[i].initial_r;
         return (initial_r > 0.0);
      }
   }
   return false;
}

bool IsPartialDone(const ulong ticket)
{
   int n = ArraySize(g_ticket_state);
   for(int i = 0; i < n; i++)
   {
      if(g_ticket_state[i].ticket == ticket) return g_ticket_state[i].partial_done;
   }
   return false;
}

void SetPartialDone(const ulong ticket)
{
   int n = ArraySize(g_ticket_state);
   for(int i = 0; i < n; i++)
   {
      if(g_ticket_state[i].ticket == ticket)
      {
         g_ticket_state[i].partial_done = true;
         return;
      }
   }
}

//----------------------------- Risk ----------------------------------
void UpdateRiskAnchors()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(g_equity_high <= 0.0) g_equity_high = equity;
   if(equity > g_equity_high) g_equity_high = equity;

   int dk = DayKey(TimeCurrent());
   if(dk != g_day_key)
   {
      g_day_key = dk;
      g_day_start_equity = equity;
   }

   int wk = WeekKey(TimeCurrent());
   if(wk != g_week_key)
   {
      g_week_key = wk;
      g_week_start_equity = equity;
   }
}

double CurrentDDPct()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(g_equity_high <= 0.0) return 0.0;
   return MathMax(0.0, (g_equity_high - equity) / g_equity_high * 100.0);
}

double RiskMultiplierByDD()
{
   double dd = CurrentDDPct();
   if(dd >= InpHardDDPct) return 0.0;
   if(dd >= InpSoftDDPct) return 0.5;
   return 1.0;
}

bool DailyOrWeeklyLossBlocked()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(g_day_start_equity > 0.0)
   {
      double day_loss = (g_day_start_equity - equity) / g_day_start_equity * 100.0;
      if(day_loss >= InpMaxDailyLossPct) return true;
   }
   if(g_week_start_equity > 0.0)
   {
      double week_loss = (g_week_start_equity - equity) / g_week_start_equity * 100.0;
      if(week_loss >= InpMaxWeeklyLossPct) return true;
   }
   return false;
}

bool NewEntriesBlocked()
{
   if(IsFridayCutoff()) return true;
   if(DailyOrWeeklyLossBlocked()) return true;
   if(CurrentDDPct() >= InpHardDDPct) return true;
   if(CurrentDDPct() >= InpStopModelDDPct) return true;
   return false;
}

bool PositionRiskMoney(const string symbol, const ENUM_POSITION_TYPE pos_type, const double volume, const double entry, const double sl, double &risk_money)
{
   risk_money = 0.0;
   if(sl <= 0.0 || volume <= 0.0) return false;

   ENUM_ORDER_TYPE order_type = (pos_type == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double profit_at_sl = 0.0;
   if(!OrderCalcProfit(order_type, symbol, volume, entry, sl, profit_at_sl)) return false;

   if(profit_at_sl < 0.0)
      risk_money = -profit_at_sl;
   else
      risk_money = 0.0;
   return true;
}

double CurrentOpenRiskPct(const bool usd_only)
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0) return 0.0;

   double total_risk = 0.0;
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;

      long magic = (long)PositionGetInteger(POSITION_MAGIC);
      if(!IsOurMagic(magic)) continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      if(usd_only && !IsUSDSymbol(symbol)) continue;

      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double entry  = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl     = PositionGetDouble(POSITION_SL);

      double risk_money = 0.0;
      if(PositionRiskMoney(symbol, type, volume, entry, sl, risk_money))
         total_risk += risk_money;
   }
   return total_risk / equity * 100.0;
}

int CountOurPositions(const string symbol_filter = "")
{
   int count = 0;
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      long magic = (long)PositionGetInteger(POSITION_MAGIC);
      if(!IsOurMagic(magic)) continue;
      if(symbol_filter != "" && PositionGetString(POSITION_SYMBOL) != symbol_filter) continue;
      count++;
   }
   return count;
}

bool HasOurPosition(const string symbol)
{
   return (CountOurPositions(symbol) >= InpMaxPositionsPerSymbol);
}

bool SelectOurPositionBySymbol(const string symbol,
                               ulong &ticket,
                               int &module,
                               ENUM_POSITION_TYPE &type,
                               double &volume,
                               double &entry,
                               double &sl,
                               double &tp,
                               datetime &open_time,
                               long &magic)
{
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol) continue;

      long m = (long)PositionGetInteger(POSITION_MAGIC);
      if(!IsOurMagic(m)) continue;

      ticket    = t;
      magic     = m;
      module    = ModuleFromMagic(m);
      type      = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      volume    = PositionGetDouble(POSITION_VOLUME);
      entry     = PositionGetDouble(POSITION_PRICE_OPEN);
      sl        = PositionGetDouble(POSITION_SL);
      tp        = PositionGetDouble(POSITION_TP);
      open_time = (datetime)PositionGetInteger(POSITION_TIME);
      return true;
   }
   return false;
}

double ApplySwapRiskFilter(const string symbol, const bool is_buy, const double base_risk_pct)
{
   if(!InpUseSwapFilter) return base_risk_pct;

   double swap_value = is_buy ? SymbolInfoDouble(symbol, SYMBOL_SWAP_LONG)
                              : SymbolInfoDouble(symbol, SYMBOL_SWAP_SHORT);

   if(swap_value <= InpSwapBlockBelow)
      return 0.0;

   if(InpReduceRiskOnNegSwap && swap_value < InpSwapReduceBelow)
   {
      double reduction = MathMax(0.0, MathMin(100.0, InpSwapRiskReductionPct));
      return base_risk_pct * (1.0 - reduction / 100.0);
   }
   return base_risk_pct;
}

double VolumeForRisk(const string symbol, const bool is_buy, const double risk_pct, const double entry, const double sl)
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0 || risk_pct <= 0.0) return 0.0;
   if(MathAbs(entry - sl) <= 0.0) return 0.0;

   ENUM_ORDER_TYPE order_type = is_buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double profit_for_one_lot = 0.0;
   if(!OrderCalcProfit(order_type, symbol, 1.0, entry, sl, profit_for_one_lot))
      return 0.0;

   double risk_per_lot = MathAbs(profit_for_one_lot);
   if(risk_per_lot <= 0.0) return 0.0;

   double risk_money = equity * risk_pct / 100.0;
   double raw_volume = risk_money / risk_per_lot;
   return NormalizeVolumeDown(symbol, raw_volume);
}

//-------------------------- Regime checks -----------------------------
bool TrendLongRegime(const SymbolContext &ctx)
{
   double ema50[], ema100[], ema200[], adx[];
   if(!CopyBufferSeries(ctx.hEmaMediumH4, 0, 0, 7, ema50)) return false;
   if(!CopyBufferSeries(ctx.hEmaSlowH4,   0, 0, 7, ema100)) return false;
   if(!CopyBufferSeries(ctx.hEmaLongH4,   0, 0, 7, ema200)) return false;
   if(!CopyBufferSeries(ctx.hAdxH4,       0, 0, 3, adx)) return false;

   double close_h4 = 0.0;
   if(!GetClose(ctx.symbol, InpFilterTF, 1, close_h4)) return false;

   return (close_h4 > ema100[1] &&
           ema50[1] > ema100[1] &&
           ema100[1] > ema200[1] &&
           ema100[1] > ema100[6] &&
           adx[1] >= InpTrendADXH4Min);
}

bool TrendShortRegime(const SymbolContext &ctx)
{
   double ema50[], ema100[], ema200[], adx[];
   if(!CopyBufferSeries(ctx.hEmaMediumH4, 0, 0, 7, ema50)) return false;
   if(!CopyBufferSeries(ctx.hEmaSlowH4,   0, 0, 7, ema100)) return false;
   if(!CopyBufferSeries(ctx.hEmaLongH4,   0, 0, 7, ema200)) return false;
   if(!CopyBufferSeries(ctx.hAdxH4,       0, 0, 3, adx)) return false;

   double close_h4 = 0.0;
   if(!GetClose(ctx.symbol, InpFilterTF, 1, close_h4)) return false;

   return (close_h4 < ema100[1] &&
           ema50[1] < ema100[1] &&
           ema100[1] < ema200[1] &&
           ema100[1] < ema100[6] &&
           adx[1] >= InpTrendADXH4Min);
}

bool RangeRegime(const SymbolContext &ctx)
{
   double adx_h1 = 0.0, adx_h4 = 0.0;
   double atr = 0.0, atr_long = 0.0, ema100 = 0.0, close_h1 = 0.0;
   double width1 = 0.0, width3 = 0.0;

   if(!CopyBufferValue(ctx.hAdxH1, 0, 1, adx_h1)) return false;
   if(!CopyBufferValue(ctx.hAdxH4, 0, 1, adx_h4)) return false;
   if(!CopyBufferValue(ctx.hAtrH1, 0, 1, atr)) return false;
   if(!CopyBufferValue(ctx.hAtrLongH1, 0, 1, atr_long)) return false;
   if(!CopyBufferValue(ctx.hEmaSlowH1, 0, 1, ema100)) return false;
   if(!GetClose(ctx.symbol, InpSignalTF, 1, close_h1)) return false;
   if(!GetBBWidth(ctx, 1, width1)) return false;
   if(!GetBBWidth(ctx, 3, width3)) return false;

   if(atr_long <= 0.0) return false;

   return (adx_h1 < InpRangeADXH1Max &&
           adx_h4 < InpRangeADXH4Max &&
           MathAbs(close_h1 - ema100) <= InpRangeNearEMAMultATR * atr &&
           atr <= InpRangeATRMaxRatio * atr_long &&
           width1 <= width3 * 1.25);
}

bool CompressionRegime(const SymbolContext &ctx)
{
   double width1 = 0.0, threshold = 0.0;
   double atr = 0.0, atr_long = 0.0, adx = 0.0;

   if(!GetBBWidth(ctx, 1, width1)) return false;
   if(!BBWidthPercentile(ctx, 1, InpBBWidthPercentileBars, InpCompressionPercentile, threshold)) return false;
   if(!CopyBufferValue(ctx.hAtrH1, 0, 1, atr)) return false;
   if(!CopyBufferValue(ctx.hAtrLongH1, 0, 1, atr_long)) return false;
   if(!CopyBufferValue(ctx.hAdxH1, 0, 1, adx)) return false;

   return (width1 <= threshold && atr < atr_long && adx < InpVolADXMax);
}

//--------------------------- Asia range -------------------------------
bool GetAsiaRange(const string symbol, double &asia_high, double &asia_low)
{
   datetime utc_now = ServerToUTC(TimeCurrent());
   MqlDateTime dt;
   TimeToStruct(utc_now, dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   datetime utc_midnight = StructToTime(dt);

   datetime utc_start = utc_midnight + InpAsiaStartHourUTC * 3600;
   datetime utc_end   = utc_midnight + InpAsiaEndHourUTC * 3600;
   datetime srv_start = UTCToServer(utc_start);
   datetime srv_end   = UTCToServer(utc_end);

   if(TimeCurrent() < srv_end) return false;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, InpSignalTF, srv_start, srv_end, rates);
   if(copied <= 0) return false;

   bool found = false;
   for(int i = 0; i < copied; i++)
   {
      if(rates[i].time < srv_start || rates[i].time >= srv_end) continue;
      if(!found)
      {
         asia_high = rates[i].high;
         asia_low  = rates[i].low;
         found = true;
      }
      else
      {
         if(rates[i].high > asia_high) asia_high = rates[i].high;
         if(rates[i].low  < asia_low)  asia_low  = rates[i].low;
      }
   }
   return found;
}

bool AsiaRangeValid(const SymbolContext &ctx, double &asia_high, double &asia_low)
{
   if(!GetAsiaRange(ctx.symbol, asia_high, asia_low)) return false;

   double atr = 0.0;
   if(!CopyBufferValue(ctx.hAtrH1, 0, 1, atr)) return false;
   if(atr <= 0.0) return false;

   double range = asia_high - asia_low;
   if(range < InpAsiaMinRangeATR * atr) return false;
   if(range > InpAsiaMaxRangeATR * atr) return false;

   double width1 = 0.0, threshold = 0.0;
   if(!GetBBWidth(ctx, 1, width1)) return false;
   if(!BBWidthPercentile(ctx, 1, InpBBWidthPercentileBars, InpAsiaWidthPercentile, threshold)) return false;

   return (width1 <= threshold);
}

//-------------------------- Signal modules ----------------------------
Signal EmptySignal()
{
   Signal s;
   s.valid = false;
   s.is_buy = false;
   s.module = MODULE_NONE;
   s.risk_pct = 0.0;
   s.sl = 0.0;
   s.comment = "";
   return s;
}

bool CheckTrendSignal(const SymbolContext &ctx, Signal &sig)
{
   sig = EmptySignal();
   if(!InpUseTrendModule) return false;

   double ema20[], ema100[], adx[], plusdi[], minusdi[], atr[], atr_long[];
   MqlRates rates[];

   if(!CopyBufferSeries(ctx.hEmaFastH1, 0, 0, 4, ema20)) return false;
   if(!CopyBufferSeries(ctx.hEmaSlowH1, 0, 0, 4, ema100)) return false;
   if(!CopyBufferSeries(ctx.hAdxH1, 0, 0, 4, adx)) return false;
   if(!CopyBufferSeries(ctx.hAdxH1, 1, 0, 4, plusdi)) return false;
   if(!CopyBufferSeries(ctx.hAdxH1, 2, 0, 4, minusdi)) return false;
   if(!CopyBufferSeries(ctx.hAtrH1, 0, 0, 4, atr)) return false;
   if(!CopyBufferSeries(ctx.hAtrLongH1, 0, 0, 4, atr_long)) return false;
   if(!CopyRatesSeries(ctx.symbol, InpSignalTF, 0, 4, rates)) return false;

   bool long_ok = TrendLongRegime(ctx) &&
                  ema20[1] > ema100[1] &&
                  rates[1].close > ema20[1] &&
                  rates[2].close <= ema20[2] &&
                  adx[1] > InpTrendADXH1Min &&
                  plusdi[1] > minusdi[1] &&
                  atr[1] > 0.75 * atr_long[1];

   bool short_ok = TrendShortRegime(ctx) &&
                   ema20[1] < ema100[1] &&
                   rates[1].close < ema20[1] &&
                   rates[2].close >= ema20[2] &&
                   adx[1] > InpTrendADXH1Min &&
                   minusdi[1] > plusdi[1] &&
                   atr[1] > 0.75 * atr_long[1];

   if(!long_ok && !short_ok) return false;

   double ask = SymbolInfoDouble(ctx.symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(ctx.symbol, SYMBOL_BID);

   sig.valid = true;
   sig.is_buy = long_ok;
   sig.module = MODULE_TREND;
   sig.risk_pct = InpRiskTrendPct;
   sig.sl = long_ok ? ask - InpTrendATRStopMult * atr[1]
                    : bid + InpTrendATRStopMult * atr[1];
   sig.comment = "FXMR|TREND";
   return true;
}

bool CheckAsiaBreakoutSignal(const SymbolContext &ctx, Signal &sig)
{
   sig = EmptySignal();
   if(!InpUseAsiaBreakoutModule) return false;
   if(!IsUTCTradingWindow(InpBreakoutStartHourUTC, InpBreakoutEndHourUTC)) return false;

   double asia_high = 0.0, asia_low = 0.0;
   if(!AsiaRangeValid(ctx, asia_high, asia_low)) return false;

   double atr[], adx[];
   MqlRates rates[];
   if(!CopyBufferSeries(ctx.hAtrH1, 0, 0, 4, atr)) return false;
   if(!CopyBufferSeries(ctx.hAdxH1, 0, 0, 4, adx)) return false;
   if(!CopyRatesSeries(ctx.symbol, InpSignalTF, 0, 4, rates)) return false;

   double close_h4 = 0.0, ema100_h4 = 0.0;
   if(!GetClose(ctx.symbol, InpFilterTF, 1, close_h4)) return false;
   if(!CopyBufferValue(ctx.hEmaSlowH4, 0, 1, ema100_h4)) return false;

   bool adx_rising = adx[1] > adx[3];
   bool atr_rising = atr[1] > atr[3];
   double buffer = InpAsiaBreakoutBufferATR * atr[1];

   bool long_ok = rates[1].close > asia_high + buffer &&
                  adx_rising && atr_rising && close_h4 > ema100_h4;

   bool short_ok = rates[1].close < asia_low - buffer &&
                   adx_rising && atr_rising && close_h4 < ema100_h4;

   if(!long_ok && !short_ok) return false;

   double ask = SymbolInfoDouble(ctx.symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(ctx.symbol, SYMBOL_BID);
   double sl = long_ok ? asia_low - buffer : asia_high + buffer;
   double entry = long_ok ? ask : bid;

   if(MathAbs(entry - sl) > InpAsiaMaxStopATR * atr[1]) return false;

   sig.valid = true;
   sig.is_buy = long_ok;
   sig.module = MODULE_ASIA_BREAKOUT;
   sig.risk_pct = InpRiskAsiaBreakoutPct;
   sig.sl = sl;
   sig.comment = "FXMR|ASIA_BREAKOUT";
   return true;
}

bool CheckMeanReversionSignal(const SymbolContext &ctx, Signal &sig)
{
   sig = EmptySignal();
   if(!InpUseMeanReversionModule) return false;
   if(!RangeRegime(ctx)) return false;

   double middle = 0.0, upper = 0.0, lower = 0.0;
   double rsi = 0.0, atr = 0.0;
   MqlRates rates[];
   if(!GetBB(ctx, 1, middle, upper, lower)) return false;
   if(!CopyBufferValue(ctx.hRsiH1, 0, 1, rsi)) return false;
   if(!CopyBufferValue(ctx.hAtrH1, 0, 1, atr)) return false;
   if(!CopyRatesSeries(ctx.symbol, InpSignalTF, 0, 3, rates)) return false;

   double dh = 0.0, dl = 0.0;
   if(!Donchian(ctx.symbol, InpSignalTF, InpDonchianPeriod, 2, dh, dl)) return false;

   double atr1 = 0.0, atr3 = 0.0;
   if(!CopyBufferValue(ctx.hAtrH1, 0, 1, atr1)) return false;
   if(!CopyBufferValue(ctx.hAtrH1, 0, 3, atr3)) return false;
   bool atr_expanding = atr1 > atr3;

   bool broke_down = rates[1].close < dl && atr_expanding;
   bool broke_up   = rates[1].close > dh && atr_expanding;

   bool long_ok = rates[1].close < lower && rsi < InpMeanRSILongMax && !broke_down;
   bool short_ok = rates[1].close > upper && rsi > InpMeanRSIShortMin && !broke_up;

   if(!long_ok && !short_ok) return false;

   double ask = SymbolInfoDouble(ctx.symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(ctx.symbol, SYMBOL_BID);

   sig.valid = true;
   sig.is_buy = long_ok;
   sig.module = MODULE_MEAN_REVERSION;
   sig.risk_pct = InpRiskMeanRevPct;
   sig.sl = long_ok ? ask - InpMeanATRStopMult * atr
                    : bid + InpMeanATRStopMult * atr;
   sig.comment = "FXMR|MEAN_REVERSION";
   return true;
}

bool CheckVolBreakoutSignal(const SymbolContext &ctx, Signal &sig)
{
   sig = EmptySignal();
   if(!InpUseVolBreakoutModule) return false;
   if(!CompressionRegime(ctx)) return false;

   double dh = 0.0, dl = 0.0;
   if(!Donchian(ctx.symbol, InpSignalTF, InpDonchianPeriod, 2, dh, dl)) return false;

   double atr1 = 0.0, atr3 = 0.0, ema50 = 0.0;
   MqlRates rates[];
   if(!CopyBufferValue(ctx.hAtrH1, 0, 1, atr1)) return false;
   if(!CopyBufferValue(ctx.hAtrH1, 0, 3, atr3)) return false;
   if(!CopyBufferValue(ctx.hEmaMediumH1, 0, 1, ema50)) return false;
   if(!CopyRatesSeries(ctx.symbol, InpSignalTF, 0, 3, rates)) return false;

   double close_h4 = 0.0, ema100_h4 = 0.0, ema100_h4_6 = 0.0;
   if(!GetClose(ctx.symbol, InpFilterTF, 1, close_h4)) return false;
   if(!CopyBufferValue(ctx.hEmaSlowH4, 0, 1, ema100_h4)) return false;
   if(!CopyBufferValue(ctx.hEmaSlowH4, 0, 6, ema100_h4_6)) return false;

   bool atr_expands = atr1 > atr3;
   bool h4_flat = MathAbs(ema100_h4 - ema100_h4_6) <= 0.25 * atr1;

   bool long_ok = rates[1].close > dh && atr_expands &&
                  rates[1].close > ema50 &&
                  (close_h4 > ema100_h4 || h4_flat);

   bool short_ok = rates[1].close < dl && atr_expands &&
                   rates[1].close < ema50 &&
                   (close_h4 < ema100_h4 || h4_flat);

   if(!long_ok && !short_ok) return false;

   double ask = SymbolInfoDouble(ctx.symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(ctx.symbol, SYMBOL_BID);

   sig.valid = true;
   sig.is_buy = long_ok;
   sig.module = MODULE_VOL_BREAKOUT;
   sig.risk_pct = InpRiskVolBreakoutPct;
   sig.sl = long_ok ? ask - InpVolATRStopMult * atr1
                    : bid + InpVolATRStopMult * atr1;
   sig.comment = "FXMR|VOL_BREAKOUT";
   return true;
}

//--------------------------- Trade open -------------------------------
bool ChooseSignal(const SymbolContext &ctx, Signal &chosen)
{
   chosen = EmptySignal();

   Signal signals[4];
   int n = 0;

   Signal s;
   if(CheckTrendSignal(ctx, s))          { signals[n] = s; n++; }
   if(CheckAsiaBreakoutSignal(ctx, s))   { signals[n] = s; n++; }
   if(CheckMeanReversionSignal(ctx, s))  { signals[n] = s; n++; }
   if(CheckVolBreakoutSignal(ctx, s))    { signals[n] = s; n++; }

   if(n <= 0) return false;

   bool has_buy = false, has_sell = false;
   for(int i = 0; i < n; i++)
   {
      if(signals[i].is_buy) has_buy = true;
      else has_sell = true;
   }
   if(has_buy && has_sell)
   {
      DebugPrint(ctx.symbol + " skipped: conflicting module signals");
      return false;
   }

   // Priority: Asia in its window, then volatility breakout, trend, mean reversion.
   int priority_modules[4];
   priority_modules[0] = MODULE_ASIA_BREAKOUT;
   priority_modules[1] = MODULE_VOL_BREAKOUT;
   priority_modules[2] = MODULE_TREND;
   priority_modules[3] = MODULE_MEAN_REVERSION;

   for(int p = 0; p < 4; p++)
   {
      int mod = priority_modules[p];
      for(int i = 0; i < n; i++)
      {
         if(signals[i].module == mod)
         {
            chosen = signals[i];
            // If multiple same-direction modules exist, use the most conservative risk.
            double min_risk = chosen.risk_pct;
            for(int j = 0; j < n; j++)
               if(signals[j].risk_pct < min_risk) min_risk = signals[j].risk_pct;
            chosen.risk_pct = min_risk;
            return true;
         }
      }
   }

   return false;
}

bool OpenSignalTrade(const SymbolContext &ctx, Signal &sig)
{
   string symbol = ctx.symbol;
   if(!sig.valid) return false;
   if(!SpreadOK(symbol)) return false;
   if(NewEntriesBlocked()) return false;
   if(HasOurPosition(symbol)) return false;
   if(CountOurPositions() >= InpMaxPositions) return false;

   double risk_mult = RiskMultiplierByDD();
   if(risk_mult <= 0.0) return false;

   double risk_pct = sig.risk_pct * risk_mult;
   risk_pct = ApplySwapRiskFilter(symbol, sig.is_buy, risk_pct);
   if(risk_pct <= 0.0) return false;

   if(CurrentOpenRiskPct(false) + risk_pct > InpMaxTotalRiskPct) return false;
   if(IsUSDSymbol(symbol) && CurrentOpenRiskPct(true) + risk_pct > InpMaxUSDRiskPct) return false;

   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double entry = sig.is_buy ? ask : bid;
   double sl = sig.sl;

   if(!IsStopDistanceValid(symbol, sig.is_buy, sl))
   {
      DebugPrint(symbol + " skipped: stop level too close");
      return false;
   }

   double volume = VolumeForRisk(symbol, sig.is_buy, risk_pct, entry, sl);
   if(volume <= 0.0)
   {
      DebugPrint(symbol + " skipped: volume <= 0");
      return false;
   }

   trade.SetExpertMagicNumber(InpMagicBase + sig.module);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(symbol);

   bool ok = false;
   if(sig.is_buy)
      ok = trade.Buy(volume, symbol, 0.0, sl, 0.0, sig.comment);
   else
      ok = trade.Sell(volume, symbol, 0.0, sl, 0.0, sig.comment);

   if(!ok)
   {
      DebugPrint(symbol + " order failed. Retcode=" + IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultRetcodeDescription());
      return false;
   }

   // Track initial R from the position ticket after opening.
   if(PositionSelect(symbol))
   {
      long magic = (long)PositionGetInteger(POSITION_MAGIC);
      if(IsOurMagic(magic))
      {
         ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
         TrackTicket(ticket, MathAbs(entry - sl));
      }
   }

   DebugPrint(symbol + " opened " + (sig.is_buy ? "BUY " : "SELL ") + ModuleName(sig.module) +
              " risk=" + DoubleToString(risk_pct, 2) + "% vol=" + DoubleToString(volume, 2));
   return true;
}

//------------------------- Position manage ----------------------------
bool HighestLowestSince(const string symbol, const datetime since_time, double &highest, double &lowest)
{
   int shift = iBarShift(symbol, InpSignalTF, since_time, false);
   if(shift < 1) shift = 1;
   int bars = shift + 2;

   MqlRates rates[];
   if(!CopyRatesSeries(symbol, InpSignalTF, 0, bars, rates)) return false;

   highest = rates[0].high;
   lowest = rates[0].low;
   for(int i = 1; i < bars; i++)
   {
      if(rates[i].high > highest) highest = rates[i].high;
      if(rates[i].low < lowest) lowest = rates[i].low;
   }
   return true;
}

void TryMoveStop(const string symbol, const bool is_buy, const double candidate_sl, const double tp)
{
   if(!PositionSelect(symbol)) return;
   double current_sl = PositionGetDouble(POSITION_SL);
   if(!IsBetterStop(is_buy, current_sl, candidate_sl)) return;
   if(!IsStopDistanceValid(symbol, is_buy, candidate_sl)) return;

   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(symbol);
   if(!trade.PositionModify(symbol, candidate_sl, tp))
      DebugPrint(symbol + " PositionModify failed: " + trade.ResultRetcodeDescription());
}

void ClosePosition(const string symbol, const string reason)
{
   if(!PositionSelect(symbol)) return;
   long magic = (long)PositionGetInteger(POSITION_MAGIC);
   if(!IsOurMagic(magic)) return;

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(symbol);
   if(!trade.PositionClose(symbol))
      DebugPrint(symbol + " close failed: " + trade.ResultRetcodeDescription());
   else
      DebugPrint(symbol + " closed: " + reason);
}

void TryAsiaPartialClose(const string symbol, const ulong ticket, const double volume, const double profit_move, const double initial_r, const long magic)
{
   if(!InpUseAsiaPartialClose) return;
   if(IsPartialDone(ticket)) return;
   if(initial_r <= 0.0) return;
   if(profit_move < InpAsiaPartialAtR * initial_r) return;

   double close_volume = NormalizeVolumeDown(symbol, volume * InpAsiaPartialFraction);
   double minv = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   if(close_volume < minv) return;
   if(volume - close_volume < minv) return;

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(symbol);

   if(trade.PositionClosePartial(symbol, close_volume))
   {
      SetPartialDone(ticket);
      DebugPrint(symbol + " partial close executed");
   }
}

void ManagePositionForSymbol(SymbolContext &ctx)
{
   string symbol = ctx.symbol;

   ulong ticket = 0;
   int module = MODULE_NONE;
   ENUM_POSITION_TYPE type;
   double volume = 0.0, entry = 0.0, sl = 0.0, tp = 0.0;
   datetime open_time = 0;
   long magic = 0;

   if(!SelectOurPositionBySymbol(symbol, ticket, module, type, volume, entry, sl, tp, open_time, magic))
      return;

   bool is_buy = (type == POSITION_TYPE_BUY);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double current = is_buy ? bid : ask;
   double profit_move = is_buy ? current - entry : entry - current;

   double initial_r = 0.0;
   if(!GetTicketInitialR(ticket, initial_r))
   {
      if(sl > 0.0) initial_r = MathAbs(entry - sl);
      if(initial_r > 0.0) TrackTicket(ticket, initial_r);
   }
   if(initial_r <= 0.0) return;

   // Break-even after +R.
   if(profit_move >= InpBreakEvenAtR * initial_r)
   {
      double be_sl = is_buy ? entry + InpBreakEvenLockR * initial_r
                            : entry - InpBreakEvenLockR * initial_r;
      TryMoveStop(symbol, is_buy, be_sl, tp);
   }

   int bars_since_open = iBarShift(symbol, InpSignalTF, open_time, false);
   if(bars_since_open < 0) bars_since_open = 0;

   double atr = 0.0;
   CopyBufferValue(ctx.hAtrH1, 0, 1, atr);

   // Module-specific exits.
   if(module == MODULE_TREND)
   {
      double ema20 = 0.0, ema100 = 0.0;
      if(CopyBufferValue(ctx.hEmaFastH1, 0, 1, ema20) && CopyBufferValue(ctx.hEmaSlowH1, 0, 1, ema100))
      {
         if(is_buy && ema20 < ema100)  { ClosePosition(symbol, "trend cross exit"); return; }
         if(!is_buy && ema20 > ema100) { ClosePosition(symbol, "trend cross exit"); return; }
      }

      if(bars_since_open >= InpTrendTimeStopBars && profit_move < 0.50 * initial_r)
      {
         ClosePosition(symbol, "trend time stop");
         return;
      }

      if(atr > 0.0)
      {
         double highest = 0.0, lowest = 0.0;
         if(HighestLowestSince(symbol, open_time, highest, lowest))
         {
            double trail_sl = is_buy ? highest - InpTrendATRTrailMult * atr
                                     : lowest + InpTrendATRTrailMult * atr;
            TryMoveStop(symbol, is_buy, trail_sl, tp);
         }
      }
   }
   else if(module == MODULE_ASIA_BREAKOUT)
   {
      TryAsiaPartialClose(symbol, ticket, volume, profit_move, initial_r, magic);

      if(IsUTCTradingWindow(InpAsiaForceExitHourUTC, InpAsiaForceExitHourUTC + 1) && profit_move < 0.50 * initial_r)
      {
         ClosePosition(symbol, "asia force exit");
         return;
      }

      if(atr > 0.0)
      {
         double highest = 0.0, lowest = 0.0;
         if(HighestLowestSince(symbol, open_time, highest, lowest))
         {
            double trail_sl = is_buy ? highest - InpAsiaTrailATR * atr
                                     : lowest + InpAsiaTrailATR * atr;
            TryMoveStop(symbol, is_buy, trail_sl, tp);
         }
      }
   }
   else if(module == MODULE_MEAN_REVERSION)
   {
      double middle = 0.0, upper = 0.0, lower = 0.0;
      if(GetBB(ctx, 1, middle, upper, lower))
      {
         if(is_buy && current >= middle)  { ClosePosition(symbol, "mean target middle band"); return; }
         if(!is_buy && current <= middle) { ClosePosition(symbol, "mean target middle band"); return; }
      }

      double adx = 0.0;
      if(CopyBufferValue(ctx.hAdxH1, 0, 1, adx))
      {
         if(adx > InpMeanEmergencyADX && profit_move < 0.0)
         {
            ClosePosition(symbol, "mean emergency ADX exit");
            return;
         }
      }

      if(bars_since_open >= InpMeanTimeStopBars)
      {
         ClosePosition(symbol, "mean time stop");
         return;
      }
   }
   else if(module == MODULE_VOL_BREAKOUT)
   {
      double width1 = 0.0, width_avg = 0.0;
      if(GetBBWidth(ctx, 1, width1) && BBWidthAverage(ctx, 1, 50, width_avg))
      {
         if(width1 < width_avg && profit_move < 0.50 * initial_r)
         {
            ClosePosition(symbol, "vol compression returned");
            return;
         }
      }

      if(bars_since_open >= InpVolTimeStopBars && profit_move < 0.50 * initial_r)
      {
         ClosePosition(symbol, "vol time stop");
         return;
      }

      if(atr > 0.0)
      {
         double highest = 0.0, lowest = 0.0;
         if(HighestLowestSince(symbol, open_time, highest, lowest))
         {
            double trail_sl = is_buy ? highest - InpVolTrailATR * atr
                                     : lowest + InpVolTrailATR * atr;
            TryMoveStop(symbol, is_buy, trail_sl, tp);
         }
      }
   }
}

void EvaluateEntriesForSymbol(SymbolContext &ctx)
{
   if(NewEntriesBlocked()) return;
   if(!SpreadOK(ctx.symbol)) return;
   if(HasOurPosition(ctx.symbol)) return;

   Signal chosen;
   if(!ChooseSignal(ctx, chosen)) return;
   OpenSignalTrade(ctx, chosen);
}

//------------------------------ Init ---------------------------------
bool CreateHandles(SymbolContext &ctx)
{
   string s = ctx.symbol;

   ctx.hEmaFastH1   = iMA(s, InpSignalTF, InpFastEMA,   0, MODE_EMA, PRICE_CLOSE);
   ctx.hEmaMediumH1 = iMA(s, InpSignalTF, InpMediumEMA, 0, MODE_EMA, PRICE_CLOSE);
   ctx.hEmaSlowH1   = iMA(s, InpSignalTF, InpSlowEMA,   0, MODE_EMA, PRICE_CLOSE);
   ctx.hAdxH1       = iADX(s, InpSignalTF, InpADXPeriod);
   ctx.hAtrH1       = iATR(s, InpSignalTF, InpATRPeriod);
   ctx.hAtrLongH1   = iATR(s, InpSignalTF, InpATRLongPeriod);
   ctx.hBandsH1     = iBands(s, InpSignalTF, InpBBPeriod, 0, InpBBDeviation, PRICE_CLOSE);
   ctx.hRsiH1       = iRSI(s, InpSignalTF, InpRSIPeriod, PRICE_CLOSE);

   ctx.hEmaMediumH4 = iMA(s, InpFilterTF, InpMediumEMA, 0, MODE_EMA, PRICE_CLOSE);
   ctx.hEmaSlowH4   = iMA(s, InpFilterTF, InpSlowEMA,   0, MODE_EMA, PRICE_CLOSE);
   ctx.hEmaLongH4   = iMA(s, InpFilterTF, InpLongEMA,   0, MODE_EMA, PRICE_CLOSE);
   ctx.hAdxH4       = iADX(s, InpFilterTF, InpADXPeriod);
   ctx.hAtrH4       = iATR(s, InpFilterTF, InpATRPeriod);

   ctx.hEmaSlowD1   = iMA(s, InpDailyTF, InpSlowEMA,    0, MODE_EMA, PRICE_CLOSE);
   ctx.hAtrD1       = iATR(s, InpDailyTF, InpATRPeriod);
   ctx.hAtrLongD1   = iATR(s, InpDailyTF, InpATRLongPeriod);

   if(ctx.hEmaFastH1   == INVALID_HANDLE || ctx.hEmaMediumH1 == INVALID_HANDLE ||
      ctx.hEmaSlowH1   == INVALID_HANDLE || ctx.hAdxH1       == INVALID_HANDLE ||
      ctx.hAtrH1       == INVALID_HANDLE || ctx.hAtrLongH1   == INVALID_HANDLE ||
      ctx.hBandsH1     == INVALID_HANDLE || ctx.hRsiH1       == INVALID_HANDLE ||
      ctx.hEmaMediumH4 == INVALID_HANDLE || ctx.hEmaSlowH4   == INVALID_HANDLE ||
      ctx.hEmaLongH4   == INVALID_HANDLE || ctx.hAdxH4       == INVALID_HANDLE ||
      ctx.hAtrH4       == INVALID_HANDLE || ctx.hEmaSlowD1   == INVALID_HANDLE ||
      ctx.hAtrD1       == INVALID_HANDLE || ctx.hAtrLongD1   == INVALID_HANDLE)
   {
      return false;
   }

   return true;
}

void ReleaseContext(SymbolContext &ctx)
{
   int handles[16];
   handles[0]  = ctx.hEmaFastH1;
   handles[1]  = ctx.hEmaMediumH1;
   handles[2]  = ctx.hEmaSlowH1;
   handles[3]  = ctx.hAdxH1;
   handles[4]  = ctx.hAtrH1;
   handles[5]  = ctx.hAtrLongH1;
   handles[6]  = ctx.hBandsH1;
   handles[7]  = ctx.hRsiH1;
   handles[8]  = ctx.hEmaMediumH4;
   handles[9]  = ctx.hEmaSlowH4;
   handles[10] = ctx.hEmaLongH4;
   handles[11] = ctx.hAdxH4;
   handles[12] = ctx.hAtrH4;
   handles[13] = ctx.hEmaSlowD1;
   handles[14] = ctx.hAtrD1;
   handles[15] = ctx.hAtrLongD1;

   for(int i = 0; i < 16; i++)
   {
      if(handles[i] != INVALID_HANDLE)
         IndicatorRelease(handles[i]);
   }
}

int OnInit()
{
   string parts[];
   int raw_count = StringSplit(InpSymbols, ',', parts);
   if(raw_count <= 0)
   {
      Print("FXMR: no symbols configured");
      return INIT_FAILED;
   }

   ArrayResize(g_ctx, 0);
   for(int i = 0; i < raw_count; i++)
   {
      string sym = TrimString(parts[i]);
      if(sym == "") continue;

      if(!SymbolSelect(sym, true))
      {
         Print("FXMR: cannot select symbol ", sym);
         continue;
      }

      int n = ArraySize(g_ctx);
      ArrayResize(g_ctx, n + 1);
      g_ctx[n].symbol = sym;
      g_ctx[n].last_bar_time = 0;

      if(!CreateHandles(g_ctx[n]))
      {
         Print("FXMR: indicator handle creation failed for ", sym);
         ReleaseContext(g_ctx[n]);
         ArrayResize(g_ctx, n);
         continue;
      }

      Print("FXMR: loaded symbol ", sym);
   }

   if(ArraySize(g_ctx) <= 0)
   {
      Print("FXMR: no valid symbols loaded");
      return INIT_FAILED;
   }

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_day_start_equity = equity;
   g_week_start_equity = equity;
   g_equity_high = equity;
   g_day_key = DayKey(TimeCurrent());
   g_week_key = WeekKey(TimeCurrent());

   trade.SetDeviationInPoints(InpDeviationPoints);

   Print("FXMR: initialized with ", ArraySize(g_ctx), " symbols. Use Strategy Tester with real ticks for final validation.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   for(int i = 0; i < ArraySize(g_ctx); i++)
      ReleaseContext(g_ctx[i]);
}

void OnTick()
{
   UpdateRiskAnchors();

   for(int i = 0; i < ArraySize(g_ctx); i++)
   {
      ManagePositionForSymbol(g_ctx[i]);

      if(IsNewSignalBar(g_ctx[i]))
         EvaluateEntriesForSymbol(g_ctx[i]);
   }
}

//+------------------------------------------------------------------+
