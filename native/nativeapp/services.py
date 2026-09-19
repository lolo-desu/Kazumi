import json
import os
from pathlib import Path
import shlex
import subprocess
import urllib.parse

APP = "Kazumi"
ROOT = Path(__file__).resolve().parents[2]
RULES = "https://raw.githubusercontent.com/Predidit/KazumiRules/main/"


class Service:
    def __init__(self, http, store):
        self.http, self.store = http, store
        self._vault = None

    @staticmethod
    def item(item):
        images = item.get("images") or {}
        rating = item.get("rating") or {}
        return {
            "id": str(item["id"]),
            "title": item.get("name_cn") or item.get("name", ""),
            "original_title": item.get("name", ""),
            "cover": images.get("large") or images.get("common") or "",
            "subtitle": f"{item.get('date', '')}   ★ {rating.get('score', item.get('score', '—'))}",
            "summary": item.get("summary", ""),
            "url": f"https://bgm.tv/subject/{item['id']}",
        }

    def browse(self, page=1):
        body = {"keyword": "", "sort": "rank", "filter": {"type": [2], "nsfw": False}}
        return [
            self.item(x)
            for x in self.http.json(
                "https://api.bgm.tv/v0/search/subjects",
                method="POST",
                query={"limit": 30, "offset": (page - 1) * 30},
                data=body,
            ).get("data", [])
        ]

    def search(self, query, page=1):
        return [
            self.item(x)
            for x in self.http.json(
                "https://api.bgm.tv/v0/search/subjects",
                method="POST",
                query={"limit": 30, "offset": (page - 1) * 30},
                data={"keyword": query, "sort": "match", "filter": {"type": [2]}},
            ).get("data", [])
        ]

    def calendar(self):
        groups = self.http.json("https://api.bgm.tv/calendar")
        return [
            (g["weekday"]["cn"], [self.item(x) for x in g["items"]]) for g in groups
        ]

    def detail(self, item):
        return self.item(
            self.http.json("https://api.bgm.tv/v0/subjects/" + str(item["id"]))
        )

    def related(self, item):
        return self.http.json(f"https://api.bgm.tv/v0/subjects/{item['id']}/characters")

    def plugins(self):
        value = self.store.get("plugins")
        if value is None:
            value = [
                json.loads(p.read_text())
                for p in sorted((ROOT / "assets/plugins").glob("*.json"))
            ]
            self.store.set("plugins", value)
        return value

    def save_plugin(self, plugin):
        if (
            not isinstance(plugin, dict)
            or not plugin.get("name")
            or not plugin.get("baseURL")
        ):
            raise ValueError("规则必须包含 name 和 baseURL")
        if int(plugin.get("api", 0)) > 8:
            raise ValueError("规则需要较新的客户端 API")
        self.core("search.prepare", plugin, input="test")
        rules = self.plugins()
        rules = [p for p in rules if p["name"] != plugin["name"]] + [plugin]
        self.store.set("plugins", rules)

    def catalog(self):
        return self.http.json(RULES + "index.json")

    def install_rule(self, name):
        rule = self.http.json(RULES + urllib.parse.quote(name, safe="") + ".json")
        self.save_plugin(rule)
        return rule

    def core(self, method, plugin, **params):
        binary = ROOT / "native/bin/kazumi-core"
        if not binary.exists():
            raise RuntimeError("规则核心尚未构建，请先运行 native/build-core")
        command = shlex.split(os.environ.get("NATIVE_CORE_RUNNER", "")) + [str(binary)]
        result = subprocess.run(
            command,
            input=json.dumps({"method": method, "plugin": plugin, **params}) + "\n",
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        response = json.loads(result.stdout)
        if "error" in response:
            raise ValueError(response["error"])
        return response["result"]

    def execute_rule(self, phase, plugin, value):
        request = self.core(phase + ".prepare", plugin, input=value)
        headers = {"Referer": plugin["baseURL"].rstrip("/") + "/"}
        headers.update(request["headers"])
        verified = self.store.get("verified_ua:" + plugin["name"])
        if verified and request["includeCookies"]:
            headers = {k: v for k, v in headers.items() if k.lower() != "user-agent"}
            headers["User-Agent"] = verified
        raw = self.http.request(
            request["url"],
            method=request["method"],
            query=request["query"],
            data=request["body"] if request["method"] == "POST" else None,
            headers=headers,
            json_body=request["bodyType"] == "json",
            cookies=request["includeCookies"],
        )
        return self.core(phase + ".parse", plugin, input=value, raw=raw)

    def sources(self, item):
        results = []
        disabled = self.store.get("disabled_rules", [])
        for rule in self.plugins():
            if rule["name"] in disabled:
                continue
            try:
                result = self.execute_rule(
                    "search", rule, item.get("original_title") or item["title"]
                )
                results.append(
                    {
                        "plugin": rule,
                        "items": result["items"],
                        "diagnostics": result["diagnostics"],
                    }
                )
            except Exception as error:
                results.append({"plugin": rule, "items": [], "error": str(error)})
        return results

    def chapters(self, rule, source):
        return self.execute_rule("chapters", rule, source)["roads"]

    @property
    def vault(self):
        if self._vault is None:
            from .credentials import Vault

            self._vault = Vault(APP, self.store.path)
        return self._vault

    def login(self, token):
        account = self.http.json(
            "https://api.bgm.tv/v0/me", headers={"Authorization": "Bearer " + token}
        )
        if not account.get("username"):
            raise ValueError("令牌未返回有效账号")
        self.vault.set("bangumi", token)
        self.store.set("bangumi_account", account)
        return account

    def logout(self):
        self.vault.remove("bangumi")
        self.store.set("bangumi_account", {})

    def authorized(self, path, **kwargs):
        token = self.vault.get("bangumi")
        if not token:
            raise ValueError("请先登录 Bangumi")
        return self.http.json(
            "https://api.bgm.tv" + path,
            headers={"Authorization": "Bearer " + token},
            **kwargs,
        )

    def set_collection(self, item, state):
        import time

        revision = time.time_ns()
        change = {"id": str(item["id"]), "state": state, "revision": revision}
        # Visible state and upload queue commit together.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR REPLACE INTO library VALUES(?, ?, ?, ?)",
                ("collect_changes", change["id"], json.dumps(change), time.time()),
            )
            if state == "移除收藏":
                db.execute(
                    "DELETE FROM library WHERE kind=? AND id=?",
                    ("collect", change["id"]),
                )
            else:
                value = {**item, "collection_type": state, "revision": revision}
                db.execute(
                    "INSERT OR REPLACE INTO library VALUES(?, ?, ?, ?)",
                    (
                        "collect",
                        change["id"],
                        json.dumps(value, ensure_ascii=False),
                        time.time(),
                    ),
                )

    def pull_collections(self):
        account = self.store.get("bangumi_account", {})
        if not account.get("username"):
            raise ValueError("请先登录 Bangumi")
        offset = 0
        updates = []
        kinds = {1: "想看", 2: "看过", 3: "在看", 4: "搁置", 5: "抛弃"}
        while True:
            data = self.authorized(
                "/v0/users/"
                + urllib.parse.quote(account["username"], safe="")
                + "/collections",
                query={"subject_type": 2, "limit": 100, "offset": offset},
            )
            entries = data.get("data", [])
            for entry in entries:
                item = self.item(entry["subject"])
                updates.append(
                    {**item, "collection_type": kinds.get(entry["type"], "想看")}
                )
            offset += len(entries)
            if not entries or offset >= data.get("total", offset):
                break
        import time

        applied = 0
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for item in updates:
                identifier = str(item["id"])
                pending = db.execute(
                    "SELECT 1 FROM library WHERE kind=? AND id=?",
                    ("collect_changes", identifier),
                ).fetchone()
                if not pending:
                    db.execute(
                        "INSERT OR REPLACE INTO library VALUES(?, ?, ?, ?)",
                        (
                            "collect",
                            identifier,
                            json.dumps(item, ensure_ascii=False),
                            time.time(),
                        ),
                    )
                    applied += 1

        return applied

    def push_collections(self):
        kinds = {"想看": 1, "看过": 2, "在看": 3, "搁置": 4, "抛弃": 5}
        count = 0
        for change in self.store.items("collect_changes"):
            path = "/v0/users/-/collections/" + str(int(change["id"]))
            if change["state"] == "移除收藏":
                self.authorized(path, method="DELETE")
            else:
                self.authorized(
                    path, method="POST", data={"type": kinds[change["state"]]}
                )
            # Do not clear a change made while this request was in flight.
            with self.store.connect() as db:
                row = db.execute(
                    "SELECT data FROM library WHERE kind=? AND id=?",
                    ("collect_changes", str(change["id"])),
                ).fetchone()
                if row and json.loads(row[0]).get("revision") == change["revision"]:
                    db.execute(
                        "DELETE FROM library WHERE kind=? AND id=?",
                        ("collect_changes", str(change["id"])),
                    )
            count += 1
        return count

    def import_hive(self, directory):
        from datetime import datetime
        import time

        snapshot = self.core("hive.export", {}, directory=str(directory))
        boxes = snapshot["boxes"]
        kinds = {1: "在看", 2: "想看", 3: "搁置", 4: "看过", 5: "抛弃"}
        mapped = []

        def timestamp(value):
            return datetime.fromisoformat(value).timestamp() if value else 0

        for row in boxes.get("collectibles", []):
            value = row["value"]
            mapped.append(
                (
                    "collect",
                    {
                        **self.item(value["subject"]),
                        "collection_type": kinds[value["type"]],
                    },
                    timestamp(value["time"]),
                )
            )
        for row in boxes.get("favorites", []):
            mapped.append(
                ("collect", {**self.item(row["value"]), "collection_type": "想看"}, 0)
            )
        for row in boxes.get("histories", []):
            value = row["value"]
            episode = value["lastWatchEpisode"]
            progress = value["progresses"].get(str(episode), {})
            item = {
                **self.item(value["subject"]),
                "episode": value["lastWatchEpisodeName"],
                "page_url": value["episodePageUrl"],
                "position": progress.get("progressMs", 0) / 1000,
                "legacy_history": value,
            }
            mapped.append(("history", item, timestamp(value["lastWatchTime"])))
        applied = 0
        with self.store.connect() as db:
            for kind, item, updated in mapped:
                row = db.execute(
                    "SELECT updated FROM library WHERE kind=? AND id=?",
                    (kind, str(item["id"])),
                ).fetchone()
                if row is None or row[0] < updated:
                    db.execute(
                        "INSERT OR REPLACE INTO library VALUES(?,?,?,?)",
                        (
                            kind,
                            str(item["id"]),
                            json.dumps(item, ensure_ascii=False),
                            updated,
                        ),
                    )
                    applied += 1
            # Keep all decoded rows, including every per-source progress and the
            # unmapped settings/download metadata. No credential fields are exported.
            for box, rows in boxes.items():
                for row in rows:
                    identifier = box + ":" + str(row["key"])
                    value = {"id": identifier, "box": box, **row}
                    db.execute(
                        "INSERT OR REPLACE INTO library VALUES(?,?,?,?)",
                        (
                            "legacy_hive",
                            identifier,
                            json.dumps(value, ensure_ascii=False),
                            time.time(),
                        ),
                    )
            db.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?)",
                ("legacy_hive_hashes", json.dumps(snapshot["sha256"])),
            )
        return {"mapped": applied, "preserved": sum(len(x) for x in boxes.values())}

    def dandan(self, path, query=None):
        import base64
        import hashlib
        import time

        identifier = os.environ.get("DANDANAPI_APPID", "")
        key = os.environ.get("DANDANAPI_KEY", "")
        if not identifier or not key:
            raise ValueError("当前构建没有弹弹Play应用授权；可使用本地弹幕导入")
        timestamp = int(time.time())
        signature = base64.b64encode(
            hashlib.sha256((identifier + str(timestamp) + path + key).encode()).digest()
        ).decode()
        result = self.http.json(
            "https://api.dandanplay.net" + path,
            query=query,
            headers={
                "X-AppId": identifier,
                "X-Timestamp": str(timestamp),
                "X-Signature": signature,
                "X-Auth": "1",
            },
        )
        if not result.get("success", True):
            raise ValueError(result.get("errorMessage", "弹幕查询失败"))
        return result

    def danmaku_episodes(self, item):
        result = self.dandan("/api/v2/bangumi/bgmtv/" + str(int(item["id"])))
        return [
            {"id": e["episodeId"], "title": e["episodeTitle"]}
            for e in result["bangumi"]["episodes"]
        ]

    def danmaku_comments(self, identifier):
        from .danmaku import parse_comments

        return parse_comments(
            json.dumps(
                self.dandan(
                    "/api/v2/comment/" + str(int(identifier)), {"withRelated": "true"}
                )
            )
        )
