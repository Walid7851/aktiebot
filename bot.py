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
            # Byt ut URL:en mot din Render-URL
            requests.get("https://din-svenska-bot.onrender.com", timeout=10)
            print("[Keep-Alive] Pingade Render.", flush=True)
        except Exception as e:
            print(f"[Keep-Alive Fel]: {e}", flush=True)
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

# ================= INSTÄLLNINGAR =================
STARTKAPITAL_SEK = 350000.0  # Startkapital i SEK

MIN_COURTAGE_SEK = 1.00       # Minsta courtage i SEK
COURTAGE_PROCENT = 0.0025     # 0.25% courtage

TELEGRAM_TOKEN = "8977093798:AAF_vJxuAGRSzw_XNUAj9vf6JLIcEKzDFBc"
TELEGRAM_CHAT_ID = "6873331016"

AKTIER_SE = [
    "VOLV-B.ST", "INVE-B.ST", "SEB-A.ST", "SHB-A.ST", "SWED-A.ST",
    "ERIC-B.ST", "HM-B.ST", "AZN.ST", "ASSA-B.ST", "ATCO-A.ST",
    "ATCO-B.ST", "SAND.ST", "SKF-B.ST", "TELIA.ST", "EVO.ST",
    "ALFA.ST", "ABB.ST", "BOL.ST", "SCA-B.ST", "ESSITY-B.ST",
    "NIBE-B.ST", "SINCH.ST", "GETI-B.ST", "LUND-B.ST", "EPI-A.ST",
    "SECU-B.ST", "HEXA-B.ST", "SWMA.ST", "SAAB-B.ST", "KINV-B.ST"
]

STOP_LOSS_PROCENT = 0.030    # Höjt till 3.0% för att tåla brus
MIN_VINST_PROCENT = 0.015    # Sälj på RSI > 65 om vinsten är minst 1.5%
# =================================================

def skicka_telegram_notis(meddelande):
    if TELEGRAM_TOKEN != "" and TELEGRAM_CHAT_ID != "":
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": meddelande}
            requests.post(url, data=payload, timeout=5)
        except Exception as e:
            print(f"Kunde inte skicka Telegram-notis: {e}", flush=True)

kassa_sek = STARTKAPITAL_SEK
portfölj = {}

def beräkna_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

skicka_telegram_notis(
    f"🇸🇪 Uppdaterad Aktie-Bot igång!\n"
    f"Kassa: {STARTKAPITAL_SEK:,.2f} SEK\n"
    f"Köpgräns: RSI < 30.0\n"
    f"Positionsstorlek: Dynamisk (30%–100% av kassan)\n"
    f"Stop-Loss: -3.0%\n"
    f"Bevakar: {len(AKTIER_SE)} st aktier"
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
                time.sleep(random.uniform(0.5, 1.2))
                objekt = yf.Ticker(aktie)
                data = objekt.history(period="1d", interval="5m")
                
                if not data.empty and 'Close' in data:
                    df_aktie = data['Close'].dropna()
                    
                    if len(df_aktie) > 15:
                        senaste_pris_sek = float(df_aktie.iloc[-1])
                        df_temp = pd.DataFrame({'Close': df_aktie})
                        rsi = beräkna_rsi(df_temp)
                        
                        print(f"[{aktie}] Pris: {senaste_pris_sek:,.2f} SEK | RSI: {rsi:.1f}", flush=True)
                        
                        # 1. KÖP: Strikt RSI < 30.0 (hoppar över allt på 30.1 eller högre)
                        if rsi < 30.0 and aktie not in portfölj and kassa_sek >= 2000.0:
                            
                            # DYNAMISK SKALNING:
                            # RSI 29.9 ger ~30% av kassan. RSI <= 15 ger 100% av kassan (ALL IN).
                            kassa_andel = min(1.0, max(0.30, (30.0 - rsi) / 15.0 * 0.70 + 0.30))
                            köp_budget_sek = kassa_sek * kassa_andel
                            
                            courtage_sek = max(MIN_COURTAGE_SEK, köp_budget_sek * COURTAGE_PROCENT)
                            netto_köp_sek = köp_budget_sek - courtage_sek
                            
                            antal = int(netto_köp_sek // senaste_pris_sek)
                            
                            if antal > 0:
                                faktiskt_köp_sek = antal * senaste_pris_sek
                                total_kostnad_sek = faktiskt_köp_sek + courtage_sek
                                
                                kassa_sek -= total_kostnad_sek
                                portfölj[aktie] = {
                                    'antal': antal,
                                    'köppris_sek': senaste_pris_sek,
                                    'totalt_sek_betalt': total_kostnad_sek
                                }
                                
                                meddelande = (
                                    f"🟢 AUTOMATISKT KÖP: {aktie}\n"
                                    f"RSI: {rsi:.1f} (Investerar {kassa_andel*100:.0f}% av kassan)\n"
                                    f"Köpt: {antal} st @ {senaste_pris_sek:,.2f} SEK\n"
                                    f"Courtage: {courtage_sek:,.2f} SEK\n"
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
                            sälj_courtage_sek = max(MIN_COURTAGE_SEK, brutto_sek * COURTAGE_PROCENT)
                            netto_utbetalat_sek = brutto_sek - sälj_courtage_sek
                            
                            ren_vinst_sek = netto_utbetalat_sek - totalt_sek_betalt
                            avkastning_procent = ren_vinst_sek / totalt_sek_betalt
                            
                            prisutveckling = (senaste_pris_sek - köppris_sek) / köppris_sek

                            # Stop-Loss (-3.0%)
                            if prisutveckling <= -STOP_LOSS_PROCENT:
                                kassa_sek += netto_utbetalat_sek
                                del portfölj[aktie]
                                meddelande = (
                                    f"🛑 STOP-LOSS: {aktie}\n"
                                    f"Utveckling: {prisutveckling*100:.2f}%\n"
                                    f"Sålt: {antal} st @ {senaste_pris_sek:,.2f} SEK\n"
                                    f"Netto förlust: {ren_vinst_sek:,.2f} SEK\n"
                                    f"Ny kassa: {kassa_sek:,.2f} SEK"
                                )
                                print(meddelande, flush=True)
                                skicka_telegram_notis(meddelande)

                            # Vinstförsäljning (RSI > 65 och minst +1.5% vinst)
                            elif rsi > 65 and avkastning_procent >= MIN_VINST_PROCENT:
                                kassa_sek += netto_utbetalat_sek
                                del portfölj[aktie]
                                meddelande = (
                                    f"🔴 VINST-FÖRSÄLJNING: {aktie}\n"
                                    f"RSI: {rsi:.1f} | Netto vinst: +{avkastning_procent*100:.2f}%\n"
                                    f"Sålt: {antal} st @ {senaste_pris_sek:,.2f} SEK\n"
                                    f"Ren vinst: +{ren_vinst_sek:,.2f} SEK\n"
                                    f"Ny kassa: {kassa_sek:,.2f} SEK"
                                )
                                print(meddelande, flush=True)
                                skicka_telegram_notis(meddelande)

            except Exception as e:
                print(f"Fel vid hämtning av {aktie}: {e}", flush=True)
                time.sleep(1)
                continue

        time.sleep(180)
    else:
        print(f"[{nu.strftime('%Y-%m-%d %H:%M:%S')}] Svenska börsen är stängd. Väntar...", flush=True)
        time.sleep(900)
