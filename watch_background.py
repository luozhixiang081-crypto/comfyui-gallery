"""Run the existing watcher without a console, with bounded local logs."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

import sync_gallery

ROOT = Path(__file__).resolve().parent


class LogStream:
    def __init__(self, logger):
        self.logger = logger
        self.pending = ""

    def write(self, text):
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.strip():
                self.logger.info(line.rstrip())
        return len(text)

    def flush(self):
        if self.pending.strip():
            self.logger.info(self.pending.rstrip())
        self.pending = ""


def main():
    parser = argparse.ArgumentParser(description="画廊后台监控启动器。")
    parser.add_argument("--git-dir", required=True, type=Path)
    arguments = parser.parse_args()
    log_directory = ROOT / ".local"
    log_directory.mkdir(exist_ok=True)
    logger = logging.getLogger("gallery-watch")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_directory / "watcher.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    stream = LogStream(logger)
    try:
        with redirect_stdout(stream), redirect_stderr(stream):
            if not (arguments.git_dir / "git.exe").is_file():
                raise ValueError(f"Git 不存在：{arguments.git_dir}；请重新运行安装脚本。")
            os.environ["PATH"] = str(arguments.git_dir) + os.pathsep + os.environ.get("PATH", "")
            os.environ.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never", GCM_GUI_PROMPT="false")
            os.chdir(ROOT)
            logger.info("[启动] PID=%s；监控并自动推送；目录=%s", os.getpid(), ROOT)
            return sync_gallery.watch(ROOT, push=True)
    except Exception:
        logger.exception("[异常退出] 等待 Windows 计划任务自动重启。")
        return 1
    finally:
        stream.flush()
        handler.close()
        logger.removeHandler(handler)


if __name__ == "__main__":
    sys.exit(main())
