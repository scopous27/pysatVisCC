# Satellite Pass Predictor

A Python script to predict visible satellite passes for a given observer location on Earth.

## Features

- **Smart TLE Caching**: Downloads TLE data once, caches locally for 12-24 hours
- **Visibility Analysis**: Shows only passes when observer is in darkness and satellite is sunlit  
- **Local Time Display**: All times shown in observer's local timezone
- **Evening/Morning Classification**: Separates optimal viewing times
- **Elevation Filtering**: Only shows passes above minimum elevation threshold
- **Comprehensive Coverage**: Includes bright visual satellites and space stations

## Setup

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Update `config.ini` with your location:
   ```ini
   [observer]
   latitude = 40.7128    # Your latitude in degrees
   longitude = -74.0060  # Your longitude in degrees
   altitude = 10         # Your altitude in meters above sea level
   timezone = America/New_York

   [satellites]
   min_elevation = 15    # Minimum elevation in degrees
   days_ahead = 1
   ```

## Usage

### Main Script

**Run the satellite pass predictor:**
```bash
source venv/bin/activate
python satellite_passes.py
```

**Alternative (direct):**
```bash
source venv/bin/activate  
python satellite_passes_visibility.py
```

### Cache Management

**Check cache status:**
```bash
python cache_manager.py status
```

**Clear cache (force fresh download):**
```bash
python cache_manager.py clear
```

## Output Format

The script outputs passes in this format:
```
Start Time (UTC)    | Start Dir | End Time (UTC)      | End Dir | Max Elev | Satellite
2025-08-04 19:40:39 | NW (316°) | 2025-08-04 19:48:39 | ENE (76°) | 17.5° | ISS (ZARYA)
```

Where:
- **Start Time**: When satellite becomes visible (UTC)
- **Start Dir**: Compass direction where satellite appears  
- **End Time**: When satellite disappears (UTC)
- **End Dir**: Compass direction where satellite disappears
- **Max Elev**: Maximum elevation angle during pass
- **Satellite**: Name of the satellite

## Key Definitions

- **TLE**: Three Line Element - mathematical description of satellite orbit
- **Elevation**: Height above horizon (0° = horizon, 90° = directly overhead)
- **Azimuth**: Compass bearing (0° = North, 90° = East, 180° = South, 270° = West)
- **Visible Pass**: When observer is in darkness and satellite is in sunlight
- **Evening**: After sunset, before satellite enters Earth's shadow
- **Morning**: Before sunrise, after satellite exits Earth's shadow

## Requirements

- Python 3.8+
- skyfield
- numpy  
- requests

## Files

- `satellite_passes.py` - **Main script** (easy entry point)
- `satellite_passes_visibility.py` - Core visibility analysis engine
- `cache_manager.py` - Utility to manage TLE data cache
- `config.ini` - Configuration file for observer location
- `requirements.txt` - Python package dependencies
- `README.md` - This documentation
- `venv/` - Virtual environment directory (auto-created)
- `tle_cache/` - **Cached TLE data** (auto-created, refreshed every 12-24 hours)
- `skyfield_data/` - Skyfield ephemeris data cache (auto-created)

## Notes

- **Efficient Caching**: TLE data cached locally, only downloads when stale (12-24 hours)
- **Times in Local Timezone**: All times displayed in observer's configured timezone
- **Visibility Filtering**: Only shows passes when conditions are optimal for viewing
- **Smart Analysis**: Separates evening/morning/daytime passes with sun elevation data
- **Performance Optimized**: Fast execution after initial cache population
- **No Runtime Downloads**: After first run, works offline until cache expires