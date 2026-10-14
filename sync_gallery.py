"""Incrementally archive ComfyUI PNGs; run from any working directory."""

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
SAFE_INTEGER = 2**53 - 1


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def metadata_json(value, field, source):
    if value is None:
        print(f"[警告] {source}：缺少 {field} 元数据。")
        return None
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict) or not parsed:
            raise ValueError("元数据不是非空 JSON 对象")
        json_text(parsed)
        return parsed
    except (ValueError, TypeError):
        print(f"[警告] {source}：{field} 元数据无效，保留可识别内容。")
        return None


def connections(value):
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int)) and type(value[1]) is int:
        yield str(value[0])


def upstream(graph, link):
    pending = list(connections(link))
    seen = set()
    while pending:
        node_id = pending.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        node = graph.get(node_id)
        if not isinstance(node, dict):
            continue
        yield node
        inputs = node.get("inputs", {})
        if isinstance(inputs, dict):
            for value in inputs.values():
                pending.extend(connections(value))


def inputs(node):
    value = node.get("inputs", {})
    return value if isinstance(value, dict) else {}


def text_from_nodes(nodes):
    for node in nodes:
        text = inputs(node).get("text")
        if node.get("class_type") == "CLIPTextEncode" and isinstance(text, str):
            return text
    return None


def model_from_nodes(nodes):
    for node in nodes:
        class_type = node.get("class_type")
        key = {"CheckpointLoaderSimple": "ckpt_name", "UNETLoader": "unet_name"}.get(class_type) if isinstance(class_type, str) else None
        name = inputs(node).get(key)
        if key and isinstance(name, str) and name:
            return name
    return None


def number(value, integer=False, minimum=0):
    if type(value) not in (int, float) or type(value) is float and not math.isfinite(value) or value < minimum:
        return None
    if integer:
        return int(value) if value == int(value) else None
    return value


def extract_parameters(graph, source):
    graph = graph or {}
    nodes = [node for node in graph.values() if isinstance(node, dict)]
    samplers = [node for node in nodes if node.get("class_type") == "KSampler"]
    sampler = inputs(samplers[0]) if samplers else {}
    if len(samplers) > 1:
        print(f"[警告] {source}：存在多个 KSampler，使用第一个。")
    if not samplers:
        print(f"[警告] {source}：未找到 KSampler，采样参数标记为未知。")
    fallback = [inputs(node).get("text") for node in nodes if node.get("class_type") == "CLIPTextEncode" and isinstance(inputs(node).get("text"), str)][:2]
    prompts = []
    for index, key in enumerate(("positive", "negative")):
        text = text_from_nodes(upstream(graph, sampler.get(key)))
        if text is None:
            text = fallback[index] if index < len(fallback) else ""
            if fallback:
                print(f"[警告] {source}：{key} 连线无法追溯，按前两个 CLIPTextEncode 文本兜底。")
        prompts.append(text)
    seed = number(sampler.get("seed"), integer=True)
    # ComfyUI accepts uint64 seeds; decimal strings avoid JavaScript rounding.
    if seed is not None and seed > SAFE_INTEGER:
        seed = str(seed)
    return {
        "model": model_from_nodes(upstream(graph, sampler.get("model"))) or model_from_nodes(nodes) or "未知模型",
        "positive": prompts[0],
        "negative": prompts[1],
        "params": {
            "seed": seed,
            "steps": number(sampler.get("steps"), integer=True, minimum=1),
            "cfg": number(sampler.get("cfg")),
            "sampler": sampler.get("sampler_name") if isinstance(sampler.get("sampler_name"), str) else "",
            "scheduler": sampler.get("scheduler") if isinstance(sampler.get("scheduler"), str) else "",
        },
    }


def auto_tags(positive):
    prompt = positive.lower()
    rules = [("人像", ("girl", "portrait", "boy")), ("电商图", ("product", "ecommerce", "bottle")), ("风景", ("landscape", "scenery"))]
    return [tag for tag, words in rules if any(word in prompt for word in words)] or ["待分类"]


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def atomic_gallery(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".sync-tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json_text(data))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@contextmanager
def sync_lock(root):
    lock = root / ".gallery-sync.lock"
    # OS locks are released even after a forced stop or Windows restart.
    if os.name == "nt":
        import msvcrt
        with lock.open("a+b") as handle:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError("已有同步进程正在写入；稍后重试。") from None
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise ValueError("已有同步进程或遗留锁；确认没有同步进程后再删除 .gallery-sync.lock。") from None
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def git(root, *arguments):
    return subprocess.run(["git", *arguments], cwd=root, check=True, text=True, encoding="utf-8", capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def check_push_scope(root):
    if Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve() != root.resolve():
        raise ValueError("--push 只允许在本项目根目录的 Git 仓库执行。")
    staged = git(root, "diff", "--cached", "--name-only").stdout.strip()
    changed = git(root, "diff", "--name-only", "-z").stdout.split("\0")
    changed += git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0")
    unrelated = [name for name in changed if name and name != "gallery.json" and not name.startswith(("images/", "workflows/"))]
    if staged or unrelated:
        raise ValueError("自动推送已停止：存在暂存内容或非同步文件改动，请先自行提交；没有添加或提交它们。")
    git(root, "var", "GIT_AUTHOR_IDENT")
    git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")


def push_gallery(root):
    check_push_scope(root)
    git(root, "add", ".")
    if git(root, "diff", "--cached", "--name-only").stdout.strip():
        result = git(root, "commit", "-m", "auto sync gallery")
        print(result.stdout.strip())
    else:
        print("[Git] 没有需要提交的新改动。")
    result = git(root, "push")
    print((result.stdout + result.stderr).strip())
    print("[Git] 推送成功。")


def configuration(root):
    config = read_json(root / "config.json")
    if not isinstance(config, dict) or not isinstance(config.get("comfyui_output_dir"), str) or not config["comfyui_output_dir"].strip() or type(config.get("auto_git_push")) is not bool:
        raise ValueError("config.json 需要非空 comfyui_output_dir 字符串和 auto_git_push 布尔值。")
    output = Path(config["comfyui_output_dir"])
    output = (output if output.is_absolute() else root / output).resolve()
    if not output.is_dir():
        raise ValueError(f"图片来源目录不存在：{output}")
    return config, output


def sync(root=ROOT, push=False, ready_sources=None, push_only_on_change=False):
    root = Path(root).resolve()
    config, output = configuration(root)
    push = push or config["auto_git_push"]
    with sync_lock(root):
        if push:
            check_push_scope(root)
        gallery_path = root / "gallery.json"
        old = read_json(gallery_path)
        if not isinstance(old, list) or not all(isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"] for item in old):
            raise ValueError("gallery.json 必须是含唯一字符串 id 的作品数组；未修改旧文件。")
        ids = {item["id"] for item in old}
        if len(ids) != len(old):
            raise ValueError("gallery.json 存在重复 id；未修改旧文件。")
        known = {item.get("source_file", "").replace("\\", "/") for item in old if isinstance(item.get("source_file", ""), str)}
        images, workflows = root / "images", root / "workflows"
        for directory in (images, workflows):
            directory.mkdir(exist_ok=True)
            if directory.resolve().parent != root:
                raise ValueError("归档目录不可指向项目外部。")
        files = sorted((path for path in output.rglob("*") if path.is_file() and path.suffix.lower() == ".png"), key=lambda path: (path.stat().st_mtime_ns, path.as_posix()))
        new, created = [], []
        skipped, failed = 0, 0
        print(f"[扫描] {output}：{len(files)} 张 PNG。")
        try:
            for path in files:
                source = path.relative_to(output).as_posix()
                if source in known:
                    skipped += 1
                    continue
                if ready_sources is not None and source not in ready_sources:
                    continue
                if not path.resolve().is_relative_to(output) or path.resolve().is_relative_to(images.resolve()):
                    failed += 1
                    print(f"[跳过] {source}：符号链接越界或归档目录回环。")
                    continue
                try:
                    with Image.open(path) as image:
                        if image.format != "PNG":
                            raise ValueError("文件不是 PNG")
                        graph = metadata_json(image.info.get("prompt"), "prompt", source)
                        workflow = metadata_json(image.info.get("workflow"), "workflow", source)
                        image.verify()
                except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as error:
                    failed += 1
                    print(f"[跳过] {source}：图片读取失败（{error}）。")
                    continue
                day = datetime.now().strftime("%Y%m%d")
                serial = len(ids) + 1
                name = re.sub(r"[^\w. -]", "_", path.stem).strip(". ") or "ComfyUI"
                # Always prefix IDs to avoid name collisions and Windows reserved names.
                while True:
                    item_id = f"{day}_{serial:03d}"
                    image_path = images / f"{item_id}_{name}.png"
                    if item_id not in ids and not (workflows / f"{item_id}.json").exists() and not image_path.exists():
                        break
                    serial += 1
                record = {"id": item_id, "title": path.stem, "source_file": source, "image": "./" + image_path.relative_to(root).as_posix(), "workflow_file": "", "created_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"), **extract_parameters(graph, source)}
                record["tags"] = auto_tags(record["positive"])
                with image_path.open("xb") as target:
                    created.append(image_path)
                    with path.open("rb") as original:
                        shutil.copyfileobj(original, target)
                if workflow:
                    workflow_path = workflows / f"{item_id}.json"
                    with workflow_path.open("x", encoding="utf-8") as target:
                        created.append(workflow_path)
                        target.write(json_text(workflow))
                    record["workflow_file"] = "./" + workflow_path.relative_to(root).as_posix()
                new.insert(0, record)
                ids.add(item_id)
                known.add(source)
                print(f"[新增] {source} → {item_id}；标签：{' / '.join(record['tags'])}。")
            if new:
                atomic_gallery(gallery_path, new + old)
        except Exception:
            # Only roll back files created by this run; never touch existing assets.
            for path in reversed(created):
                path.unlink(missing_ok=True)
            raise
        print(f"[完成] 新增 {len(new)}，已收录跳过 {skipped}，失败 {failed}；共 {len(old) + len(new)} 条记录。")
        pending_push = push and push_only_on_change and (
            git(root, "status", "--porcelain", "--", "gallery.json", "images/", "workflows/").stdout.strip() or
            int(git(root, "rev-list", "--count", "@{u}..HEAD").stdout.strip()) > 0
        )
        if push and (new or not push_only_on_change or pending_push):
            push_gallery(root)
        return len(new), failed


def watch(root=ROOT, push=False):
    root = Path(root).resolve()
    previous = {}
    print("[监控] 每 10 秒轮询；新 PNG 连续两次大小/修改时间不变后导入，Ctrl+C 停止。")
    try:
        while True:
            try:
                _, output = configuration(root)
                current = {}
                for path in output.rglob("*"):
                    if path.is_file() and path.suffix.lower() == ".png":
                        stat = path.stat()
                        current[path.relative_to(output).as_posix()] = (stat.st_size, stat.st_mtime_ns)
                ready = {name for name, signature in current.items() if previous.get(name) == signature}
                sync(root, push=push, ready_sources=ready, push_only_on_change=True)
                previous = current
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
                print(f"[监控警告] {detail}；10 秒后重试。", file=sys.stderr)
            time.sleep(10)
    except KeyboardInterrupt:
        print("[监控] 已停止。")
        return 0


def main():
    parser = argparse.ArgumentParser(description="增量同步 ComfyUI PNG 到静态画廊。")
    parser.add_argument("--push", action="store_true", help="同步后提交并推送（仓库不得有非同步改动）。")
    parser.add_argument("--watch", action="store_true", help="每 10 秒监控 PNG；可与 --push 一起使用。")
    arguments = parser.parse_args()
    try:
        if arguments.watch:
            return watch(push=arguments.push)
        _, failed = sync(push=arguments.push)
        return 1 if failed else 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(f"[错误] {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
