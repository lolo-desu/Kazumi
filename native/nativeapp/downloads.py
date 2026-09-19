"""Download media with FFmpeg's demuxers into an atomic local MKV output."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import shutil
import subprocess
import threading


class Downloads:
    def __init__(self, store):
        self.store = store
        self.worker = ThreadPoolExecutor(max_workers=2, thread_name_prefix="download")
        self.cancelled = set()
        self.processes = {}
        self.lock = threading.Lock()
        for item in store.items("downloads"):
            if item.get("state") in ("queued", "running"):
                item["state"] = "interrupted"
                store.put("downloads", item)

    def start(self, item, name, url, headers=None, audio=None):
        if not shutil.which("ffmpeg"):
            raise RuntimeError("缺少 FFmpeg，无法下载")
        identifier = hashlib.sha256(
            (str(item["id"]) + "\0" + name).encode()
        ).hexdigest()
        with self.lock:
            if identifier in self.processes:
                raise ValueError("该集已经在下载队列中")
            self.processes[identifier] = None
            self.cancelled.discard(identifier)
        directory = self.store.path / "downloads"
        directory.mkdir(exist_ok=True)
        record = {
            "id": identifier,
            "title": item["title"],
            "episode": name,
            "state": "queued",
            "path": str(directory / (identifier + ".mkv")),
            "source_item": item,
        }
        self.store.put("downloads", record)
        self.worker.submit(self.run, record, url, headers or {}, audio)

    def run(self, record, url, headers, audio):
        identifier = record["id"]
        temporary = Path(record["path"]).with_suffix(".part.mkv")
        try:
            if identifier in self.cancelled:
                return
            args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
            # Each input owns its headers. Arguments are passed without a shell.
            header = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            for source in [url] + ([audio] if audio else []):
                if header and source.startswith(("http://", "https://")):
                    args += ["-headers", header]
                args += ["-i", source]
            if audio:
                args += ["-map", "0:v:0", "-map", "1:a:0"]
            args += ["-c", "copy", str(temporary)]
            with subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            ) as process:
                with self.lock:
                    self.processes[identifier] = process
                if identifier in self.cancelled:
                    process.terminate()
                record["state"] = "running"
                self.store.put("downloads", record)
                _, error = process.communicate()
                if identifier in self.cancelled:
                    record["state"] = "cancelled"
                elif process.returncode:
                    record["state"] = "failed"
                    record["error"] = error.decode(errors="replace")[-1000:]
                else:
                    temporary.replace(record["path"])
                    record["state"] = "completed"
        except Exception as error:
            record["state"] = "failed"
            record["error"] = str(error)
        finally:
            with self.lock:
                if identifier in self.cancelled:
                    record["state"] = "cancelled"
                self.processes.pop(identifier, None)
            self.store.put("downloads", record)
            if temporary.exists():
                temporary.unlink()

    def cancel(self, identifier):
        with self.lock:
            self.cancelled.add(identifier)
            process = self.processes.get(identifier)
            if process and process.poll() is None:
                process.terminate()

    def close(self):
        for identifier in list(self.processes):
            self.cancel(identifier)
        self.worker.shutdown(wait=False)
