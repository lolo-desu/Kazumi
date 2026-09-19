from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request

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

    def test_proxy_setting_is_applied_without_replacing_cookie_jar(self):
        http = Http(self.store)
        self.store.set("proxy", "http://127.0.0.1:7890")
        http.set_proxy(self.store.get("proxy"))
        self.assertTrue(
            any(
                isinstance(handler, urllib.request.ProxyHandler)
                for handler in http.opener.handlers
            )
        )
        self.assertIsInstance(
            next(
                handler
                for handler in http.opener.handlers
                if isinstance(handler, urllib.request.HTTPCookieProcessor)
            ),
            urllib.request.HTTPCookieProcessor,
        )
        http.set_proxy("")
        self.assertFalse(
            any(
                isinstance(handler, urllib.request.ProxyHandler)
                for handler in http.opener.handlers
            )
        )

    def test_local_history_uses_stable_id(self):
        self.store.put("history", {"id": "1", "position": 10})
        self.store.put("history", {"id": "1", "position": 20})
        self.assertEqual(len(self.store.items("history")), 1)
        self.assertEqual(self.store.items("history")[0]["position"], 20)


if __name__ == "__main__":
    unittest.main()


class AccountAndMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store("test", self.temp.name)
        self.service = Service(None, self.store)

    def test_login_uses_keyring_not_profile(self):
        class Vault:
            def set(self, key, value):
                self.saved = (key, value)

        class Http:
            def json(inner, url, headers):
                self.assertEqual(headers["Authorization"], "Bearer private-token")
                return {"username": "test-user", "nickname": "测试"}

        vault = Vault()
        self.service._vault = vault
        self.service.http = Http()
        self.service.login("private-token")
        self.assertEqual(vault.saved, ("bangumi", "private-token"))
        self.assertNotIn("private-token", str(self.store.export_data()))

    def test_upload_keeps_change_made_during_request(self):
        item = {"id": "42", "title": "test"}
        self.service.set_collection(item, "想看")

        def authorized(path, **kwargs):
            self.assertEqual(kwargs["method"], "POST")
            self.assertEqual(kwargs["data"]["type"], 1)
            self.service.set_collection(item, "在看")

        self.service.authorized = authorized
        self.assertEqual(self.service.push_collections(), 1)
        self.assertEqual(self.store.items("collect_changes")[0]["state"], "在看")

    def test_pull_keeps_local_pending_changes(self):
        self.store.set("bangumi_account", {"username": "test"})
        self.service.set_collection({"id": "42", "title": "local"}, "在看")
        self.service.authorized = lambda *a, **k: {
            "total": 1,
            "data": [{"subject": {"id": 42, "name": "remote"}, "type": 2}],
        }
        self.assertEqual(self.service.pull_collections(), 0)
        self.assertEqual(self.store.items("collect")[0]["collection_type"], "在看")

    def test_hive_import_preserves_all_progress_and_newer_local_records(self):
        self.store.put("history", {"id": "42", "title": "new", "position": 123})
        history = {
            "subject": {"id": 42, "name": "old"},
            "lastWatchEpisode": 2,
            "lastWatchEpisodeName": "第2集",
            "episodePageUrl": "https://example.com/2",
            "lastWatchTime": "2025-01-01T00:00:00",
            "progresses": {"1": {"progressMs": 1000}, "2": {"progressMs": 90000}},
        }
        self.service.core = lambda *a, **k: {
            "boxes": {"histories": [{"key": "rule42", "value": history}]},
            "sha256": {"histories": "fixture"},
        }
        result = self.service.import_hive("/unused")
        self.assertEqual(result["mapped"], 0)
        self.assertEqual(self.store.items("history")[0]["position"], 123)
        self.assertEqual(
            self.store.items("legacy_hive")[0]["value"]["progresses"]["1"][
                "progressMs"
            ],
            1000,
        )
