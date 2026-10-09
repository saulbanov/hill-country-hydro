"""Station lists shared by the collectors, read from data/stations-regional.json when it exists.

AUSTIN_TEN is the original Austin set; it is always included so the storm-week protocol and the
place rules keep their stations even if the inventory file is missing or rebuilt.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / 'data/stations-regional.json'
AUSTIN_TEN = ['08154700', '08155240', '08155300', '08155400', '08155500', '08156800', '08158827', '08158930', '08158970', '08159000']

def _inventory():
    return json.loads(INVENTORY.read_text())['stations'] if INVENTORY.exists() else []

# Springflow records the Edwards Aquifer Authority publishes as Comal and San Marcos springflow. They
# carry daily discharge history only (no live context here), so only usgs_history.py collects them.
# Added 2026-10-08 for swimming-hole-decline Track A, which reads the springflow, not the river below it.
SPRINGFLOW_HISTORY = ['08168710', '08170000']

# Every USGS gauge the Austin Swim Map rates swimming places from: the ids in its public Site's
# dist/data/gauges.json (sha256 91d85de5…, 2026-10-09). The water map keeps the full daily record and
# a station page for each, so usgs_history.py collects them and regional_history.py names them. Like
# SPRINGFLOW_HISTORY, they join usgs_history.py's default list only; context, ledger and peaks keep
# history_stations(). Ids are frozen; add a gauge here when the swim map adds one.
SWIM_MAP_GAUGES = ['08155240', '08154700', '08155300', '08156800', '08159000', '08158970', '08158930', '08170500',
                   '08170860', '08170990', '08155400', '08169000', '08168500', '08169500', '08167370', '08194930',
                   '08194970', '08195000', '08155500', '08104900', '08158827', '08158000', '08159200', '08171400']

def history_stations():
    """Full daily history, ledger, and context: the Austin ten plus tiers 'austin' and 'regional-key'."""
    ids = list(AUSTIN_TEN)
    for s in _inventory():
        if s['tier'] in ('austin', 'regional-key') and s['id'] not in ids: ids.append(s['id'])
    return ids

LOCATIONS = ROOT / 'data/usgs-locations-regional.json'

def all_stations():
    """Current readings every day: every USGS location in the region with any live series (streams, springs, wells, lakes), discharge or not."""
    ids = list(AUSTIN_TEN)
    for s in _inventory():
        if s['id'] not in ids: ids.append(s['id'])
    if LOCATIONS.exists():
        for r in json.loads(LOCATIONS.read_text())['locations']:
            if r['id'] not in ids: ids.append(r['id'])
    return ids
