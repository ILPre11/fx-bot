@echo off
title FX Bot LIVE (demo)
rem Avvio automatico del bot FX Multi-Regime in modalita' LIVE (conto demo).
rem Per attivarlo: copia questo file nella cartella Esecuzione automatica
rem (Win+R -> shell:startup -> Invio, poi incolla il file li').
rem Per disattivarlo: eliminalo da quella cartella.

rem Attende 30s che rete e sistema siano pronti dopo l'accensione
timeout /t 30 /nobreak >nul

cd /d "C:\Users\User\Nuova cartella"
echo Avvio FX Bot in modalita' LIVE (demo)...
echo (Il terminale MT5 viene avviato automaticamente se non e' aperto.)
echo.
.venv\Scripts\python.exe main.py --live

echo.
echo ============================================================
echo Il bot si e' FERMATO. Leggi i messaggi qui sopra per capire
echo il motivo (es. credenziali, MT5 non raggiungibile, doppione).
echo ============================================================
pause
