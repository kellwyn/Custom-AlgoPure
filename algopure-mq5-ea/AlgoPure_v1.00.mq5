//+------------------------------------------------------------------+
//|  AlgoPure — v1.00                                                |
//|  Date    : 2026-04-23                                            |
//|  Author  : kellwyn                                               |
//|  Desc    : Strategy TBD — implement rules starting with Rule 1  |
//+------------------------------------------------------------------+
#property copyright "kellwyn"
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//|  Inputs                                                          |
//+------------------------------------------------------------------+
input group "=== Risk Management ==="
input double InpRiskPct      = 1.0;      // Risk % per trade
input double InpSLPoints     = 20.0;     // Stop loss in points
input double InpTPPoints     = 30.0;     // Take profit in points
input double InpMaxLots      = 2.0;      // Max lot size (0 = no cap)

input group "=== Trade Management ==="
input bool   InpManualConfirm = true;    // Require manual confirmation
input int    InpMagicNumber   = 20260423;// Magic number

input group "=== Session Filter ==="
input bool   InpFilterSession = true;    // Enable session filter
input int    InpSessionStartH = 9;       // Session start hour (server time)
input int    InpSessionStartM = 30;      // Session start minute
input int    InpSessionEndH   = 16;      // Session end hour
input int    InpSessionEndM   = 0;       // Session end minute

//+------------------------------------------------------------------+
//|  Globals                                                         |
//+------------------------------------------------------------------+
#include <Trade\Trade.mqh>
CTrade Trade;

datetime g_lastBar = 0;

//+------------------------------------------------------------------+
//|  OnInit                                                          |
//+------------------------------------------------------------------+
int OnInit()
{
   Trade.SetExpertMagicNumber(InpMagicNumber);
   Print("AlgoPure v1.00 initialised.");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//|  OnDeinit                                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("AlgoPure v1.00 deinitialised. Reason: ", reason);
}

//+------------------------------------------------------------------+
//|  OnTick — bar-open gate                                          |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime barTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(barTime == g_lastBar) return;
   g_lastBar = barTime;

   RunStrategy();
}

//+------------------------------------------------------------------+
//|  RunStrategy — implement strategy rules here                     |
//+------------------------------------------------------------------+
void RunStrategy()
{
   if(InpFilterSession && !IsInSession()) return;
   if(HasOpenPosition()) return;

   // TODO: implement strategy rules
   // Rule 1: ...
   // Rule 2: ...
}

//+------------------------------------------------------------------+
//|  IsInSession                                                     |
//+------------------------------------------------------------------+
bool IsInSession()
{
   MqlDateTime now;
   TimeToStruct(TimeCurrent(), now);
   int mins = now.hour * 60 + now.min;
   int start = InpSessionStartH * 60 + InpSessionStartM;
   int end   = InpSessionEndH   * 60 + InpSessionEndM;
   return (mins >= start && mins < end);
}

//+------------------------------------------------------------------+
//|  HasOpenPosition                                                 |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
         if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
            PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
            return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//|  CalcLots — risk-based position sizing                           |
//+------------------------------------------------------------------+
double CalcLots(double slPoints)
{
   if(slPoints <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmt   = balance * InpRiskPct / 100.0;
   double tickVal   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double pointSize = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   if(tickSize == 0 || tickVal == 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double valPerPt = tickVal / tickSize * pointSize;
   double lots     = riskAmt / (slPoints * pointSize * (valPerPt / pointSize));

   double maxLots  = InpMaxLots > 0
                     ? MathMin(InpMaxLots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX))
                     : SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double minLots  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double step     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   lots = MathMax(minLots, MathMin(maxLots, lots));
   if(step > 0) lots = MathFloor(lots / step) * step;

   return lots;
}
//+------------------------------------------------------------------+
