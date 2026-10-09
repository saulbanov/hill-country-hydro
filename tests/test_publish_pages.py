import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import publish_pages as pp  # noqa: E402


class PublishPagesTests(unittest.TestCase):
    def test_up_paths_become_site_relative(self):
        js = "fetch('../dist/water-state.json');const s=`../data/model/storms/${id}.json`;"
        html = '<a href="../docs/REGIONAL_ANALYTICS.md">notes</a>'
        self.assertEqual(pp.rewrite_up_paths(js), "fetch('dist/water-state.json');const s=`data/model/storms/${id}.json`;")
        self.assertEqual(pp.rewrite_up_paths(html), '<a href="docs/REGIONAL_ANALYTICS.md">notes</a>')

    def test_other_up_paths_are_left_for_the_guard(self):
        text = pp.rewrite_up_paths("fetch('../secret/file.json')")
        self.assertTrue(pp.ANY_UP.search(text), 'a path outside dist, data and docs is not rewritten, so build() refuses it')

    def test_daily_mode_never_raises(self):
        original = pp.bundle_problem
        pp.bundle_problem = lambda: (_ for _ in ()).throw(RuntimeError('boom'))
        try:
            self.assertEqual(pp.main(['--daily']), 0)
        finally:
            pp.bundle_problem = original


if __name__ == '__main__':
    unittest.main()
