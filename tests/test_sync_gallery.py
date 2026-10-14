from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_gallery as sync


def graph_fixture():
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "test.safetensors"}},
        "negative": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad hands"}},
        "positive": {"class_type": "CLIPTextEncode", "inputs": {"text": "portrait girl product bottle landscape"}},
        "bridge": {"class_type": "ConditioningSetArea", "inputs": {"conditioning": ["positive", 0]}},
        "sampler": {"class_type": "KSampler", "inputs": {"positive": ["bridge", 0], "negative": ["negative", 0], "model": ["4", 0], "seed": 123456, "steps": 25, "cfg": 7.0, "sampler_name": "dpmpp_2m", "scheduler": "karras"}},
    }


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gallery-test-", dir="E:/downloads" if Path("E:/downloads").is_dir() else None)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "raw_output").mkdir()
        self.write("config.json", {"comfyui_output_dir": "./raw_output", "auto_git_push": False})
        self.old = [{"id": "existing", "source_file": "old.png", "title": "Do not change", "custom": {"kept": True}}]
        self.write("gallery.json", self.old)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding="utf-8")

    def png(self, name="new.png", prompt=None, workflow=True):
        destination = self.root / "raw_output" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        info = PngInfo()
        info.add_text("prompt", json.dumps(graph_fixture() if prompt is None else prompt))
        if workflow:
            info.add_text("workflow", json.dumps({"nodes": [], "test": True}))
        Image.new("RGB", (8, 8)).save(destination, pnginfo=info)
        return destination

    def records(self):
        return sync.read_json(self.root / "gallery.json")

    def test_connected_prompts_and_parameters(self):
        result = sync.extract_parameters(graph_fixture(), "test")
        self.assertEqual(result["positive"], "portrait girl product bottle landscape")
        self.assertEqual(result["negative"], "bad hands")
        self.assertEqual(result["model"], "test.safetensors")
        self.assertEqual(result["params"], {"seed": 123456, "steps": 25, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras"})
        self.assertEqual(sync.auto_tags(result["positive"]), ["人像", "电商图", "风景"])
        self.assertEqual(sync.auto_tags("abstract"), ["待分类"])

    def test_unet_cycle_fallback_and_large_seed(self):
        graph = graph_fixture()
        graph["4"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}}
        graph["bridge"]["inputs"]["conditioning"] = ["bridge", 0]
        graph["sampler"]["inputs"]["seed"] = 2**64 - 1
        result = sync.extract_parameters(graph, "test")
        self.assertEqual(result["model"], "flux.safetensors")
        self.assertEqual(result["positive"], "bad hands")
        self.assertEqual(result["params"]["seed"], str(2**64 - 1))
        self.assertEqual(sync.extract_parameters({"bad": {"class_type": []}}, "test")["model"], "未知模型")

    def test_incremental_preserves_old_and_bytes(self):
        original = self.png()
        self.assertEqual(sync.sync(self.root), (1, 0))
        records = self.records()
        self.assertEqual(records[-1], self.old[0])
        item = records[0]
        self.assertEqual(item["title"], "new")
        self.assertEqual(item["source_file"], "new.png")
        self.assertEqual((self.root / item["image"]).read_bytes(), original.read_bytes())
        self.assertEqual(sync.read_json(self.root / item["workflow_file"]), {"nodes": [], "test": True})
        before = (self.root / "gallery.json").read_bytes()
        self.assertEqual(sync.sync(self.root), (0, 0))
        self.assertEqual((self.root / "gallery.json").read_bytes(), before)

    def test_nested_duplicate_names_and_id_collision(self):
        today = datetime.now().strftime("%Y%m%d")
        self.old[0]["id"] = today + "_001"
        self.write("gallery.json", self.old)
        (self.root / "workflows").mkdir()
        self.write(f"workflows/{today}_002.json", {"keep": True})
        self.png("a/same.PNG")
        self.png("b/same.png")
        self.assertEqual(sync.sync(self.root), (2, 0))
        items = self.records()[:2]
        self.assertEqual(len({item["id"] for item in items}), 2)
        self.assertEqual({item["source_file"] for item in items}, {"a/same.PNG", "b/same.png"})
        self.assertEqual(len(list((self.root / "images").glob("*.png"))), 2)
        self.assertEqual(sync.read_json(self.root / f"workflows/{today}_002.json"), {"keep": True})

    def test_missing_metadata_and_corrupt_png(self):
        self.png(prompt="invalid graph", workflow=False)
        (self.root / "raw_output" / "broken.png").write_bytes(b"not PNG")
        self.assertEqual(sync.sync(self.root), (1, 1))
        item = self.records()[0]
        self.assertEqual(item["workflow_file"], "")
        self.assertEqual(item["tags"], ["待分类"])
        self.assertIsNone(item["params"]["seed"])

    def test_bad_gallery_and_atomic_rollback(self):
        self.png()
        original = (self.root / "gallery.json").read_bytes()
        with patch.object(sync.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                sync.sync(self.root)
        self.assertEqual((self.root / "gallery.json").read_bytes(), original)
        self.assertFalse(list((self.root / "images").glob("*")))
        self.assertFalse(list((self.root / "workflows").glob("*")))
        self.assertFalse((self.root / ".gallery-sync.lock").exists())
        (self.root / "gallery.json").write_text("invalid", encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.sync(self.root)
        self.assertEqual((self.root / "gallery.json").read_text(), "invalid")

    def test_lock_blocks_second_writer(self):
        (self.root / ".gallery-sync.lock").write_text("running")
        with self.assertRaises(ValueError):
            sync.sync(self.root)
        self.assertEqual((self.root / ".gallery-sync.lock").read_text(), "running")

    def prepare_git(self):
        # Identity is fixture-only, never applied to the user's repository.
        sync.git(self.root, "init", "-b", "main")
        sync.git(self.root, "config", "user.name", "Fixture Test")
        sync.git(self.root, "config", "user.email", "fixture@example.invalid")
        sync.git(self.root, "config", "commit.gpgsign", "false")
        (self.root / ".gitignore").write_text("raw_output/\n.gallery-sync.lock\n", encoding="utf-8")
        sync.git(self.root, "add", ".")
        sync.git(self.root, "commit", "-m", "fixture")
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        with (self.root / ".gitignore").open("a", encoding="utf-8") as handle:
            handle.write("remote.git/\n")
        sync.git(self.root, "add", ".gitignore")
        sync.git(self.root, "commit", "-m", "ignore local remote")
        sync.git(self.root, "remote", "add", "origin", str(remote))
        sync.git(self.root, "push", "-u", "origin", "main")

    def test_push_to_local_bare_repository(self):
        self.prepare_git()
        self.png()
        self.assertEqual(sync.sync(self.root, push=True), (1, 0))
        self.assertEqual(sync.git(self.root, "log", "-1", "--format=%s").stdout.strip(), "auto sync gallery")
        self.assertEqual(sync.git(self.root, "rev-parse", "HEAD").stdout, sync.git(self.root, "rev-parse", "origin/main").stdout)
        self.assertFalse(sync.git(self.root, "ls-files", "raw_output").stdout)
        self.assertEqual(sync.sync(self.root, push=True), (0, 0))

    def test_config_auto_push(self):
        self.write("config.json", {"comfyui_output_dir": "./raw_output", "auto_git_push": True})
        self.prepare_git()
        self.png()
        self.assertEqual(sync.sync(self.root), (1, 0))
        self.assertEqual(sync.git(self.root, "rev-parse", "HEAD").stdout, sync.git(self.root, "rev-parse", "origin/main").stdout)

    def test_push_cli_from_another_directory(self):
        script = self.root / "sync_gallery.py"
        script.write_bytes(Path(sync.__file__).read_bytes())
        self.prepare_git()
        self.png()
        result = subprocess.run([sys.executable, str(script), "--push"], cwd=self.root.parent, capture_output=True, text=True, encoding="utf-8", env={**sync.os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(sync.git(self.root, "log", "-1", "--format=%s").stdout.strip(), "auto sync gallery")
        self.assertEqual(sync.git(self.root, "rev-parse", "HEAD").stdout, sync.git(self.root, "rev-parse", "origin/main").stdout)

    def test_push_rejects_unrelated_or_staged_changes(self):
        self.prepare_git()
        self.png()
        (self.root / "unrelated.txt").write_text("keep")
        with self.assertRaises(ValueError):
            sync.sync(self.root, push=True)
        self.assertEqual(self.records(), self.old)
        self.assertFalse(sync.git(self.root, "diff", "--cached", "--name-only").stdout)
        sync.git(self.root, "add", "unrelated.txt")
        with self.assertRaises(ValueError):
            sync.sync(self.root, push=True)
        self.assertIn("unrelated.txt", sync.git(self.root, "diff", "--cached", "--name-only").stdout)

    def test_watch_stable_files_and_push_only_on_changes(self):
        self.prepare_git()
        self.png()
        sleeps = 0

        def tick(seconds):
            nonlocal sleeps
            self.assertEqual(seconds, 10)
            sleeps += 1
            if sleeps == 1:
                self.assertEqual(len(self.records()), 1)
            elif sleeps == 2:
                self.assertEqual(len(self.records()), 2)
                self.png("next.png")
            elif sleeps == 3:
                self.assertEqual(len(self.records()), 2)
            else:
                self.assertEqual(len(self.records()), 3)
                raise KeyboardInterrupt

        with patch.object(sync.time, "sleep", side_effect=tick), patch.object(sync, "push_gallery", wraps=sync.push_gallery) as pushing:
            self.assertEqual(sync.watch(self.root, push=True), 0)
            self.assertEqual(pushing.call_count, 2)
        self.assertEqual(sync.git(self.root, "rev-parse", "HEAD").stdout, sync.git(self.root, "rev-parse", "origin/main").stdout)

    def test_watch_defers_changing_png(self):
        self.png()
        sleeps = 0

        def tick(seconds):
            nonlocal sleeps
            self.assertEqual(seconds, 10)
            sleeps += 1
            if sleeps == 1:
                graph = graph_fixture()
                graph["positive"]["inputs"]["text"] += " still writing another portion of metadata"
                self.png(prompt=graph)
            if sleeps < 3:
                self.assertEqual(len(self.records()), 1)
            else:
                self.assertEqual(len(self.records()), 2)
                raise KeyboardInterrupt

        with patch.object(sync.time, "sleep", side_effect=tick):
            self.assertEqual(sync.watch(self.root), 0)

    def test_watch_recovers_from_transient_error(self):
        with patch.object(sync, "sync", side_effect=[ValueError("temporary error"), (0, 0)]) as synchronizing, patch.object(sync.time, "sleep", side_effect=[None, KeyboardInterrupt]):
            self.assertEqual(sync.watch(self.root), 0)
            self.assertEqual(synchronizing.call_count, 2)

    def test_watch_retries_failed_push_without_duplicate_commit(self):
        self.prepare_git()
        self.png()
        original_git = sync.git
        pushes = 0

        def offline_once(root, *arguments):
            nonlocal pushes
            if arguments == ("push",):
                pushes += 1
                if pushes == 1:
                    raise subprocess.CalledProcessError(1, ["git", "push"], stderr="simulated offline")
            return original_git(root, *arguments)

        with patch.object(sync, "git", side_effect=offline_once), patch.object(sync.time, "sleep", side_effect=[None, None, KeyboardInterrupt]):
            self.assertEqual(sync.watch(self.root, push=True), 0)
        self.assertEqual(pushes, 2)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(sync.git(self.root, "log", "--format=%s").stdout.splitlines().count("auto sync gallery"), 1)
        self.assertEqual(sync.git(self.root, "rev-parse", "HEAD").stdout, sync.git(self.root, "rev-parse", "origin/main").stdout)


if __name__ == "__main__":
    unittest.main()
