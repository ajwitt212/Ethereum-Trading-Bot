# Binance API Keys
BINANCE_API_KEY = 'api key here'
BINANCE_API_SECRET_KEY = 'secret api key here'

# Binance Websocket Info
BASE_URL = "wss://stream.binance.us:9443"
SOCKET_SYMBOL = 'ethusd' # lowercase symbol
SOCKET_INTERVAL = '1m'
BINANCE_SOCKET = f'{BASE_URL}/ws/{SOCKET_SYMBOL}@kline_{SOCKET_INTERVAL}'

# Program Info
TICKER = 'ETHUSD' # uppercase symbol