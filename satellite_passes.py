#!/usr/bin/env python3
"""
Satellite Pass Predictor - Main Script
Easy-to-use satellite pass prediction with visibility analysis.

This is the main script - just run: python satellite_passes.py
"""

# Import the visibility analysis module
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the satellite visibility analysis
try:
    from satellite_passes_visibility import main
    
    if __name__ == "__main__":
        print("🛰️  Satellite Pass Predictor")
        print("=" * 50)
        main()
        
except ImportError as e:
    print(f"Error importing satellite_passes_visibility: {e}")
    print("Please ensure all required files are present.")
    sys.exit(1)
except Exception as e:
    print(f"Error running satellite pass predictor: {e}")
    sys.exit(1)