# ComfyUI 生图画廊 v2.1

手机优先的纯静态单页，原生 HTML / CSS / JavaScript，无框架、无 npm 依赖、无构建步骤。前端与同步脚本统一使用 v2 数据格式。

## 本地预览

在项目目录运行 `python -m http.server 8080 --bind 127.0.0.1`，打开 `http://127.0.0.1:8080/`。不要直接双击 HTML，`file://` 不能正常 fetch JSON。

手机 2 列，760px 起 3 列；支持人像 / 风景 / 电商图筛选、实时关键词搜索、详情参数、正负提示词复制和真实 workflow JSON 下载。搜索标题、正反提示词与模型名，不区分大小写、忽略关键词首尾空白，并与当前标签取交集。标题统一取 `title`，空值显示“未命名作品”。缺图、空数据、复制权限不足、下载失败均有提示，保留键盘焦点管理。

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

v2.0 的模拟 `sync_test` 记录及对应归档图片、工作流、raw_output 测试源已在 v2.1 清理。原示例的 source_file 已通过原图 SHA-256 核验后修正为真实来源名，接入真实 output 不再重复收录三张示例。

## 本地自动同步

唯一依赖 Pillow：

```powershell
python -m pip install -r requirements.txt
python sync_gallery.py
```

本机已定位真实目录，`config.json` 当前为：

```json
{
  "comfyui_output_dir": "E:/ComfyUI_windows_portable/ComfyUI/output",
  "auto_git_push": false
}
```

真实目录有 6 张 PNG，本轮新增 3 条、已收录跳过 3 条，画廊共 6 条。新增图片没有 workflow 元数据，因此不编造工作流；StarOcean_2077_Benchmark.png 连 prompt 元数据也没有，对应参数显示未知。

需要离线试验时，可改为 `./raw_output` 并把自己的 PNG 放入该目录。相对路径以脚本目录为基准，不受终端当前目录影响。

- 递归扫描 .png（大小写不限），以源目录内相对 `source_file` 去重；旧数据不覆盖，更新同名源文件也不会重新导入。
- 图片按“日期序号 + 原名”归档到 `images/`，防止重名覆盖；新记录按文件修改时间由新到旧放在列表最前面。
- 从 KSampler 上游追溯 CheckpointLoaderSimple / UNETLoader、正负 CLIPTextEncode 与采样参数；复杂连线无法解析时按前两个 CLIPTextEncode 文本兜底并打印警告。多个 KSampler 使用第一个。
- 缺少或损坏的元数据不编造：模型“未知模型”、文本空字符串、未知数值 null；workflow_file 为空时前端禁用下载。坏 PNG 跳过并报告，其他好图继续导入，有坏图时退出码 1。
- uint64 seed 超过 JavaScript 安全整数时保存为十进制字符串，避免前端舍入。
- gallery.json 原子替换、独占同步锁、失败时只清理本轮新文件；源图片不修改。Windows 使用系统文件锁，强制停止或重启后自动释放；`.gallery-sync.lock` 空闲时保留，不要手动删除正在使用的锁文件。非 Windows 平台若异常遗留锁，确认没有同步进程后再删除。
- 切换源目录时同名 source_file 仍视为已收录；改变根目录前请确认不会与已有来源重名。

## 实时监控（10 秒轮询）

```powershell
python sync_gallery.py --watch
python sync_gallery.py --watch --push
```

前者只归档到本地，后者遇到新图会归档、提交并推送；config 的 auto_git_push=true 也会开启推送。使用标准库 time.sleep(10)，没有新增依赖。PNG 连续两次轮询的文件大小与修改时间相同后才导入，避免同步尚未写完的图（首次监控约 10 秒后导入，写入中会继续等待）。

空闲时不执行 git push；网络推送失败会保留本地归档/提交，在后续轮询重试，不重复创建记录或提交。临时目录/解析错误会警告并继续；Ctrl+C 停止。原有“禁止夹带非同步改动或已有暂存”的保护保留。

## Windows 后台常驻与登录自启

本机使用 Windows 计划任务 `ComfyUI-Gallery-Watcher`，等效运行 `python sync_gallery.py --watch --push`，无需开着终端或 Codex。重新安装：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_watcher.ps1
```

启动器复用原监控函数，使用 pythonw 隐藏运行；任务以当前用户普通权限执行，在该用户登录 30 秒后自动启动，并立即启动一次。**这是开机登录后自启，不是未登录就运行的系统服务**；不保存 Windows 或 GitHub 密码，沿用当前用户 Git Credential Manager 授权。退出登录或关机期间不运行，睡眠期间暂停；恢复运行后补扫未收录的 PNG。

计划任务禁止重复实例、无运行时长上限、不因电池供电停止；进程异常退出后每分钟重启，最多重试 999 次。Git 调用超时为 120 秒，网络/授权失败写日志并后续重试，不弹出登录窗口。授权失效时仍需要人工重新授权；存在其他未提交代码改动时安全暂停同步，需先提交，避免夹带上传。

日志：`.local/watcher.log`（UTF-8，2 MiB × 当前文件及 3 个备份，约 8 MiB 上限），已忽略，不上传。Git 绝对目录由安装器写入任务参数；若移动 Python、Git 或项目目录，请重新安装任务。后台运行不依赖 Codex 窗口，但使用现有 Codex 随附 Git；若将其卸载，需安装 Git 并重新注册任务。

```powershell
Get-ScheduledTask -TaskName ComfyUI-Gallery-Watcher
Get-Content .\.local\watcher.log -Tail 15
Stop-ScheduledTask -TaskName ComfyUI-Gallery-Watcher   # 本次停止，下次登录仍自启
Disable-ScheduledTask -TaskName ComfyUI-Gallery-Watcher # 关闭自启
# 重新开启：Enable-ScheduledTask -TaskName ComfyUI-Gallery-Watcher
# 立即启动：Start-ScheduledTask -TaskName ComfyUI-Gallery-Watcher
```

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
python -m unittest discover -s tests -v
```

20 项测试在独立临时目录进行；覆盖原有解析/同步、监控 10 秒间隔、写入稳定性、空闲不推送、错误/超时恢复、失败 push 重试、Ctrl+C 停止，以及 Windows 锁在强制退出后释放、后台日志缓冲/轮转和缺 Git 的故障日志。Git 测试只推到临时本地裸仓库，**不推送 GitHub**，不会在真实 ComfyUI output 或画廊中制造测试记录。

## GitHub Pages

[查看画廊](https://luozhixiang081-crypto.github.io/comfyui-gallery/)。main 为发布分支；推送后由 GitHub Pages 更新线上页面。

仓库 Settings → Pages 使用 Deploy from a branch → main → /(root)。根目录的 .nojekyll 已存在，不需要额外构建。该仓库公开，只应放可公开图片、提示词和工作流。

参考：[GitHub Pages 发布源](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)、[Pillow PNG 元数据](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#png)。
