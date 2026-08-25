import os
import ccxt
from dotenv import load_dotenv

load_dotenv()

def check_symbols():
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'options': {'defaultType': 'future'}
        })
        print("Fetching first 10 tickers...")
        tickers = exchange.fetch_tickers()
        keys = list(tickers.keys())
        print(f"Sample keys: {keys[:10]}")
        
        test_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        for p in test_pairs:
            match = [k for k in keys if p in k]
            print(f"Search for {p}: Found {match}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_symbols()
