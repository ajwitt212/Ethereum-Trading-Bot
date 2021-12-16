from collections import deque
from numpy.lib.function_base import append
import websocket
import json
import numpy
import talib
import datetime

from binance.client import Client
from binance.enums import *

from config import *

#TODO: figure out how to stream ethusd NOT ethusdt
#       or figure out how to buy and eth and instead of sell convert to usdt

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
        # track program statistics
        self.num_bars_processed = 0
        # get historical klines and calculate previous indicators
        self.initialize()
    
    def initialize(self):
        """
        Loads historical data into attributes and calculates past value of indicators that we use for slope.
        Allows program to begin analyzing market live.
        """
        # loads historical into variables so no delay when starting program
        for kline in self.client.get_historical_klines(
            "ETHUSD", 
            Client.KLINE_INTERVAL_1MINUTE, 
            str(datetime.datetime.utcnow() - datetime.timedelta(minutes=100)) # import 101 bc we pop most recent unclosed candle 
            ):
            self.opens.append(float(kline[1]))
            self.closes.append(float(kline[4]))
            self.highs.append(float(kline[2]))
            self.lows.append(float(kline[3]))
            self.volumes.append(float(kline[5]))
        # deletes most recent candle which isn't yet closed
        self.pop_newest_bar()
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
        print('-', self.num_bars_processed, '-')
        # bar processing initialization
        self.append_bar(bar)
        # convert stored stock values to numpy arrays for ta-lib processing
        np_opens = numpy.array(self.opens)
        np_closes = numpy.array(self.closes)
        np_highs = numpy.array(self.highs)
        np_lows = numpy.array(self.lows)
        np_volumes = numpy.array(self.volumes)
        # getting rsi info
        rsi_list = talib.RSI(np_closes, timeperiod=14)
        rsi = rsi_list[-1]
        # getting atr info
        atr_list = talib.ATR(np_highs, np_lows, np_closes)
        atr = atr_list[-1]
        # getting bbands info
        upper_bband_list, middle_bband_list, lower_bband_list = talib.BBANDS(np_closes, timeperiod=20)
        upper_bband, middle_bband, lower_bband = upper_bband_list[-1], middle_bband_list[-1], lower_bband_list[-1]
        # getting macd info
        macd_list, macdsignal_list, macdhist_list = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)
        macd, macdsignal, macdhist = macd_list[-1], macdsignal_list[-1], macdhist_list[-1] # note: correct only to hundredths decimal place
        self.macds.append(macdhist)
        self.macds.popleft()

        # bar processing finalization
        self.num_bars_processed += 1
        bar_closed = bar['x']  
        if bar_closed: # if the bar is closed we add it on the list as permanent
            self.pop_oldest_bar()
        else: # if the bar isn't closed we remove it and process the next live valu
            self.pop_newest_bar()

    def buy(self, quantity):
        """
        Performs buy of crypto

        Args:
            quantity (float): quantity of crypto to buy
        """
        # makes order
        order = self.client.order_market_buy(
                symbol='ETHUSD',
                quantity=quantity
            )
    
    def liquidate(self):
        """
        Calculates size of position and sells entire stake. 
        Truncates position size to decimal number binance server will take.
        """
        # gets account information
        info = self.client.get_account()
        # calculates eth_pos, the truncated account position
        eth_pos = (info['balances'][1]['free'])
        num_decimals = len(eth_pos.split('.')[-1])
        num_decimals_to_remove = (num_decimals - (num_decimals - 3))
        eth_pos = float(eth_pos[:-1*num_decimals_to_remove])
        # makes order
        order = self.client.order_market_sell(
                symbol='ETHUSD',
                quantity=eth_pos
        )
    
    def append_bar(self, bar):
        """
        Appends most recent bar to the data structures in the class

        Args:
            bar (dict): binance kline bar see binance api for more details
        """
        #TODO: check why value isn't lining up with website for closes
        self.opens.append(float(bar['o']))
        self.closes.append(float(bar['c']))
        self.highs.append(float(bar['h']))
        self.lows.append(float(bar['l']))
        self.volumes.append(float(bar['v']))
    
    def pop_oldest_bar(self):
        """
        Removes the oldest bar from the datastructures in the class
        """
        self.opens.popleft()
        self.closes.popleft()
        self.highs.popleft()
        self.lows.popleft()
        self.volumes.popleft()
    
    def pop_newest_bar(self):
        """
        Removes the oldest bar from the datastructures in the class
        """
        self.opens.pop()
        self.closes.pop()
        self.highs.pop()
        self.lows.pop()
        self.volumes.pop()

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
