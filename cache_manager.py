#!/usr/bin/env python3
"""
TLE Cache Manager
Utility to manage cached satellite TLE data.
"""

import os
from datetime import datetime, timezone, timedelta

def show_cache_status():
    """Show current cache status"""
    print("TLE Cache Status:")
    print("-" * 50)
    
    cache_dir = 'tle_cache'
    if not os.path.exists(cache_dir):
        print("No cache directory found.")
        return
    
    catalogs = ['visual', 'stations']
    for catalog in catalogs:
        cache_file = f'{cache_dir}/{catalog}.txt'
        timestamp_file = f'{cache_dir}/{catalog}_timestamp.txt'
        
        if os.path.exists(cache_file) and os.path.exists(timestamp_file):
            try:
                # Get cache age
                with open(timestamp_file, 'r') as f:
                    cache_time_str = f.read().strip()
                cache_time = datetime.fromisoformat(cache_time_str)
                age = datetime.now(timezone.utc) - cache_time
                
                # Get cache size
                size_kb = os.path.getsize(cache_file) / 1024
                
                # Count satellites
                with open(cache_file, 'r') as f:
                    lines = f.readlines()
                sat_count = len(lines) // 3
                
                status = "FRESH" if age < timedelta(hours=12) else "STALE"
                
                print(f"{catalog:>8}: {status} | Age: {age.total_seconds()/3600:5.1f}h | "
                      f"Size: {size_kb:6.1f}KB | Satellites: {sat_count:3d}")
                      
            except Exception as e:
                print(f"{catalog:>8}: ERROR - {e}")
        else:
            print(f"{catalog:>8}: MISSING")

def clear_cache():
    """Clear all cached data"""
    cache_dir = 'tle_cache'
    if not os.path.exists(cache_dir):
        print("No cache to clear.")
        return
    
    import shutil
    try:
        shutil.rmtree(cache_dir)
        print("Cache cleared successfully.")
    except Exception as e:
        print(f"Error clearing cache: {e}")

def main():
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'clear':
            clear_cache()
            return
        elif sys.argv[1] == 'status':
            show_cache_status()
            return
        else:
            print("Usage: python cache_manager.py [status|clear]")
            return
    
    # Default: show status
    show_cache_status()

if __name__ == "__main__":
    main()