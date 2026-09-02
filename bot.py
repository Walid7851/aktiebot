import warnings
warnings.filterwarnings("ignore")

import logging
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

import threading
import os
import random
import time
import requests
from datetime import datetime
import pytz
from flask import Flask
import yfinance as yf
import pandas as pd

app = Flask(__name__)

@app.route('/')
def home():
    return "Svenska Aktie-Boten körs!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

def keep_alive():
    while True:
        try:
            # Rätt URL till din Render-app
            requests.get("https://aktiebot.onrender.com", timeout=10)
            print("[Keep-Alive] Pingade Render.", flush=True)
        except Exception as e:
            print(f"[Keep-Alive Fel]: {e}", flush=True)
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

# ================= INSTÄLLNINGAR =================
STARTKAPITAL_SEK = 350000.0  # Ursprungligt startkapital i SEK
FAST_COURTAGE_SEK = 99.00    # Fast courtage på EXAKT 99 SEK per transaktion
MINSTA_KÖPBELOPP_SEK = 25000.0 # Spärr för mindre köp

TELEGRAM_TOKEN = "8977093798:AAF_vJxuAGRSzw_XNUAj9vf6JLIcEKzDFBc"
TELEGRAM_CHAT_ID = "6873331016"

AKTIER_SE = [
    "VOLV-B.ST", "INVE-B.ST", "SEB-A.ST", "SHB-A.ST", "SWED-A.ST",
    "ERIC-B.ST", "AZN.ST", "ASSA-B.ST", "ATCO-A.ST", "EQT.ST",
    "SAND.ST", "SKF-B.ST", "TELIA.ST", "EVO.ST", "ALFA.ST",
    "ABB.ST", "BOL.ST", "SCA-B.ST", "ESSITY-B.ST", "NIBE-B.ST",
    "SINCH.ST", "GETI-B.ST", "LUND-B.ST", "EPI-A.ST", "SECU-B.ST",
    "HEXA-B.ST", "SWMA.ST", "SAAB-B.ST", "KINV-B.ST", "BIOA-B.ST"
]

STOP_LOSS_PROCENT = 0.030    # Stop-Loss på -3.0%
MIN_VINST_PROCENT = 0.015    # Sälj på RSI > 65 om ren vinst är minst +1.5% efter båda courtagen
# =================================================

def skicka_telegram_notis(meddelande):
    if TELEGRAM_TOKEN != "" and TELEGRAM_CHAT_ID != "":
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": meddelande}
            requests.post(url, data=payload, timeout=5)
        except Exception as e:
            print(f"Kunde inte skicka Telegram-notis: {e}", flush=True)

# ---------------- BEFINTLIGT INNEHAV (VOLVO B) ----------------
VOLVO_ANTAL = 1012
VOLVO_KÖPPRIS = 345.50
VOLVO_TOTALT_BETALT = (VOLVO_ANTAL * VOLVO_KÖPPRIS) + FAST_COURTAGE_SEK  # 349 742 SEK

# Justera startkassan med dragen köpeskilling
kassa_sek = STARTKAPITAL_SEK - VOLVO_TOTALT_BETALT  # Återstår: 258.00 SEK

portfölj = {
    "VOLV-B.ST": {
        'antal': VOLVO_ANTAL,
        'köppris_sek': VOLVO_KÖPPRIS,
        'totalt_sek_betalt': VOLVO_TOTALT_BETALT
    }
}
# -------------------------------------------------------------

def beräkna_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

skicka_telegram_notis(
    f"🇸🇪 Aktie-Bot igång (Innehav laddat)!\n"
    f"Kassa: {kassa_sek:,.2f} SEK\n"
    f"Befintligt innehav: 1 012 st VOLV-B.ST @ {VOLVO_KÖPPRIS:.2f} SEK\n"
    f"Köpgräns: RSI < 30.0\n"
    f"Courtage: Fast 99.00 SEK per köp/sälj\n"
    f"Bevakar: {len(AKTIER_SE)} st svenska aktier"
)

tz = pytz.timezone('Europe/Stockholm')

while True:
    nu = datetime.now(tz)
    
    # Börsens öppettider (09:00 - 17:30 CET)
    if nu.weekday() < 5 and ((nu.hour == 9 and nu.minute >= 0) or (10 <= nu.hour < 17) or (nu.hour == 17 and nu.minute <= 30)):
        tid_str = nu.strftime("%Y-%m-%d %H:%M:%S CET")
        print(f"[{tid_str}] Svenska Börsen Öppen | Kassa: {kassa_sek:,.2f} SEK", flush=True)
        
        for aktie in AKTIER_SE:
            try:
                # Ökad väntetid mellan aktier (2.5 till 4.0 sek) för att undvika Rate Limit
                time.sleep(random.uniform(2.5, 4.0))
                
                objekt = yf.Ticker(aktie)
                data = objekt.history(period="1d", interval="5m")
                
                if not data.empty and 'Close' in data:
                    df_aktie = data['Close'].dropna()
                    
                    if len(df_aktie) > 15:
                        senaste_pris_sek = float(df_aktie.iloc[-1])
                        df_temp = pd.DataFrame({'Close': df_aktie})
                        rsi = beräkna_rsi(df_temp)
                        
                        print(f"[{aktie}] Pris: {senaste_pris_sek:,.2f} SEK | RSI: {rsi:.1f}", flush=True)
                        
                        # 1. KÖP: RSI < 30.0 och tillräcklig kassa
                        if rsi < 30.0 and aktie not in portfölj and kassa_sek >= MINSTA_KÖPBELOPP_SEK:
                            
                            kassa_andel = min(1.0, max(0.30, (30.0 - rsi) / 15.0 * 0.70 + 0.30))
                            köp_budget_sek = max(MINSTA_KÖPBELOPP_SEK, kassa_sek * kassa_andel)
                            
                            if köp_budget_sek > kassa_sek:
                                köp_budget_sek = kassa_sek
                            
                            netto_köp_sek = köp_budget_sek - FAST_COURTAGE_SEK
                            antal = int(netto_köp_sek // senaste_pris_sek)
                            
                            if antal > 0:
                                faktiskt_köp_sek = antal * senaste_pris_sek
                                total_kostnad_sek = faktiskt_köp_sek + FAST_COURTAGE_SEK
                                
                                kassa_sek -= total_kostnad_sek
                                portfölj[aktie] = {
                                    'antal': antal,
                                    'köppris_sek': senaste_pris_sek,
                                    'totalt_sek_betalt': total_kostnad_sek
                                }
                                
                                meddelande = (
                                    f"🟢 AUTOMATISKT AKTIEKÖP: {aktie}\n"
                                    f"RSI: {rsi:.1f} (Investerar {kassa_andel*100:.0f}% av kassan)\n"
                                    f"Köpt: {antal} st @ {senaste_pris_sek:,.2f} SEK\n"
                                    f"Aktievärde: {faktiskt_köp_sek:,.2f} SEK\n"
                                    f"Courtage: {FAST_COURTAGE_SEK:.2f} SEK\n"
                                    f"Totalt dragen kassa: {total_kostnad_sek:,.2f} SEK\n"
                                    f"Kassa kvar: {kassa_sek:,.2f} SEK"
                                )
                                print(meddelande, flush=True)
                                skicka_telegram_notis(meddelande)

                        # 2. INNEHAV - STOP-LOSS ELLER VINST
                        elif aktie in portfölj:
                            innehav = portfölj[aktie]
                            antal = innehav['antal']
                            köppris_sek = innehav['köppris_sek']
                            totalt_sek_betalt = innehav['totalt_sek_betalt']
                            
                            brutto_sek = antal * senaste_pris_sek
                            netto_utbetalat_sek = brutto_sek - FAST_COURTAGE_SEK
                            
                            ren_vinst_sek = netto_utbetalat_sek - totalt_sek_betalt
                            avkastning_procent = ren_vinst_sek / totalt_sek_betalt
                            
                            prisutveckling = (senaste_pris_sek - köppris_sek) / köppris_sek

                            # Stop-Loss (-3.0%)
                            if prisutveckling <= -STOP_LOSS_PROCENT:
                                kassa_sek += netto_utbetalat_sek
                                del portfölj[aktie]
                                meddelande = (
                                    f"🛑 STOP-LOSS UTLÖST: {aktie}\n"
                                    f"Nedgång: {prisutveckling*100:.2f}%\n"
                                    f"Sålt: {antal} st @ {senaste_pris_sek:,.2f} SEK\n"
                                    f"Netto utbetalt (efter säljcourtage): {netto_utbetalat_sek:,.2f} SEK\n"
                                    f"Total förlust: {ren_vinst_sek:,.2f} SEK\n"
                                    f"Ny kassa: {kassa_sek:,.2f} SEK"
                                )
                                print(meddelande, flush=True)
                                skicka_telegram_notis(meddelande)

                            # Vinstförsäljning (RSI > 65 och minst +1.5% REN vinst efter courtage)
                            elif rsi > 65 and avkastning_procent >= MIN_VINST_PROCENT:
                                kassa_sek += netto_utbetalat_sek
                                del portfölj[aktie]
                                meddelande = (
                                    f"🔴 VINST-FÖRSÄLJNING: {aktie}\n"
                                    f"RSI: {rsi:.1f} | Netto vinst: +{avkastning_procent*100:.2f}%\n"
                                    f"Sålt: {antal} st @ {senaste_pris_sek:,.2f} SEK\n"
                                    f"Ren vinst (efter courtage): +{ren_vinst_sek:,.2f} SEK\n"
                                    f"Ny kassa: {kassa_sek:,.2f} SEK"
                                )
                                print(meddelande, flush=True)
                                skicka_telegram_notis(meddelande)

            except Exception as e:
                err_msg = str(e)
                print(f"Fel vid hämtning av {aktie}: {err_msg}", flush=True)
                if "Too Many Requests" in err_msg or "Rate limited" in err_msg:
                    print("⚠️ Yahoo Finance Rate Limit upptäckt! Pausar boten i 3 minuter...", flush=True)
                    time.sleep(180)
                else:
                    time.sleep(2)
                continue

        # Vänta 5 minuter mellan svepen
        time.sleep(300)
    else:
        print(f"[{nu.strftime('%Y-%m-%d %H:%M:%S')}] Svenska börsen är stängd. Väntar...", flush=True)
        time.sleep(900)
