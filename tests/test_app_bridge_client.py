from pathlib import Path
import importlib.util
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'app_bridge_client.py'
SPEC = importlib.util.spec_from_file_location('app_bridge_client', SCRIPT)
app_bridge_client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app_bridge_client)


class TestAppBridgeClient(unittest.TestCase):
    def test_request_requires_a_command_object(self):
        self.assertEqual(app_bridge_client.parse_request('{"cmd":"capabilities"}'), {'cmd': 'capabilities'})
        with self.assertRaises(ValueError):
            app_bridge_client.parse_request('[]')
        with self.assertRaises(ValueError):
            app_bridge_client.parse_request('{"cmd": 3}')


if __name__ == '__main__':
    unittest.main()
