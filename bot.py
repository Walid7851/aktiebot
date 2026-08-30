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
            requests.get("https://aktiebot.onrender.com", timeout=10)
            print("[Keep-Alive] Pingade Render.", flush=True)
        except Exception as e:
            print(f"[Keep-Alive Fel]: {e}", flush=True)
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

# ================= INSTÄLLNINGAR =================
STARTKAPITAL = 350000.0   # i SEK
COURTAGE_SEK = 99.0       # Courtage i SEK per transaktion (köp & sälj)

TELEGRAM_TOKEN = "8977093798:AAF_vJxuAGRSzw_XNUAj9vf6JLIcEKzDFBc"
TELEGRAM_CHAT_ID = "6873331016"

# Dina valda svenska aktier
AKTIER = [
    "EQT.ST",         # EQT
    "SKF-B.ST",       # SKF B
    "ASSA-B.ST",      # Assa Abloy B
    "INVE-B.ST",      # Investor B
    "XVIVO.ST",       # Xvivo Perfusion
    "BOL.ST"          # Boliden
]

STOP_LOSS_PROCENT = 0.015    # Sälj om aktien faller 1.5%
MIN_VINST_PROCENT = 0.010    # Sälj på RSI > 60 bara om vinsten efter courtage är minst +1.0%
# =================================================

def skicka_telegram_notis(meddelande):
    if TELEGRAM_TOKEN != "" and TELEGRAM_CHAT_ID != "":
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": meddelande}
            requests.post(url, data=payload, timeout=5)
        except Exception as e:
            print(f"Kunde inte skicka Telegram-notis: {e}", flush=True)

kassa = STARTKAPITAL
portfölj = {}

def beräkna_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def är_börsen_öppen(tz):
    nu = datetime.now(tz)
    # 0 = måndag, 4 = fredag
    if nu.weekday() >= 5:
        return False
    
    start = nu.replace(hour=9, minute=0, second=0, microsecond=0)
    slut = nu.replace(hour=17, minute=30, second=0, microsecond=0)
    
    return start <= nu <= slut

skicka_telegram_notis(
    f"🇸🇪 Svenska Aktie-Boten startad!\n"
    f"Bevakar: EQT, SKF, ASSA ABLOY, Investor, XVIVO & Boliden\n"
    f"Startkapital: {STARTKAPITAL:,.2f} SEK\n"
    f"Courtage: {COURTAGE_SEK:.2f} SEK / transaktion"
)

tz = pytz.timezone('Europe/Stockholm')

while True:
    nu = datetime.now(tz)
    tid_str = nu.strftime("%Y-%m-%d %H:%M:%S")
    
    if not är_börsen_öppen(tz):
        print(f"[{tid_str}] Börsen är stängd (Öppen Mån-Fre 09:00-17:30). Väntar...", flush=True)
        time.sleep(300)  # Vänta 5 minuter när börsen är stängd
        continue

    print(f"[{tid_str}] Analyserar aktier... (Kassa: {kassa:,.2f} SEK)", flush=True)
    
    for aktie in AKTIER:
        try:
            time.sleep(random.uniform(1.0, 2.5))
            objekt = yf.Ticker(aktie)
            data = objekt.history(period="1d", interval="5m")
            
            if not data.empty and 'Close' in data:
                df_aktie = data['Close'].dropna()
                
                if len(df_aktie) > 15:
                    senaste_pris = float(df_aktie.iloc[-1])
                    df_temp = pd.DataFrame({'Close': df_aktie})
                    rsi = beräkna_rsi(df_temp)
                    
                    print(f"[{aktie}] Pris: {senaste_pris:,.2f} SEK | RSI: {rsi:.1f}", flush=True)
                    
                    # 1. KÖP: RSI < 35 och vi äger inte aktien
                    if rsi < 35 and aktie not in portfölj and kassa >= (STARTKAPITAL * 0.20):
                        köpbelopp = STARTKAPITAL * 0.20  # Max 20% av startkapitalet per aktie
                        # Dra av köpcourtage från tillgängligt köpbelopp
                        effektivt_köpbelopp = köpbelopp - COURTAGE_SEK
                        antal = int(effektivt_köpbelopp / senaste_pris)
                        
                        if antal > 0:
                            aktiekostnad = antal * senaste_pris
                            totalt_avdrag = aktiekostnad + COURTAGE_SEK
                            
                            kassa -= totalt_avdrag
                            portfölj[aktie] = {
                                'antal': antal, 
                                'köppris': senaste_pris,
                                'total_anskaffning': totalt_avdrag  # Inkl. köpcourtage
                            }
                            
                            meddelande = (
                                f"🟢 AUTOMATISKT AKTIEKÖP: {aktie}\n"
                                f"RSI: {rsi:.1f}\n"
                                f"Köpt: {antal} st @ {senaste_pris:,.2f} SEK\n"
                                f"Aktievärde: {aktiekostnad:,.2f} SEK\n"
                                f"Courtage: {COURTAGE_SEK:.2f} SEK\n"
                                f"Totalt dragen kassa: {totalt_avdrag:,.2f} SEK\n"
                                f"Kassa kvar: {kassa:,.2f} SEK"
                            )
                            print(meddelande, flush=True)
                            skicka_telegram_notis(meddelande)

                    # 2. INNEHAV - KONTROLLERA STOP-LOSS ELLER VINST
                    elif aktie in portfölj:
                        innehav = portfölj[aktie]
                        antal = innehav['antal']
                        köppris = innehav['köppris']
                        total_anskaffning = innehav['total_anskaffning']
                        
                        brutto_försäljning = antal * senaste_pris
                        netto_försäljning = brutto_försäljning - COURTAGE_SEK
                        
                        # Vinst/förlust efter BÅDA courtagen (köp + sälj)
                        nettovinst = netto_försäljning - total_anskaffning
                        utveckling = nettovinst / total_anskaffning

                        # Stop-Loss (-1.5% på aktiepriset)
                        prisutveckling = (senaste_pris - köppris) / köppris
                        if prisutveckling <= -STOP_LOSS_PROCENT:
                            kassa += netto_försäljning
                            del portfölj[aktie]
                            meddelande = (
                                f"🛑 STOP-LOSS UTLÖST: {aktie}\n"
                                f"Nedgång: {prisutveckling*100:.2f}%\n"
                                f"Sålt: {antal} st @ {senaste_pris:,.2f} SEK\n"
                                f"Netto utbetalt (efter säljcourtage): {netto_försäljning:,.2f} SEK\n"
                                f"Total förlust: {nettovinst:,.2f} SEK\n"
                                f"Ny kassa: {kassa:,.2f} SEK"
                            )
                            print(meddelande, flush=True)
                            skicka_telegram_notis(meddelande)

                        # Vinstförsäljning (RSI > 60 och minst +1.0% REN vinst efter båda courtagen)
                        elif rsi > 60 and utveckling >= MIN_VINST_PROCENT:
                            kassa += netto_försäljning
                            del portfölj[aktie]
                            meddelande = (
                                f"🔴 VINST-FÖRSÄLJNING: {aktie}\n"
                                f"RSI: {rsi:.1f} | Netto vinst: +{utveckling*100:.2f}%\n"
                                f"Sålt: {antal} st @ {senaste_pris:,.2f} SEK\n"
                                f"Netto utbetalt (efter säljcourtage): {netto_försäljning:,.2f} SEK\n"
                                f"Ren vinst (efter courtage): +{nettovinst:,.2f} SEK\n"
                                f"Ny kassa: {kassa:,.2f} SEK"
                            )
                            print(meddelande, flush=True)
                            skicka_telegram_notis(meddelande)

        except Exception as e:
            print(f"Fel vid hämtning av {aktie}: {e}", flush=True)
            time.sleep(2)
            continue

    time.sleep(180)
