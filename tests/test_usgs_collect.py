"""Offline tests for USGS collection order, refusals and latest coverage; no provider request is made."""

import datetime as dt
import io
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from tools import monitor

NOW = dt.datetime.now(dt.timezone.utc)
REFUSAL = b'{"error":{"code":"OVER_RATE_LIMIT","message":"You have exceeded your rate limit."}}'


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status, self.headers = body, status, headers or {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def feature(station, value, when):
    return {'properties': {'monitoring_location_id': 'USGS-' + station, 'parameter_code': '00060', 'unit_of_measure': 'ft^3/s',
                           'time': when.isoformat(), 'value': value, 'time_series_id': 'ts-' + station}}


def filtered_ids(url):
    text = parse_qs(urlparse(url).query)['filter'][0]
    return [part.strip(" '")[5:] for part in text[text.index('(') + 1:text.rindex(')')].split(',')]


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.patches = [mock.patch.object(monitor, 'ROOT', root), mock.patch.object(monitor, 'RAW', root / 'data/raw/usgs'),
                        mock.patch.object(monitor, 'NORM', root / 'data/normalized'), mock.patch.dict(os.environ, {'USGS_API_KEY': 'test-key-not-real'})]
        for p in self.patches: p.start()
        self.requests = []

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def run_collect(self, stations, answer):
        def fake_urlopen(req, timeout):
            self.requests.append(req)
            return answer(req.full_url)
        with mock.patch.object(monitor, 'urlopen', side_effect=fake_urlopen), mock.patch('builtins.print') as out:
            monitor.collect(stations, pause=0)
        return out.call_args[0][0]

    def test_latest_comes_first_in_batches_and_refusals_stop_the_run(self):
        stations = [f'0815{n:04d}' for n in range(45)]

        def answer(url):
            if '/latest-continuous/' in url:
                return Response(json.dumps({'features': [feature(s, '12.5', NOW) for s in filtered_ids(url)], 'links': []}).encode())
            raise HTTPError(url, 429, 'Too Many Requests', {'Retry-After': '3600'}, io.BytesIO(REFUSAL))

        report = self.run_collect(stations, answer)
        urls = [r.full_url for r in self.requests]
        self.assertEqual(2 + monitor.STOP_AFTER_REFUSALS, len(urls))
        self.assertEqual([stations[:40], stations[40:]], [filtered_ids(u) for u in urls[:2]])
        self.assertTrue(all('/continuous/items' in u for u in urls[2:]))
        self.assertTrue(all(r.get_header('X-api-key') == 'test-key-not-real' for r in self.requests))
        self.assertIn('latest values for 45 of 45 stations', report)
        self.assertIn(f'REFUSED {monitor.STOP_AFTER_REFUSALS} REQUESTS', report)
        self.assertIn(f'{2 * 45 - monitor.STOP_AFTER_REFUSALS} not requested', report)
        metas = [json.loads(p.read_text()) for p in sorted(monitor.RAW.glob('*.meta.json'))]
        self.assertEqual([200, 200, 429, 429, 429], [m['status'] for m in metas])
        self.assertEqual({'Retry-After': '3600'}, metas[-1]['rate_limit'])
        self.assertFalse(any('test-key-not-real' in p.read_text() for p in monitor.RAW.iterdir()))
        # The saved refusals stay raw; only the two latest batches become observations.
        with mock.patch('builtins.print'):
            monitor.normalize()
        db = sqlite3.connect(monitor.NORM / 'water.sqlite')
        rows = db.execute('select raw_path from observations').fetchall(); db.close()
        self.assertEqual(45, len(rows))
        self.assertTrue(all('latest-continuous-batch' in r[0] for r in rows))

    def test_latest_pages_follow_next_link_and_a_healthy_run_has_no_banner(self):
        stations = ['08155500', '08158000', '08170500']
        page2 = monitor.BASE + '/latest-continuous/items?f=json&offset=2'

        def answer(url):
            if url == page2:
                return Response(json.dumps({'features': [feature('08158000', '174', NOW)], 'links': []}).encode())
            if '/latest-continuous/' in url:
                return Response(json.dumps({'features': [feature('08155500', '17.0', NOW)], 'links': [{'rel': 'next', 'href': page2}]}).encode())
            return Response(b'{"type":"FeatureCollection","features":[]}')

        report = self.run_collect(stations, answer)
        names = sorted(p.name.split('Z-', 1)[1] for p in monitor.RAW.glob('*.meta.json'))
        self.assertIn('latest-continuous-batch01-page2.meta.json', names)
        self.assertEqual(2 + 2 * len(stations), len(self.requests))
        self.assertIn('latest values for 2 of 3 stations (2 within 24 h)', report)
        self.assertNotIn('⚠️', report)

    def test_coverage_counts_only_values_from_accepted_responses(self):
        old = NOW - dt.timedelta(days=3)
        accepted = monitor.save('latest-continuous-batch01', 'u', 200, json.dumps({'features': [
            feature('A', None, NOW), feature('B', '1.0', old), feature('C', '2.0', NOW)]}).encode())
        empty = monitor.save('latest-continuous-batch02', 'u', 200, b'{"features":[]}')
        refused = monitor.save('latest-continuous-batch03', 'u', 429, json.dumps({'features': [feature('D', '3.0', NOW)]}).encode())
        self.assertEqual((2, 1), monitor.latest_coverage([accepted, empty, refused], NOW))
        report = monitor.collect_report(['A', 'B', 'C', 'D', 'E'], [accepted, empty, refused], {200: 2, 429: 1}, 0, NOW)
        self.assertIn('ONLY 2 OF 5 STATIONS HAVE A LATEST VALUE', report)


if __name__ == '__main__':
    unittest.main()
