#!/usr/bin/env python3
"""
Satellite Pass Predictor with Visibility Analysis (Optimized Version)
Shows satellite passes with detailed visibility information.
Optimized for better performance and memory usage.
"""

import configparser
from datetime import datetime, timedelta, timezone
import requests
from skyfield.api import load, Topos
from skyfield.sgp4lib import EarthSatellite
import numpy as np
import pytz
import warnings
import logging
from collections import namedtuple
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import math
import time

warnings.filterwarnings('ignore', module='skyfield')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Data structures for better performance
PassInfo = namedtuple('PassInfo', [
    'satellite', 'start_time', 'start_time_local', 'start_az', 'start_alt',
    'max_time', 'max_time_local', 'max_az', 'max_elevation',
    'end_time', 'end_time_local', 'end_az', 'end_alt',
    'time_category', 'sun_elevation', 'observer_dark', 'potentially_visible', 'duration'
])

@dataclass
class Config:
    """Configuration class to hold all settings"""
    lat: float
    lon: float
    alt: float
    timezone_str: str
    local_tz: pytz.BaseTzInfo
    min_elevation: float
    days_ahead: int

class ProgressTracker:
    """Dedicated progress tracking class"""
    def __init__(self, total: int, bar_length: int = 50):
        self.total = total
        self.current = 0
        self.bar_length = bar_length
    
    def update(self, increment: int = 1):
        """Update progress and display progress bar"""
        self.current += increment
        percent = int((self.current / self.total) * 100)
        filled_length = int(self.bar_length * self.current / self.total)
        bar = '█' * filled_length + '░' * (self.bar_length - filled_length)
        print(f"\r  Progress: [{bar}] {percent}% ({self.current}/{self.total})", end='', flush=True)
    
    def finish(self):
        """Complete the progress bar"""
        print()  # Move to next line

class SatellitePassPredictor:
    """Main class for satellite pass prediction"""
    
    def __init__(self, config: Config):
        self.config = config
        self.ts = load.timescale()
        self.observer_location = Topos(
            latitude_degrees=config.lat, 
            longitude_degrees=config.lon, 
            elevation_m=config.alt
        )
        
        # Load ephemeris for sun calculations
        self.planets = load('de421.bsp')
        self.earth = self.planets['earth']
        self.sun = self.planets['sun']
        self.observer_geocentric = self.earth + self.observer_location
        
        # Sun position cache
        self.sun_cache = {}
        
        # Compass directions
        self.directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                          "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    
    def get_sun_elevation(self, t):
        """Get sun elevation at given time with caching"""
        # Round time to nearest 10 minutes for caching
        cache_key = (t.whole, round(t.tt_fraction * 24 * 60 / 10) * 10)
        if cache_key in self.sun_cache:
            return self.sun_cache[cache_key]
            
        sun_position = self.observer_geocentric.at(t).observe(self.sun)
        sun_alt, _, _ = sun_position.apparent().altaz()
        sun_elev = sun_alt.degrees
        
        # Cache result
        self.sun_cache[cache_key] = sun_elev
        return sun_elev
    
    def categorize_pass_time(self, start_time_local):
        """Categorize pass by local time"""
        hour = start_time_local.hour
        if 18 <= hour <= 23:
            return "Evening"
        elif 4 <= hour <= 8:
            return "Morning" 
        elif 8 <= hour <= 17:  # More precise daytime hours
            return "Daytime"
        else:
            return "Night"  # 0-4 and 23-24 hours
    
    def az_to_compass(self, azimuth):
        """Convert azimuth to degrees only"""
        return f"{azimuth:.0f}°"
    
    def estimate_magnitude(self, satellite_name, max_elevation):
        """Estimate satellite magnitude based on type and elevation"""
        name_upper = satellite_name.upper()
        
        # Base magnitude estimates for known satellites
        if 'ISS' in name_upper:
            base_mag = -3.0  # Very bright
        elif 'HST' in name_upper or 'HUBBLE' in name_upper:
            base_mag = 2.0   # Moderately bright
        elif any(rocket in name_upper for rocket in ['CZ-4B', 'CZ-2C', 'SL-', 'R/B']):
            base_mag = 3.5   # Rocket bodies, dimmer
        elif any(station in name_upper for station in ['CSS', 'TIANHE', 'TIANGONG']):
            base_mag = -2.0  # Space stations, bright
        else:
            base_mag = 4.0   # Generic satellite
        
        # Adjust for elevation (higher = brighter due to less atmosphere)
        elevation_factor = (max_elevation - 10) * 0.02  # Brighter at higher elevations
        estimated_mag = base_mag - elevation_factor
        
        return max(-4.0, min(6.0, estimated_mag))  # Clamp between -4 and +6
    
    def get_cached_tle_data(self):
        """Load TLE data from cache or download if needed"""
        import os
        from datetime import timedelta
        
        os.makedirs('tle_cache', exist_ok=True)
        
        urls = {
            'visual': 'https://celestrak.com/NORAD/elements/visual.txt',
            'stations': 'https://celestrak.com/NORAD/elements/stations.txt'
        }
        
        satellites = []
        
        for catalog_name, url in urls.items():
            cache_file = f'tle_cache/{catalog_name}.txt'
            cache_age_file = f'tle_cache/{catalog_name}_timestamp.txt'
            
            # Check if cache exists and is fresh (less than 24 hours old)
            should_download = True
            if os.path.exists(cache_file) and os.path.exists(cache_age_file):
                try:
                    with open(cache_age_file, 'r') as f:
                        cache_time_str = f.read().strip()
                    cache_time = datetime.fromisoformat(cache_time_str)
                    age = datetime.now(timezone.utc) - cache_time
                    
                    if age < timedelta(hours=24):
                        print(f"  Using cached {catalog_name} data (age: {age.total_seconds()/3600:.1f} hours)")
                        should_download = False
                except Exception:
                    pass
            
            # Download if needed with retry logic
            if should_download:
                max_retries = 3
                retry_delay = 5  # seconds
                
                for attempt in range(max_retries):
                    try:
                        print(f"  Downloading fresh {catalog_name} catalog (attempt {attempt + 1}/{max_retries})...")
                        response = requests.get(url, timeout=30)
                        response.raise_for_status()
                        
                        # Save to cache
                        with open(cache_file, 'w') as f:
                            f.write(response.text)
                        with open(cache_age_file, 'w') as f:
                            f.write(datetime.now(timezone.utc).isoformat())
                            
                        print(f"  Cached {catalog_name} data")
                        break  # Success, exit retry loop
                        
                    except Exception as e:
                        logger.warning(f"  Warning: Could not download {catalog_name} (attempt {attempt + 1}): {e}")
                        if attempt < max_retries - 1:
                            print(f"  Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                        else:
                            if not os.path.exists(cache_file):
                                continue
                            print(f"  Using existing cached {catalog_name} data")
            
            # Load from cache
            try:
                with open(cache_file, 'r') as f:
                    lines = f.read().strip().split('\n')
                
                # Parse satellites - be more selective for performance
                for i in range(0, len(lines), 3):
                    if i + 2 < len(lines):
                        name = lines[i].strip()
                        line1 = lines[i + 1].strip()
                        line2 = lines[i + 2].strip()
                        
                        if line1.startswith('1 ') and line2.startswith('2 '):
                            # Include more satellites, especially CZ-4B R/B as mentioned by user
                            if catalog_name == 'visual':
                                # Include bright visual satellites and rocket bodies
                                keywords = ['ISS', 'HST', 'AJISAI', 'GENESIS', 'LAGEOS', 'CZ-4B', 'CZ-2C', 'SL-']
                                if any(keyword in name.upper() for keyword in keywords):
                                    satellites.append((name, line1, line2))
                            elif catalog_name == 'stations':
                                # Include space stations
                                if any(keyword in name.upper() for keyword in ['ISS', 'CSS', 'TIANHE', 'TIANGONG']):
                                    satellites.append((name, line1, line2))
                                    
            except Exception as e:
                logger.error(f"  Error reading cached {catalog_name} data: {e}")
                continue
        
        return satellites
    
    def filter_satellites_by_orbit(self, satellites):
        """Filter satellites based on orbital characteristics to reduce calculations"""
        # For now, we'll keep all satellites but this could be enhanced
        # to filter based on inclination and observer latitude
        return satellites
    
    def detect_passes_adaptive(self, satellite, t_array, time_range):
        """Detect passes using adaptive time sampling"""
        # Calculate satellite positions
        positions = (satellite - self.observer_location).at(t_array)
        alt_degrees, az_degrees, distance = positions.altaz()
        
        # Find passes above horizon
        above_horizon = alt_degrees.degrees > 0
        
        # Find pass segments
        passes = []
        in_pass = False
        pass_start_idx = None
        
        for j, is_above in enumerate(above_horizon):
            if is_above and not in_pass:
                # Start of pass
                in_pass = True
                pass_start_idx = j
            elif not is_above and in_pass:
                # End of pass
                in_pass = False
                if pass_start_idx is not None:
                    # Extract pass data
                    pass_elevations = alt_degrees.degrees[pass_start_idx:j]
                    max_elevation = np.max(pass_elevations)
                    
                    if max_elevation >= self.config.min_elevation:
                        max_idx = pass_start_idx + np.argmax(pass_elevations)
                        
                        start_time_utc = time_range[pass_start_idx]
                        end_time_utc = time_range[j-1]
                        max_time_utc = time_range[max_idx]
                        
                        start_time_local = start_time_utc.astimezone(self.config.local_tz)
                        end_time_local = end_time_utc.astimezone(self.config.local_tz)
                        max_time_local = max_time_utc.astimezone(self.config.local_tz)
                        
                        # Get sun elevation at pass time for visibility analysis
                        pass_time_skyfield = t_array[pass_start_idx]
                        sun_elev = self.get_sun_elevation(pass_time_skyfield)
                        
                        # Determine visibility - sun must be below -6° for good visibility
                        time_category = self.categorize_pass_time(start_time_local)
                        observer_dark = sun_elev < -6  # Civil twilight or darker required
                        # Allow visibility during evening, morning, and night hours with proper darkness
                        potentially_visible = (observer_dark and
                                             time_category in ['Evening', 'Morning', 'Night'])
                        
                        passes.append(PassInfo(
                            satellite=satellite.name,
                            start_time=start_time_utc,
                            start_time_local=start_time_local,
                            start_az=az_degrees.degrees[pass_start_idx],
                            start_alt=alt_degrees.degrees[pass_start_idx],
                            max_time=max_time_utc,
                            max_time_local=max_time_local,
                            max_az=az_degrees.degrees[max_idx],
                            max_elevation=max_elevation,
                            end_time=end_time_utc,
                            end_time_local=end_time_local,
                            end_az=az_degrees.degrees[j-1],
                            end_alt=alt_degrees.degrees[j-1],
                            time_category=time_category,
                            sun_elevation=sun_elev,
                            observer_dark=observer_dark,
                            potentially_visible=potentially_visible,
                            duration=(j - pass_start_idx) * 3  # minutes (3 min intervals)
                        ))
        
        # Handle case where pass is still in progress at end of time range
        if in_pass and pass_start_idx is not None:
            j = len(above_horizon)
            pass_elevations = alt_degrees.degrees[pass_start_idx:j]
            max_elevation = np.max(pass_elevations)
            
            if max_elevation >= self.config.min_elevation:
                max_idx = pass_start_idx + np.argmax(pass_elevations)
                
                start_time_utc = time_range[pass_start_idx]
                end_time_utc = time_range[j-1]
                max_time_utc = time_range[max_idx]
                
                start_time_local = start_time_utc.astimezone(self.config.local_tz)
                end_time_local = end_time_utc.astimezone(self.config.local_tz)
                max_time_local = max_time_utc.astimezone(self.config.local_tz)
                
                # Get sun elevation at pass time for visibility analysis
                pass_time_skyfield = t_array[pass_start_idx]
                sun_elev = self.get_sun_elevation(pass_time_skyfield)
                
                # Determine visibility - sun must be below -6° for good visibility
                time_category = self.categorize_pass_time(start_time_local)
                observer_dark = sun_elev < -6  # Civil twilight or darker required
                # Allow visibility during evening, morning, and night hours with proper darkness
                potentially_visible = (observer_dark and
                                     time_category in ['Evening', 'Morning', 'Night'])
                
                passes.append(PassInfo(
                    satellite=satellite.name,
                    start_time=start_time_utc,
                    start_time_local=start_time_local,
                    start_az=az_degrees.degrees[pass_start_idx],
                    start_alt=alt_degrees.degrees[pass_start_idx],
                    max_time=max_time_utc,
                    max_time_local=max_time_local,
                    max_az=az_degrees.degrees[max_idx],
                    max_elevation=max_elevation,
                    end_time=end_time_utc,
                    end_time_local=end_time_local,
                    end_az=az_degrees.degrees[j-1],
                    end_alt=alt_degrees.degrees[j-1],
                    time_category=time_category,
                    sun_elevation=sun_elev,
                    observer_dark=observer_dark,
                    potentially_visible=potentially_visible,
                    duration=(j - pass_start_idx) * 3  # minutes (3 min intervals)
                ))
        
        return passes
    
    def calculate_passes_vectorized(self, satellites):
        """Calculate passes using vectorized operations for better performance"""
        # Time range - next 24 hours
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now + timedelta(hours=self.config.days_ahead * 24)
        
        # Create time array with 3-minute intervals for accuracy
        def create_time_array(start_time, end_time, interval=3):
            """Create time array with consistent 3-minute intervals"""
            time_range = []
            current = start_time
            while current < end_time:
                time_range.append(current)
                current += timedelta(minutes=interval)
            return time_range
        
        # Convert to Skyfield time objects
        time_range = create_time_array(start_time, end_time)
        time_tuples = []
        for t in time_range:
            utc_t = t.astimezone(timezone.utc) if t.tzinfo else t
            time_tuples.append((utc_t.year, utc_t.month, utc_t.day, utc_t.hour, utc_t.minute, utc_t.second))
        
        t_array = self.ts.utc(*zip(*time_tuples))
        
        all_passes = []
        progress = ProgressTracker(len(satellites))
        
        # Process satellites individually for accuracy
        for sat_name, line1, line2 in satellites:
            progress.update()
            satellite = EarthSatellite(line1, line2, sat_name, self.ts)
            
            try:
                # Detect passes with 3-minute time sampling for accuracy
                passes = self.detect_passes_adaptive(satellite, t_array, time_range)
                all_passes.extend(passes)
                
            except Exception:
                continue
        
        progress.finish()
        return all_passes
    
    def print_passes(self, passes, title):
        """Print passes in a formatted table"""
        if passes:
            print(f"\n{title} ({len(passes)} passes):")
            print("Start | Start Dir | Stop  | Stop Dir | Max Alt | Mag   | Satellite")
            print("-" * 75)
            
            for pass_info in passes:
                start_time_str = pass_info.start_time_local.strftime("%H:%M")
                start_dir = self.az_to_compass(pass_info.start_az)
                
                end_time_str = pass_info.end_time_local.strftime("%H:%M")
                end_dir = self.az_to_compass(pass_info.end_az)
                
                max_elevation_str = f"{pass_info.max_elevation:3.0f}°"
                
                magnitude = self.estimate_magnitude(pass_info.satellite, pass_info.max_elevation)
                mag_str = f"{magnitude:+4.1f}"
                
                print(f"{start_time_str:>5} | {start_dir:>9} | {end_time_str:>5} | {end_dir:>8} | {max_elevation_str:>7} | {mag_str:>5} | {pass_info.satellite}")
    
    def run(self):
        """Main execution method"""
        print(f"Satellite Pass Predictor with Visibility Analysis (Optimized)")
        print(f"Observer: {self.config.lat:.4f}°, {self.config.lon:.4f}°, {self.config.alt}m")
        print(f"Timezone: {self.config.timezone_str}")
        print(f"Minimum elevation: {self.config.min_elevation}°")
        print()
        
        try:
            print("Loading satellite TLE data...")
            satellites = self.get_cached_tle_data()
            print(f"Found {len(satellites)} bright satellites")
            
            # Filter satellites by orbit (could be enhanced)
            filtered_satellites = self.filter_satellites_by_orbit(satellites)
            
            # Calculate passes
            print(f"\nCalculating passes for {len(filtered_satellites)} satellites...")
            all_passes = self.calculate_passes_vectorized(filtered_satellites)
            
            # Sort passes by start time
            all_passes.sort(key=lambda x: x.start_time)
            
            # Separate passes by visibility
            visible_passes = [p for p in all_passes if p.potentially_visible]
            evening_passes = [p for p in visible_passes if p.time_category == 'Evening']
            morning_passes = [p for p in visible_passes if p.time_category == 'Morning']
            
            # Output results
            current_local = datetime.now(self.config.local_tz)
            print(f"\nCurrent local time: {current_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            if visible_passes:
                print(f"\n🌟 POTENTIALLY VISIBLE PASSES ({len(visible_passes)} total)")
                print("(Observer in darkness, optimal viewing conditions)")
                self.print_passes(evening_passes, "🌆 EVENING PASSES (6 PM - 11 PM)")
                self.print_passes(morning_passes, "🌅 MORNING PASSES (4 AM - 8 AM)")
            else:
                print(f"\n🌟 No potentially visible passes found in next 24 hours")
            
            print(f"\nNote: Only passes with sun below -6° (civil twilight or darker) are shown.")
            print(f"Mag = estimated magnitude (lower/negative = brighter).")
            print(f"Times shown in local timezone. Directions shown as azimuth degrees (0°-360°).")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

def load_config():
    """Load configuration from config.ini"""
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    # Observer location from config
    lat = float(config['observer']['latitude'])
    lon = float(config['observer']['longitude'])
    alt = float(config['observer']['altitude'])
    timezone_str = config['observer']['timezone']
    local_tz = pytz.timezone(timezone_str)
    min_elevation = float(config['satellites']['min_elevation'])
    days_ahead = int(config['satellites'].get('days_ahead', 1))
    
    return Config(
        lat=lat,
        lon=lon,
        alt=alt,
        timezone_str=timezone_str,
        local_tz=local_tz,
        min_elevation=min_elevation,
        days_ahead=days_ahead
    )

def main():
    """Main function"""
    config = load_config()
    predictor = SatellitePassPredictor(config)
    predictor.run()

if __name__ == "__main__":
    main()