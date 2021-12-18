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

# TODO modularize initialize and process_bar code for calculating technical indicators and comparing them with stock prices

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
        # track indicator values between bars
        self.min_since_upped_ubband = 100 # start high enough where its irrelevant
        self.min_since_dipped_lbband = 100 
        self.has_upped_rsi = False
        self.has_upped_mfi = False
        self.macd_hists = deque()
        # track position values
        self.position_high_price = None
        self.position_enter_price = None
        self.position_minutes = 0
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
            str(datetime.datetime.utcnow() - datetime.timedelta(minutes=101)) # import 101 bc we pop most recent unclosed candle 
            ):
            self.opens.append(float(kline[1]))
            self.closes.append(float(kline[4]))
            self.highs.append(float(kline[2]))
            self.lows.append(float(kline[3]))
            self.volumes.append(float(kline[5]))
        # deletes most recent candle which isn't yet closed
        self.pop_newest_bar()
        # calculates historical macds and adds them to attributes for slope calcs 
        np_closes = numpy.array(self.closes)
        macd_list, macdsignal_list, macdhist_list = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)
        for i in range(-3, 0):
            macdhist = macdhist_list[i]
            self.macd_hists.append(macdhist)
        
    
    def process_bar(self, bar):
        """
        Called each time websocket gets a ping. Processes bar, calculates indicators, and performs buys/sells

        Args:
            bar (dict): binance kline bar see binance api for more details
        """
        # bar processing initialization
        self.append_bar(bar)
        bar_closed = bar['x']
        avg_price = (self.highs[-1] + self.lows[-1] + self.closes[-1]) / 3.0
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
        # getting mfi info
        mfi = talib.MFI(np_highs, np_lows, np_closes, np_volumes, timeperiod=14)
        mfi = mfi[-1]
        # getting bbands info
        # TODO: swinging too much with live data, works with historical data
        upper_bband_list, middle_bband_list, lower_bband_list = talib.BBANDS(np_closes, timeperiod=20, nbdevup=1.95, nbdevdn=1.95, matype=0)
        upper_bband, middle_bband, lower_bband = upper_bband_list[-1], middle_bband_list[-1], lower_bband_list[-1]
        # getting macd info
        macd_list, macdsignal_list, macdhist_list = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)
        macd, macdsignal, macdhist = macd_list[-1], macdsignal_list[-1], macdhist_list[-1] # note: correct only to hundredths decimal place
        self.macd_hists.append(macdhist)
        macdhist_slope = self.calc_slope(self.macd_hists)
        # comparing indicator values for inter-bar analysis
        if bar_closed:
            if self.lows[-1] < lower_bband:
                self.min_since_dipped_lbband = 0 # if we just dipped set to 0
            elif self.min_since_dipped_lbband >= 0:
                self.min_since_dipped_lbband += 1 # if we've dipped before increase time

            if self.highs[-1] > upper_bband: # if we just upped set to 0
                self.min_since_upped_ubband = 0
            elif self.min_since_upped_ubband >= 0: # if we've upped before increase time
                self.min_since_upped_ubband += 1


        if self.position_high_price != None: # if we are in position
            if bar_closed:
                self.position_minutes += 1
            # comparing indicators for inter-bar position analysis
            if rsi > 69:
                self.has_upped_rsi = True
            if mfi > 79:
                self.has_upped_mfi = True
            if self.position_high_price is not None and self.highs[-1] > self.position_high_price:
                self.position_high_price = self.highs[-1]
            # checking sell conditions

            if not (rsi < 50 and mfi < 50 and self.closes[-1] > lower_bband and self.min_since_dipped_lbband <= 7 and -3 <= macdhist <= 1.5 and macdhist_slope > -0.05): # not in a buy condition
                if (
                # Take Profit: rsi too high and came back down
                (self.has_upped_rsi and rsi < 69) or  
                # Take Profit: mfi too high and came back down
                (self.has_upped_mfi and mfi < 79) or
                # Stop Loss: avg price too low (relative)
                (avg_price <= self.position_enter_price - 0.5*atr) or
                # Take Profit: crossed ubband and is too low
                (self.min_since_upped_ubband <= self.position_minutes and avg_price < upper_bband and avg_price <= self.position_high_price - .85*atr) or
                # Take Profit: 2*atr and dropped ever so slightly
                (self.position_high_price >= self.position_enter_price + 1.7*atr and self.closes[-1] < self.position_high_price - 0.5*atr)):
                    self.liquidate()
                    self.reset_position_trackers()

        else: # if we aren't in position
            if rsi < 50 and mfi < 50 and self.closes[-1] > lower_bband and self.min_since_dipped_lbband <= 7 and -3 <= macdhist <= 1.5 and macdhist_slope > -0.05:
                self.buy(quantity=.003)
                # updating position trackers
                self.position_high_price = self.position_enter_price

        # if bar closed keep new val as permanent and del oldest val, else we remove newest val 
        self.pop_oldest_bar() if bar_closed else self.pop_newest_bar() 
        self.macd_hists.popleft() if bar_closed else self.macd_hists.pop()

        # bar processing finalization
        if bar_closed:
            self.num_bars_processed += 1 
            print('-', self.num_bars_processed, '-')

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
        self.position_enter_price = float(order['fills'][0]['price'])
        print(f'- BOUGHT at price ({self.position_enter_price}) -')
        return order
    
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
        
        sell_price = float(order['fills'][0]['price'])
        money_diff = sell_price - self.position_enter_price
        percentage_diff = "{:.3%}".format(money_diff / sell_price)
        print(f'- SOLD at price ({sell_price}) for change of: ${money_diff} and {percentage_diff} -')

        return order
    
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

    def reset_position_trackers(self):
        """ 
        Function to reset all indicator values to their respective default states
        """
        self.has_upped_rsi = False
        self.has_upped_mfi = False        
        self.position_high_price = None
        self.position_enter_price = None
        self.position_minutes = 0
    
    def calc_slope(self, indicator_vals):
        x_vals = numpy.array(range(0, len(indicator_vals)))
        y_vals = numpy.array(indicator_vals)
        slope, y_int = numpy.polyfit(x_vals, y_vals, 1)
        return slope


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
