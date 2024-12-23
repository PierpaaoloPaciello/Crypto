import unittest
import sqlite3
import json
import time
from Crypto.crypto_kit import Logger, Listener, AlpacaOrderManager, OrderType, APIKey

class TestTradingModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open("config.json", "r") as file:
            cls.config = json.load(file)

        cls.logger = Logger(db_path="test_logs.db")
        cls.listener = Listener(
            exchange_id="binance",
            crypto_symbols=["BTC/USDT", "ETH/USDT"],
            logger=cls.logger
        )
        alpaca_credentials = APIKey(
            key=cls.config.get("alpaca", {}).get("key", ""), 
            secret=cls.config.get("alpaca", {}).get("secret", "")
        )
        cls.order_manager = AlpacaOrderManager(
            exchange_id="alpaca", 
            credentials=alpaca_credentials,
            logger=cls.logger
        )

    def test_logging_to_console_and_database(self):
        time.sleep(5)
        message = "Test log message"
        self.logger.log(message)

        # Check Database Entry
        conn = sqlite3.connect(self.logger.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT message FROM logs ORDER BY id DESC LIMIT 1')
        last_message = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(last_message, message)

    def test_listen_to_prices(self):
        time.sleep(5)
        try:
            price = self.listener.fetch_price("BTC/USDT")
            self.assertIsNotNone(price, "Price fetch failed or returned None")
            self.logger.log(f"Test price fetch: {price.price}")
        except Exception as e:
            self.fail(f"Exception during test_listen_to_prices: {e}")

    def test_fetch_historical_data(self):
        time.sleep(5)
        from datetime import datetime
        try:
            since_date = datetime(2023, 1, 1)
            data = self.listener.fetch_historical_data("BTC/USDT", "1d", since_date)
            self.assertTrue(len(data) > 0, "Historical data fetch returned no data")
        except Exception as e:
            self.fail(f"Exception during test_fetch_historical_data: {e}")

    def test_create_order(self):
        time.sleep(5)
        try:
            order = self.order_manager.create_order(
                symbol="BTC/USD",
                order_type=OrderType.MARKET,
                side="buy",
                qty=0.1
            )
            self.assertIsNotNone(order, "Order creation failed")
        except Exception as e:
            self.fail(f"Exception during test_create_order: {e}")

    def test_fetch_open_orders(self):
        time.sleep(5)
        try:
            open_orders = self.order_manager.fetch_open_orders()
            self.assertIsInstance(open_orders, list, "Fetch open orders failed")
        except Exception as e:
            self.fail(f"Exception during test_fetch_open_orders: {e}")

    def test_cancel_order(self):
        time.sleep(5)
        try:
            order = self.order_manager.create_order(
                symbol="BTC/USD",
                order_type=OrderType.MARKET,
                side="buy",
                qty=0.1
            )
            self.assertIsNotNone(order, "Order creation for cancellation test failed")

            order_id = getattr(order, 'id', None)
            if order_id:
                result = self.order_manager.cancel_order(order_id=order_id)
                self.logger.log(f"Cancel order result: {result}")
                self.assertIsNotNone(result, "Cancel order failed")
            else:
                self.fail("Order ID is missing")
        except Exception as e:
            self.logger.log(f"Error during test_cancel_order: {e}")
            self.fail(f"Exception during test_cancel_order: {e}")

    def test_fetch_order_status(self):
        time.sleep(5)
        try:
            order = self.order_manager.create_order(
                symbol="BTC/USD",
                order_type=OrderType.MARKET,
                side="buy",
                qty=0.1
            )
            self.assertIsNotNone(order, "Order creation for status test failed")

            order_id = getattr(order, 'id', None)
            if order_id:
                order_status = self.order_manager.fetch_order_status(order_id=order_id)
                self.assertIsNotNone(order_status, "Fetch order status failed")
            else:
                self.fail("Order ID is missing")
        except Exception as e:
            self.logger.log(f"Error during test_fetch_order_status: {e}")
            self.fail(f"Exception during test_fetch_order_status: {e}")

    def test_exit_position(self):
        time.sleep(5)
        try:
            positions = self.order_manager.fetch_positions()
            if not positions:
                self.logger.log("No positions available to exit")
                self.skipTest("No positions to exit for testing")

            for position in positions:
                symbol = getattr(position, 'symbol', None)
                if symbol == "BTCUSD":  
                    result = self.order_manager.exit_position(symbol)
                    self.assertIsNotNone(result, f"Exit position failed for {symbol}")
                    break  #
            else:
                self.logger.log("BTC/USD position not found")
                self.skipTest("No BTC/USD position to exit for testing")
        except Exception as e:
            self.logger.log(f"Error during test_exit_position: {e}")
            self.fail(f"Exception during test_exit_position: {e}")

    def test_fetch_positions(self):
        time.sleep(5)
        try:
            positions = self.order_manager.fetch_positions()
            self.assertTrue(positions, "No positions found")
        except Exception as e:
            self.logger.log(f"Error during test_fetch_positions: {e}")
            self.fail(f"Exception during test_fetch_positions: {e}")

if __name__ == "__main__":
    unittest.main()
