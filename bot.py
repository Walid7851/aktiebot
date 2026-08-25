import warnings
warnings.filterwarnings("ignore")

import threading
import os
from flask import Flask

# Lura Render med en dummy-webbserver
app = Flask(__name__)

@app.route('/')
def home():
    return "Boten är igång!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime
from google import genai

# ================= INSTÄLLNINGAR =================
GEMINI_API_KEY = "AQ.Ab8RN6Ltxf7nHve5zqN7tFlG1JmYrJ-miL3sERLiqAgi0cuotA"
STARTKAPITAL = 200000.0

TELEGRAM_TOKEN = "8977093798:AAF_vJxuAGRSzw_XNUAj9vf6JLIcEKzDFBc"
TELEGRAM_CHAT_ID = "6873331016"

SVENSKA_AKTIER = [
    "VOLV-B.ST", "ERIC-B.ST", "INVE-B.ST", "ATCO-A.ST", "HM-B.ST",
    "SEB-A.ST", "SAND.ST", "EVO.ST", "NIBE-B.ST", "TELIA.ST",
    "EQT.ST", "SKF-B.ST", "TREL-B.ST", "ASSA-B.ST", "ABB.ST",
    "AZN.ST", "ALFA.ST", "BIOA-B.ST", "XVIVO.ST"
]
# =================================================

def skicka_telegram_notis(meddelande):
    if TELEGRAM_TOKEN != "" and TELEGRAM_CHAT_ID != "":
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": meddelande}
            requests.post(url, data=payload, timeout=5)
        except Exception as e:
            print(f"Kunde inte skicka Telegram-notis: {e}", flush=True)

client = genai.Client(api_key=GEMINI_API_KEY)
kassa = STARTKAPITAL
portfölj = {}

def beräkna_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def utvärdera_aktie_med_gemini(ticker, pris, rsi, nyhet_titel, tillgänglig_kassa):
    prompt = f"""
    Du är en erfaren och riskmedveten aktiehandlare på Stockholmsbörsen.
    Gör en helhetsbedömning av följande aktie:

    - Aktie: {ticker}
    - Aktuellt Pris: {pris:.2f} SEK
    - RSI (14-minuter): {rsi:.2f} (Vägledning: RSI < 30 är översålt/köpläge, RSI > 70 är överköpt/säljläge)
    - Senaste nyhet: "{nyhet_titel}"
    - Tillgänglig kassa i portföljen: {tillgänglig_kassa:.2f} SEK

    Väg samman BÅDE den tekniska indikatorn (RSI) och nyhetsfundamentan.
    Sätt ett samlat beslutsbetyg (1-10) samt HUR STOR ANDEL av den tillgängliga kassan (mellan 20% och 100%) som är rimlig att investera baserat på hur stark och säker signalen är.

    - Betyg 8-10: Köp. Ange allokering i procent (t.ex. 25%, 50% eller 100%).
    - Betyg 4-7: Avvakta. Allokering = 0%.
    - Betyg 1-3: Sälj. Allokering = 0%.

    Svara BARA i detta exakta format utan extra tecken:
    BETYG: [siffra] | ALLOKERING: [procentsats]% | MOTIVERING: [max 1 kort mening]
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        return f"FEL: {e}"

skicka_telegram_notis(f"🚀 AI-Boten har startats på Render med {STARTKAPITAL:,.2f} SEK i kassan!")
print(f"Bot startad på Render! Startkapital: {STARTKAPITAL:,.2f} SEK | Bevakar {len(SVENSKA_AKTIER)} aktier\n", flush=True)

while True:
    nu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{nu}] Analyserar marknad via Gemini... (Kassa: {kassa:,.2f} SEK)", flush=True)
    
    for ticker in SVENSKA_AKTIER:
        try:
            # Pausa 3 sekunder mellan varje aktie för att undvika YFRateLimitError
            time.sleep(3)
            data = yf.download(tickers=ticker, period="1d", interval="1m", progress=False)
            
            if not data.empty and 'Close' in data:
                df_aktie = data['Close'].dropna()
                
                if len(df_aktie) > 15:
                    senaste_pris = float(df_aktie.iloc[-1])
                    df_temp = pd.DataFrame({'Close': df_aktie})
                    rsi = beräkna_rsi(df_temp)
                    
                    try:
                        objekt = yf.Ticker(ticker)
                        nyheter = objekt.news
                        senaste_nyhet = nyheter[0].get('title', 'Inga färska nyheter') if nyheter else 'Inga färska nyheter'
                    except Exception:
                        senaste_nyhet = 'Inga färska nyheter'
                    
                    ai_svar = utvärdera_aktie_med_gemini(ticker, senaste_pris, rsi, senaste_nyhet, kassa)
                    
                    if "BETYG:" in ai_svar and "ALLOKERING:" in ai_svar:
                        delar = ai_svar.split("|")
                        betyg = int(''.join(filter(str.isdigit, delar[0])))
                        procent_str = ''.join(filter(str.isdigit, delar[1]))
                        procent = int(procent_str) if procent_str else 0
                        motivering = delar[2] if len(delar) > 2 else ""
                        
                        if betyg >= 8 and ticker not in portfölj and kassa >= senaste_pris:
                            köpbelopp = kassa * (procent / 100.0)
                            if köpbelopp < senaste_pris:
                                köpbelopp = senaste_pris
                                
                            antal = int(köpbelopp // senaste_pris)
                            totalt_köp = antal * senaste_pris
                            
                            if antal > 0 and totalt_köp <= kassa:
                                kassa -= totalt_köp
                                portfölj[ticker] = {'antal': antal, 'köppris': senaste_pris}
                                
                                meddelande = (
                                    f"🟢 AUTOMATISKT KÖP: {ticker}\n"
                                    f"Betyg: {betyg}/10 | Insats: {procent}%\n"
                                    f"Köpt: {antal} st @ {senaste_pris:.2f} SEK\n"
                                    f"Totalt: {totalt_köp:,.2f} SEK\n"
                                    f"Analys: {motivering.strip()}\n"
                                    f"Kassa kvar: {kassa:,.2f} SEK"
                                )
                                print(meddelande, flush=True)
                                skicka_telegram_notis(meddelande)

                        elif betyg <= 3 and ticker in portfölj:
                            innehav = portfölj[ticker]
                            antal = innehav['antal']
                            köppris = innehav['köppris']
                            totalt_sålt = antal * senaste_pris
                            vinst = totalt_sålt - (antal * köppris)
                            
                            kassa += totalt_sålt
                            del portfölj[ticker]
                            
                            meddelande = (
                                f"🔴 AUTOMATISK FÖRSÄLJNING: {ticker}\n"
                                f"Betyg: {betyg}/10\n"
                                f"Sålt: {antal} st @ {senaste_pris:.2f} SEK\n"
                                f"Vinst/Förlust: {vinst:+,.2f} SEK\n"
                                f"Analys: {motivering.strip()}\n"
                                f"Ny kassa: {kassa:,.2f} SEK"
                            )
                            print(meddelande, flush=True)
                            skicka_telegram_notis(meddelande)

        except Exception as e:
            # Om vi blir spärrade, pausa 10 sekunder
            time.sleep(10)
            continue

    # Paus på 5 minuter mellan varje helomgång
    time.sleep(300)
