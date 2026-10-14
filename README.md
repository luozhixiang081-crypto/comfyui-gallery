# ComfyUI 生图画廊 v1

手机优先的纯静态单页，原生 HTML / CSS / JavaScript，无框架、无 npm 依赖、无构建步骤。图片、数据和脚本全部使用相对路径，适合 GitHub Pages 项目子目录。

## 本地预览

在项目目录运行：

```powershell
python -m http.server 8080 --bind 127.0.0.1
```

浏览器打开 `http://127.0.0.1:8080/`。不要直接双击 HTML：浏览器通常禁止 `file://` 页面通过 fetch 读取 JSON。

## 已实现

- 手机 2 列，760px 起 3 列；图片按固定比例展示，弹窗中查看完整大图。
- 人像 / 风景 / 电商图 / 全部标签筛选。
- 原生 dialog 弹窗，查看正负提示词、模型、seed、steps、cfg、sampler；支持关闭按钮、Esc、点击背景关闭和焦点返回。
- 正向、负向提示词分别一键复制；权限受限时尝试兼容复制，再失败会选中文本并提示手动复制。
- workflow JSON 下载按钮明确禁用占位，不下载伪造的 workflow。
- 加载失败、空列表、卡片图片缺失的反馈；键盘焦点、44px 按钮和减少动态效果设置。

## 数据与图片

编辑 `gallery.json`，根元素是作品数组。v1 手写了 3 条示例数据，对应本机 ComfyUI 生成的演示图，不是用户历史作品。参数与生成配置一致；不同设备与版本不保证像素完全一致。

每条数据必须包含：`id, img, prompt, negative, model, seed, steps, cfg, sampler, tags[]`。`id` 使用唯一非空字符串；图片放在 `assets/`，路径写成 `./assets/文件名.png`。支持 PNG / JPG / WebP / AVIF / SVG。seed 必须为非负安全整数，steps 为正整数，cfg 为非负数。

示例使用 `dreamshaper_8_pruned.safetensors`、`euler_ancestral`、normal scheduler、denoise 1、512×640、20 steps、CFG 7。标签可填写多项，v1 筛选按钮固定为人像 / 风景 / 电商图。新增作品可直接追加记录；未知 id 的标题自动使用首个标签。

## GitHub Pages

1. 创建用于此项目的 GitHub 仓库，上传当前仓库的 `main` 分支。
2. 仓库 Settings → Pages → Source 选择 **Deploy from a branch**。
3. Branch 选择 **main**，目录选择 **/(root)**，保存。
4. 等待 Pages 部署完成，打开设置页给出的站点链接。

仓库根目录已有 `.nojekyll`，无需额外构建。GitHub Free 使用公开仓库；Pages 页面面向公网，因此只放可以公开的图片、提示词与数据。

官方说明：[配置发布源](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。

## 练习 Git

```powershell
git status                 # 看哪些文件改了
git diff                   # 看具体改动
git add gallery.json       # 选择本次要存档的文件
git commit -m "添加新作品"  # 保存一个可以追溯的版本
git log --oneline          # 看历史版本
```

添加图片时也需要 `git add assets/图片名.png`。`commit` 只保存在本地；配置远程仓库后，`git push` 才会上传。
