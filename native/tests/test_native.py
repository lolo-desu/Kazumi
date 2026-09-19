from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nativeapp.storage import Store
from nativeapp.services import Service
from nativeapp.network import Http


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store("test", self.temp.name)
        self.service = Service(Http(self.store), self.store)

    def test_profile_round_trip_and_no_credentials_in_export(self):
        self.store.set("theme", "dark")
        self.store.set("token", "not-for-backup")
        self.store.put("collect", {"id": "1", "title": "测试"})
        data = self.store.export_data()
        self.assertNotIn("token", data["settings"])
        self.store.remove("collect", "1")
        self.store.import_data(data)
        self.assertEqual(self.store.items("collect")[0]["title"], "测试")
        self.assertEqual(self.store.get("theme"), "dark")

    def test_invalid_backup_does_not_partially_update(self):
        self.store.set("theme", "light")
        bad = {
            "format": "gnome-media-profile",
            "version": 1,
            "settings": {"theme": "dark"},
            "library": [["bad"]],
        }
        with self.assertRaises(ValueError):
            self.store.import_data(bad)
        self.assertEqual(self.store.get("theme"), "light")

    def test_reject_foreign_backup(self):
        with self.assertRaises(ValueError):
            self.store.import_data({"format": "hive", "version": 1})

    def test_rules_keep_original_fields(self):
        rule = {
            "name": "fixture",
            "api": "8",
            "baseURL": "https://example.com",
            "searchURL": "https://example.com/?q=@keyword",
            "searchList": "//article",
            "searchName": ".//a",
            "searchResult": ".//a",
            "chapterRoads": "//ul",
            "chapterResult": ".//a",
            "userAgent": "fixture-UA",
            "antiCrawlerConfig": {"enabled": False},
            "futureField": {"preserve": True},
        }
        self.service.save_plugin(rule)
        self.assertEqual(
            next(p for p in self.service.plugins() if p["name"] == "fixture"), rule
        )

    def test_upstream_xpath_search_and_episode_identity(self):
        rule = {
            "name": "fixture",
            "baseURL": "https://example.com",
            "searchURL": "https://example.com/?q=@keyword",
            "searchList": "//article",
            "searchName": ".//a",
            "searchResult": ".//a",
            "chapterRoads": "//ul",
            "chapterResult": ".//a",
        }
        raw = '<article><a href="/show/1">测试</a></article><ul><li><a href="/play/1">第1集</a></li></ul>'
        prepared = self.service.core("search.prepare", rule, input="中文 & x")
        self.assertIn("%E4%B8%AD%E6%96%87", prepared["url"])
        items = self.service.core("search.parse", rule, raw=raw)["items"]
        self.assertEqual(items, [{"name": "测试", "src": "/show/1"}])
        road = self.service.core("chapters.parse", rule, raw=raw, input="/show/1")[
            "roads"
        ][0]
        self.assertEqual(road["data"], ["https://example.com/play/1"])
        self.assertEqual(road["identifier"], ["第1集"])

    def test_reject_newer_rule_before_mutation(self):
        self.store.set("plugins", [])
        with self.assertRaises(ValueError):
            self.service.save_plugin(
                {"name": "new", "api": "99", "baseURL": "https://example.com"}
            )
        self.assertEqual(self.service.plugins(), [])

    def test_local_history_uses_stable_id(self):
        self.store.put("history", {"id": "1", "position": 10})
        self.store.put("history", {"id": "1", "position": 20})
        self.assertEqual(len(self.store.items("history")), 1)
        self.assertEqual(self.store.items("history")[0]["position"], 20)


if __name__ == "__main__":
    unittest.main()
