"""Report demo vs backtest: confronta i trade LIVE del bot con le attese.

Legge dallo storico MT5 i trade chiusi dal bot (magic = config.MAGIC),
calcola PF / win rate / payoff / profitto netto e li affianca alle attese
del backtest validato (strategies/validated/*.md). Serve a decidere, con
i numeri, se e quando il comportamento live replica quello validato.

Uso:
  python report.py                  report a schermo
  python report.py --telegram       invia anche il riepilogo su Telegram
  python report.py --since 2026-07-02   data di inizio (default: avvio live)
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

import config

# Giorno in cui il bot e' andato in --live sul demo Vantage 5K.
LIVE_START = "2026-07-02"

# Attese dal backtest validato (fonte: strategies/validated/*.md, 2026-07-01).
# I valori OOS del walk-forward sono il riferimento piu' prudente.
EXPECTATIONS = {
    "NZDUSD": {"strategia": "Trend Pullback", "pf": 1.32, "wr": 0.40,
               "payoff": 1.98, "trades_anno": 170 / 8, "pf_oos": (1.33, 1.58)},
    "USDJPY": {"strategia": "Vol Breakout", "pf": 1.28, "wr": 0.39,
               "payoff": 2.00, "trades_anno": 164 / 8, "pf_oos": (1.36, 1.64)},
}

MIN_TRADES_VERDICT = 20   # sotto questa soglia il confronto non e' significativo


def _closed_trades(since: datetime, magic: int) -> dict[str, list[float]]:
    """Profitti netti (profit+swap+commission) dei trade chiusi, per simbolo.

    Raggruppa i deal per position_id: un trade e' chiuso quando ha un deal
    di uscita (DEAL_ENTRY_OUT); il netto somma tutti i deal della posizione.
    """
    deals = mt5.history_deals_get(since, datetime.now(timezone.utc) + timedelta(days=1))
    if deals is None:
        raise SystemExit(f"history_deals_get fallita: {mt5.last_error()}")

    by_position: dict[int, list] = defaultdict(list)
    for d in deals:
        if d.magic == magic and d.position_id:
            by_position[d.position_id].append(d)

    profits: dict[str, list[float]] = defaultdict(list)
    for pos_deals in by_position.values():
        if not any(d.entry == mt5.DEAL_ENTRY_OUT for d in pos_deals):
            continue  # posizione ancora aperta
        net = sum(d.profit + d.swap + d.commission for d in pos_deals)
        profits[pos_deals[0].symbol].append(net)
    return profits


def _stats(profits: list[float]) -> dict:
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "n": len(profits),
        "wr": len(wins) / len(profits) if profits else 0.0,
        "pf": gross_win / gross_loss if gross_loss > 0 else float("inf"),
        "payoff": ((gross_win / len(wins)) / (gross_loss / len(losses))
                   if wins and losses else 0.0),
        "net": sum(profits),
    }


def _fmt_pf(pf: float) -> str:
    return "inf" if pf == float("inf") else f"{pf:.2f}"


def build_report(since_str: str) -> str:
    since = datetime.strptime(since_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    days = max((datetime.now(timezone.utc) - since).days, 1)
    profits = _closed_trades(since, config.MAGIC)
    open_pos = [p for p in (mt5.positions_get() or []) if p.magic == config.MAGIC]
    acc = mt5.account_info()

    lines = [f"REPORT DEMO vs BACKTEST  ({since_str} -> oggi, {days} giorni)",
             f"Account {acc.login} [{'DEMO' if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else 'REALE'}]"
             f"  equity {acc.equity:.2f} {acc.currency}", ""]

    total_n = 0
    for symbol, exp in EXPECTATIONS.items():
        st = _stats(profits.get(symbol, []))
        total_n += st["n"]
        expected_n = exp["trades_anno"] * days / 365
        lines.append(f"--- {symbol} ({exp['strategia']}) ---")
        lines.append(f"  Trade chiusi : {st['n']}   (attesi nel periodo: ~{expected_n:.1f})")
        if st["n"]:
            lines.append(f"  Win rate     : {st['wr']:.0%}   (backtest: {exp['wr']:.0%})")
            lines.append(f"  Profit Factor: {_fmt_pf(st['pf'])}   "
                         f"(backtest: {exp['pf']:.2f}, OOS {exp['pf_oos'][0]:.2f}-{exp['pf_oos'][1]:.2f})")
            lines.append(f"  Payoff       : {st['payoff']:.2f}   (backtest: {exp['payoff']:.2f})")
            lines.append(f"  Netto        : {st['net']:+.2f} {acc.currency}")
        lines.append("")

    extra = {s: p for s, p in profits.items() if s not in EXPECTATIONS}
    for symbol, pr in extra.items():
        st = _stats(pr)
        lines.append(f"--- {symbol} (FUORI STRATEGIA!) --- trade={st['n']} netto={st['net']:+.2f}")
        lines.append("")

    if open_pos:
        lines.append("Posizioni aperte del bot:")
        for p in open_pos:
            side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
            lines.append(f"  {p.symbol} {side} {p.volume} @ {p.price_open}  "
                         f"P/L {p.profit:+.2f} {acc.currency}")
    else:
        lines.append("Posizioni aperte del bot: nessuna")
    lines.append("")

    if total_n < MIN_TRADES_VERDICT:
        lines.append(f"VERDETTO: campione insufficiente ({total_n}/{MIN_TRADES_VERDICT} trade "
                     "chiusi): continuare il demo, nessuna conclusione possibile.")
    else:
        pf_all = _stats([p for pr in profits.values() for p in pr])["pf"]
        ok = pf_all >= 1.0
        lines.append(f"VERDETTO: {total_n} trade, PF complessivo {_fmt_pf(pf_all)} -> "
                     + ("coerente: confrontare le metriche per simbolo con le attese."
                        if ok else "PF sotto 1: live NON in linea con il backtest, indagare."))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report demo vs backtest del bot.")
    parser.add_argument("--since", default=LIVE_START, help="data inizio (YYYY-MM-DD)")
    parser.add_argument("--telegram", action="store_true", help="invia il report su Telegram")
    args = parser.parse_args()

    ok = mt5.initialize(config.MT5_PATH) if config.MT5_PATH else mt5.initialize()
    if not ok:
        raise SystemExit(f"Connessione MT5 fallita: {mt5.last_error()}")
    try:
        report = build_report(args.since)
    finally:
        mt5.shutdown()

    print(report)
    if args.telegram and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        from forex_bot.telegram import TelegramNotifier
        sent = TelegramNotifier(config.TELEGRAM_BOT_TOKEN,
                                config.TELEGRAM_CHAT_ID).send(f"<pre>{report}</pre>")
        print(f"\n[telegram] inviato: {sent}")


if __name__ == "__main__":
    main()
