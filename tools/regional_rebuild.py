"""Rebuild every regional output for one saved-data cutoff. Offline; reads only preserved captures.

  python3 tools/regional_rebuild.py --through 2026-10-10T12:15:00Z

Runs, in order: compact store, coverage audit, full-history store, continuity audit, earlier
floods, history partitions, geology, pilot snapshot. It does not fetch, commit, package or deploy.
The seasonal view stays on its fixed date; only the storm window and the history end move.
"""
import argparse
from pathlib import Path
try:
    from . import regional_normalize, regional_analytics, regional_history, regional_events, regional_history_package, regional_geology, regional_pilot
except ImportError:
    import regional_normalize, regional_analytics, regional_history, regional_events, regional_history_package, regional_geology, regional_pilot

ROOT = Path(__file__).resolve().parents[1]


def rebuild(through, since='2026-09-01', rain_at=regional_pilot.RAIN_AT, storm_daily_end=None):
    regional_normalize.build(ROOT, None, since, through)
    regional_analytics.audit(ROOT/'data/normalized/regional-analytics')
    regional_history.build(through=through)
    regional_history.audit()
    regional_events.build()
    regional_history_package.package()
    regional_geology.build()
    return regional_pilot.build(rain_at, storm_daily_end)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--through', required=True, help='saved-data cutoff, UTC, e.g. 2026-10-10T12:15:00Z')
    p.add_argument('--since', default='2026-09-01'); p.add_argument('--rain-at', default=regional_pilot.RAIN_AT); p.add_argument('--storm-daily-end')
    a = p.parse_args(); rebuild(a.through, a.since, a.rain_at, a.storm_daily_end)
    print('Rebuilt for', a.through, '- now run the tests, then tools/package_regional_site.py')
