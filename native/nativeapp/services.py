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
