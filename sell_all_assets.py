import os
import math
import asyncio
import requests
from dotenv import load_dotenv
from binance import AsyncClient

# Load environment variables
load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

async def sell_all_assets():
    client = await AsyncClient.create(API_KEY, API_SECRET, testnet=True)

    try:
        print("🛑 Selling all assets...")
        account_info = await client.get_account()
        balances = account_info['balances']

        for asset in balances:
            asset_name = asset['asset']
            free_balance = float(asset['free'])

            # Skip if balance is zero or near zero
            if free_balance <= 0:
                continue

            # Skip USDT
            if asset_name == 'USDT':
                continue

            try:
                symbol = f"{asset_name}USDT"

                # Check if symbol exists
                try:
                    price_info = await client.get_symbol_info(symbol)
                except Exception:
                    print(f"❌ {symbol} trading pair mavjud emas. O'tkazildi.")
                    continue

                # Calculate quantity
                step_size = float(next(f for f in price_info['filters'] if f['filterType'] == 'LOT_SIZE')['stepSize'])
                qty = round(math.floor(free_balance / step_size) * step_size, 6)

                if qty <= 0:
                    continue

                # Sell the asset
                sell_order = await client.order_market_sell(symbol=symbol, quantity=qty)
                sell_price = float(sell_order['fills'][0]['price'])

                send_telegram_message(
                    f"🛑 SOLD {asset_name}\n💲 Price: {sell_price:.6f} USDT\n🔢 Quantity: {qty}"
                )
                print(f"✅ SOLD {qty} {asset_name} at {sell_price:.6f}")
                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ Error selling {asset_name}: {e}")

    finally:
        await client.close_connection()
        print("✅ All assets sold and connection closed.")

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        }
        requests.post(url, data=payload)
    except Exception as e:
        print(f"⚠️ Telegram send error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(sell_all_assets())
    except KeyboardInterrupt:
        print("\n🛑 Script stopped manually.")
