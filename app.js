"use strict";

const gallery = document.querySelector("#gallery");
const loadState = document.querySelector("#load-state");
const count = document.querySelector("#count");
const dialog = document.querySelector("#art-dialog");
const copyStatus = document.querySelector("#copy-status");
const detailImage = document.querySelector("#detail-image");
const detailImageState = document.querySelector("#detail-image-state");
const filters = [...document.querySelectorAll(".filter")];
const titles = { portrait: "霓虹人像", landscape: "云海山脊", product: "光影香水" };
let artworks = [];
let selectedArtwork = null;
let activeTag = "全部";

detailImage.addEventListener("load", () => {
  detailImage.hidden = false;
  detailImageState.hidden = true;
});
detailImage.addEventListener("error", () => {
  detailImage.hidden = true;
  detailImageState.hidden = false;
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function validateData(data) {
  if (!Array.isArray(data)) throw new Error("gallery.json 应为数组。");
  const ids = new Set();
  for (const item of data) {
    if (!item || typeof item !== "object" ||
        !["id", "img", "prompt", "negative", "model", "sampler"].every(key => typeof item[key] === "string") ||
        !["seed", "steps", "cfg"].every(key => Number.isFinite(item[key])) ||
        !Number.isSafeInteger(item.seed) || item.seed < 0 ||
        !Number.isInteger(item.steps) || item.steps <= 0 || item.cfg < 0 ||
        !Array.isArray(item.tags) || !item.tags.every(tag => typeof tag === "string") ||
        !item.id || ids.has(item.id) || !item.img.startsWith("./assets/") ||
        !/\.(png|jpe?g|webp|avif|svg)$/i.test(item.img) ||
        item.img.includes("..") || item.img.includes("\\")) {
      throw new Error("gallery.json 含有无效或重复的作品数据。");
    }
    ids.add(item.id);
  }
  return data;
}

function renderGallery() {
  const visible = artworks.filter(item => activeTag === "全部" || item.tags.includes(activeTag));
  gallery.replaceChildren();
  count.textContent = `${String(visible.length).padStart(2, "0")} 件作品`;
  loadState.hidden = visible.length > 0;
  loadState.textContent = "这个标签下还没有作品。";

  for (const item of visible) {
    const index = artworks.indexOf(item) + 1;
    const title = titles[item.id] || `${item.tags[0] || "未分类"}作品`;
    const card = element("button", "art-card");
    card.type = "button";
    card.setAttribute("aria-label", `查看${title}的图片、提示词和生成参数`);
    const imageWrap = element("span", "card-image-wrap");
    const image = element("img");
    image.src = item.img;
    image.alt = title;
    image.loading = index > 2 ? "lazy" : "eager";
    image.decoding = "async";
    image.addEventListener("error", () => {
      imageWrap.classList.add("image-fallback");
      imageWrap.replaceChildren(element("span", "", "图片暂不可用"), element("small", "", "仍可查看提示词和参数"));
    }, { once: true });
    const open = element("span", "card-open", "↗");
    open.setAttribute("aria-hidden", "true");
    imageWrap.append(image, open);
    const info = element("span", "card-info");
    const meta = element("span", "card-meta");
    meta.append(element("span", "", item.tags[0] || "未分类"), element("span", "card-number", `G—${String(index).padStart(3, "0")}`));
    info.append(meta, element("span", "card-title", title), element("span", "card-model", item.model));
    card.append(imageWrap, info);
    card.addEventListener("click", () => openArtwork(item, title, index));
    gallery.append(card);
  }
}

function openArtwork(item, title, index) {
  selectedArtwork = item;
  copyStatus.textContent = "";
  document.querySelector("#dialog-title").textContent = title;
  document.querySelector("#dialog-id").textContent = `G—${String(index).padStart(3, "0")} / 作品详情`;
  const image = document.querySelector("#detail-image");
  image.hidden = false;
  detailImageState.hidden = true;
  image.alt = title;
  image.src = item.img;
  document.querySelector("#detail-prompt").textContent = item.prompt;
  document.querySelector("#detail-negative").textContent = item.negative || "无负向提示词";
  document.querySelector("#detail-tags").replaceChildren(...item.tags.map(tag => element("span", "tag", tag)));
  const parameters = [["模型", item.model], ["Seed", item.seed], ["Steps", item.steps], ["CFG", item.cfg], ["Sampler", item.sampler]];
  document.querySelector("#detail-parameters").replaceChildren(...parameters.map(([label, value]) => {
    const row = element("div", "parameter");
    row.append(element("dt", "", label), element("dd", "", String(value)));
    return row;
  }));
  dialog.showModal();
  dialog.scrollTop = 0;
  document.body.classList.add("modal-open");
}

function legacyCopy(text) {
  const textarea = element("textarea");
  textarea.value = text;
  textarea.setAttribute("aria-label", "待复制的提示词");
  textarea.style.cssText = "position:fixed;top:0;left:0;opacity:0;pointer-events:none;";
  // Keep the fallback inside the modal: outside elements are inert.
  dialog.append(textarea);
  textarea.focus();
  textarea.select();
  let copied = false;
  try { copied = document.execCommand("copy"); } finally { textarea.remove(); }
  if (!copied) throw new Error("复制未获允许。");
}

for (const button of document.querySelectorAll("[data-copy]")) {
  button.addEventListener("click", async () => {
    if (!selectedArtwork) return;
    const item = selectedArtwork;
    const key = button.dataset.copy;
    const text = item[key];
    button.disabled = true;
    button.textContent = "复制中…";
    copyStatus.textContent = "";
    try {
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard API 不可用。");
        await navigator.clipboard.writeText(text);
      } catch {
        if (!dialog.open || selectedArtwork !== item) return;
        legacyCopy(text);
      }
      if (selectedArtwork === item && dialog.open) copyStatus.textContent = key === "prompt" ? "正向提示词已复制。" : "负向提示词已复制。";
    } catch {
      if (selectedArtwork === item && dialog.open) {
        copyStatus.textContent = "复制未获允许，请长按提示词手动复制。";
        const target = document.querySelector(key === "prompt" ? "#detail-prompt" : "#detail-negative");
        const range = document.createRange();
        range.selectNodeContents(target);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
    } finally {
      button.disabled = false;
      button.textContent = "复制";
      if (dialog.open && selectedArtwork === item) button.focus({ preventScroll: true });
    }
  });
}

document.querySelector("#close-dialog").addEventListener("click", () => dialog.close());
dialog.addEventListener("keydown", event => {
  if (event.key !== "Tab") return;
  const focusable = [...dialog.querySelectorAll('button:not(:disabled), [tabindex="0"]')];
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
dialog.addEventListener("click", event => {
  if (event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
});
dialog.addEventListener("close", () => {
  selectedArtwork = null;
  document.body.classList.remove("modal-open");
});
for (const button of filters) {
  button.addEventListener("click", () => {
    activeTag = button.dataset.tag;
    for (const filter of filters) {
      const active = filter === button;
      filter.classList.toggle("is-active", active);
      filter.setAttribute("aria-pressed", String(active));
    }
    renderGallery();
  });
}

async function loadGallery() {
  try {
    const response = await fetch("./gallery.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    artworks = validateData(await response.json());
    renderGallery();
  } catch {
    loadState.hidden = false;
    loadState.textContent = location.protocol === "file:"
      ? "请通过本地 HTTP 服务或 GitHub Pages 打开，直接双击 HTML 无法读取 gallery.json。"
      : "作品加载失败，请检查 gallery.json 后刷新重试。";
    count.textContent = "加载失败";
  } finally {
    gallery.setAttribute("aria-busy", "false");
  }
}
loadGallery();
