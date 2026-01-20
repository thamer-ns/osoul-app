import sqlite3
import pandas as pd
import os

print("Current Directory:", os.getcwd())

if os.path.exists("stocks.db"):
    print("✅ stocks.db found!")
    try:
        conn = sqlite3.connect("stocks.db")
        df = pd.read_sql("SELECT * FROM Trades", conn)
        print(f"📊 Number of trades found: {len(df)}")
        if not df.empty:
            print(df.head())
        else:
            print("⚠️ Table exists but is empty.")
        conn.close()
    except Exception as e:
        print(f"❌ Error reading DB: {e}")
else:
    print("❌ stocks.db NOT found in this directory.")
    print("Listing files:", os.listdir())
