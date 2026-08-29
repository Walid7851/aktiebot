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
    return "Krypto-boten är igång 24/7!"

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
STARTKAPITAL = 20000.0  # i USD (eller SEK)

TELEGRAM_TOKEN = "8977093798:AAF_vJxuAGRSzw_XNUAj9vf6JLIcEKzDFBc"
TELEGRAM_CHAT_ID = "6873331016"

# Krypto-par från Yahoo Finance
KRYPTO_PAR = ["BTC-USD", "LTC-USD"]
# =================================================

def skicka_telegram_notis(meddelande):
    if TELEGRAM_TOKEN != "" and TELEGRAM_CHAT_ID != "":
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": meddelande}
            res = requests.post(url, data=payload, timeout=5)
            print(f"[Telegram Status]: {res.status_code}", flush=True)
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

skicka_telegram_notis(f"🪙 Krypto-Boten har startat!\nBevakar: Bitcoin (BTC) & Litecoin (LTC)\nStartkapital: ${STARTKAPITAL:,.2f}")
print(f"Krypto-bot startad! Startkapital: ${STARTKAPITAL:,.2f} | Bevakar {KRYPTO_PAR}\n", flush=True)

tz = pytz.timezone('Europe/Stockholm')

while True:
    nu = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{nu}] Analyserar kryptomarknaden... (Kassa: ${kassa:,.2f})", flush=True)
    
    for coin in KRYPTO_PAR:
        try:
            time.sleep(random.uniform(1.5, 3.0))
            objekt = yf.Ticker(coin)
            data = objekt.history(period="1d", interval="5m")
            
            if not data.empty and 'Close' in data:
                df_krypto = data['Close'].dropna()
                
                if len(df_krypto) > 15:
                    senaste_pris = float(df_krypto.iloc[-1])
                    df_temp = pd.DataFrame({'Close': df_krypto})
                    rsi = beräkna_rsi(df_temp)
                    
                    print(f"[{coin}] Pris: ${senaste_pris:,.2f} | RSI: {rsi:.1f}", flush=True)
                    
                    # LOGIK FÖR KÖP / SÄLJ BASERAT PÅ RSI:
                    # Köpsignal: Översålt (RSI < 35) och vi äger inte coinet än
                    if rsi < 35 and coin not in portfölj and kassa >= senaste_pris:
                        köpbelopp = kassa * 0.50  # Köper för 50% av tillgänglig kassa
                        antal = köpbelopp / senaste_pris
                        totalt_köp = antal * senaste_pris
                        
                        kassa -= totalt_köp
                        portfölj[coin] = {'antal': antal, 'köppris': senaste_pris}
                        
                        meddelande = (
                            f"🟢 AUTOMATISKT KRYPTO-KÖP: {coin}\n"
                            f"RSI: {rsi:.1f} (Översålt)\n"
                            f"Köpt: {antal:.4f} st @ ${senaste_pris:,.2f}\n"
                            f"Totalt: ${totalt_köp:,.2f}\n"
                            f"Kassa kvar: ${kassa:,.2f}"
                        )
                        print(meddelande, flush=True)
                        skicka_telegram_notis(meddelande)

                    # Säljsignal: Överköpt (RSI > 65) och vi äger coinet
                    elif rsi > 65 and coin in portfölj:
                        innehav = portfölj[coin]
                        antal = innehav['antal']
                        köppris = innehav['köppris']
                        totalt_sålt = antal * senaste_pris
                        vinst = totalt_sålt - (antal * köppris)
                        
                        kassa += totalt_sålt
                        del portfölj[coin]
                        
                        meddelande = (
                            f"🔴 AUTOMATISK KRYPTO-FÖRSÄLJNING: {coin}\n"
                            f"RSI: {rsi:.1f} (Överköpt)\n"
                            f"Sålt: {antal:.4f} st @ ${senaste_pris:,.2f}\n"
                            f"Vinst/Förlust: ${vinst:+,.2f}\n"
                            f"Ny kassa: ${kassa:,.2f}"
                        )
                        print(meddelande, flush=True)
                        skicka_telegram_notis(meddelande)

        except Exception as e:
            print(f"Fel vid hämtning av {coin}: {e}", flush=True)
            time.sleep(3)
            continue

    # Pausa i 3 minuter innan nästa avläsning
    time.sleep(180)
