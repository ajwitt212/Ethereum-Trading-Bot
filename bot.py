from collections import deque
import websocket
import json
import numpy
import talib
import datetime

from binance.client import Client
from binance.enums import *

from config import *

class Bot:

    def __init__(self):
        # data structures to track ohlcv
        self.opens = deque()
        self.closes = deque()
        self.highs = deque()
        self.lows = deque()
        self.volumes = deque()
        # track indicators between bars
        self.macds = deque([1, 2, 3]) # filled at beginning so I can append and pop on each iteration. Minimizaes conditinals
        self.position_atr = None
        self.time_since_upped_ubband = -1 # < 0 means hasn't crossed. >= 0 represents time since last crossed upper bband
        self.time_since_dipped_lbband = -1 # < 0 means hasn't crossed. >= 0 represents time since last crossed lower bband
        self.has_upped_rsi = False
        self.has_upped_mfi = False
        self.position_high = None
        self.position_buy_price = None
        # track program statistics
        self.num_bars_processed = 0
        # get historical klines and calculate previous indicators
        self.initialize()
    
    def initialize(self):
        pass
        # get historical klines and calculate previous indicators

    def process_bar(self, bar):
        """
        Called each time websocket gets a ping. Processes bar, calculates indicators, and performs buys/sells

        Args:
            bar (dict): binance kline bar see binance api for more details
        """
        pass
    
    def append_bar(self, bar):
        """
        Appends most recent bar to the data structures in the class

        Args:
            bar (dict): binance kline bar see binance api for more details
        """
        self.opens.append(float(bar['o']))
        self.closes.append(float(bar['c']))
        self.highs.append(float(bar['h']))
        self.lows.append(float(bar['l']))
        self.volumes.append(float(bar['v']))
    
    def pop_last_bar(self):
        """
        Removes the oldest bar from the datastructures in the class
        """
        self.opens.popleft()
        self.closes.popleft()
        self.highs.popleft()
        self.lows.popleft()
        self.volumes.popleft()

    def reset_indicators(self, side):
        """ 
        Function to reset all indicator values to their respective default states

        Args:
            side (bool): 1 represents buy, 0 represents sell
        """
        self.has_upped_rsi = False
        self.has_upped_mfi = False
        self.time_since_upped_ubband = -1
        self.time_since_dipped_lbband = -1

        if side == 'buy':  # only reset all indicators if we're closing a position
            return
        
        self.buy_price = None
        self.buy_time = None
        self.position_high = None
        self.position_atr = None
    

def on_open(ws):
    print("\n### connection opened ###\n")

def on_error(ws, error):
    print(error)

def on_close(ws, close_status_code, close_msg):
    print("\n### connection closed ###")
    
def on_message(ws, message):
    global eth_bot
    eth_bot.process_bar(json.loads(message)['k'])

# declare bot object
eth_bot = Bot()
# runs websocket
ws = websocket.WebSocketApp(
    BINANCE_SOCKET,
    on_open=on_open,
    on_close=on_close,
    on_message=on_message,
    on_error=on_error)
ws.run_forever()
