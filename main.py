import os
import math
import asyncio
import requests
from dotenv import load_dotenv
from binance import AsyncClient, BinanceSocketManager

# Load .env
load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

class TraderBot:
    def __init__(self):
        self.client = None
        self.bsm = None
        self.running = True
        self.symbol_targets = {}
        self.initial_balance = 0
        self.sockets = {}

    async def start(self, profit_percent=0.005):
        self.send_telegram_message("🟢 Savdo boshlandi!")
        self.client = await AsyncClient.create(API_KEY, API_SECRET, testnet=True)
        self.bsm = BinanceSocketManager(self.client)
        self.initial_balance = float((await self.client.get_asset_balance(asset='USDT'))['free'])
        print(f"✅ Connected. Initial Balance: {self.initial_balance:.2f} USDT")

        trending = await self.get_trending_coins()
        slots = 4
        usdt = float((await self.client.get_asset_balance(asset='USDT'))['free'])
        spendable = usdt * 0.9
        part = spendable / slots

        bought = 0
        for sym in trending:
            if not self.running or bought >= slots:
                break
            if await self.buy_coin(sym, part, profit_percent):
                bought += 1
            await asyncio.sleep(0.5)

    async def get_trending_coins(self):
        print("🔄 Scanning trending coins...")
        all_tickers = await self.client.get_ticker()
        usdt_symbols = [t['symbol'] for t in all_tickers if t['symbol'].endswith('USDT') and not t['symbol'].startswith('USD')]
        trending = []
        timeframes = ['1m', '5m', '30m', '1h', '1d']

        for sym in usdt_symbols:
            try:
                total_change = 0
                for tf in timeframes:
                    klines = await self.client.get_klines(symbol=sym, interval=tf, limit=2)
                    open_ = float(klines[0][1])
                    close = float(klines[-1][4])
                    change = ((close - open_) / open_) * 100
                    total_change += change
                if total_change > 0:
                    trending.append((sym, total_change))
            except:
                continue

        trending = sorted(trending, key=lambda x: x[1], reverse=True)
        print(f"📈 Trending coins: {[x[0] for x in trending[:10]]}")
        return [x[0] for x in trending[:10]]

    async def buy_coin(self, sym, part, profit_percent):
        try:
            price = float((await self.client.get_symbol_ticker(symbol=sym))['price'])
            info = await self.client.get_symbol_info(sym)
            step = float(next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')['stepSize'])
            qty = round(math.floor((part / price) / step) * step, 6)

            if qty == 0:
                return False

            order = await self.client.order_market_buy(symbol=sym, quantity=qty)
            buy_price = float(order['fills'][0]['price'])
            target_price = buy_price * (1 + profit_percent)

            self.symbol_targets[sym.lower()] = {
                'symbol': sym,
                'qty': qty,
                'target_price': target_price,
                'buy_price': buy_price
            }

            print(f"🟢 Bought {qty} {sym} at {buy_price:.6f}, target {target_price:.6f}")

            self.send_telegram_message(
                f"🟢 Sotib olindi: {qty} {sym}\n💲 Narx: {buy_price:.6f} USDT\n🎯 Target: {target_price:.6f} USDT"
            )

            socket = self.bsm.trade_socket(sym)
            asyncio.create_task(self.monitor_socket(socket, sym.lower()))
            return True
        except Exception as e:
            print(f"❌ Failed to buy {sym}: {e}")
            return False

    async def monitor_socket(self, socket, sym):
        async with socket as trade_socket:
            while self.running and sym in self.symbol_targets:
                msg = await trade_socket.recv()
                try:
                    price = float(msg['p'])
                    data = self.symbol_targets[sym]
                    if price >= data['target_price']:
                        print(f"🎯 Target reached for {data['symbol']} at {price:.6f}. Trying to sell...")
                        await self.sell_and_notify(data)
                        del self.symbol_targets[sym]
                        asyncio.create_task(self.find_and_buy_new_coin())
                        break
                except Exception as e:
                    print(f"⚠️ Socket error: {e}")
                    break

    async def sell_and_notify(self, data):
        for attempt in range(3):
            try:
                sell_order = await self.client.order_market_sell(symbol=data['symbol'], quantity=data['qty'])
                sell_price = float(sell_order['fills'][0]['price'])
                qty = data['qty']
                buy_price = data['buy_price']
                real_profit = (sell_price * 0.998 - buy_price * 1.001) * qty
                self.send_telegram_message(
                    f"✅ {data['symbol']} sotildi\n💵 Real Foyda: {real_profit:+.4f} USDT"
                )
                print(f"✅ SOLD {qty} {data['symbol']} at {sell_price:.6f}, Real Profit: {real_profit:+.4f} USDT")
                break
            except Exception as e:
                print(f"⚠️ Sell attempt {attempt+1} failed: {e}")
                await asyncio.sleep(1)

    def send_telegram_message(self, text):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text
            }
            requests.post(url, data=payload)
        except Exception as e:
            print(f"⚠️ Telegram send error: {e}")

    async def find_and_buy_new_coin(self):
        await asyncio.sleep(2)
        trending = await self.get_trending_coins()
        for new_sym in trending:
            if new_sym.lower() not in self.symbol_targets:
                usdt = float((await self.client.get_asset_balance(asset='USDT'))['free'])
                spendable = usdt * 0.9
                slots = 4
                part = spendable / slots
                await self.buy_coin(new_sym, part, 0.005)
                break

    async def force_sell_all(self):
        print("🛑 Force selling all active coins...")
        self.running = False
        for sym, data in list(self.symbol_targets.items()):
            try:
                sell_order = await self.client.order_market_sell(symbol=data['symbol'], quantity=data['qty'])
                sell_price = float(sell_order['fills'][0]['price'])
                qty = data['qty']
                buy_price = data['buy_price']
                real_profit = (sell_price * 0.998 - buy_price * 1.001) * qty
                self.send_telegram_message(
                    f"🛑 FORCE SOLD {data['symbol']}\n💵 Real Foyda: {real_profit:+.4f} USDT"
                )
                print(f"✅ FORCE SOLD {qty} {data['symbol']} at {sell_price:.6f}, Real Profit: {real_profit:+.4f} USDT")
            except Exception as e:
                print(f"❌ Error force selling {data['symbol']}: {e}")
        self.symbol_targets.clear()
        await self.client.close_connection()
        print("✅ All coins sold, bot stopped.")

async def main():
    bot = TraderBot()
    task = asyncio.create_task(bot.start(profit_percent=0.004))  # target 0.4% profit

    while True:
        cmd = await asyncio.to_thread(input)
        if cmd.lower() == 'stop':
            print("🛑 Stop command received!")
            await bot.force_sell_all()
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped manually.")
