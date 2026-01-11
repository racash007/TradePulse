import sqlite3
import pandas as pd
from datetime import datetime

def query_database(db_path='resource/stock_data.db'):
    """Query and display database statistics"""
    conn = sqlite3.connect(db_path)
    
    # Get list of stocks
    print("\n" + "="*60)
    print("Stock Data Database Summary")
    print("="*60)
    
    # Count total records
    query = "SELECT COUNT(*) as total_records FROM stock_data"
    result = pd.read_sql_query(query, conn)
    print(f"\nTotal records: {result['total_records'][0]:,}")
    
    # Count unique stocks
    query = "SELECT COUNT(DISTINCT symbol) as unique_stocks FROM stock_data"
    result = pd.read_sql_query(query, conn)
    print(f"Unique stocks: {result['unique_stocks'][0]}")
    
    # Records per stock
    query = """
        SELECT symbol, COUNT(*) as record_count, 
               MIN(datetime) as earliest_date, 
               MAX(datetime) as latest_date
        FROM stock_data 
        GROUP BY symbol 
        ORDER BY record_count DESC
    """
    result = pd.read_sql_query(query, conn)
    print(f"\n{'Symbol':<15} {'Records':>10} {'Earliest':>20} {'Latest':>20}")
    print("-" * 70)
    for _, row in result.iterrows():
        print(f"{row['symbol']:<15} {row['record_count']:>10} {row['earliest_date']:>20} {row['latest_date']:>20}")
    
    # Download log summary
    print("\n" + "="*60)
    print("Download Log Summary")
    print("="*60)
    
    query = """
        SELECT status, COUNT(*) as count
        FROM download_log
        GROUP BY status
    """
    result = pd.read_sql_query(query, conn)
    print(f"\n{'Status':<15} {'Count':>10}")
    print("-" * 30)
    for _, row in result.iterrows():
        print(f"{row['status']:<15} {row['count']:>10}")
    
    # Failed downloads by error
    query = """
        SELECT error_message, COUNT(*) as count, 
               GROUP_CONCAT(symbol, ', ') as symbols
        FROM download_log
        WHERE status = 'failed'
        GROUP BY error_message
        ORDER BY count DESC
    """
    result = pd.read_sql_query(query, conn)
    if not result.empty:
        print("\n" + "="*60)
        print("Failed Downloads by Error Type")
        print("="*60)
        for _, row in result.iterrows():
            symbols = row['symbols'].split(', ')
            symbols_display = ', '.join(symbols[:5]) + ('...' if len(symbols) > 5 else '')
            print(f"\n{row['error_message']} ({row['count']} stocks):")
            print(f"  {symbols_display}")
    
    conn.close()
    print("\n" + "="*60 + "\n")

def get_stock_data(symbol, db_path='resource/stock_data.db'):
    """Get data for a specific stock"""
    conn = sqlite3.connect(db_path)
    query = f"""
        SELECT datetime, open, high, low, close, volume
        FROM stock_data
        WHERE symbol = '{symbol}'
        ORDER BY datetime
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

if __name__ == "__main__":
    query_database()
    
    # Example: Get data for a specific stock
    # df = get_stock_data('INFY')
    # print(f"\nINFY data shape: {df.shape}")
    # print(df.head())
