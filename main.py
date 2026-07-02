"""Punto d'ingresso: analizza i mercati con la strategia FX Multi-Regime (port
dell'EA) e mostra i segnali.

Uso:
  python main.py                      analisi singola (una passata sui simboli)
  python main.py --watch              monitoraggio continuo (su nuova barra H4, da config)
  python main.py --watch --interval 60   controlla ogni 60s (default 30)
  python main.py --watch --watch-tf H1   ri-valuta su ogni barra H1 invece che H4
  python main.py --live               trading automatico su demo:
                                        - attiva AUTO_EXECUTE
                                        - applica portfolio risk layer (DD, max pos, Friday)
                                        - re-ottimizza ogni notte a mezzanotte UTC
                                        - usa solo i moduli/simboli con edge (PF≥1.5, ≥30 trade)
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import config
from forex_bot.executors.manual import ManualExecutor
from forex_bot.executors.mt5_executor import Mt5Executor
from forex_bot.models import MarketData, Signal
from forex_bot.mt5_client import Mt5Client, Mt5Error
from forex_bot.risk import lots_for_risk, position_size
from forex_bot.strategies.fx_multi_regime import FxMultiRegimeStrategy
from forex_bot.telegram import TelegramNotifier


_MODULE_FLAGS = {"trend": "use_trend", "vol": "use_vol",
                 "meanrev": "use_mean_rev", "asia": "use_asia"}


def build_strategies(active_modules: dict[int, list[str]] | None = None
                     ) -> dict[str, FxMultiRegimeStrategy]:
    """Una strategia per simbolo: attiva SOLO i moduli VALIDATI per quella coppia
    (config.VALIDATED_STRATEGIES), con parametri DEFAULT + modello di uscita
    validato (TP a R:R + time-stop). Niente parametri ottimizzati (overfit)."""
    strategies: dict[str, FxMultiRegimeStrategy] = {}
    for symbol in config.SYMBOLS:
        s = FxMultiRegimeStrategy(
            risk_trend_pct=config.RISK_TREND_PCT,
            risk_asia_pct=config.RISK_ASIA_PCT,
            risk_vol_pct=config.RISK_VOL_PCT,
            risk_mean_pct=config.RISK_MEAN_PCT,
        )
        # attiva solo i moduli validati per questa coppia
        active = config.VALIDATED_STRATEGIES.get(symbol)
        if active is not None:
            s.use_trend = s.use_mean_rev = s.use_vol = s.use_asia = False
            for m in active:
                setattr(s, _MODULE_FLAGS[m], True)
        # modello di uscita validato (altrimenti niente TP/time-stop)
        s.rr = config.EXIT_RR
        s.max_bars_open = config.EXIT_MAX_BARS
        s._active_modules = active_modules
        strategies[symbol] = s
    return strategies


def analyze(client, strategy, symbol, equity, offset):
    """Scarica i dati, genera l'idea e calcola i lotti. Ritorna (Signal|None, info)."""
    info = client.symbol(symbol)
    tick = client.tick(symbol)
    rates = {tf: client.rates(symbol, tf, config.BARS) for tf in strategy.required_timeframes}
    data = MarketData(symbol, tick.bid, tick.ask, rates, info, offset)

    idea = _generate_for_symbol(strategy, data, symbol)
    if idea is None:
        return None, info

    risk_pct = idea.risk_pct if idea.risk_pct is not None else config.RISK_PCT
    loss = client.loss_per_lot(symbol, idea.side, idea.entry, idea.stop_loss)
    lots = (lots_for_risk(equity, risk_pct, loss, info) if loss
            else position_size(equity, risk_pct, idea.entry, idea.stop_loss, info))

    primary_tf = strategy.required_timeframes[0]
    bar_time = data.df(primary_tf)["time"].iloc[-2].to_pydatetime()
    signal = Signal(symbol, primary_tf, idea.side, idea.entry, idea.stop_loss,
                    idea.take_profit, lots, equity * risk_pct, risk_pct,
                    idea.reason, bar_time)
    return signal, info


def _generate_for_symbol(strategy, data, symbol):
    """Chiama strategy.generate() abilitando solo i moduli attivi per questo simbolo."""
    active = getattr(strategy, "_active_modules", None)
    if active is None:
        # modalita' segnali: usa tutti i moduli configurati nella strategia
        return strategy.generate(data)

    # modalita' live: abilita solo i moduli che hanno edge su questo simbolo
    from forex_bot.strategies.fx_multi_regime import (
        MODULE_TREND, MODULE_ASIA, MODULE_MEANREV, MODULE_VOL,
    )
    orig = (strategy.use_trend, strategy.use_mean_rev, strategy.use_vol, strategy.use_asia)
    strategy.use_trend = MODULE_TREND in active and symbol in active[MODULE_TREND]
    strategy.use_mean_rev = MODULE_MEANREV in active and symbol in active[MODULE_MEANREV]
    strategy.use_vol = MODULE_VOL in active and symbol in active[MODULE_VOL]
    strategy.use_asia = MODULE_ASIA in active and symbol in active[MODULE_ASIA]

    try:
        return strategy.generate(data)
    finally:
        strategy.use_trend, strategy.use_mean_rev, strategy.use_vol, strategy.use_asia = orig


def run_once(client, strategies, executor, offset, notifier=None, portfolio=None):
    acc = client.account()
    for symbol in config.SYMBOLS:
        try:
            signal, info = analyze(client, strategies[symbol], symbol, acc.equity, offset)
            if signal is None:
                print(f"[{symbol}] Nessun segnale.")
            else:
                if portfolio is not None:
                    ok, reason = portfolio.can_trade(symbol, acc.equity, config.MAGIC)
                    if not ok:
                        print(f"[{symbol}] Bloccato: {reason}")
                        continue
                executor.handle(signal, info)
                if notifier:
                    notifier.send_signal(signal, info)
                print()
        except Mt5Error as exc:
            print(f"[{symbol}] Errore: {exc}")


def watch(client, strategies, executor, offset, interval, max_cycles=0, notifier=None,
          watch_tf="H1", live_mode=False):
    watch_tf = watch_tf.upper()
    mode_label = "LIVE (auto-trading demo)" if live_mode else "WATCH"
    print(f"Modalita' {mode_label} - controllo ogni {interval}s, "
          f"valuto su nuova barra {watch_tf}. Ctrl+C per uscire.\n")

    portfolio = None
    if live_mode:
        from risk import portfolio_layer as _pl
        _pl.MAX_DAILY_DD = config.PORTFOLIO_MAX_DAILY_DD
        _pl.MAX_OPEN_POSITIONS = config.PORTFOLIO_MAX_POSITIONS
        _pl.FRIDAY_CUTOFF_HOUR = config.PORTFOLIO_FRIDAY_CUTOFF_HOUR
        portfolio = _pl
    # Time-stop ottimizzato per-simbolo (chiude le posizioni troppo vecchie)
    max_bars = {sym: s.max_bars_open for sym, s in strategies.items() if s.max_bars_open}

    active_modules: dict[int, list[str]] | None = None
    last_optimizer_date: str = ""

    last_seen: dict[str, object] = {}
    cycle = 0
    try:
        while True:
            cycle += 1
            acc = client.account()

            # ---- re-ottimizzazione notturna (solo --live, se abilitata) ------
            if live_mode and config.LIVE_NIGHTLY_REOPTIMIZE:
                today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                now_hour = datetime.now(timezone.utc).hour
                if today_utc != last_optimizer_date and now_hour >= config.LIVE_OPTIMIZER_HOUR:
                    print(f"\n[{_ts()}] Re-ottimizzazione notturna...")
                    try:
                        from optimizer.run_optimizer import run_optimizer
                        active_modules = run_optimizer(client)
                        for _s in strategies.values():
                            _s._active_modules = active_modules
                        last_optimizer_date = today_utc
                        if notifier:
                            _notify_optimizer(notifier, active_modules)
                    except Exception as exc:
                        print(f"[Optimizer] ERRORE: {exc}  (mantengo config precedente)")

            # ---- controlli di rischio di portafoglio (sempre in --live) ------
            # Devono girare a OGNI ciclo live, indipendentemente dalla
            # re-ottimizzazione notturna: gestiscono le posizioni GIA' aperte
            # (Friday cutoff, DD giornaliero, time-stop del modello validato).
            if live_mode and portfolio:
                # Traccia il picco di equity a ogni ciclo (serve al DD giornaliero),
                # anche quando non ci sono segnali che chiamano can_trade().
                portfolio.update_equity_peak(acc.equity)

                # ---- Friday cutoff ------------------------------------------
                if portfolio.is_friday_cutoff():
                    print(f"[{_ts()}] Friday cutoff: chiudo tutte le posizioni del bot.")
                    n = portfolio.close_all_bot_positions(config.MAGIC)
                    print(f"  Chiuse {n} posizioni. Bot in pausa fino a lunedì.")
                    time.sleep(interval)
                    continue

                # ---- DD giornaliero -----------------------------------------
                if portfolio.is_daily_dd_breached(acc.equity):
                    print(f"[{_ts()}] DD giornaliero -10% superato "
                          f"(equity {acc.equity:.2f}). Nessun nuovo trade oggi.")
                    time.sleep(interval)
                    continue

                # ---- time-stop del modello validato (chiude posizioni vecchie) -
                if max_bars:
                    n = portfolio.close_expired_positions(max_bars, config.MAGIC)
                    if n:
                        print(f"[{_ts()}] Time-stop: chiuse {n} posizioni oltre la durata massima.")

            # ---- normale logica di watch ------------------------------------
            new_syms = []
            for symbol in config.SYMBOLS:
                try:
                    bar_time = client.rates(symbol, watch_tf, 3)["time"].iloc[-2]
                    if last_seen.get(symbol) != bar_time:
                        last_seen[symbol] = bar_time
                        new_syms.append(symbol)
                except Mt5Error as exc:
                    print(f"[{symbol}] errore: {exc}")

            if new_syms:
                stamp = _ts()
                print(f"[{stamp}] nuova barra {watch_tf} - analizzo {len(new_syms)} simbolo/i...")
                found = 0
                acc = client.account()  # equity aggiornata

                for symbol in new_syms:
                    try:
                        signal, info = analyze(client, strategies[symbol], symbol, acc.equity, offset)
                        if signal is None:
                            continue
                        if portfolio is not None:
                            ok, reason = portfolio.can_trade(symbol, acc.equity, config.MAGIC)
                            if not ok:
                                print(f"  [{symbol}] Bloccato: {reason}")
                                continue
                        executor.handle(signal, info)
                        if notifier:
                            notifier.send_signal(signal, info)
                        print()
                        found += 1
                    except Mt5Error as exc:
                        print(f"[{symbol}] errore: {exc}")

                if not found:
                    print("  nessun segnale su questa barra.\n")

            if max_cycles and cycle >= max_cycles:
                break
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nWatch interrotto.")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _notify_optimizer(notifier, active_modules: dict) -> None:
    if not active_modules:
        msg = "🔄 Re-ottimizzazione: nessuna combo supera PF≥1.5+15 trade. Bot in standby."
    else:
        lines = ["🔄 Re-ottimizzazione completata. Combo attive:"]
        for mod_id, symbols in active_modules.items():
            from forex_bot.strategies.fx_multi_regime import (
                MODULE_TREND, MODULE_ASIA, MODULE_MEANREV, MODULE_VOL,
            )
            names = {MODULE_TREND: "TREND", MODULE_MEANREV: "MEANREV",
                     MODULE_VOL: "VOL", MODULE_ASIA: "ASIA"}
            lines.append(f"  {names.get(mod_id, mod_id)}: {', '.join(symbols)}")
        msg = "\n".join(lines)
    try:
        notifier.send(msg)
    except Exception:
        pass


def detect_offset(client) -> int:
    offset = config.SERVER_UTC_OFFSET
    if offset is not None:
        print(f"Offset server (da config): UTC{offset:+d}\n")
        return offset
    offset = client.server_utc_offset(config.SYMBOLS[0])
    if offset is None:
        print("[avviso] Offset server non rilevato (tick non fresco?); uso UTC+0. "
              "Imposta SERVER_UTC_OFFSET in config.py se serve.\n")
        return 0
    print(f"Offset server rilevato: UTC{offset:+d}\n")
    return offset


def _acquire_single_instance(port: int = 59321):
    """Lock anti-doppione: prova a riservare una porta locale. Se fallisce, un
    altro bot (--live/--watch) e' gia' in esecuzione. Ritorna il socket (da
    tenere vivo per tutta la durata) oppure None se gia' attivo altrove.
    Si libera da solo alla chiusura del processo (niente lock-file rimasti)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="FX Multi-Regime: analisi e segnali da MT5.")
    parser.add_argument("--watch", action="store_true",
                        help="monitoraggio continuo (nuova barra H4)")
    parser.add_argument("--live", action="store_true",
                        help="trading automatico su demo: AUTO_EXECUTE + portfolio risk + re-ottimizzazione notturna")
    parser.add_argument("--interval", type=int, default=30,
                        help="secondi tra i controlli in --watch / --live")
    parser.add_argument("--cycles", type=int, default=0,
                        help="numero di cicli watch (0 = infinito)")
    parser.add_argument("--watch-tf", default=config.WATCH_TIMEFRAME,
                        help="timeframe su cui scatta il watch (default da config.WATCH_TIMEFRAME)")
    args = parser.parse_args()

    if not config.MT5_LOGIN or not config.MT5_PASSWORD or not config.MT5_SERVER:
        raise SystemExit("Credenziali mancanti: compila il file .env (vedi .env.example).")

    live_mode = args.live
    auto_execute = config.AUTO_EXECUTE or live_mode

    # Anti-doppione: un solo bot continuo per volta (evita ordini duplicati).
    _lock = None
    if live_mode or args.watch:
        _lock = _acquire_single_instance()
        if _lock is None:
            raise SystemExit(
                "ERRORE: un altro bot (--live/--watch) e' GIA' in esecuzione.\n"
                "Chiudi prima quello attivo (Ctrl+C nella sua finestra) per evitare "
                "ordini doppi. Avvio annullato.")

    strategies = build_strategies(active_modules=None)  # una per simbolo, params ottimizzati se presenti
    executor = (Mt5Executor(magic=config.MAGIC, deviation=config.DEVIATION)
                if auto_execute else ManualExecutor())
    notifier = None
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)

    try:
        with Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD,
                       config.MT5_SERVER, config.MT5_PATH) as client:
            acc = client.account()
            tipo = "DEMO" if client.is_demo() else "REALE (!)"
            mode_label = "LIVE AUTO-TRADE" if live_mode else ("AUTO" if auto_execute else "segnali")
            print(f"Connesso: account {acc.login} [{tipo}] - equity {acc.equity:.2f} "
                  f"{acc.currency}  |  strategia: fx_multi_regime  |  profilo: {config.RISK_PROFILE}"
                  f"  |  modalita': {mode_label}\n")

            # Mostra le strategie validate attive (modulo per coppia, params default)
            print("Strategie VALIDATE attive (parametri default + uscita R:R "
                  f"{config.EXIT_RR:.1f} / time-stop {config.EXIT_MAX_BARS} barre):")
            for sym, mods in config.VALIDATED_STRATEGIES.items():
                print(f"  - {sym}: {', '.join(m.upper() for m in mods)}")
            print()

            if auto_execute and not client.is_demo():
                print("ATTENZIONE: esecuzione automatica attiva ma conto NON demo. "
                      "Ordini bloccati per sicurezza.\n")

            if live_mode:
                print("Modalita' LIVE attivata:")
                print(f"  - AUTO_EXECUTE: ON (solo demo)")
                print(f"  - Portfolio risk: DD giornaliero -{config.PORTFOLIO_MAX_DAILY_DD:.0%}, "
                      f"max {config.PORTFOLIO_MAX_POSITIONS} posizioni, "
                      f"Friday cutoff ore {config.PORTFOLIO_FRIDAY_CUTOFF_HOUR} UTC")
                if config.LIVE_NIGHTLY_REOPTIMIZE:
                    print(f"  - Re-ottimizzazione: ogni notte alle {config.LIVE_OPTIMIZER_HOUR:02d}:00 UTC")
                    print("\nAvvio prima ottimizzazione (potrebbe richiedere qualche minuto)...")
                    from optimizer.run_optimizer import run_optimizer
                    active_modules = run_optimizer(client)
                    for _s in strategies.values():
                        _s._active_modules = active_modules
                    if notifier:
                        _notify_optimizer(notifier, active_modules)
                else:
                    print("  - Strategie validate FISSE (nessuna re-ottimizzazione)")
                print()

            offset = detect_offset(client)
            if notifier:
                print("Notifiche Telegram: attive\n")

            if args.watch or live_mode:
                watch(client, strategies, executor, offset, args.interval, args.cycles,
                      notifier, args.watch_tf, live_mode=live_mode)
            else:
                run_once(client, strategies, executor, offset, notifier)
    except Mt5Error as exc:
        raise SystemExit(f"Connessione a MT5 fallita: {exc}")


if __name__ == "__main__":
    main()
