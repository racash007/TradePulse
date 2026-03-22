"""
Database Manager - Store and retrieve OHLCV data in SQLite.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manage OHLCV data storage in SQLite database."""
    
    def __init__(self, db_path: str = "market_data.db"):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_db()
    
    def _initialize_db(self):
        """Create database tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # Create stocks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stocks (
                    symbol TEXT PRIMARY KEY,
                    name TEXT,
                    token TEXT,
                    exchange TEXT DEFAULT 'NSE',
                    has_fno INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create OHLCV data table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    interval TEXT DEFAULT 'ONE_DAY',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timestamp, interval),
                    FOREIGN KEY (symbol) REFERENCES stocks(symbol)
                )
            """)
            
            # Create indices for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_timestamp 
                ON ohlcv_data(symbol, timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_timestamp 
                ON ohlcv_data(timestamp)
            """)
            
            self.conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def save_stocks(self, stocks: List[Dict[str, str]]):
        """
        Save stock information to database.
        
        Args:
            stocks: List of stock dictionaries with 'symbol', 'name', 'token'
        """
        try:
            cursor = self.conn.cursor()
            
            for stock in stocks:
                symbol = stock.get('symbol')
                name = stock.get('name', symbol)
                token = stock.get('token', '')
                
                cursor.execute("""
                    INSERT OR REPLACE INTO stocks (symbol, name, token, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (symbol, name, token))
            
            self.conn.commit()
            logger.info(f"Saved {len(stocks)} stocks to database")
            
        except Exception as e:
            logger.error(f"Error saving stocks: {e}")
            self.conn.rollback()
            raise
    
    def save_ohlcv_data(self, symbol: str, df: pd.DataFrame, interval: str = "ONE_DAY"):
        """
        Save OHLCV data to database.
        
        Args:
            symbol: Stock symbol
            df: DataFrame with OHLCV data (index should be timestamp)
            interval: Timeframe interval
        """
        try:
            if df.empty:
                logger.warning(f"Empty DataFrame provided for {symbol}")
                return
            
            cursor = self.conn.cursor()
            
            # Prepare data for insertion
            records = []
            for timestamp, row in df.iterrows():
                records.append((
                    symbol,
                    timestamp,
                    float(row['Open']),
                    float(row['High']),
                    float(row['Low']),
                    float(row['Close']),
                    int(row['Volume']),
                    interval
                ))
            
            # Insert or replace records
            cursor.executemany("""
                INSERT OR REPLACE INTO ohlcv_data 
                (symbol, timestamp, open, high, low, close, volume, interval)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            
            self.conn.commit()
            logger.info(f"Saved {len(records)} records for {symbol}")
            
        except Exception as e:
            logger.error(f"Error saving OHLCV data for {symbol}: {e}")
            self.conn.rollback()
            raise
    
    def get_ohlcv_data(
        self,
        symbol: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        interval: str = "ONE_DAY"
    ) -> Optional[pd.DataFrame]:
        """
        Retrieve OHLCV data from database.
        
        Args:
            symbol: Stock symbol
            from_date: Start date (optional)
            to_date: End date (optional)
            interval: Timeframe interval
        
        Returns:
            DataFrame with OHLCV data or None if not found
        """
        try:
            query = """
                SELECT timestamp, open, high, low, close, volume
                FROM ohlcv_data
                WHERE symbol = ? AND interval = ?
            """
            params = [symbol, interval]
            
            if from_date:
                query += " AND timestamp >= ?"
                params.append(from_date)
            
            if to_date:
                query += " AND timestamp <= ?"
                params.append(to_date)
            
            query += " ORDER BY timestamp ASC"
            
            df = pd.read_sql_query(query, self.conn, params=params)
            
            if df.empty:
                logger.warning(f"No data found for {symbol}")
                return None
            
            # Convert timestamp to datetime and set as index
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Rename columns to match expected format
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            
            logger.info(f"Retrieved {len(df)} records for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error retrieving data for {symbol}: {e}")
            return None
    
    def get_all_symbols(self) -> List[str]:
        """
        Get list of all symbols in database.
        
        Returns:
            List of stock symbols
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]
            return symbols
        except Exception as e:
            logger.error(f"Error retrieving symbols: {e}")
            return []
    
    def get_symbols_with_data(self, min_records: int = 100) -> List[str]:
        """
        Get symbols that have sufficient historical data.
        
        Args:
            min_records: Minimum number of records required
        
        Returns:
            List of symbols with sufficient data
        """
        try:
            query = """
                SELECT symbol, COUNT(*) as count
                FROM ohlcv_data
                GROUP BY symbol
                HAVING count >= ?
                ORDER BY symbol
            """
            df = pd.read_sql_query(query, self.conn, params=[min_records])
            return df['symbol'].tolist()
        except Exception as e:
            logger.error(f"Error retrieving symbols with data: {e}")
            return []
    
    def get_data_info(self, symbol: str) -> Optional[Dict]:
        """
        Get information about available data for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Dictionary with data information or None
        """
        try:
            query = """
                SELECT 
                    COUNT(*) as record_count,
                    MIN(timestamp) as first_date,
                    MAX(timestamp) as last_date,
                    interval
                FROM ohlcv_data
                WHERE symbol = ?
                GROUP BY interval
            """
            df = pd.read_sql_query(query, self.conn, params=[symbol])
            
            if df.empty:
                return None
            
            return {
                'symbol': symbol,
                'record_count': int(df.iloc[0]['record_count']),
                'first_date': df.iloc[0]['first_date'],
                'last_date': df.iloc[0]['last_date'],
                'interval': df.iloc[0]['interval']
            }
        except Exception as e:
            logger.error(f"Error getting data info for {symbol}: {e}")
            return None
    
    def delete_symbol_data(self, symbol: str):
        """
        Delete all data for a symbol.
        
        Args:
            symbol: Stock symbol
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM ohlcv_data WHERE symbol = ?", (symbol,))
            cursor.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))
            self.conn.commit()
            logger.info(f"Deleted all data for {symbol}")
        except Exception as e:
            logger.error(f"Error deleting data for {symbol}: {e}")
            self.conn.rollback()
            raise
    
    def export_to_csv(self, symbol: str, output_path: str):
        """
        Export symbol data to CSV file.
        
        Args:
            symbol: Stock symbol
            output_path: Path to output CSV file
        """
        try:
            df = self.get_ohlcv_data(symbol)
            if df is not None:
                df.to_csv(output_path)
                logger.info(f"Exported {symbol} data to {output_path}")
            else:
                logger.warning(f"No data to export for {symbol}")
        except Exception as e:
            logger.error(f"Error exporting {symbol} to CSV: {e}")
            raise
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
