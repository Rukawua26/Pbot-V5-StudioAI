import os
import ccxt
from dotenv import load_dotenv

load_dotenv()

def sanitize_symbol(sym):
    if not sym: return ""
    clean = str(sym).strip().upper()
    clean = clean.split(":")[0] 
    if not "/" in clean:
        clean = f"{clean}/USDT"
    elif clean.endswith("/USD") and not clean.endswith("/USDT"):
        clean = clean.replace("/USD", "/USDT")
    elif clean.endswith("/US") and not clean.endswith("/USDT"):
        clean = clean.replace("/US", "/USDT")
    if not clean.endswith("/USDT"):
        base = clean.split("/")[0]
        clean = f"{base}/USDT"
    return clean

def test_connection():
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'options': {'defaultType': 'future'}
        })
        print("Fetching tickers...")
        tickers = exchange.fetch_tickers()
        print(f"Total tickers received: {len(tickers)}")
        
        sample_syms = list(tickers.keys())[:5]
        print(f"Sample raw symbols: {sample_syms}")
        
        for s in sample_syms:
            print(f"Sanitized {s} -> {sanitize_symbol(s)}")
            
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_connection()
