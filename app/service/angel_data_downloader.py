"""
Angel One Data Downloader - Fetch NSE stocks with options and historical OHLCV data.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

import pandas as pd
import pyotp
from SmartApi import SmartConnect

logger = logging.getLogger(__name__)


class AngelDataDownloader:
    """Download market data using Angel One SmartAPI."""
    
    def __init__(self, api_key: str, client_id: str, password: str, totp_secret: str):
        """
        Initialize Angel One API connection.
        
        Args:
            api_key: Angel One API key
            client_id: Angel One client ID
            password: Angel One password
            totp_secret: TOTP secret for 2FA
        """
        self.api_key = api_key
        self.client_id = client_id
        self.password = password
        self.totp_secret = totp_secret
        self.smart_api: Optional[SmartConnect] = None
        self.auth_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.feed_token: Optional[str] = None
        
    def connect(self) -> bool:
        """
        Establish connection to Angel One API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.smart_api = SmartConnect(api_key=self.api_key)
            
            # Generate TOTP token
            totp = pyotp.TOTP(self.totp_secret)
            totp_token = totp.now()
            
            # Login
            data = self.smart_api.generateSession(
                clientCode=self.client_id,
                password=self.password,
                totp=totp_token
            )
            
            if data['status']:
                self.auth_token = data['data']['jwtToken']
                self.refresh_token = data['data']['refreshToken']
                self.feed_token = self.smart_api.getfeedToken()
                
                logger.info("Successfully connected to Angel One API")
                return True
            else:
                logger.error(f"Failed to connect: {data.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to Angel One API: {e}")
            return False
    
    def get_nse_fno_stocks(self) -> List[Dict[str, str]]:
        """
        Get list of NSE stocks with F&O (Futures & Options) derivatives.
        
        Returns:
            List of dictionaries containing stock information
        """
        try:
            if not self.smart_api:
                raise RuntimeError("Not connected to Angel One API. Call connect() first.")
            
            # Angel One provides instrument list which includes F&O stocks
            # Download the instrument file
            logger.info("Fetching NSE F&O stocks list...")
            
            # Get all instruments
            instruments_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            
            import requests
            response = requests.get(instruments_url)
            
            if response.status_code == 200:
                instruments = response.json()
                
                # Filter for NSE F&O stocks (equity derivatives)
                fno_stocks = []
                seen_symbols = set()
                
                for instrument in instruments:
                    # Check if it's NSE F&O
                    if instrument.get('exch_seg') == 'NFO':  # NSE F&O segment
                        symbol = instrument.get('symbol', '')
                        # Get underlying symbol (remove expiry dates, strike prices, etc.)
                        if symbol and symbol not in seen_symbols:
                            # Basic cleanup - symbols in NFO have derivatives
                            # Extract base symbol (before any digits or special chars)
                            base_symbol = ''.join([c for c in symbol if c.isalpha() or c == '&'])
                            
                            if base_symbol and base_symbol not in seen_symbols:
                                seen_symbols.add(base_symbol)
                                fno_stocks.append({
                                    'symbol': base_symbol,
                                    'token': instrument.get('token', ''),
                                    'name': instrument.get('name', base_symbol)
                                })
                
                # Additionally, get stocks from NSE cash segment that have F&O
                # These are typically the major stocks
                nse_fno_symbols = [
                    'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'HINDUNILVR',
                    'ITC', 'SBIN', 'BHARTIARTL', 'BAJFINANCE', 'KOTAKBANK', 'LT',
                    'ASIANPAINT', 'MARUTI', 'TITAN', 'M&M', 'TATAMOTORS', 'AXISBANK',
                    'WIPRO', 'ULTRACEMCO', 'SUNPHARMA', 'NTPC', 'ONGC', 'POWERGRID',
                    'BAJAJFINSV', 'HCLTECH', 'TECHM', 'TATASTEEL', 'INDUSINDBK', 'ADANIENT',
                    'ADANIPORTS', 'DRREDDY', 'JSWSTEEL', 'BRITANNIA', 'GRASIM', 'CIPLA',
                    'COALINDIA', 'SHREECEM', 'DIVISLAB', 'EICHERMOT', 'APOLLOHOSP', 'BPCL',
                    'HINDALCO', 'UPL', 'TATACONSUM', 'NESTLEIND', 'HEROMOTOCO', 'BAJAJ-AUTO',
                    'SBILIFE', 'TATAPOWER', 'VEDL', 'GODREJCP', 'OFSS'
                ]
                
                # Add known F&O stocks if not already in list
                for symbol in nse_fno_symbols:
                    if symbol not in seen_symbols:
                        seen_symbols.add(symbol)
                        fno_stocks.append({
                            'symbol': symbol,
                            'token': '',
                            'name': symbol
                        })
                
                logger.info(f"Found {len(fno_stocks)} NSE F&O stocks")
                return fno_stocks
            else:
                logger.error(f"Failed to download instruments: Status {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching F&O stocks: {e}")
            return []
    
    def get_historical_data(
        self,
        symbol: str,
        token: str,
        from_date: datetime,
        to_date: datetime,
        interval: str = "ONE_DAY"
    ) -> Optional[pd.DataFrame]:
        """
        Download historical OHLCV data for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., 'INFY')
            token: Instrument token from Angel One
            from_date: Start date
            to_date: End date
            interval: Timeframe (ONE_DAY, ONE_HOUR, etc.)
        
        Returns:
            DataFrame with OHLCV data or None if failed
        """
        try:
            if not self.smart_api:
                raise RuntimeError("Not connected to Angel One API. Call connect() first.")
            
            logger.info(f"Downloading data for {symbol} from {from_date} to {to_date}")
            
            # If token is empty, try to find it
            if not token:
                token = self._find_token(symbol)
                if not token:
                    logger.warning(f"Could not find token for {symbol}, skipping")
                    return None
            
            # Angel One API requires specific format
            params = {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
                "todate": to_date.strftime("%Y-%m-%d %H:%M")
            }
            
            # Get historical data
            response = self.smart_api.getCandleData(params)
            
            if response['status'] and response['data']:
                data = response['data']
                
                # Convert to DataFrame
                df = pd.DataFrame(
                    data,
                    columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
                )
                
                # Convert timestamp to datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                
                # Add symbol column
                df['Symbol'] = symbol
                
                logger.info(f"Downloaded {len(df)} rows for {symbol}")
                return df
            else:
                logger.warning(f"No data available for {symbol}: {response.get('message', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading data for {symbol}: {e}")
            return None
    
    def _find_token(self, symbol: str) -> Optional[str]:
        """
        Find instrument token for a given symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Token string or None if not found
        """
        try:
            instruments_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            
            import requests
            response = requests.get(instruments_url)
            
            if response.status_code == 200:
                instruments = response.json()
                
                # Look for exact match in NSE segment
                for instrument in instruments:
                    if (instrument.get('exch_seg') == 'NSE' and 
                        instrument.get('symbol') == symbol and
                        instrument.get('instrumenttype') == 'EQ'):
                        return instrument.get('token')
                
                # Fallback: try to find in NFO
                for instrument in instruments:
                    if instrument.get('exch_seg') == 'NFO':
                        inst_symbol = instrument.get('symbol', '')
                        if inst_symbol.startswith(symbol):
                            return instrument.get('token')
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding token for {symbol}: {e}")
            return None
    
    def download_bulk_historical_data(
        self,
        symbols: List[str],
        years: int = 5,
        interval: str = "ONE_DAY"
    ) -> Dict[str, pd.DataFrame]:
        """
        Download historical data for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            years: Number of years of historical data
            interval: Timeframe
        
        Returns:
            Dictionary mapping symbol to DataFrame
        """
        results = {}
        to_date = datetime.now()
        from_date = to_date - timedelta(days=365 * years)
        
        logger.info(f"Downloading data for {len(symbols)} symbols...")
        
        for i, symbol_info in enumerate(symbols):
            # Handle both dict and string formats
            if isinstance(symbol_info, dict):
                symbol = symbol_info['symbol']
                token = symbol_info.get('token', '')
            else:
                symbol = symbol_info
                token = ''
            
            try:
                df = self.get_historical_data(
                    symbol=symbol,
                    token=token,
                    from_date=from_date,
                    to_date=to_date,
                    interval=interval
                )
                
                if df is not None and not df.empty:
                    results[symbol] = df
                    logger.info(f"[{i+1}/{len(symbols)}] Downloaded {symbol}: {len(df)} rows")
                else:
                    logger.warning(f"[{i+1}/{len(symbols)}] No data for {symbol}")
                
                # Rate limiting - wait between requests
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error downloading {symbol}: {e}")
                continue
        
        logger.info(f"Successfully downloaded data for {len(results)}/{len(symbols)} symbols")
        return results
    
    def close(self):
        """Close the API connection."""
        if self.smart_api:
            try:
                self.smart_api.terminateSession(self.client_id)
                logger.info("Closed Angel One API connection")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
