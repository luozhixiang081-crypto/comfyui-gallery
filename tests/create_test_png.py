"""Create a clearly marked synthetic metadata fixture, not generated artwork."""

import json
from pathlib import Path
import sys

from PIL import Image
from PIL.PngImagePlugin import PngInfo

ROOT = Path(__file__).resolve().parents[1]


def create_test_png(destination):
    graph = json.loads((ROOT / "workflows" / "001.json").read_text(encoding="utf-8"))
    graph["4"]["inputs"]["ckpt_name"] = "mock-test-model.safetensors"
    graph["6"]["inputs"]["text"] = "metadata sync test, portrait girl, product bottle, landscape scenery"
    graph["7"]["inputs"]["text"] = "test negative, blurry, bad hands"
    graph["3"]["inputs"].update(seed=123456, steps=25, cfg=7.0, sampler_name="dpmpp_2m", scheduler="karras")
    graph["5"]["inputs"].update(width=64, height=80)
    info = PngInfo()
    info.add_text("prompt", json.dumps(graph))
    info.add_text("workflow", json.dumps(graph))
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"测试文件已存在，未覆盖：{destination}")
    Image.new("RGB", (64, 80), (51, 40, 76)).save(destination, pnginfo=info)
    return graph


if __name__ == "__main__":
    target = ROOT / "raw_output" / "sync_test.png"
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    create_test_png(target)
    print(f"[测试 PNG] 已生成 {target}（含模拟 prompt 和 workflow，非真实生图作品）。")
