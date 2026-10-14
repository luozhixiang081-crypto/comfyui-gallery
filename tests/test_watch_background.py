import io
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import watch_background as background


class BackgroundTests(unittest.TestCase):
    def test_line_buffering_and_flush(self):
        output = io.StringIO()
        logger = logging.Logger("test")
        logger.addHandler(logging.StreamHandler(output))
        stream = background.LogStream(logger)
        self.assertEqual(stream.write("扫描"), 2)
        stream.write("完成\n\n尾行")
        self.assertEqual(output.getvalue(), "扫描完成\n")
        stream.flush()
        self.assertEqual(output.getvalue(), "扫描完成\n尾行\n")

    def test_log_rotation_keeps_bounded_backups(self):
        with tempfile.TemporaryDirectory(dir="E:/downloads") as directory:
            log = Path(directory) / "watcher.log"
            handler = RotatingFileHandler(log, maxBytes=80, backupCount=3, encoding="utf-8")
            logger = logging.Logger("test-rotation")
            logger.addHandler(handler)
            try:
                for _ in range(100):
                    logger.info("测试轮转日志 %s", "x" * 20)
            finally:
                handler.close()
            self.assertEqual(len(list(Path(directory).glob("watcher.log*"))), 4)

    def test_missing_git_fails_with_log_without_starting_watcher(self):
        with tempfile.TemporaryDirectory(dir="E:/downloads") as directory:
            with patch.object(background, "ROOT", Path(directory)), patch.object(sys, "argv", ["watch_background.py", "--git-dir", directory]), patch.object(background.sync_gallery, "watch") as watching:
                self.assertEqual(background.main(), 1)
                watching.assert_not_called()
            self.assertIn("Git 不存在", (Path(directory) / ".local/watcher.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
