import tempfile
import unittest
from pathlib import Path

from services.streamers import get_streamer_cards, load_streamer_config


class StreamerConfigTests(unittest.TestCase):
    def _write(self, text):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        tmp.write(text)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_defaults_and_name(self):
        path = self._write('''
default_limit: 250
streamers:
  - username: "RebeccaHarris"
    name: "Даниил Народицкий"
    title: "GM"
''')
        cfg = load_streamer_config(path)
        self.assertEqual(cfg["default_limit"], 250)
        self.assertEqual(cfg["streamers"][0]["username"], "RebeccaHarris")
        self.assertEqual(cfg["streamers"][0]["name"], "Даниил Народицкий")
        self.assertEqual(cfg["streamers"][0]["limit"], 250)

    def test_invalid_and_disabled_skipped(self):
        path = self._write('''
default_limit: 300
streamers:
  - username: "bad name"
  - username: "EricRosen"
    enabled: false
  - username: "Jepetto"
''')
        cfg = load_streamer_config(path)
        self.assertEqual([s["username"] for s in cfg["streamers"]], ["Jepetto"])

    def test_duplicate_skipped(self):
        path = self._write('''
streamers:
  - username: "RebeccaHarris"
  - username: "rebeccaharris"
''')
        cfg = load_streamer_config(path)
        self.assertEqual(len(cfg["streamers"]), 1)

    def test_loaded_status(self):
        path = self._write('''
streamers:
  - username: "RebeccaHarris"
    name: "Даниил Народицкий"
''')
        cards = get_streamer_cards([{
            "table_name": "games_rebeccaharris",
            "games": 5,
            "last_game": "2026-01-01",
        }], path)
        self.assertTrue(cards[0]["loaded"])
        self.assertEqual(cards[0]["games"], 5)
        self.assertEqual(cards[0]["name"], "Даниил Народицкий")


if __name__ == "__main__":
    unittest.main()
