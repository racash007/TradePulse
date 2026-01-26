import os
import re
import time
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from SmartApi import SmartConnect
import pandas as pd
import pyotp

# Load environment variables
load_dotenv()

# Granularity mapping
granularity_map = {
    '1 min': 'ONE_MINUTE',
    '5 min': 'FIVE_MINUTE',
    '15 min': 'FIFTEEN_MINUTE',
    '30 min': 'THIRTY_MINUTE',
    '1 hour': 'ONE_HOUR',
    '1 day': 'ONE_DAY'
}

# Global variable for SmartAPI object
obj = None
logged_in = False

def login():
    """Login to Angel One API"""
    global obj, logged_in
    if logged_in:
        print("Already logged in")
        return True
    
    # Try both naming conventions for credentials
    API_KEY = os.getenv('ANGEL_API_KEY') or os.getenv('API_KEY')
    CLIENT_ID = os.getenv('ANGEL_CLIENT_ID') or os.getenv('CLIENT_ID')
    PASSWORD = os.getenv('ANGEL_PASSWORD') or os.getenv('PASSWORD')
    TOTP_SECRET = os.getenv('ANGEL_TOTP_SECRET') or os.getenv('TOTP_SECRET')

    if not API_KEY or not CLIENT_ID or not PASSWORD or not TOTP_SECRET:
        print("Error: Missing credentials in .env file.")
        print(f"API_KEY: {'Set' if API_KEY else 'Missing'}")
        print(f"CLIENT_ID: {'Set' if CLIENT_ID else 'Missing'}")
        print(f"PASSWORD: {'Set' if PASSWORD else 'Missing'}")
        print(f"TOTP_SECRET: {'Set' if TOTP_SECRET else 'Missing'}")
        return False

    print(f"Initializing SmartAPI...")
    obj = SmartConnect(api_key=API_KEY)

    # Generate TOTP
    totp = pyotp.TOTP(TOTP_SECRET).now()

    # Try login with TOTP
    try:
        data = obj.generateSession(CLIENT_ID, PASSWORD, totp)
        if data and data.get('status'):
            print("✓ Login successful")
            logged_in = True
            return True
        else:
            print(f"✗ Login failed: {data.get('message', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"✗ Login exception: {e}")
        return False

def historical_data(exchange, token, from_date, to_date, interval):
    """Fetch historical data"""
    if not logged_in and not login():
        return None, "Not logged in"

    historic_params = {
        "exchange": exchange,
        "symboltoken": token,
        "interval": interval,
        "fromdate": from_date,
        "todate": to_date
    }
    
    try:
        response = obj.getCandleData(historic_params)
        if response and response.get('status'):
            data = response['data']
            columns = ['DateTime', 'Open', 'High', 'Low', 'Close', 'Volume']
            df = pd.DataFrame(data, columns=columns)
            return df, None
        else:
            error_msg = response.get('message', 'Unknown error') if response else 'No response'
            return None, error_msg
    except Exception as e:
        error_msg = str(e)
        print(f"    Error: {error_msg}")
        return None, error_msg

def create_database(db_path='resource/stock_data.db'):
    """Create SQLite database and tables"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table for stock data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            datetime TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, datetime)
        )
    ''')
    
    # Create table for download tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS download_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            token TEXT,
            status TEXT,
            records_count INTEGER,
            error_message TEXT,
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_datetime ON stock_data(symbol, datetime)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_download_log_symbol ON download_log(symbol, download_date)')
    
    conn.commit()
    conn.close()
    print(f"✓ Database created/verified at {db_path}")

def save_to_database(df, symbol, db_path='resource/stock_data.db'):
    """Save dataframe to SQLite database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Add symbol column
    df_copy = df.copy()
    df_copy['symbol'] = symbol
    
    # Rename columns to match database schema
    df_copy.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'symbol']
    
    # Insert or replace data
    for _, row in df_copy.iterrows():
        cursor.execute('''
            INSERT OR REPLACE INTO stock_data (symbol, datetime, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (row['symbol'], row['datetime'], row['open'], row['high'], row['low'], row['close'], row['volume']))
    
    conn.commit()
    conn.close()

def log_download(symbol, token, status, records_count, error_message, db_path='resource/stock_data.db'):
    """Log download attempt"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO download_log (symbol, token, status, records_count, error_message)
        VALUES (?, ?, ?, ?, ?)
    ''', (symbol, token, status, records_count, error_message))
    
    conn.commit()
    conn.close()


# Extended stock symbols with their Angel One tokens
stock_tokens = {
    # Banking & Financial Services
    'HDFCBANK': '1333',
    'ICICIBANK': '4963',
    'AXISBANK': '5900',
    'KOTAKBANK': '1922',
    'INDUSINDBK': '5258',
    'FEDERALBNK': '1023',
    'IDFCFIRSTB': '11184',
    'BANDHANBNK': '579',
    'AUBANK': '21808',
    'YESBANK': '3066',
    'SBIN': '3045',
    'BANKBARODA': '4668',
    'CANBK': '10794',
    'PNB': '10666',
    'UNIONBANK': '4685',
    'INDIANB': '7595',
    'BANKINDIA': '4717',
    'BAJFINANCE': '317',
    'BAJAJFINSV': '16675',
    'CHOLAFIN': '685',
    'SHRIRAMFIN': '4306',
    'M&MFIN': '13285',
    'MUTHOOTFIN': '23650',
    'LICHSGFIN': '7005',
    'LTFH': '24948',
    'JIOFIN': '5258',  # Check actual token
    'ANGELONE': '26729',
    'BSE': '534976',
    'CDSL': '4749',
    'CAMS': '17818',
    
    # Information Technology
    'TCS': '11536',
    'INFY': '1594',
    'WIPRO': '3787',
    'HCLTECH': '7229',
    'TECHM': '13538',
    'LTIM': '17818',
    'MPHASIS': '4503',
    'PERSISTENT': '3814',
    'COFORGE': '11543',
    'TATAELXSI': '2065',
    'KPITTECH': '16366',
    'TATATECH': '39678',
    
    # Automobiles & Auto Components
    'TATAMOTORS': '3456',
    'MARUTI': '10999',
    'M&M': '2031',
    'EICHERMOT': '910',
    'BAJAJ-AUTO': '16669',
    'HEROMOTOCO': '1348',
    'TVSMOTOR': '8479',
    'ASHOKLEY': '212',
    'BOSCHLTD': '2181',
    'MOTHERSON': '14977',
    'MRF': '2277',
    'APOLLOTYRE': '163',
    'JK TYRE': '1723',
    'UNOMINDA': '11287',
    
    # Energy, Oil & Gas
    'RELIANCE': '2885',
    'ONGC': '2475',
    'BPCL': '526',
    'IOC': '1624',
    'HINDPETRO': '1406',
    'GAIL': '4717',
    'PETRONET': '2700',
    'OIL': '2534',
    'ATGL': '4752',
    'NTPC': '11630',
    'POWERGRID': '14977',
    'TATAPOWER': '3426',
    'JSWENERGY': '21238',
    'ADANIPOWER': '3548',
    'NHPC': '4953',
    'IREDA': '11184',
    
    # Pharmaceuticals & Healthcare
    'SUNPHARMA': '3351',
    'DRREDDY': '881',
    'CIPLA': '694',
    'APOLLOHOSP': '157',
    'DIVISLAB': '10940',
    'AUROPHARMA': '275',
    'LUPIN': '10440',
    'GLENMARK': '7406',
    'BIOCON': '11373',
    'GRANULES': '11872',
    'SYNGENE': '10243',
    'MAXHEALTH': '30108',
    'PIRAMAL': '6769',
    
    # Metal, Mining & Commodities
    'TATASTEEL': '3499',
    'JSWSTEEL': '11723',
    'HINDALCO': '1363',
    'VEDL': '3063',
    'JINDALSTEL': '6733',
    'NMDC': '15332',
    'COALINDIA': '5215',
    'NATIONALUM': '6364',
    'HINDZINC': '1364',
    'SAIL': '2963',
    
    # Consumer Goods (FMCG) & Retail
    'ITC': '1660',
    'HINDUNILVR': '1394',
    'NESTLEIND': '17963',
    'BRITANNIA': '547',
    'TATACONSUM': '3432',
    'ASIANPAINT': '236',
    'BERGEPAINT': '404',
    'PIDILITIND': '2664',
    'TITAN': '3506',
    'DMART': '14299',
    'ZOMATO': '13404',
    'TRENT': '1964',
    'SWIGGY': '43901',
    
    # Infrastructure, Realty & Cement
    'LT': '11483',
    'DLF': '14732',
    'GODREJPROP': '17975',
    'OBEROIRLTY': '20242',
    'LODHA': '16675',
    'ULTRACEMCO': '11532',
    'GRASIM': '1232',
    'AMBUJACEM': '1270',
    'ACC': '22',
    'SHREECEM': '3103',
    'DALBHARAT': '8075',
    'NBCC': '14977',
}

def extract_stock_symbols(filename):
    """Extract stock symbols from stock_list.txt"""
    symbols = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Define known mappings for special cases
        name_to_symbol = {
            'HDFC Bank': 'HDFCBANK',
            'ICICI Bank': 'ICICIBANK',
            'Axis Bank': 'AXISBANK',
            'Kotak Mahindra Bank': 'KOTAKBANK',
            'IndusInd Bank': 'INDUSINDBK',
            'Federal Bank': 'FEDERALBNK',
            'IDFC First Bank': 'IDFCFIRSTB',
            'Bandhan Bank': 'BANDHANBNK',
            'AU Small Finance Bank': 'AUBANK',
            'Yes Bank': 'YESBANK',
            'State Bank of India': 'SBIN',
            'SBI': 'SBIN',
            'Bank of Baroda': 'BANKBARODA',
            'Canara Bank': 'CANBK',
            'PNB': 'PNB',
            'Union Bank of India': 'UNIONBANK',
            'Indian Bank': 'INDIANB',
            'Bank of India': 'BANKINDIA',
            'Bajaj Finance': 'BAJFINANCE',
            'Bajaj Finserv': 'BAJAJFINSV',
            'Chola Investment': 'CHOLAFIN',
            'Shriram Finance': 'SHRIRAMFIN',
            'M&M Financial': 'M&MFIN',
            'Muthoot Finance': 'MUTHOOTFIN',
            'LIC Housing Finance': 'LICHSGFIN',
            'L&T Finance': 'LTFH',
            'Jio Financial Services': 'JIOFIN',
            'Angel One': 'ANGELONE',
            'BSE Ltd': 'BSE',
            'CDSL': 'CDSL',
            'CAMS': 'CAMS',
            'TCS': 'TCS',
            'Infosys': 'INFY',
            'Wipro': 'WIPRO',
            'HCL Tech': 'HCLTECH',
            'Tech Mahindra': 'TECHM',
            'LTIMindtree': 'LTIM',
            'Mphasis': 'MPHASIS',
            'Persistent Systems': 'PERSISTENT',
            'Coforge': 'COFORGE',
            'Tata Elxsi': 'TATAELXSI',
            'KPIT Tech': 'KPITTECH',
            'Tata Technologies': 'TATATECH',
            'Tata Motors': 'TATAMOTORS',
            'Maruti Suzuki': 'MARUTI',
            'Mahindra & Mahindra': 'M&M',
            'M&M': 'M&M',
            'Eicher Motors': 'EICHERMOT',
            'Bajaj Auto': 'BAJAJ-AUTO',
            'Hero MotoCorp': 'HEROMOTOCO',
            'TVS Motor': 'TVSMOTOR',
            'Ashok Leyland': 'ASHOKLEY',
            'Bosch': 'BOSCHLTD',
            'Samvardhana Motherson': 'MOTHERSON',
            'MRF': 'MRF',
            'Apollo Tyres': 'APOLLOTYRE',
            'JK Tyre': 'JK TYRE',
            'UNO Minda': 'UNOMINDA',
            'Reliance Industries': 'RELIANCE',
            'RIL': 'RELIANCE',
            'ONGC': 'ONGC',
            'BPCL': 'BPCL',
            'IOC': 'IOC',
            'HPCL': 'HINDPETRO',
            'GAIL': 'GAIL',
            'Petronet LNG': 'PETRONET',
            'Oil India': 'OIL',
            'Adani Total Gas': 'ATGL',
            'NTPC': 'NTPC',
            'Power Grid': 'POWERGRID',
            'Tata Power': 'TATAPOWER',
            'JSW Energy': 'JSWENERGY',
            'Adani Power': 'ADANIPOWER',
            'NHPC': 'NHPC',
            'IREDA': 'IREDA',
            'Sun Pharma': 'SUNPHARMA',
            'Dr. Reddy\'s': 'DRREDDY',
            'Cipla': 'CIPLA',
            'Apollo Hospitals': 'APOLLOHOSP',
            'Divi\'s Lab': 'DIVISLAB',
            'Aurobindo Pharma': 'AUROPHARMA',
            'Lupin': 'LUPIN',
            'Glenmark': 'GLENMARK',
            'Biocon': 'BIOCON',
            'Granules India': 'GRANULES',
            'Syngene': 'SYNGENE',
            'Max Healthcare': 'MAXHEALTH',
            'Piramal Pharma': 'PIRAMAL',
            'Tata Steel': 'TATASTEEL',
            'JSW Steel': 'JSWSTEEL',
            'Hindalco': 'HINDALCO',
            'Vedanta': 'VEDL',
            'Jindal Steel': 'JINDALSTEL',
            'NMDC': 'NMDC',
            'Coal India': 'COALINDIA',
            'National Aluminium': 'NATIONALUM',
            'NALCO': 'NATIONALUM',
            'Hindustan Zinc': 'HINDZINC',
            'Sail': 'SAIL',
            'ITC': 'ITC',
            'Hindustan Unilever': 'HINDUNILVR',
            'HUL': 'HINDUNILVR',
            'Nestle India': 'NESTLEIND',
            'Britannia': 'BRITANNIA',
            'Tata Consumer': 'TATACONSUM',
            'Asian Paints': 'ASIANPAINT',
            'Berger Paints': 'BERGEPAINT',
            'Pidilite': 'PIDILITIND',
            'Titan Company': 'TITAN',
            'Avenue Supermarts': 'DMART',
            'DMart': 'DMART',
            'Zomato': 'ZOMATO',
            'Trent': 'TRENT',
            'Swiggy': 'SWIGGY',
            'Larsen & Toubro': 'LT',
            'L&T': 'LT',
            'DLF': 'DLF',
            'Godrej Properties': 'GODREJPROP',
            'Oberoi Realty': 'OBEROIRLTY',
            'Macrotech Developers': 'LODHA',
            'Lodha': 'LODHA',
            'UltraTech Cement': 'ULTRACEMCO',
            'Grasim': 'GRASIM',
            'Ambuja Cement': 'AMBUJACEM',
            'ACC': 'ACC',
            'Shree Cement': 'SHREECEM',
            'Dalmia Bharat': 'DALBHARAT',
            'NBCC': 'NBCC',
        }
        
        # Search for known company names in content
        for name, symbol in name_to_symbol.items():
            if name in content:
                symbols.append(symbol)
        
        # Also try to find direct symbol matches
        for symbol in stock_tokens.keys():
            pattern = r'\b' + re.escape(symbol) + r'\b'
            if re.search(pattern, content, re.IGNORECASE):
                symbols.append(symbol)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_symbols = []
        for symbol in symbols:
            if symbol not in seen:
                seen.add(symbol)
                unique_symbols.append(symbol)
        
        return unique_symbols
    except Exception as e:
        print(f"Error reading stock_list.txt: {e}")
        return []

def download_stock_data(symbols, granularity='1 day', period='5 years', save_to_db=True, save_to_csv=True, delay_between_requests=1.0):
    """Download stock data for given symbols"""
    if not symbols:
        print("No valid stock symbols found!")
        return
    
    print(f"\nFound {len(symbols)} stocks to download:")
    print(", ".join(symbols))
    print(f"\nGranularity: {granularity}")
    print(f"Period: {period}")
    print(f"Save to DB: {save_to_db}")
    print(f"Save to CSV: {save_to_csv}")
    print(f"Delay between requests: {delay_between_requests}s")
    
    # Create database if saving to DB
    db_path = 'resource/stock_data.db'
    if save_to_db:
        create_database(db_path)
    
    # Login first
    if not login():
        print("Failed to login. Please check your credentials in .env file.")
        return
    
    # Get date range
    now = datetime.now()
    if period == '1 month':
        from_date = now - timedelta(days=30)
    elif period == '1 year':
        from_date = now - timedelta(days=365)
    elif period == '3 years':
        from_date = now - timedelta(days=365*3)
    elif period == '5 years':
        from_date = now - timedelta(days=365*5)
    else:
        from_date = now - timedelta(days=365*5)  # default 5 years
    
    to_date = now
    from_date = from_date.replace(hour=9, minute=15, second=0, microsecond=0)
    to_date = to_date.replace(hour=15, minute=30, second=0, microsecond=0)
    
    from_date_str = from_date.strftime('%Y-%m-%d %H:%M')
    to_date_str = to_date.strftime('%Y-%m-%d %H:%M')
    
    interval = granularity_map.get(granularity, 'ONE_DAY')
    
    # Create output directory for CSV
    output_dir = 'resource/data'
    if save_to_csv:
        os.makedirs(output_dir, exist_ok=True)
    
    success_count = 0
    failed_stocks = {}
    rate_limit_count = 0
    
    # Download data for each symbol
    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] Downloading {symbol}...")
        
        token = stock_tokens.get(symbol)
        if not token:
            error_msg = "Token not found"
            print(f"  ⚠ {error_msg}")
            failed_stocks[symbol] = error_msg
            if save_to_db:
                log_download(symbol, None, 'failed', 0, error_msg, db_path)
            continue
        
        # Add delay to avoid rate limiting
        if i > 1:
            time.sleep(delay_between_requests)
        
        try:
            df, error = historical_data("NSE", token, from_date_str, to_date_str, interval)
            
            if df is not None and not df.empty:
                # Save to database
                if save_to_db:
                    try:
                        save_to_database(df, symbol, db_path)
                        log_download(symbol, token, 'success', len(df), None, db_path)
                    except Exception as db_error:
                        print(f"  ⚠ DB save error: {db_error}")
                
                # Save to CSV
                if save_to_csv:
                    filename = f"{output_dir}/{symbol}_{granularity.replace(' ', '_')}_{period.replace(' ', '_')}.csv"
                    df.to_csv(filename, index=False)
                    print(f"  ✓ Downloaded {len(df)} records (CSV: {filename})")
                else:
                    print(f"  ✓ Downloaded {len(df)} records (saved to DB)")
                
                success_count += 1
            else:
                # Categorize the error
                if error and 'rate' in error.lower():
                    rate_limit_count += 1
                    error_msg = "Rate limit exceeded"
                else:
                    error_msg = error or "No data available"
                
                print(f"  ✗ {error_msg}")
                failed_stocks[symbol] = error_msg
                
                if save_to_db:
                    log_download(symbol, token, 'failed', 0, error_msg, db_path)
                    
        except Exception as e:
            error_msg = str(e)
            print(f"  ✗ Error: {error_msg}")
            failed_stocks[symbol] = error_msg
            
            if save_to_db:
                log_download(symbol, token, 'failed', 0, error_msg, db_path)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Download Summary:")
    print(f"  Total stocks: {len(symbols)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {len(failed_stocks)}")
    print(f"  Rate limit errors: {rate_limit_count}")
    
    if failed_stocks:
        print(f"\nFailed stocks by reason:")
        # Group by error reason
        error_groups = {}
        for symbol, error in failed_stocks.items():
            if error not in error_groups:
                error_groups[error] = []
            error_groups[error].append(symbol)
        
        for error, symbols_list in error_groups.items():
            print(f"  {error} ({len(symbols_list)}): {', '.join(symbols_list[:10])}{'...' if len(symbols_list) > 10 else ''}")
    
    if save_to_db:
        print(f"\n✓ Data saved to database: {db_path}")
    
    print(f"{'='*60}\n")

if __name__ == "__main__":
    # Extract symbols from stock_list.txt
    symbols = extract_stock_symbols('stock_list.txt')
    
    if not symbols:
        print("No valid stock symbols found in stock_list.txt")
        print("\nAvailable symbols in the token database:")
        print(", ".join(sorted(stock_tokens.keys())))
    else:
        # Download data at 1 day granularity for 5 years
        # Increased delay to avoid rate limiting
        download_stock_data(
            symbols, 
            granularity='1 day', 
            period='5 years',
            save_to_db=True,
            save_to_csv=True,
            delay_between_requests=2.0  # 2 second delay between requests
        )
