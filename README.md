# ComfyUI 生图画廊 v2.0

手机优先的纯静态单页，原生 HTML / CSS / JavaScript，无框架、无 npm 依赖、无构建步骤。前端与同步脚本统一使用 v2 数据格式。

## 本地预览

在项目目录运行 `python -m http.server 8080 --bind 127.0.0.1`，打开 `http://127.0.0.1:8080/`。不要直接双击 HTML，`file://` 不能正常 fetch JSON。

手机 2 列，760px 起 3 列；支持人像 / 风景 / 电商图筛选、详情参数、正负提示词复制和真实 workflow JSON 下载。标题统一取 `title`，空值显示“未命名作品”。缺图、空数据、复制权限不足、下载失败均有提示，保留键盘焦点管理。

## 数据格式

`gallery.json` 是作品数组。每条记录包含：

```json
{
  "id": "20261014_001",
  "title": "ComfyUI_00001",
  "source_file": "ComfyUI_00001_.png",
  "image": "./images/20261014_001_ComfyUI_00001_.png",
  "workflow_file": "./workflows/20261014_001.json",
  "tags": ["人像"],
  "created_at": "2026-10-14 09:00:00",
  "model": "realisticVisionV60B1.safetensors",
  "positive": "masterpiece, portrait girl",
  "negative": "bad hands",
  "params": {
    "seed": 123456,
    "steps": 25,
    "cfg": 7.0,
    "sampler": "dpmpp_2m",
    "scheduler": "karras"
  }
}
```

图片路径允许 `./images/` 或原有 `./assets/`；工作流只允许 `./workflows/*.json`，不接受绝对路径、父目录跳转或外站链接。

原有三条示例保留原图片、ID 与实际生图参数（DreamShaper 8、512×640、seed 14001/14002/14003）。`workflows/001.json`、`002.json`、`003.json` 从它们 PNG 的真实 prompt 元数据提取，是 ComfyUI **API 节点格式**，不是伪造的空占位，也不是 UI 布局格式；可作为 API 请求的 prompt。同步到的 workflow 则原样保留图片嵌入的 JSON 格式。

自检记录 `sync_test` 是 64×80 的纯色测试 PNG，带模拟元数据，**不是模型生成作品**。

## 本地自动同步

唯一依赖 Pillow：

```powershell
python -m pip install -r requirements.txt
python sync_gallery.py
```

`config.json` 默认：

```json
{
  "comfyui_output_dir": "./raw_output",
  "auto_git_push": false
}
```

把 ComfyUI PNG 放入 `raw_output/`；之后可将配置改为真实路径，例如 `E:/ComfyUI_windows_portable/ComfyUI/output`。相对路径以脚本目录为基准，不受终端当前目录影响。

- 递归扫描 .png（大小写不限），以源目录内相对 `source_file` 去重；旧数据不覆盖，更新同名源文件也不会重新导入。
- 图片按“日期序号 + 原名”归档到 `images/`，防止重名覆盖；新记录按文件修改时间由新到旧放在列表最前面。
- 从 KSampler 上游追溯 CheckpointLoaderSimple / UNETLoader、正负 CLIPTextEncode 与采样参数；复杂连线无法解析时按前两个 CLIPTextEncode 文本兜底并打印警告。多个 KSampler 使用第一个。
- 缺少或损坏的元数据不编造：模型“未知模型”、文本空字符串、未知数值 null；workflow_file 为空时前端禁用下载。坏 PNG 跳过并报告，其他好图继续导入，有坏图时退出码 1。
- uint64 seed 超过 JavaScript 安全整数时保存为十进制字符串，避免前端舍入。
- gallery.json 原子替换、独占同步锁、失败时只清理本轮新文件；源图片不修改。进程异常退出若遗留锁，确认没有同步进程后删除 `.gallery-sync.lock` 再运行。
- 切换源目录时同名 source_file 仍视为已收录；改变根目录前请确认不会与已有来源重名。

## 可选 Git 推送

`python sync_gallery.py --push`，或将 `auto_git_push` 设为 true。默认只同步本地，不上传。

执行前须已配置 Git 用户身份、origin、main 的上游，以及可用授权。流程为 `git add .` → `git commit -m "auto sync gallery"` → `git push`；无改动时跳过 commit，仍尝试 push（方便重试上次网络失败）。

安全保护：存在任何已暂存内容，或 gallery.json / images/ / workflows/ 以外的未提交文件，自动推送会停止，保留改动，不擅自夹带提交。请先自行提交代码/配置，再运行同步推送。原始输入 raw_output/、密钥、模型、缓存在 .gitignore 中排除；归档图片与 workflow 会上传，运行 --push 前请确认允许公开。

```powershell
git status
git diff
git add gallery.json images workflows
git commit -m "添加新作品"
git push
```

commit 保存本地版本；push 才会上传到 GitHub。不要把账号密码或访问令牌写入项目。

## 自检

```powershell
python tests/create_test_png.py
python sync_gallery.py
python sync_gallery.py
python -m unittest discover -s tests -v
```

生成的测试 PNG 已存在时生成器拒绝覆盖；再次同步应新增 0 条。测试在独立临时目录进行，Git 推送测试只推到临时本地裸仓库，**不推送 GitHub**。

## GitHub Pages

v1 已上线：[查看画廊](https://luozhixiang081-crypto.github.io/comfyui-gallery/)。本轮 v2 改造与自检仅保存到本地并提交；推送 main 后才会更新线上页面。

仓库 Settings → Pages 使用 Deploy from a branch → main → /(root)。根目录的 .nojekyll 已存在，不需要额外构建。该仓库公开，只应放可公开图片、提示词和工作流。

参考：[GitHub Pages 发布源](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)、[Pillow PNG 元数据](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#png)。
