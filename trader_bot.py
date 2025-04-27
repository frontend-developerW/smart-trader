import os
import math
import asyncio
from dotenv import load_dotenv
from binance.client import Client
from binance import AsyncClient, BinanceSocketManager

load_dotenv()

class TraderBot:
    def __init__(self):
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_API_SECRET')
        self.client = None
        self.socket_manager = None
        self.sockets = []
        self.symbol_targets = {}
        self.running = False
        self.initial_balance = 0

    async def start(self, profit_percent=0.002):
        self.client = await AsyncClient.create(self.api_key, self.api_secret)
        self.socket_manager = BinanceSocketManager(self.client)
        self.running = True

        balance = await self.client.get_asset_balance(asset='USDT')
        self.initial_balance = float(balance['free'])
        print(f"✅ Connected. Initial Balance: {self.initial_balance:.2f} USDT")

        trending = await self.get_trending_coins()
        slots = 4
        spendable = self.initial_balance * 0.9
        part = spendable / slots

        bought = 0
        for sym in trending:
            if bought >= slots:
                break
            success = await self.buy_coin(sym, part, profit_percent)
            if success:
                bought += 1
            await asyncio.sleep(1)

    async def get_trending_coins(self):
        tickers = await self.client.get_ticker()
        usdt_symbols = [t['symbol'] for t in tickers if t['symbol'].endswith('USDT') and not t['symbol'].startswith('USD')]
        trending = []
        timeframes = ['1m', '5m', '30m', '1h', '1d']

        for sym in usdt_symbols:
            try:
                total_change = 0
                for tf in timeframes:
                    klines = await self.client.get_klines(symbol=sym, interval=tf, limit=2)
                    open_ = float(klines[0][1])
                    close = float(klines[-1][4])
                    total_change += ((close - open_) / open_) * 100
                if total_change > 0:
                    trending.append((sym, total_change))
            except:
                continue

        trending = sorted(trending, key=lambda x: x[1], reverse=True)
        print(f"📈 Trending coins: {[x[0] for x in trending[:10]]}")
        return [x[0] for x in trending[:10]]

    async def buy_coin(self, symbol, part, profit_percent):
        try:
            ticker = await self.client.get_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])
            info = await self.client.get_symbol_info(symbol)
            step = float(next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')['stepSize'])
            qty = math.floor(part / price / step) * step

            if qty == 0:
                return False

            order = await self.client.order_market_buy(symbol=symbol, quantity=qty)
            buy_price = float(order['fills'][0]['price'])
            target_price = buy_price * (1 + profit_percent)

            self.symbol_targets[symbol.lower()] = {
                'symbol': symbol,
                'qty': qty,
                'target_price': target_price,
                'buy_price': buy_price
            }

            socket = self.socket_manager.trade_socket(symbol.lower())
            self.sockets.append(socket)
            asyncio.create_task(self.monitor_socket(socket, symbol.lower()))
            print(f"🟢 Bought {qty} {symbol} at {buy_price:.6f}, target {target_price:.6f}")
            return True
        except Exception as e:
            print(f"❌ Buy failed for {symbol}: {e}")
            return False

    async def monitor_socket(self, socket, symbol):
        async with socket as trade_socket:
            while self.running:
                msg = await trade_socket.recv()
                price = float(msg['p'])
                data = self.symbol_targets.get(symbol)
                if data and price >= data['target_price']:
                    print(f"🎯 Target hit for {symbol} at {price}")
                    await self.sell(symbol)
                    break

    async def sell(self, symbol):
        try:
            data = self.symbol_targets.get(symbol)
            if not data:
                return
            order = await self.client.order_market_sell(symbol=data['symbol'], quantity=data['qty'])
            sell_price = float(order['fills'][0]['price'])
            real_profit = (sell_price - data['buy_price']) * data['qty']
            print(f"✅ SOLD {data['qty']} {data['symbol']} at {sell_price:.6f}, Real Profit: {real_profit:.4f} USDT")
            del self.symbol_targets[symbol]
        except Exception as e:
            print(f"❌ Sell error for {symbol}: {e}")

    async def force_sell_all(self):
        print("🛑 Force selling all active coins...")
        self.running = False
        for symbol in list(self.symbol_targets.keys()):
            await self.sell(symbol)
        print("✅ All coins sold, bot stopped.")
