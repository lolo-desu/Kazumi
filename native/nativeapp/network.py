from contextlib import nullcontext
import gzip
import hashlib
import http.cookiejar
import json
import threading
import urllib.parse
import urllib.request


class Http:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.cookies = http.cookiejar.MozillaCookieJar(str(store.path / "cookies.txt"))
        if (store.path / "cookies.txt").exists():
            self.cookies.load(ignore_discard=True)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(
        self,
        url,
        *,
        method="GET",
        data=None,
        headers=None,
        query=None,
        json_body=True,
        cookies=True,
        raw=False,
    ):
        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("仅支持 HTTP/HTTPS 网络请求")
        if query:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
        h = {
            "User-Agent": "lolo-desu/GNOME-native (https://github.com/lolo-desu/Kazumi)",
            "Accept-Encoding": "gzip",
        }
        h.update(headers or {})
        body = None
        if data is not None:
            body = (
                json.dumps(data).encode()
                if json_body
                else urllib.parse.urlencode(data).encode()
            )
            h.setdefault(
                "Content-Type",
                "application/json"
                if json_body
                else "application/x-www-form-urlencoded",
            )
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        # CookieJar writes and its disk snapshot are serialized across workers.
        with self.lock if cookies else nullcontext():
            opener = self.opener if cookies else urllib.request.build_opener()
            with opener.open(req, timeout=25) as response:
                content = response.read(32 * 1024 * 1024 + 1)
                if len(content) > 32 * 1024 * 1024:
                    raise ValueError("响应过大")
                if response.headers.get("Content-Encoding") == "gzip":
                    content = gzip.decompress(content)
                encoding = response.headers.get_content_charset() or "utf-8"
            if cookies:
                self.cookies.save(ignore_discard=True)
                (self.store.path / "cookies.txt").chmod(0o600)
        return content if raw else content.decode(encoding, errors="replace")

    def json(self, url, **kwargs):
        value = self.request(url, **kwargs)
        return json.loads(value) if value.strip() else None

    def image(self, url):
        if url.startswith("//"):
            url = "https:" + url
        path = self.store.path / "images" / hashlib.sha256(url.encode()).hexdigest()
        if not path.exists():
            data = self.request(url, raw=True, cookies=False)
            path.parent.mkdir(exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return str(path)
