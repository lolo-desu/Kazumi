from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nativeapp.storage import Store
from nativeapp.downloads import Downloads


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required"
)
class DownloadTests(unittest.TestCase):
    def test_ffmpeg_output_is_playable_and_committed_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store("test", directory)
            source = Path(directory) / "source.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=160x90:rate=10",
                    "-t",
                    "1",
                    "-c:v",
                    "mpeg4",
                    str(source),
                ],
                check=True,
            )
            manager = Downloads(store)
            try:
                manager.start({"id": "1", "title": "fixture"}, "第1集", str(source))
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    record = store.items("downloads")[0]
                    if record["state"] in ("completed", "failed"):
                        break
                    time.sleep(0.05)
                self.assertEqual(record["state"], "completed", record)
                self.assertFalse(Path(record["path"]).with_suffix(".part.mkv").exists())
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=width",
                        "-of",
                        "csv=p=0",
                        record["path"],
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertEqual(result.stdout.strip(), "160")
            finally:
                manager.close()

    def test_interrupted_jobs_are_reported_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store("test", directory)
            store.put("downloads", {"id": "1", "state": "running"})
            manager = Downloads(store)
            try:
                self.assertEqual(store.items("downloads")[0]["state"], "interrupted")
            finally:
                manager.close()
