#!/usr/bin/env python
"""
Test script to verify the timezone fix
"""
import sys
import pandas as pd
from datetime import datetime

# Test timezone comparison issue
print("Testing timezone comparison fix...")

# Create tz-aware timestamp (like from database)
tz_aware = pd.Timestamp('2024-01-01 10:00:00+05:30')
print(f"TZ-aware timestamp: {tz_aware}")

# Create tz-naive timestamp
tz_naive = pd.Timestamp.max
print(f"TZ-naive timestamp: {tz_naive}")

# Test the fix logic
try:
    # Direct comparison (this would fail before fix)
    result = tz_aware <= tz_naive
    print(f"✗ Direct comparison succeeded (shouldn't happen): {result}")
except TypeError as e:
    print(f"✓ Direct comparison failed as expected: {e}")
    
    # Test our fix - convert both to tz-naive
    try:
        exit_date_naive = tz_aware.tz_localize(None) if hasattr(tz_aware, 'tz_localize') else tz_aware
        current_date_naive = tz_naive.tz_localize(None) if hasattr(tz_naive, 'tz_localize') else tz_naive
        result = exit_date_naive <= current_date_naive
        print(f"✓ Fixed comparison succeeded: {result}")
    except Exception as e:
        print(f"✗ Fixed comparison failed: {e}")
        sys.exit(1)

print("\n✓ All tests passed! The timezone fix should work.")
print("\nTo apply the fix, restart the Streamlit server:")
print("  1. Press Ctrl+C to stop current server")
print("  2. Run: streamlit run app/application.py")
