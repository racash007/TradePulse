"""
Verify Setup - Test that all components are properly configured.
"""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    try:
        import pandas as pd
        print("✓ pandas")
    except ImportError as e:
        print(f"✗ pandas: {e}")
        return False
    
    try:
        import numpy as np
        print("✓ numpy")
    except ImportError as e:
        print(f"✗ numpy: {e}")
        return False
    
    try:
        from SmartApi import SmartConnect
        print("✓ smartapi-python")
    except ImportError as e:
        print(f"✗ smartapi-python: {e}")
        return False
    
    try:
        import pyotp
        print("✓ pyotp")
    except ImportError as e:
        print(f"✗ pyotp: {e}")
        return False
    
    try:
        import scipy
        print("✓ scipy")
    except ImportError as e:
        print(f"✗ scipy: {e}")
        return False
    
    try:
        from service.angel_data_downloader import AngelDataDownloader
        print("✓ AngelDataDownloader")
    except ImportError as e:
        print(f"✗ AngelDataDownloader: {e}")
        return False
    
    try:
        from service.database_manager import DatabaseManager
        print("✓ DatabaseManager")
    except ImportError as e:
        print(f"✗ DatabaseManager: {e}")
        return False
    
    try:
        from ui.optimizer import BacktestOptimizer
        print("✓ BacktestOptimizer")
    except ImportError as e:
        print(f"✗ BacktestOptimizer: {e}")
        return False
    
    try:
        from agent.paper_trade_agent import PaperTradeAgent
        print("✓ PaperTradeAgent")
    except ImportError as e:
        print(f"✗ PaperTradeAgent: {e}")
        return False
    
    return True


def test_env_file():
    """Test that .env file exists and has required credentials."""
    print("\nTesting .env file...")
    
    import os
    from pathlib import Path
    
    env_path = Path(__file__).resolve().parents[2] / '.env'
    if not env_path.exists():
        print("✗ .env file not found")
        return False
    
    print("✓ .env file exists")
    
    # Try to load environment variables
    try:
        from utility.env_loader import load_env
        load_env()
    except:
        # If env_loader doesn't work, try dotenv or manual
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except:
            pass
    
    required_vars = ['ANGEL_API_KEY', 'ANGEL_CLIENT_ID', 'ANGEL_PASSWORD', 'ANGEL_TOTP_SECRET']
    missing = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var} is set")
        else:
            print(f"✗ {var} is missing")
            missing.append(var)
    
    if missing:
        print(f"\nMissing credentials: {', '.join(missing)}")
        print("Please update your .env file with Angel One API credentials")
        return False
    
    return True


def test_database():
    """Test database operations."""
    print("\nTesting database...")
    
    try:
        from service.database_manager import DatabaseManager
        import os
        
        # Use a test database
        test_db = "test_market_data.db"
        db = DatabaseManager(test_db)
        
        print("✓ Database connection")
        
        # Test saving and retrieving
        test_stocks = [
            {'symbol': 'TEST', 'name': 'Test Stock', 'token': '123'}
        ]
        db.save_stocks(test_stocks)
        print("✓ Save stocks")
        
        symbols = db.get_all_symbols()
        if 'TEST' in symbols:
            print("✓ Retrieve symbols")
        else:
            print("✗ Failed to retrieve symbols")
            return False
        
        db.close()
        
        # Clean up test database
        if os.path.exists(test_db):
            os.remove(test_db)
            print("✓ Database operations complete")
        
        return True
        
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("TradePulse Setup Verification")
    print("=" * 60)
    
    all_passed = True
    
    # Test imports
    if not test_imports():
        all_passed = False
    
    # Test .env file
    if not test_env_file():
        all_passed = False
    
    # Test database
    if not test_database():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED - Setup is complete!")
        print("\nYou can now run:")
        print("  python app/utility/run_backtest_optimizer.py")
    else:
        print("✗ SOME TESTS FAILED - Please fix the issues above")
        return 1
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
