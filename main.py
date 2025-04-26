import tkinter as tk
from tkinter import scrolledtext
import threading
import math
import time
from binance.client import Client
from binance import ThreadedWebsocketManager

class TraderBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🧠 Smart Binance Bot (One Cycle, 5 Coins, 90% Balance)")
        self.root.geometry("630x720")

        tk.Label(root, text="API Key:").pack()
        self.api_key_entry = tk.Entry(root, show="*", width=60)
        self.api_key_entry.pack()

        tk.Label(root, text="API Secret:").pack()
        self.api_secret_entry = tk.Entry(root, show="*", width=60)
        self.api_secret_entry.pack()

        tk.Label(root, text="Profit % (e.g. 0.5)").pack()
        self.profit_entry = tk.Entry(root, width=10)
        self.profit_entry.insert(0, "0.5")
        self.profit_entry.pack()

        self.start_button = tk.Button(root, text="🚀 Start Trading", command=self.on_start)
        self.start_button.pack(pady=5)

        self.stop_button = tk.Button(root, text="🛑 Stop Trading", command=self.stop_trading, state='disabled')
        self.stop_button.pack(pady=5)

        self.balance_label = tk.Label(root, text="💰 USDT Balance: --")
        self.balance_label.pack()

        self.profit_label = tk.Label(root, text="📈 Total Profit: --")
        self.profit_label.pack()

        tk.Label(root, text="📋 Logs:").pack()
        self.log_area = scrolledtext.ScrolledText(root, height=26, width=75, state='disabled')
        self.log_area.pack()

        self.client = None
        self.twm = None
        self.running = False
        self.initial_balance = 0
        self.symbol_targets = {}
        self.sold_coins = set()

    def log(self, message):
        print(message)
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + '\n')
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def on_start(self):
        api_key = self.api_key_entry.get()
        api_secret = self.api_secret_entry.get()
        profit_str = self.profit_entry.get()

        if not api_key or not api_secret or not profit_str:
            self.log("❗ Please fill in all fields.")
            return

        try:
            profit_percent = float(profit_str) / 100
        except:
            self.log("❗ Invalid profit percentage.")
            return

        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.running = True
        threading.Thread(target=self.run_bot, args=(api_key, api_secret, profit_percent)).start()

    def stop_trading(self):
        self.log("🛑 Stop requested. Selling all open positions...")
        self.running = False
        for sym, data in list(self.symbol_targets.items()):
            try:
                self.client.order_market_sell(symbol=data['symbol'], quantity=data['qty'])
                self.log(f"✅ FORCE SOLD {data['qty']} {data['symbol']} at market")
            except Exception as e:
                self.log(f"❌ Sell error: {data['symbol']}: {str(e)}")
        self.symbol_targets.clear()
        self.stop_button.config(state='disabled')
        self.start_button.config(state='normal')
        self.log("❌ Trading stopped.")

    def round_step_size(self, qty, step):
        return math.floor(qty / step) * step

    def run_bot(self, api_key, api_secret, profit_percent):
        try:
            self.client = Client(api_key, api_secret, testnet=True)
            self.twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret, testnet=True)
            self.twm.start()
            self.initial_balance = float(self.client.get_asset_balance(asset='USDT')['free'])
            self.start_balance_monitor()
            self.log(f"✅ Connected. Initial USDT: {self.initial_balance:.2f}")

            trending = self.get_trending_coins()
            slots = 5  # <<< faqat 5ta coin
            usdt = float(self.client.get_asset_balance(asset='USDT')['free'])
            spendable = usdt * 0.9  # <<< 90% balance ishlatamiz
            part = spendable / slots

            for sym in trending[:slots]:
                if not self.running:
                    break
                try:
                    price = float(self.client.get_symbol_ticker(symbol=sym)['price'])
                    info = self.client.get_symbol_info(sym)
                    step = float(next(f for f in info['filters'] if f['filterType'] == 'LOT_SIZE')['stepSize'])
                    qty = round(self.round_step_size(part / price, step), 6)

                    order = self.client.order_market_buy(symbol=sym, quantity=qty)
                    buy_price = float(order['fills'][0]['price'])
                    target_price = buy_price * (1 + profit_percent)

                    self.symbol_targets[sym.lower()] = {
                        'symbol': sym,
                        'qty': qty,
                        'target_price': target_price
                    }

                    self.log(f"🟢 Bought {qty} {sym} at {buy_price:.4f}, target: {target_price:.4f}")
                    self.twm.start_aggtrade_socket(callback=self.handle_trade, symbol=sym.lower())
                    time.sleep(0.5)
                except Exception as e:
                    self.log(f"❌ Failed to buy {sym}: {str(e)}")

        except Exception as e:
            self.log(f"❌ Bot error: {str(e)}")

    def get_trending_coins(self):
        self.log("🔄 Scanning market for trending coins...")
        try:
            all_tickers = self.client.get_ticker()
            usdt_symbols = [t['symbol'] for t in all_tickers if t['symbol'].endswith('USDT') and not t['symbol'].startswith('USD')]
            trending = []
            for sym in usdt_symbols:
                try:
                    klines = self.client.get_klines(symbol=sym, interval=Client.KLINE_INTERVAL_5MINUTE, limit=3)
                    if len(klines) < 2: continue
                    open_ = float(klines[0][1])
                    close = float(klines[-1][4])
                    change = ((close - open_) / open_) * 100
                    vol = float(klines[-1][5])
                    score = change * vol
                    trending.append((sym, score))
                except:
                    continue
            return [x[0] for x in sorted(trending, key=lambda x: x[1], reverse=True)]
        except Exception as e:
            self.log(f"❌ Error scanning: {str(e)}")
            return []

    def handle_trade(self, msg):
        if not self.running:
            return
        sym = msg['s'].lower()
        if sym not in self.symbol_targets:
            return
        try:
            price = float(msg['p'])
            data = self.symbol_targets[sym]
            if price >= data['target_price']:
                self.client.order_market_sell(symbol=data['symbol'], quantity=data['qty'])
                self.log(f"✅ SOLD {data['qty']} {data['symbol']} at {price:.4f}")
                del self.symbol_targets[sym]
                if not self.symbol_targets:
                    self.log("🎯 All coins sold. Cycle complete.")
                    self.running = False
                    self.stop_button.config(state='disabled')
                    self.start_button.config(state='normal')
        except Exception as e:
            self.log(f"⚠️ Error on {sym.upper()}: {str(e)}")

    def start_balance_monitor(self):
        def loop():
            while self.running:
                try:
                    curr = float(self.client.get_asset_balance(asset='USDT')['free'])
                    profit = curr - self.initial_balance
                    self.balance_label.config(text=f"💰 USDT Balance: {curr:.2f}")
                    self.profit_label.config(text=f"📈 Total Profit: {profit:+.2f} USDT")
                except:
                    pass
                time.sleep(10)
        threading.Thread(target=loop, daemon=True).start()

# Run
if __name__ == "__main__":
    root = tk.Tk()
    app = TraderBotGUI(root)
    root.mainloop()
