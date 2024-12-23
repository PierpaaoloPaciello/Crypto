import pandas as pd
import requests
import json
import time
import ccxt
import alpaca_trade_api as alpaca
import logging
from enum import Enum
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import sqlite3

# OrderType Enum
OrderType = Enum("OrderType", ["LIMIT", "MARKET"])

@dataclass
class APIKey:
    key: str
    secret: str

@dataclass
class CryptoPrice:
    symbol: str
    price: float

# Logging Class
class Logger:
    def __init__(self, db_path: str = "logs.db"):
        self.logger = logging.getLogger("TradingLogger")
        self.logger.setLevel(logging.INFO)

        # Avoid adding multiple handlers
        if not self.logger.handlers:
            # Console Handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(asctime)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

        # Database Setup
        self.db_path = db_path
        self._setup_database()

    def _setup_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs (
                            id INTEGER PRIMARY KEY,
                            timestamp TEXT,
                            message TEXT)''')
        conn.commit()
        conn.close()

    def log(self, message: str):
        self.logger.info(message)
        self._log_to_database(message)

    def _log_to_database(self, message: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO logs (timestamp, message) VALUES (datetime("now"), ?)', (message,))
        conn.commit()
        conn.close()


class BaseListener:
    def __init__(self, exchange_id: str, crypto_symbols: List[str], logger: Logger):
        self.crypto_symbols = crypto_symbols
        self.logger = logger
        self.exchange = getattr(ccxt, exchange_id)()
        self.exchange.load_markets()

    def fetch_price(self, symbol: str) -> CryptoPrice:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            price = ticker['last']
            self.logger.log(f"Live price of {symbol}: {price}")
            return CryptoPrice(symbol=symbol, price=price)
        except Exception as e:
            self.logger.log(f"Error fetching live price for {symbol}: {e}")
            return None
        
    def fetch_historical_data(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[Dict]:
        try:
            start_timestamp = int(start.timestamp() * 1000)  # Convert start date to milliseconds
            end_timestamp = int(end.timestamp() * 1000)      # Convert end date to milliseconds
            all_data = []
            current_start = start_timestamp

            while current_start < end_timestamp:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=current_start)
                if not ohlcv:
                    break
                self.logger.log(f"Fetched batch of historical data for {symbol} with timeframe {timeframe}.")
                all_data.extend(ohlcv)

                # Update current_start to fetch the next batch
                last_timestamp = ohlcv[-1][0]
                if last_timestamp >= end_timestamp:
                    break
                current_start = last_timestamp + 1

            return [
                {
                    "timestamp": datetime.fromtimestamp(candle[0] / 1000),
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5]
                }
                for candle in all_data if candle[0] < end_timestamp
            ]
        except Exception as e:
            self.logger.log(f"Error fetching historical data for {symbol}: {e}")
            return []



    def create_dataframe(self, data: List[Dict]) -> pd.DataFrame:
        return pd.DataFrame(data)

class Listener(BaseListener):
    def listen_to_prices(self):
        while True:
            try:
                for symbol in self.crypto_symbols:
                    price = self.fetch_price(symbol)
                    if price:
                        print(f"Price of {price.symbol}: {price.price}")
            except Exception as e:
                self.logger.log(f"Error in listener: {e}")
            time.sleep(5)

class Uploader:
    def __init__(self, config_path: str, order_manager_class, logger: Logger):
        self.api_keys: Dict[str, APIKey] = self.load_keys(config_path)
        self.order_manager_class = order_manager_class
        self.logger = logger

    def load_keys(self, config_path: str) -> Dict[str, APIKey]:
        with open(config_path, 'r') as file:
            data = json.load(file)
        return {name: APIKey(**creds) for name, creds in data.items()}

    def connect_api(self, api_names: List[str]):
        for api_name in api_names:
            if api_name in self.api_keys:
                api_key = self.api_keys[api_name]
                self.logger.log(f"Connecting to {api_name} with key: {api_key.key}... Successful")
                # Initialize order manager for the connected API
                self.order_manager_class(api_name, self.api_keys[api_name])
            else:
                self.logger.log(f"API keys for {api_name} not found.")

class Broker(Uploader):
    def connect_to_broker(self, broker_name: str):
        if broker_name in self.api_keys:
            api_key = self.api_keys[broker_name]
            self.logger.log(f"Connecting to broker {broker_name} with key: {api_key.key}... Successful")
            # Initialize order manager for the broker
            self.order_manager_class(broker_name, self.api_keys[broker_name])
        else:
            self.logger.log(f"Broker {broker_name} keys not found.")

class AlpacaOrderManager:
    def __init__(self, exchange_id: str, credentials: APIKey, logger):
        self.logger = logger
        if exchange_id.lower() == "alpaca":
            self.api = alpaca.REST(
                credentials.key, 
                credentials.secret, 
                "https://paper-api.alpaca.markets"
            )
        else:
            self.api = getattr(ccxt, exchange_id)({
                'apiKey': credentials.key,
                'secret': credentials.secret
            })

    def create_order(self, symbol: str, order_type: OrderType, side: str, qty: float, price: float = None, time_in_force: str = "gtc"):
        try:
            if isinstance(self.api, alpaca.REST):
                if order_type == OrderType.LIMIT:
                    order = self.api.submit_order(
                        symbol=symbol,
                        qty=qty,
                        side=side,
                        type="limit",
                        time_in_force=time_in_force,
                        limit_price=price
                    )
                elif order_type == OrderType.MARKET:
                    order = self.api.submit_order(
                        symbol=symbol,
                        qty=qty,
                        side=side,
                        type="market",
                        time_in_force=time_in_force
                    )
                else:
                    raise ValueError("Unsupported order type")
            else:
                if order_type == OrderType.LIMIT:
                    order = self.api.create_limit_order(symbol, side, qty, price)
                elif order_type == OrderType.MARKET:
                    order = self.api.create_market_order(symbol, side, qty)
                else:
                    raise ValueError("Unsupported order type")

            self.logger.log(f"Order placed: {order}")
            return order

        except Exception as e:
            self.logger.log(f"Error placing order: {e}")
            return None

    def fetch_open_orders(self, symbol: str = None):
        try:
            if isinstance(self.api, alpaca.REST):
                open_orders = self.api.list_orders(status="open")
            else:
                open_orders = self.api.fetch_open_orders(symbol)
            self.logger.log(f"Open orders: {open_orders}")
            return open_orders
        except Exception as e:
            self.logger.log(f"Error fetching open orders: {e}")
            return []

    def cancel_order(self, order_id: str, symbol: str = None):
        try:
            if isinstance(self.api, alpaca.REST):
                result = self.api.cancel_order(order_id)
            else:
                result = self.api.cancel_order(order_id, symbol)
            self.logger.log(f"Order {order_id} canceled.")
            return result
        except Exception as e:
            self.logger.log(f"Error canceling order: {e}")
            return None

    def exit_position(self, symbol: str):
        try:
            if isinstance(self.api, alpaca.REST):
                positions = self.api.list_positions()
                for position in positions:
                    if position.symbol == symbol:
                        qty = float(position.qty)
                        side = "sell" if qty > 0 else "buy"
                        self.logger.log(f"Exiting position: {qty} {symbol} with a {side} order")
                        order = self.create_order(
                            symbol=symbol,
                            order_type=OrderType.MARKET,
                            side=side,
                            qty=abs(qty)
                        )
                        return order
                self.logger.log(f"No open position found for symbol: {symbol}")
                return None
            else:
                balance = self.api.fetch_balance()
                symbol_info = self.api.market(symbol)
                position_qty = balance.get(symbol_info['base'], {}).get('free', 0)
                if position_qty > 0:
                    order = self.api.create_market_sell_order(symbol, position_qty)
                elif position_qty < 0:
                    order = self.api.create_market_buy_order(symbol, abs(position_qty))
                else:
                    self.logger.log(f"No open position found for symbol: {symbol}")
                    return None
                self.logger.log(f"Exited position in {symbol}: {order}")
                return order
        except Exception as e:
            self.logger.log(f"Error exiting position for {symbol}: {e}")
            return None

    def fetch_order_status(self, order_id: str):
        try:
            if isinstance(self.api, alpaca.REST):
                order = self.api.get_order(order_id)
            else:
                order = self.api.fetch_order(order_id)
            self.logger.log(f"Order status for {order_id}: {order}")
            return order
        except Exception as e:
            self.logger.log(f"Error fetching order status: {e}")
            return None

    def fetch_positions(self):
        try:
            if isinstance(self.api, alpaca.REST):
                positions = self.api.list_positions()
            else:
                positions = self.api.fetch_balance()
            self.logger.log(f"Fetched positions: {positions}")
            return positions
        except Exception as e:
            self.logger.log(f"Error fetching positions: {e}")
            return None

    def modify_order(self, order_id: str, qty: float = None, price: float = None):
        try:
            if isinstance(self.api, alpaca.REST):
                modified_order = self.api.replace_order(
                    order_id=order_id,
                    qty=qty,
                    limit_price=price
                )
            else:
                self.logger.log("Order modification is not supported for ccxt-based exchanges.")
                return None
            self.logger.log(f"Order modified: {modified_order}")
            return modified_order
        except Exception as e:
            self.logger.log(f"Error modifying order {order_id}: {e}")
            return None
