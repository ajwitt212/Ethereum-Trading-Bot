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
        #intialize client from binance api
        self.client = Client(BINANCE_API_KEY, BINANCE_API_SECRET_KEY, tld='us')
        # data structures to track ohlcv
        self.opens = deque()
        self.closes = deque()
        self.highs = deque()
        self.lows = deque()
        self.volumes = deque()
        # track previous indicator values for slope calculation
        self.macds = deque()
        # track position stats
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
        # TODO:
        # get historical klines and calculate previous indicators
        # loads historical into variables so no delay when starting program
        for kline in self.client.get_historical_klines_generator(
            "ETHUSD", 
            Client.KLINE_INTERVAL_1MINUTE, 
            str(datetime.datetime.utcnow() - datetime.timedelta(minutes=101)) # import 101 bc we pop most recent unclosed candle 
            ):
            self.opens.append(float(kline[1]))
            self.closes.append(float(kline[4]))
            self.highs.append(float(kline[2]))
            self.lows.append(float(kline[3]))
            self.volumes.append(float(kline[5]))
        # deletes most recent candle which isn't yet closed
        self.closes.pop() 
        # calculates macds and adds them to attributes for slope calcs 
        np_closes = numpy.array(self.closes)
        macd_list, macdsignal_list, macdhist_list = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)
        for i in range(-3, 0):
            macdhist = macdhist_list[i]
            self.macds.append(macdhist)
    

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
