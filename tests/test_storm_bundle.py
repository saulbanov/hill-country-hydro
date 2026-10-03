import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from tools import publish_bundle as p
class StormBundleTests(unittest.TestCase):
    def test_optional_storm_block_preserves_null_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp); expected={'storms':{'fixture':{'rain':{'missing':{'inches_window':None},'zero':{'inches_window':0}}}}}
            (app/'storm-delta.json').write_text(json.dumps(expected))
            with patch.object(p,'APP',app): b=p.build()
            self.assertEqual(b['schema_version'],1); self.assertEqual(b['storm_delta'],expected)
