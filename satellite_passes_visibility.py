#!/usr/bin/env python3
"""
Satellite Pass Predictor with Visibility Analysis
Shows satellite passes with detailed visibility information.
"""

import configparser
from datetime import datetime, timedelta, timezone
import requests
from skyfield.api import load, Topos
from skyfield.sgp4lib import EarthSatellite
import numpy as np
import pytz
import warnings

warnings.filterwarnings('ignore', module='skyfield')

def main():
    # Read configuration
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    # Observer location from config
    lat = float(config['observer']['latitude'])
    lon = float(config['observer']['longitude'])
    alt = float(config['observer']['altitude'])
    timezone_str = config['observer']['timezone']
    local_tz = pytz.timezone(timezone_str)
    min_elevation = float(config['satellites']['min_elevation'])
    
    print(f"Satellite Pass Predictor with Visibility Analysis")
    print(f"Observer: {lat:.4f}°, {lon:.4f}°, {alt}m")
    print(f"Timezone: {timezone_str}")
    print(f"Minimum elevation: {min_elevation}°")
    print()
    
    try:
        # Cache satellite TLE data locally
        def get_cached_tle_data():
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
                
                # Download if needed
                if should_download:
                    try:
                        print(f"  Downloading fresh {catalog_name} catalog...")
                        response = requests.get(url, timeout=30)
                        response.raise_for_status()
                        
                        # Save to cache
                        with open(cache_file, 'w') as f:
                            f.write(response.text)
                        with open(cache_age_file, 'w') as f:
                            f.write(datetime.now(timezone.utc).isoformat())
                            
                        print(f"  Cached {catalog_name} data")
                        
                    except Exception as e:
                        print(f"  Warning: Could not download {catalog_name}: {e}")
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
                    print(f"  Error reading cached {catalog_name} data: {e}")
                    continue
            
            return satellites
        
        print("Loading satellite TLE data...")
        satellites = get_cached_tle_data()
        print(f"Found {len(satellites)} bright satellites")
        
        # Setup Skyfield
        ts = load.timescale()
        observer_location = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt)
        
        # Load ephemeris for sun calculations
        planets = load('de421.bsp')
        earth = planets['earth']
        sun = planets['sun']
        observer_geocentric = earth + observer_location
        
        # Simplified visibility functions
        def get_sun_elevation(t):
            """Get sun elevation at given time"""
            sun_position = observer_geocentric.at(t).observe(sun)
            sun_alt, _, _ = sun_position.apparent().altaz()
            return sun_alt.degrees
        
        def categorize_pass_time(start_time_local):
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
        
        # Time range - next 24 hours
        now = datetime.now(timezone.utc)
        start_time = now
        end_time = now + timedelta(hours=24)
        
        all_passes = []
        
        print(f"\nCalculating passes for {len(satellites)} satellites...")
        
        def update_progress_bar(current, total):
            """Display a progress bar"""
            percent = int((current / total) * 100)
            bar_length = 50
            filled_length = int(bar_length * current / total)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"\r  Progress: [{bar}] {percent}% ({current}/{total})", end='', flush=True)
        
        for i, (sat_name, line1, line2) in enumerate(satellites, 1):
            update_progress_bar(i, len(satellites))
            satellite = EarthSatellite(line1, line2, sat_name, ts)
            
            try:
                # Create time array - sample every 3 minutes for better accuracy
                time_range = []
                current = start_time
                while current < end_time:
                    time_range.append(current)
                    current += timedelta(minutes=3)
                
                # Convert to Skyfield time objects
                time_tuples = []
                for t in time_range:
                    utc_t = t.astimezone(timezone.utc) if t.tzinfo else t
                    time_tuples.append((utc_t.year, utc_t.month, utc_t.day, utc_t.hour, utc_t.minute, utc_t.second))
                
                t_array = ts.utc(*zip(*time_tuples))
                
                # Calculate satellite positions
                positions = (satellite - observer_location).at(t_array)
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
                            
                            if max_elevation >= min_elevation:
                                max_idx = pass_start_idx + np.argmax(pass_elevations)
                                
                                start_time_utc = time_range[pass_start_idx]
                                end_time_utc = time_range[j-1]
                                max_time_utc = time_range[max_idx]
                                
                                start_time_local = start_time_utc.astimezone(local_tz)
                                end_time_local = end_time_utc.astimezone(local_tz)
                                max_time_local = max_time_utc.astimezone(local_tz)
                                
                                # Get sun elevation at pass time for visibility analysis
                                pass_time_skyfield = t_array[pass_start_idx]
                                sun_elev = get_sun_elevation(pass_time_skyfield)
                                
                                # Determine visibility - sun must be below -6° for good visibility
                                time_category = categorize_pass_time(start_time_local)  
                                observer_dark = sun_elev < -6  # Civil twilight or darker required
                                # Allow visibility during evening, morning, and night hours with proper darkness
                                potentially_visible = (observer_dark and 
                                                     time_category in ['Evening', 'Morning', 'Night'])
                                
                                passes.append({
                                    'satellite': sat_name,
                                    'start_time': start_time_utc,
                                    'start_time_local': start_time_local,
                                    'start_az': az_degrees.degrees[pass_start_idx],
                                    'start_alt': alt_degrees.degrees[pass_start_idx],
                                    'max_time': max_time_utc,
                                    'max_time_local': max_time_local,
                                    'max_az': az_degrees.degrees[max_idx],
                                    'max_elevation': max_elevation,
                                    'end_time': end_time_utc,
                                    'end_time_local': end_time_local,
                                    'end_az': az_degrees.degrees[j-1],
                                    'end_alt': alt_degrees.degrees[j-1],
                                    'time_category': time_category,
                                    'sun_elevation': sun_elev,
                                    'observer_dark': observer_dark,
                                    'potentially_visible': potentially_visible,
                                    'duration': (j - pass_start_idx) * 3  # minutes (3 min intervals)
                                })
                
                all_passes.extend(passes)
                
            except Exception as e:
                continue
        
        # Complete the progress bar
        print()  # Move to next line after progress bar
        
        # Sort passes by start time
        all_passes.sort(key=lambda x: x['start_time'])
        
        # Separate passes by visibility
        visible_passes = [p for p in all_passes if p['potentially_visible']]
        evening_passes = [p for p in visible_passes if p['time_category'] == 'Evening']
        morning_passes = [p for p in visible_passes if p['time_category'] == 'Morning']
        
        # Convert azimuth to degrees only
        def az_to_compass(azimuth):
            return f"{azimuth:.0f}°"
        
        def estimate_magnitude(satellite_name, max_elevation):
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

        def print_passes(passes, title):
            if passes:
                print(f"\n{title} ({len(passes)} passes):")
                print("Start | Start Dir | Stop  | Stop Dir | Max Alt | Mag   | Satellite")
                print("-" * 75)
                
                for pass_info in passes:
                    start_time_str = pass_info['start_time_local'].strftime("%H:%M")
                    start_dir = az_to_compass(pass_info['start_az'])  # Degrees only
                    
                    end_time_str = pass_info['end_time_local'].strftime("%H:%M")
                    end_dir = az_to_compass(pass_info['end_az'])
                    
                    max_elevation_str = f"{pass_info['max_elevation']:3.0f}°"
                    
                    magnitude = estimate_magnitude(pass_info['satellite'], pass_info['max_elevation'])
                    mag_str = f"{magnitude:+4.1f}"
                    
                    print(f"{start_time_str:>5} | {start_dir:>9} | {end_time_str:>5} | {end_dir:>8} | {max_elevation_str:>7} | {mag_str:>5} | {pass_info['satellite']}")
        
        # Output results
        current_local = datetime.now(local_tz)
        print(f"\nCurrent local time: {current_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        if visible_passes:
            print(f"\n🌟 POTENTIALLY VISIBLE PASSES ({len(visible_passes)} total)")
            print("(Observer in darkness, optimal viewing conditions)")
            print_passes(evening_passes, "🌆 EVENING PASSES (6 PM - 11 PM)")
            print_passes(morning_passes, "🌅 MORNING PASSES (4 AM - 8 AM)")
        else:
            print(f"\n🌟 No potentially visible passes found in next 24 hours")
        
        print(f"\nNote: Only passes with sun below -6° (civil twilight or darker) are shown.")
        print(f"Mag = estimated magnitude (lower/negative = brighter).")
        print(f"Times shown in local timezone. Directions shown as azimuth degrees (0°-360°).")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()