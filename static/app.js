import { $, toast, setDirty, api } from "./js/utils.js";
import { state } from "./js/state.js";
import { initP2Enhancements, showTimingBreakdown, renderStoryStats, renderCharacterNetworkFromData, renderFactionGlobalNetwork, renderCultureGlobalNetwork, renderSingleFactionNetwork, renderSingleCultureNetwork } from "./js/p2-enhancements.js";
// $, toast, api, setDirty, state, renderStoryStats, showTimingBreakdown, renderCharacterNetwork are now provided by the modules above.

/** 切换世界时清空搜索 UI，避免命中仍显示上一世界 */
let _searchPanelWorldId = null;

const VIEW_TO_SCOPE = {
  geo: "geography",
  ecology: "ecology",
  powers: "power_system",
  attributes: "attribute_system",
  items: "item_quality_system",
  cultures: "cultures",
  factions: "factions",
  history: "history",
  economy: "economy",
  charChat: "characters",
  charProtagonists: "characters",
  charSupporting: "characters",
  charRelations: "characters",
  charData: "characters",
  charKnowledge: "characters",
  storyChat: "story",
  storyOverview: "story",
  storyOutline: "story",
  storyChapter: "story",
  storyForeshadow: "story",
  storyWrite: "story",
};

/** 左侧「情节」导航 → 情节工作台子页 */
const STORY_NAV_VIEWS = {
  storyOverview: "overview",
  storyOutline: "outline",
  storyChapter: "chapter",
  storyForeshadow: "foreshadow",
  storyWrite: "write",
  storyAudit: "audit",
  storyAgent: "agent",
  storyStats: "stats",
};

const STORY_NAV_LABELS = {
  storyOverview: "总览",
  storyOutline: "大纲",
  storyChapter: "章节",
  storyForeshadow: "伏笔",
  storyWrite: "写作",
  storyAudit: "审校",
  storyAgent: "Agent",
  storyStats: "统计",
};

const STORY_SUB_TO_NAV = {
  overview: "storyOverview",
  outline: "storyOutline",
  chapter: "storyChapter",
  foreshadow: "storyForeshadow",
  write: "storyWrite",
  audit: "storyAudit",
  stats: "storyStats",
  agent: "storyAgent",
};

function isStoryPanelView(name) {
  return name === "story" || name === "storyStats" || name in STORY_NAV_VIEWS;
}

function resolveStoryPanelRoute(name) {
  if (name === "outlines") {
    return { panel: "story", storySubView: "outline", storyOutlineSub: "auxiliary", activeStoryNav: "storyOutline" };
  }
  if (name === "storyStats") {
    return { panel: "story", storySubView: "stats", activeStoryNav: "storyStats" };
  }
  if (name in STORY_NAV_VIEWS) {
    return {
      panel: "story",
      storySubView: STORY_NAV_VIEWS[name],
      activeStoryNav: name,
      storyOutlineSub: name === "storyOutline" ? state.storyOutlineSub || "macro" : state.storyOutlineSub,
    };
  }
  if (name === "story") {
    return {
      panel: "story",
      storySubView: state.storySubView || "overview",
      activeStoryNav: state.activeStoryNav || STORY_SUB_TO_NAV[state.storySubView] || "storyOverview",
    };
  }
  return { panel: name };
}

/** 左侧「角色」分组：各入口为独立 #view-char* 页面 */
function isCharacterPanelView(name) {
  return (
    name === "charProtagonists" ||
    name === "charSupporting" ||
    name === "charRelations" ||
    name === "charData" ||
    name === "charKnowledge"
  );
}

function syncNavActiveButtons() {
  document.querySelectorAll(".nav button").forEach((b) => {
    const v = b.dataset.view;
    let active = false;
    if (isStoryPanelView(v) && state.activeView === "story") {
      active = v === (state.activeStoryNav || STORY_SUB_TO_NAV[state.storySubView] || "storyOverview");
    } else {
      active = v === state.activeView;
    }
    b.classList.toggle("active", active);
  });
}

/** 主导航中「世界观」各子页（不含世界观构建页 / 大纲 / 数据页） */
const WORLDVIEW_EDIT_PANEL_IDS = [
  "geo",
  "ecology",
  "powers",
  "attributes",
  "items",
  "cultures",
  "factions",
  "history",
  "economy",
  "charProtagonists",
  "charSupporting",
];

const WORLDVIEW_EDIT_LABELS = {
  geo: "地理",
  ecology: "生态与生境",
  powers: "境界体系",
  attributes: "通用人物属性",
  items: "物品品质",
  cultures: "文化与宗教",
  factions: "派系",
  history: "历史",
  economy: "经济与流通",
  charProtagonists: "主角团",
  charSupporting: "重要配角",
  charKnowledge: "知识图谱",
};

function isWorldviewPanelEditEnabled(panelId) {
  return state.worldviewEditMode[panelId] !== false;
}

function shouldSkipWorldviewEditLock(el, panelRoot) {
  if (!el || !panelRoot || !panelRoot.contains(el)) return true;
  if (el.closest("[data-edit-mode-toolbar]")) return true;
  if (el.closest(".mermaid-zoom-toolbar")) return true;
  if (el.closest(".panel-subtabs")) return true;
  return false;
}

function applyWorldviewPanelEditMode(panelId) {
  const enabled = isWorldviewPanelEditEnabled(panelId);
  const root = document.getElementById(`view-${panelId}`);
  if (!root) return;
  root.classList.toggle("worldview-panel--readonly", !enabled);
  const sw = document.getElementById(`editModeSwitch-${panelId}`);
  if (sw) sw.checked = enabled;
  root.querySelectorAll("textarea").forEach((el) => {
    if (shouldSkipWorldviewEditLock(el, root)) return;
    el.readOnly = !enabled;
  });
  root.querySelectorAll("select").forEach((el) => {
    if (shouldSkipWorldviewEditLock(el, root)) return;
    el.disabled = !enabled;
  });
  root.querySelectorAll("input").forEach((el) => {
    if (shouldSkipWorldviewEditLock(el, root)) return;
    if (el.type === "hidden") return;
    const t = (el.type || "text").toLowerCase();
    if (t === "checkbox" || t === "radio") el.disabled = !enabled;
    else if (t === "button" || t === "submit" || t === "reset") el.disabled = !enabled;
    else el.readOnly = !enabled;
  });
  root.querySelectorAll("button").forEach((btn) => {
    if (shouldSkipWorldviewEditLock(btn, root)) return;
    if (btn.closest(".panel-subtabs")) return;
    if (btn.closest(".mermaid-zoom-toolbar")) return;
    btn.disabled = !enabled;
  });
  if (panelId === "charProtagonists" || panelId === "charSupporting") refreshCharactersVizFromForm();
}

// ── Character Detail Panel ──────────────────────────────────────

async function openCharDetail(charId) {
  if (!state.world?.meta?.id) return;
  const wid = state.world.meta.id;
  const overlay = $("charDetailOverlay");
  const body = $("charDetailBody");
  const nameEl = $("charDetailName");
  if (!overlay || !body) return;

  overlay.classList.remove("hidden");
  body.innerHTML = '<p class="muted" style="padding:20px;text-align:center">加载中…</p>';

  try {
    const res = await api(`/api/worlds/${wid}/characters/${charId}/detail`);
    nameEl.textContent = res.name || charId;

    // Build tier/profession options from world data
    const tiers = state.world.power_system?.tiers || [];
    const tierOpts = tiers.map(t => `<option value="${escapeHtml(t.name)}" ${res.power_tier===t.name?'selected':''}>${escapeHtml(t.name)}</option>`).join("");
    const profs = [];
    (state.world.power_system?.profession_system?.by_tier || []).forEach(b =>
      (b.professions||[]).forEach(p => profs.push({...p, tier_name: b.tier_name})));
    const profOpts = profs.map(p =>
      `<option value="${escapeHtml(p.id)}" ${res.profession_id===p.id?'selected':''}>${escapeHtml(p.tier_name||'')} · ${escapeHtml(p.name)}</option>`
    ).join("");

    const inv = res.inventory || [];
    const invRows = inv.map((item, i) => `
      <div class="cd-inv-row ${item.status==='已失去'?'cd-inv-lost':''}">
        <div class="cd-inv-main">
          <input class="cd-inv-name" value="${escapeAttr(item.name||'')}" placeholder="物品名" data-inv-idx="${i}" data-inv-field="name">
          <input class="cd-inv-desc" value="${escapeAttr(item.description||'')}" placeholder="描述" data-inv-idx="${i}" data-inv-field="description">
          <input class="cd-inv-usage" value="${escapeAttr(item.usage||'')}" placeholder="用法/效果" data-inv-idx="${i}" data-inv-field="usage">
        </div>
        <div class="cd-inv-meta">
          <input class="cd-inv-qty" type="number" min="1" value="${item.quantity||1}" data-inv-idx="${i}" data-inv-field="quantity" style="width:50px" title="数量">
          <input class="cd-inv-src" value="${escapeAttr(item.source_chapter||'')}" placeholder="来源章" data-inv-idx="${i}" data-inv-field="source_chapter" style="width:70px" title="来源章节">
          <select data-inv-idx="${i}" data-inv-field="status" style="font-size:0.72rem">
            <option value="携带中" ${item.status==='携带中'?'selected':''}>携带中</option>
            <option value="已使用" ${item.status==='已使用'?'selected':''}>已使用</option>
            <option value="已失去" ${item.status==='已失去'?'selected':''}>已失去</option>
            <option value="已损坏" ${item.status==='已损坏'?'selected':''}>已损坏</option>
          </select>
          <button class="btn-sm cd-inv-del" onclick="deleteInvItem(this,${i})" title="移除此物品"><span class="ms" aria-hidden="true" style="font-size:16px">delete</span></button>
        </div>
      </div>
    `).join("");

    body.innerHTML = `
      <div class="cd-grid">
        <div class="cd-field">
          <label class="cd-label"><span class="ms cd-field-ic" aria-hidden="true">theater_comedy</span> 角色定位</label>
          <span class="cd-val">${escapeHtml(res.cast_role||'—')}</span>
        </div>
        <div class="cd-field">
          <label class="cd-label"><span class="ms cd-field-ic" aria-hidden="true">wc</span> 性别</label>
          <select id="cdGender" class="cd-select" title="角色性别">
            <option value="" ${!res.gender?'selected':''}>— 未知 —</option>
            <option value="男" ${res.gender==='男'?'selected':''}>男</option>
            <option value="女" ${res.gender==='女'?'selected':''}>女</option>
            <option value="其他" ${res.gender==='其他'?'selected':''}>其他</option>
          </select>
        </div>
        <div class="cd-field">
          <label class="cd-label"><span class="ms cd-field-ic" aria-hidden="true">calendar_today</span> 年龄</label>
          <input id="cdAge" class="cd-input" value="${escapeAttr(res.age||'')}" placeholder="未知">
        </div>
        <div class="cd-field">
          <label class="cd-label"><span class="ms cd-field-ic" aria-hidden="true">bolt</span> 力量境界</label>
          <select id="cdPowerTier" class="cd-select" title="选择角色当前所属的境界等级">${tierOpts}</select>
          ${res.tier_description ? `<p class="cd-hint">${escapeHtml(res.tier_description.slice(0,120))}</p>` : ''}
        </div>
        <div class="cd-field">
          <label class="cd-label"><span class="ms cd-field-ic" aria-hidden="true">school</span> 职业</label>
          <select id="cdProfession" class="cd-select" title="选择角色在力量体系中的职业"><option value="">— 无 —</option>${profOpts}</select>
        </div>
      </div>
      ${(res.attributes||[]).length ? `
      <div class="cd-section">
        <div class="cd-section-head">
          <span class="cd-section-title"><span class="ms cd-field-ic" aria-hidden="true">bar_chart</span> 角色属性</span>
          <span class="muted tiny">拖拽滑块动态调整，保存后生效</span>
        </div>
        <div class="cd-attr-list">
          ${res.attributes.map(a => `
            <div class="cd-attr-row">
              <div class="cd-attr-info">
                <span class="cd-attr-name">${escapeHtml(a.name)}</span>
                ${a.abbreviation ? `<span class="cd-attr-abbr">${escapeHtml(a.abbreviation)}</span>` : ''}
                <span class="cd-attr-val" id="cdAttrVal_${escapeAttr(a.stat_id)}">${a.value}</span>
                ${a.intro ? `<span class="cd-attr-intro" title="${escapeHtml(a.intro)}">?</span>` : ''}
              </div>
              <div class="cd-attr-bar-wrap">
                <input type="range" class="cd-attr-slider" data-attr-id="${escapeAttr(a.stat_id)}"
                  min="0" max="100" value="${a.value}"
                  oninput="document.getElementById('cdAttrVal_${escapeAttr(a.stat_id)}').textContent=this.value"
                  title="${escapeHtml(a.name)}: ${a.value}/100">
                <div class="cd-attr-ticks">
                  <span>0</span><span>25</span><span class="cd-attr-ref" style="left:${a.reference_percent||55}%" title="参考值 ${a.reference_percent||55}">▼</span><span>75</span><span>100</span>
                </div>
              </div>
            </div>
          `).join("")}
        </div>
      </div>` : '<p class="muted tiny" style="padding:8px 12px">该世界暂无属性体系定义。请在「属性」面板中创建 stats。</p>'}
      <div class="cd-section">
        <div class="cd-section-head">
          <span class="cd-section-title"><span class="ms cd-field-ic" aria-hidden="true">inventory_2</span> 物品清单 <span class="cd-badge">${inv.length}</span></span>
          <button class="btn-sm btn-ic cd-add-btn" onclick="window.addInvItem()" title="添加新物品到清单">
            <span class="ms" aria-hidden="true" style="font-size:16px">add</span> 添加物品
          </button>
        </div>
        <div class="cd-inv-list" id="cdInvList">${invRows||'<p class="muted tiny" style="padding:12px;text-align:center">暂无物品，点击「添加物品」开始记录</p>'}</div>
        <div class="cd-inv-legend">
          <span class="cd-legend-dot cd-legend-active"></span> 携带中
          <span class="cd-legend-dot cd-legend-used"></span> 已使用
          <span class="cd-legend-dot cd-legend-lost"></span> 已失去
          <span class="cd-legend-dot cd-legend-damaged"></span> 已损坏
        </div>
      </div>
      <div class="cd-actions">
        <button class="primary btn-ic cd-save-btn" onclick="window.saveCharDetail('${charId}')" title="将修改保存到 world.json">
          <span class="ms" aria-hidden="true" style="font-size:18px">save</span> 保存角色详情
        </button>
        <button class="btn-ic cd-cancel-btn" onclick="window.closeCharDetail()" title="关闭面板（不保存未提交的修改）">
          <span class="ms" aria-hidden="true" style="font-size:18px">close</span> 取消
        </button>
        <span id="cdSaveStatus" class="muted tiny" style="margin-left:8px"></span>
      </div>
    `;
    // Store charId for save
    overlay.dataset.charId = charId;
  } catch(e) {
    body.innerHTML = `<p class="muted">加载失败：${escapeHtml(String(e.message||e))}</p>`;
  }
}
window.openCharDetail = openCharDetail;

function closeCharDetail() {
  const overlay = $("charDetailOverlay");
  if (overlay) overlay.classList.add("hidden");
}
window.closeCharDetail = closeCharDetail;

// ESC key to close
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    const overlay = $("charDetailOverlay");
    if (overlay && !overlay.classList.contains("hidden")) closeCharDetail();
  }
});

function addInvItem() {
  const list = $("cdInvList");
  if (!list) return;
  const idx = list.querySelectorAll(".cd-inv-row").length;
  const row = document.createElement("div");
  row.className = "cd-inv-row";
  row.innerHTML = `
    <div class="cd-inv-main">
      <input class="cd-inv-name" placeholder="物品名" data-inv-idx="${idx}" data-inv-field="name">
      <input class="cd-inv-desc" placeholder="描述" data-inv-idx="${idx}" data-inv-field="description">
      <input class="cd-inv-usage" placeholder="用法/效果" data-inv-idx="${idx}" data-inv-field="usage">
    </div>
    <div class="cd-inv-meta">
      <input type="number" min="1" value="1" data-inv-idx="${idx}" data-inv-field="quantity" style="width:50px" title="数量">
      <input value="" placeholder="来源章" data-inv-idx="${idx}" data-inv-field="source_chapter" style="width:70px" title="来源章节">
      <select data-inv-idx="${idx}" data-inv-field="status" style="font-size:0.72rem">
        <option value="携带中" selected>携带中</option>
        <option value="已使用">已使用</option>
        <option value="已失去">已失去</option>
        <option value="已损坏">已损坏</option>
      </select>
      <button class="btn-sm cd-inv-del" onclick="this.closest('.cd-inv-row').remove()">×</button>
    </div>`;
  list.appendChild(row);
  // Remove empty placeholder if present
  const empty = list.querySelector("p.muted");
  if (empty) empty.remove();
}
window.addInvItem = addInvItem;

function deleteInvItem(btn, idx) {
  btn.closest(".cd-inv-row")?.remove();
}
window.deleteInvItem = deleteInvItem;

async function saveCharDetail(charId) {
  if (!state.world?.meta?.id) return;
  const wid = state.world.meta.id;
  const statusEl = $("cdSaveStatus");
  if (statusEl) statusEl.textContent = "保存中…";

  // Collect inventory
  const invRows = document.querySelectorAll("#cdInvList .cd-inv-row");
  const inventory = [];
  invRows.forEach(row => {
    const item = {};
    row.querySelectorAll("[data-inv-field]").forEach(el => {
      item[el.dataset.invField] = el.value;
    });
    if (item.name) {
      item.quantity = parseInt(item.quantity) || 1;
      inventory.push(item);
    }
  });

  const body = {
    power_tier: $("cdPowerTier")?.value || "",
    profession_id: $("cdProfession")?.value || "",
    age: $("cdAge")?.value || "",
    gender: $("cdGender")?.value || "",
    inventory: inventory,
    // Collect attribute values from sliders
    attributes: (() => {
      const attrs = {};
      document.querySelectorAll(".cd-attr-slider").forEach(slider => {
        attrs[slider.dataset.attrId] = parseInt(slider.value) || 0;
      });
      return Object.keys(attrs).length > 0 ? attrs : null;
    })(),
  };

  try {
    const res = await api(`/api/worlds/${wid}/characters/${charId}`, {
      method: "PATCH", body: JSON.stringify(body),
    });
    if (res.ok) {
      state.world = res.world;
      if (statusEl) { statusEl.textContent = "已保存"; statusEl.className = "agent-status-active tiny"; }
      // Refresh roster if visible
      setTimeout(() => { if (statusEl) { statusEl.textContent = ""; } }, 2000);
    }
  } catch(e) {
    if (statusEl) { statusEl.textContent = "保存失败: " + e.message; statusEl.className = "muted tiny"; }
  }
}
window.saveCharDetail = saveCharDetail;

// Hook: click character card to open detail
document.addEventListener("click", function(e) {
  const card = e.target.closest(".char-roster-card");
  if (card) {
    const codeEl = card.querySelector(".char-roster-code");
    if (codeEl) openCharDetail(codeEl.textContent.trim());
  }
});

// ── Power System Batch Progress Tracker ─────────────────────────

function togglePowerBatchGuide() {
  const body = $("powerBatchBody");
  const btn = document.querySelector("#powerBatchHint button");
  if (!body || !btn) return;
  if (body.style.display === "none") {
    body.style.display = "";
    btn.textContent = "收起";
  } else {
    body.style.display = "none";
    btn.textContent = "展开";
  }
}

function updatePowerBatchProgress() {
  const steps = document.querySelectorAll("#powerBatchSteps input[type=checkbox]");
  const progressDiv = $("powerBatchProgress");
  const fillEl = $("powerBatchFill");
  const textEl = $("powerBatchProgressText");
  if (!steps.length || !fillEl || !textEl || !progressDiv) return;
  const done = Array.from(steps).filter(cb => cb.checked).length;
  const total = steps.length;
  const pct = Math.round(done / total * 100);
  fillEl.style.width = pct + "%";
  textEl.textContent = `${done}/${total} 步完成 (${pct}%)`;
  progressDiv.style.display = done > 0 ? "" : "none";
  // Persist to localStorage
  try {
    const state = Array.from(steps).map(cb => cb.checked);
    localStorage.setItem("mcw_power_batch_progress", JSON.stringify(state));
  } catch (_) {}
}

// Restore progress on page load
(function _restorePowerBatchProgress() {
  try {
    const saved = JSON.parse(localStorage.getItem("mcw_power_batch_progress") || "[]");
    const steps = document.querySelectorAll("#powerBatchSteps input[type=checkbox]");
    steps.forEach((cb, i) => { if (saved[i]) cb.checked = true; });
    if (saved.some(Boolean)) updatePowerBatchProgress();
  } catch (_) {}
})();

function applyAllWorldviewEditModes() {
  for (const id of WORLDVIEW_EDIT_PANEL_IDS) applyWorldviewPanelEditMode(id);
}

function ensureWorldviewEditModeToolbars() {
  for (const panelId of WORLDVIEW_EDIT_PANEL_IDS) {
    const root = document.getElementById(`view-${panelId}`);
    if (!root) continue;
    const card = root.querySelector(".card");
    if (!card || card.querySelector("[data-edit-mode-toolbar]")) continue;
    const bar = document.createElement("div");
    bar.className = "edit-mode-toolbar";
    bar.dataset.editModeToolbar = "1";
    const swId = `editModeSwitch-${panelId}`;
    const lab = WORLDVIEW_EDIT_LABELS[panelId] || panelId;
    bar.innerHTML = `<label class="edit-mode-toggle lbl-ic" title="关闭后本页设定为只读展示，避免误改；关系图仍可缩放。">
      <span class="ms edit-mode-ic" aria-hidden="true">edit_note</span>
      <span class="edit-mode-label">编辑模式</span>
      <input type="checkbox" id="${swId}" class="edit-mode-cb" aria-label="${lab}：允许编辑设定" />
    </label>`;
    const h2 = card.querySelector("h2");
    if (h2) h2.insertAdjacentElement("afterend", bar);
    else card.prepend(bar);
    const cb = document.getElementById(swId);
    if (cb) {
      cb.checked = isWorldviewPanelEditEnabled(panelId);
      cb.addEventListener("change", () => {
        state.worldviewEditMode[panelId] = cb.checked;
        applyWorldviewPanelEditMode(panelId);
      });
    }
  }
  applyAllWorldviewEditModes();
}

// toast() is imported from ./js/utils.js and exposed on window by main.js

const GENRE_MODE_HINTS = {
  "": "未选择时：对话仍用通用架构师；若世界已保存载体，则对话/同步/大纲会沿用该载体。",
  novel: "小说：叙事弧线、人物动机与伏笔；地理请按 geography（summary / regions 的 id·relations·短名列表）写，便于同步与关系图。",
  game: "游戏：成长与任务链、系统边界；地理请按 regions[].id 与 relations 写，便于任务引用与区域解锁。",
  coc: "CoC：调查链、理智与神话代价；地理请把可调查点与压力写进 regions[].landmarks / notes，短名列表利落后端归一。",
  dnd: "DnD：冒险引导、遭遇与对抗边界；地理请写清 regions[].terrain、notes 与 relations，便于裁定旅行与遭遇。",
};

function updateGenreModeHint() {
  const el = $("genreModeHint");
  const sel = $("genreMode");
  if (!el || !sel) return;
  el.textContent = GENRE_MODE_HINTS[sel.value] ?? GENRE_MODE_HINTS[""];
}

/** 文化·宗教页：字段说明 + 随创作模式变化的写作/同步侧重 */
const CULTURE_MODULE_HINT =
  "每条实体须有唯一 id；relations 的 target_id 指向另一文化实体 id。kind：文化=习俗与族群叙事，宗教=教团/神话组织，融合=综摄或混血传统。对话后结构化同步的顶层键为 cultures。";

const CULTURE_GENRE_HINTS = {
  "": "未选创作模式：仍可写民俗、禁忌、教团；同步会按通用规则写入 cultures。",
  novel:
    "小说侧重：信仰如何塑造日常选择、仪式与秘密教义的叙事张力；与派系/地理挂钩时请用稳定 id，便于关系图与第二路 JSON。",
  game:
    "游戏侧重：节日与声望系统、阵营 Buff 文案、可做成活动或副本的圣地；实体可对应可刷新的「文化标签」或势力声望。",
  coc:
    "CoC 侧重：民间禁忌、密教变体、调查员易忽视的「正常中的异常」；教团与神话线索可与 factions 并行，勿把一切都写成战斗数值。",
  dnd:
    "DnD 侧重：神殿网络、圣徽、阵营意识形态、可扮演钩子；与派系据点、任务发布者交叉时用 id 引用，便于 DM 快速裁定。",
};

function updateCultureHint() {
  const el = $("cultureHintPanel");
  const sel = $("genreMode");
  if (!el) return;
  const g = sel?.value ?? "";
  el.textContent = `${CULTURE_MODULE_HINT} ${CULTURE_GENRE_HINTS[g] ?? CULTURE_GENRE_HINTS[""]}`;
}

// api() and setDirty() are imported from ./js/utils.js and exposed on window by main.js

function syncScopeForRequest() {
  if (!$("syncScopeToView")?.checked) return "all";
  return VIEW_TO_SCOPE[state.activeView] || "all";
}

/** 人物卡司：从表单 JSON 解析；失败返回 null（调用方勿刷 viz） */
function tryParseCharacterEntitiesRelations() {
  const parseJson = (txt, label) => {
    try {
      return JSON.parse(txt || "[]");
    } catch {
      throw new Error(`${label} JSON 无效`);
    }
  };
  try {
    const entities = parseJson($("charEntitiesJson")?.value, "characters.entities");
    const relations = parseJson($("charRelationsJson")?.value, "characters.relations");
    if (!Array.isArray(entities) || !Array.isArray(relations)) return null;
    return { entities, relations };
  } catch {
    return null;
  }
}

const CAST_ROLE_LABELS = {
  protagonist_core: "主角团",
  supporting_major: "重要配角",
  supporting_minor: "配角",
  antagonist: "对立面",
  background: "背景",
};

const CAST_ROLE_HUES = {
  protagonist_core: 200,
  supporting_major: 268,
  supporting_minor: 245,
  antagonist: 350,
  background: 160,
};

/** 卡司卡片内联编辑：与 JSON 锚定 id 一致；勿在卡片内改 id（请用卡司数据 JSON）。 */
const CHAR_ROSTER_EDIT_ROLE_ORDER = [
  "protagonist_core",
  "supporting_major",
  "supporting_minor",
  "antagonist",
  "background",
];

function escapeAttr(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;");
}

function charCastRoleSelectHtml(currentRaw) {
  const cur = String(currentRaw ?? "").trim() || "background";
  return CHAR_ROSTER_EDIT_ROLE_ORDER.map((r) => {
    const sel = r === cur ? " selected" : "";
    const lab = CAST_ROLE_LABELS[r] || r;
    return `<option value="${escapeAttr(r)}"${sel}>${escapeHtml(lab)}</option>`;
  }).join("");
}

function renderCharCastCardEditHtml(ent, variant = "protagonists") {
  const idRaw = String(ent?.id ?? "").trim();
  if (!idRaw) return "";
  const id = escapeHtml(idRaw);
  const roleRaw = String(ent?.cast_role ?? "").trim();
  const hue = CAST_ROLE_HUES[roleRaw] ?? 210;
  const hook = String(ent?.one_line_hook ?? "");
  const notes = String(ent?.notes ?? "");
  const skills = Array.isArray(ent?.notable_skills) ? ent.notable_skills : [];
  const skillsTxt = skills.map((s) => String(s).trim()).filter(Boolean).join("\n");
  const aliases = Array.isArray(ent?.aliases) ? ent.aliases : [];
  const aliasesTxt = aliases.map((a) => String(a).trim()).filter(Boolean).join("，");
  const fac = Array.isArray(ent?.faction_ids) ? ent.faction_ids.map((x) => String(x).trim()).filter(Boolean) : [];
  const home = String(ent?.home_region_id ?? "").trim();
  const sp = (ent?.speech_profile && typeof ent.speech_profile === "object") ? ent.speech_profile : {};
  const spSent = String(sp.avg_sentence_length || "mixed");
  const spExpr = String(sp.emotional_expression || "direct");
  const spConf = String(sp.confrontation_style || "faces_it");
  const spTics = Array.isArray(sp.verbal_tics) ? sp.verbal_tics.join("，") : "";
  const spAvoid = Array.isArray(sp.avoidance_topics) ? sp.avoidance_topics.join("，") : "";
  const spSilence = String(sp.silence_meaning || "");
  const spStress = String(sp.under_stress || "");
  // Select avatar icon based on character data: power_tier > profession > cast_role
  const tierName = String(ent?.power_tier || "").trim();
  const profId = String(ent?.profession_id || "").trim();
  const tierIcons = {
    "拓雾者": "visibility", "凝痕者": "fingerprint", "塑脉师": "psychology",
    "锻脉师": "build", "域主": "domain", "逆理行者": "auto_awesome",
    "共鸣体": "hub", "同尘": "blur_on",
  };
  const roleIcons = {
    protagonist_core: "star", protagonist: "star",
    supporting_major: "person", supporting_minor: "person_outline",
    antagonist: "skull", background: "public",
  };
  const avIc = tierIcons[tierName]
    || tierIcons[Object.keys(tierIcons).find(k => tierName.includes(k)) || ""]
    || (profId ? "school" : "")
    || roleIcons[roleRaw] || (variant === "supporting" ? "person" : "badge");
  return `<article class="char-roster-card char-roster-card--edit" data-char-edit-card="1" data-char-entity-id="${escapeAttr(
    idRaw
  )}" style="--char-card-hue:${hue}">
    <div class="char-roster-card-rim" aria-hidden="true"></div>
    <div class="char-roster-card-inner">
      <header class="char-roster-card-head char-roster-card-head--edit">
        <div class="char-roster-avatar" aria-hidden="true"><span class="ms char-roster-avatar-ic">${avIc}</span></div>
        <div class="char-roster-head-main">
          <label class="char-roster-field"><span class="char-roster-field-lbl">名称</span>
            <input type="text" class="char-roster-field-ctrl" data-char-field="name" value="${escapeAttr(
              String(ent?.name ?? "").trim()
            )}" autocomplete="off" spellcheck="true" /></label>
          <div class="char-roster-idline">
            <span class="char-roster-k">id</span><code class="char-roster-code">${id}</code>
            <button class="char-roster-detail-btn" onclick="event.stopPropagation();window.openCharDetail('${escapeAttr(idRaw)}')" title="查看角色详情（力量境界/职业/物品）">
              <span class="ms" aria-hidden="true" style="font-size:16px">info</span>
            </button>
          </div>
        </div>
        <div class="char-roster-edit-head-actions">
          <label class="char-roster-field char-roster-field--inline"><span class="char-roster-field-lbl">卡司位</span>
            <select class="char-roster-field-ctrl char-roster-select-role" data-char-field="cast_role" title="cast_role">${charCastRoleSelectHtml(
              roleRaw
            )}</select></label>
          <button type="button" class="ghost btn-sm btn-ic char-roster-del" data-char-delete-entity="${escapeAttr(
            idRaw
          )}" title="从卡司删除该实体，并移除 relations 中相关边">
            <span class="ms" aria-hidden="true">delete</span></button>
        </div>
      </header>
      <section class="char-roster-block char-roster-block--edit"><div class="char-roster-block-hd">叙事钩 · one_line_hook</div>
        <textarea class="char-roster-field-ta" data-char-field="one_line_hook" rows="2" spellcheck="true">${escapeHtml(
          hook
        )}</textarea></section>
      <section class="char-roster-block char-roster-block--edit"><div class="char-roster-block-hd">备注 · notes</div>
        <textarea class="char-roster-field-ta" data-char-field="notes" rows="2" spellcheck="true">${escapeHtml(
          notes
        )}</textarea></section>
      <section class="char-roster-block char-roster-block--edit"><div class="char-roster-block-hd">别名 aliases（逗号或顿号分隔）</div>
        <input type="text" class="char-roster-field-ctrl" data-char-field="aliases" value="${escapeAttr(
          aliasesTxt
        )}" autocomplete="off" /></section>
      <section class="char-roster-block char-roster-block--edit char-roster-block--skills"><div class="char-roster-block-hd">特长 notable_skills（每行一条）</div>
        <textarea class="char-roster-field-ta" data-char-field="notable_skills" rows="3" spellcheck="true">${escapeHtml(
          skillsTxt
        )}</textarea></section>
      <section class="char-roster-block char-roster-block--edit char-roster-block--meta"><div class="char-roster-block-hd">边界 · 引用锚点</div>
        <label class="char-roster-field"><span class="char-roster-field-lbl">faction_ids（逗号或空格分隔）</span>
          <input type="text" class="char-roster-field-ctrl" data-char-field="faction_ids" value="${escapeAttr(
            fac.join("，")
          )}" autocomplete="off" /></label>
        <label class="char-roster-field"><span class="char-roster-field-lbl">home_region_id</span>
          <input type="text" class="char-roster-field-ctrl" data-char-field="home_region_id" value="${escapeAttr(
            home
          )}" autocomplete="off" /></label>
      </section>
      <details class="char-roster-block char-roster-block--edit char-roster-speech"><summary class="char-roster-block-hd" style="cursor:pointer">🎤 语言风格 · speech_profile</summary>
        <div class="speech-card-inline">
          <label class="muted tiny">句式 <select data-char-field="sp_avg_sentence_length" style="font-size:0.74rem"><option value="mixed"${spSent==="mixed"?" selected":""}>混合</option><option value="short"${spSent==="short"?" selected":""}>短句</option><option value="medium"${spSent==="medium"?" selected":""}>中等</option><option value="long"${spSent==="long"?" selected":""}>长句</option></select></label>
          <label class="muted tiny">情绪表达 <select data-char-field="sp_emotional_expression" style="font-size:0.74rem"><option value="direct"${spExpr==="direct"?" selected":""}>直接表达</option><option value="indirect"${spExpr==="indirect"?" selected":""}>间接暗示</option><option value="suppressed"${spExpr==="suppressed"?" selected":""}>压抑型</option><option value="explosive"${spExpr==="explosive"?" selected":""}>爆发型</option><option value="sarcastic"${spExpr==="sarcastic"?" selected":""}>讽刺型</option></select></label>
          <label class="muted tiny">对抗 <select data-char-field="sp_confrontation_style" style="font-size:0.74rem"><option value="faces_it"${spConf==="faces_it"?" selected":""}>直接面对</option><option value="deflects"${spConf==="deflects"?" selected":""}>转移话题</option><option value="withdraws"${spConf==="withdraws"?" selected":""}>沉默离开</option><option value="escalates"${spConf==="escalates"?" selected":""}>升级冲突</option></select></label>
          <label class="muted tiny">口头禅 <input type="text" data-char-field="sp_verbal_tics" value="${escapeAttr(spTics)}" placeholder="啧, ……算了" style="font-size:0.74rem;width:100%" /></label>
          <label class="muted tiny">回避话题 <input type="text" data-char-field="sp_avoidance_topics" value="${escapeAttr(spAvoid)}" placeholder="家庭, 过去" style="font-size:0.74rem;width:100%" /></label>
          <label class="muted tiny">沉默含义 <input type="text" data-char-field="sp_silence_meaning" value="${escapeAttr(spSilence)}" placeholder="在思考，不是冷漠" style="font-size:0.74rem;width:100%" /></label>
          <label class="muted tiny">压力下 <input type="text" data-char-field="sp_under_stress" value="${escapeAttr(spStress)}" placeholder="开始说短句" style="font-size:0.74rem;width:100%" /></label>
        </div>
      </details>
    </div>
  </article>`;
}

function shouldSkipCharRosterReRender(panelId) {
  const ae = document.activeElement;
  if (!ae?.closest) return false;
  if (!isWorldviewPanelEditEnabled(panelId)) return false;
  const root = document.getElementById(`view-${panelId}`);
  if (!root?.contains(ae)) return false;
  return Boolean(ae.closest("[data-char-edit-card]"));
}

let _charRosterPersistTimer = {};

function readCharEditCardFromDom(article) {
  const id = String(article?.dataset?.charEntityId ?? "").trim();
  if (!id) return null;
  const g = (field) => article.querySelector(`[data-char-field="${field}"]`);
  const name = (g("name")?.value ?? "").trim();
  const cast_role = (g("cast_role")?.value ?? "").trim() || "background";
  const one_line_hook = (g("one_line_hook")?.value ?? "").trim();
  const notes = (g("notes")?.value ?? "").trim();
  const aliasesRaw = (g("aliases")?.value ?? "").trim();
  const aliases = aliasesRaw
    .split(/[,，;；\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const skillsRaw = (g("notable_skills")?.value ?? "").trim();
  const notable_skills = skillsRaw
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const factionRaw = (g("faction_ids")?.value ?? "").trim();
  const faction_ids = factionRaw
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const home_region_id = (g("home_region_id")?.value ?? "").trim();
  // Speech profile
  const spSent = (g("sp_avg_sentence_length")?.value ?? "mixed").trim();
  const spExpr = (g("sp_emotional_expression")?.value ?? "direct").trim();
  const spConf = (g("sp_confrontation_style")?.value ?? "faces_it").trim();
  const spTics = (g("sp_verbal_tics")?.value ?? "").trim();
  const spAvoid = (g("sp_avoidance_topics")?.value ?? "").trim();
  const spSilence = (g("sp_silence_meaning")?.value ?? "").trim();
  const spStress = (g("sp_under_stress")?.value ?? "").trim();
  const speech_profile = {
    avg_sentence_length: spSent,
    emotional_expression: spExpr,
    confrontation_style: spConf,
    verbal_tics: spTics ? spTics.split(/[,，]/).map(s => s.trim()).filter(Boolean) : [],
    avoidance_topics: spAvoid ? spAvoid.split(/[,，]/).map(s => s.trim()).filter(Boolean) : [],
    silence_meaning: spSilence,
    under_stress: spStress,
    verbosity: "normal",
  };
  return { id, name, cast_role, one_line_hook, notes, aliases, notable_skills, faction_ids, home_region_id, speech_profile };
}

function persistCharRosterCards(panelId) {
  const rootId = panelId === "charProtagonists" ? "vizCharProtagonists" : "vizCharSupporting";
  const root = $(rootId);
  if (!root || !isWorldviewPanelEditEnabled(panelId)) return;
  let entities;
  try {
    entities = JSON.parse($("charEntitiesJson")?.value || "[]");
  } catch {
    return;
  }
  if (!Array.isArray(entities)) return;
  const cards = root.querySelectorAll("[data-char-edit-card]");
  cards.forEach((article) => {
    const patch = readCharEditCardFromDom(article);
    if (!patch) return;
    const idx = entities.findIndex((e) => String(e?.id ?? "").trim() === patch.id);
    if (idx < 0) return;
    const prev = entities[idx] && typeof entities[idx] === "object" ? { ...entities[idx] } : {};
    const next = {
      ...prev,
      id: patch.id,
      name: patch.name,
      cast_role: patch.cast_role,
      aliases: patch.aliases,
      notable_skills: patch.notable_skills,
    };
    if (patch.one_line_hook) next.one_line_hook = patch.one_line_hook;
    else delete next.one_line_hook;
    if (patch.notes) next.notes = patch.notes;
    else delete next.notes;
    if (patch.faction_ids.length) next.faction_ids = patch.faction_ids;
    else delete next.faction_ids;
    if (patch.home_region_id) next.home_region_id = patch.home_region_id;
    else delete next.home_region_id;
    if (patch.speech_profile && Object.values(patch.speech_profile).some(v => v && (!Array.isArray(v) || v.length))) {
      next.speech_profile = patch.speech_profile;
    }
    entities[idx] = next;
  });
  $("charEntitiesJson").value = JSON.stringify(entities, null, 2);
  setDirty(true);
  refreshCharactersVizFromForm();
}

function scheduleCharRosterPersist(panelId) {
  clearTimeout(_charRosterPersistTimer[panelId]);
  _charRosterPersistTimer[panelId] = setTimeout(() => persistCharRosterCards(panelId), 320);
}

function deleteCharacterEntityById(entityId) {
  const id = String(entityId ?? "").trim();
  if (!id) return;
  let entities;
  let relations;
  try {
    entities = JSON.parse($("charEntitiesJson")?.value || "[]");
    relations = JSON.parse($("charRelationsJson")?.value || "[]");
  } catch {
    toast("卡司 JSON 无效，无法删除");
    return;
  }
  if (!Array.isArray(entities)) return;
  const nextEnt = entities.filter((e) => String(e?.id ?? "").trim() !== id);
  const nextRel = Array.isArray(relations)
    ? relations.filter((r) => String(r?.source_id ?? "").trim() !== id && String(r?.target_id ?? "").trim() !== id)
    : [];
  $("charEntitiesJson").value = JSON.stringify(nextEnt, null, 2);
  $("charRelationsJson").value = JSON.stringify(nextRel, null, 2);
  setDirty(true);
  refreshCharactersVizFromForm();
  // Auto-save after deletion
  persistWorldFromForm().then(() => {
    toast("已删除该角色并清理相关关系边（已落盘）");
  }).catch(() => {
    toast("已删除（落盘失败，请手动保存）");
  });
}

function appendCharacterEntity(defaultRole) {
  let entities;
  try {
    entities = JSON.parse($("charEntitiesJson")?.value || "[]");
  } catch {
    toast("entities JSON 无效");
    return;
  }
  if (!Array.isArray(entities)) entities = [];
  const rid = defaultRole === "protagonist_core" ? uid("prot") : uid("sup");
  entities.push({
    id: rid,
    name: defaultRole === "protagonist_core" ? "新主角" : "新配角",
    cast_role: defaultRole,
    aliases: [],
    notable_skills: [],
  });
  $("charEntitiesJson").value = JSON.stringify(entities, null, 2);
  setDirty(true);
  refreshCharactersVizFromForm();
  persistWorldFromForm().then(() => {
    toast("已添加角色并落盘，可在卡片中填写详情");
  }).catch(() => {
    toast("已添加角色（落盘失败，请手动保存）");
  });
}

function renderCharCastCardHtml(ent, opts = {}) {
  const idRaw = String(ent?.id ?? "").trim();
  const id = escapeHtml(idRaw || "（无 id）");
  const name = escapeHtml(String(ent?.name ?? "").trim() || idRaw || "未命名");
  const roleRaw = String(ent?.cast_role ?? "").trim();
  const roleLab = escapeHtml(CAST_ROLE_LABELS[roleRaw] || roleRaw || "未标注");
  const hue = CAST_ROLE_HUES[roleRaw] ?? 210;
  const hookRaw = String(ent?.one_line_hook ?? "").trim();
  const notesRaw = String(ent?.notes ?? "").trim();
  const displayHook = hookRaw || notesRaw;
  const hook = displayHook ? escapeHtml(displayHook) : "";
  const hookLabel = hookRaw ? "叙事钩 · one_line_hook" : notesRaw ? "备注 · notes" : "叙事";
  const skills = Array.isArray(ent?.notable_skills) ? ent.notable_skills : [];
  const skillsLi = skills
    .map((s) => String(s).trim())
    .filter(Boolean)
    .slice(0, 14)
    .map((s) => `<li>${escapeHtml(s)}</li>`)
    .join("");
  const aliases = Array.isArray(ent?.aliases)
    ? ent.aliases.map((a) => String(a).trim()).filter(Boolean).slice(0, 8)
    : [];
  const aliasesStr = aliases.length ? escapeHtml(aliases.join(" · ")) : "";
  const fac = Array.isArray(ent?.faction_ids) ? ent.faction_ids.map((x) => String(x).trim()).filter(Boolean) : [];
  const home = String(ent?.home_region_id ?? "").trim();
  const facRow = fac.length
    ? `<div class="char-roster-meta-row"><span class="char-roster-k">faction_ids</span><code class="char-roster-code">${escapeHtml(
        fac.join(" · ")
      )}</code></div>`
    : "";
  const homeRow = home
    ? `<div class="char-roster-meta-row"><span class="char-roster-k">home_region_id</span><code class="char-roster-code">${escapeHtml(
        home
      )}</code></div>`
    : "";
  const metaBlock =
    facRow || homeRow
      ? `<section class="char-roster-block char-roster-block--meta" aria-label="引用锚点"><div class="char-roster-block-hd">边界 · 引用锚点</div><div class="char-roster-block-bd">${facRow}${homeRow}</div></section>`
      : "";
  const tierName2 = String(ent?.power_tier || "").trim();
  const profId2 = String(ent?.profession_id || "").trim();
  const tierIcons2 = {
    "拓雾者": "visibility", "凝痕者": "fingerprint", "塑脉师": "psychology",
    "锻脉师": "build", "域主": "domain", "逆理行者": "auto_awesome",
    "共鸣体": "hub", "同尘": "blur_on",
  };
  const roleIcons2 = {
    protagonist_core: "star", protagonist: "star",
    supporting_major: "person", supporting_minor: "person_outline",
    antagonist: "skull", background: "public",
  };
  const avIc = tierIcons2[tierName2]
    || tierIcons2[Object.keys(tierIcons2).find(k => tierName2.includes(k)) || ""]
    || (profId2 ? "school" : "")
    || roleIcons2[roleRaw] || (opts.variant === "supporting" ? "person" : "badge");
  return `<article class="char-roster-card" style="--char-card-hue:${hue}">
    <div class="char-roster-card-rim" aria-hidden="true"></div>
    <div class="char-roster-card-inner">
      <header class="char-roster-card-head">
        <div class="char-roster-avatar" aria-hidden="true"><span class="ms char-roster-avatar-ic">${avIc}</span></div>
        <div class="char-roster-head-main">
          <h3 class="char-roster-name">${name}</h3>
          <div class="char-roster-idline">
            <span class="char-roster-k">id</span><code class="char-roster-code">${id}</code>
            <button class="char-roster-detail-btn" onclick="event.stopPropagation();window.openCharDetail('${escapeAttr(idRaw)}')" title="查看角色详情（力量境界/职业/物品）">
              <span class="ms" aria-hidden="true" style="font-size:16px">info</span>
            </button>
          </div>
        </div>
        <span class="char-roster-role-chip" title="cast_role">${roleLab}</span>
      </header>
      ${(tierName2 || profId2) ? `<div class="char-roster-tags">
        ${tierName2 ? `<span class="char-roster-tier-tag" title="力量境界"><span class="ms" aria-hidden="true" style="font-size:14px;vertical-align:-3px">bolt</span> ${escapeHtml(tierName2)}</span>` : ''}
        ${profId2 ? `<span class="char-roster-prof-tag" title="职业"><span class="ms" aria-hidden="true" style="font-size:14px;vertical-align:-3px">school</span> ${escapeHtml(profId2)}</span>` : ''}
      </div>` : ''}
      ${
        aliasesStr
          ? `<section class="char-roster-block"><div class="char-roster-block-hd">别名 aliases</div><div class="char-roster-block-bd char-roster-aliases">${aliasesStr}</div></section>`
          : ""
      }
      ${
        displayHook
          ? `<section class="char-roster-block"><div class="char-roster-block-hd">${hookLabel}</div><div class="char-roster-block-bd char-roster-hook">${hook}</div></section>`
          : ""
      }
      ${
        skillsLi
          ? `<section class="char-roster-block char-roster-block--skills"><div class="char-roster-block-hd">特长 notable_skills</div><ul class="char-roster-skill-list">${skillsLi}</ul></section>`
          : ""
      }
      ${metaBlock}
    </div>
  </article>`;
}

function renderCharCastSubgrid(panelId, rootId, emptyId, list, variant = "protagonists") {
  const root = $(rootId);
  const emptyEl = $(emptyId);
  if (!root) return;
  const arr = Array.isArray(list) ? list : [];
  if (emptyEl) emptyEl.hidden = arr.length > 0;
  const editing = isWorldviewPanelEditEnabled(panelId);
  root.innerHTML = arr.length
    ? arr
        .map((e) => (editing ? renderCharCastCardEditHtml(e, variant) : renderCharCastCardHtml(e, { variant })))
        .join("")
    : "";
}

function countCharacterGraphEdges(entities, relations) {
  const list = Array.isArray(entities) ? entities.filter((e) => e && typeof e === "object") : [];
  const rels = Array.isArray(relations) ? relations.filter((r) => r && typeof r === "object") : [];
  const idToIdx = new Map();
  list.forEach((e, i) => {
    const id = String(e.id ?? "").trim();
    if (id && !idToIdx.has(id)) idToIdx.set(id, i);
  });
  let n = 0;
  for (const r of rels) {
    const s = String(r.source_id ?? "").trim();
    const t = String(r.target_id ?? "").trim();
    if (!s || !t || s === t) continue;
    if (idToIdx.get(s) === undefined || idToIdx.get(t) === undefined) continue;
    n += 1;
  }
  return n;
}

function buildCharacterRelationMermaid(entities, relations) {
  const list = Array.isArray(entities) ? entities.filter((e) => e && typeof e === "object") : [];
  const rels = Array.isArray(relations) ? relations.filter((r) => r && typeof r === "object") : [];
  if (!list.length) return mermaidFactionInit() + 'flowchart TB\n  empty["（无人物实体，无法绘图）"]';

  const idToIdx = new Map();
  list.forEach((e, i) => {
    const id = String(e.id ?? "").trim();
    if (id && !idToIdx.has(id)) idToIdx.set(id, i);
  });

  const lines = [
    "flowchart LR",
    "  classDef chP fill:#e0f2fe,color:#0c4a6e,stroke:#0284c7,stroke-width:1.5px",
    "  classDef chS fill:#ede9fe,color:#4c1d95,stroke:#7c3aed,stroke-width:1.2px",
    "  classDef chA fill:#ffe4e6,color:#881337,stroke:#e11d48,stroke-width:1.2px",
    "  classDef chB fill:#f1f5f9,color:#334155,stroke:#94a3b8",
  ];
  list.forEach((e, i) => {
    const lab = mermaidEscape(e.name || e.id || `角色${i + 1}`);
    lines.push(`  C${i}["${lab}"]`);
  });
  for (const r of rels) {
    const s = String(r.source_id ?? "").trim();
    const t = String(r.target_id ?? "").trim();
    if (!s || !t || s === t) continue;
    const si = idToIdx.get(s);
    const ti = idToIdx.get(t);
    if (si === undefined || ti === undefined) continue;
    const rt = String(r.relation_type ?? "关联").trim();
    const notes = String(r.notes ?? "").trim();
    const edgeLab = mermaidEscape(`${rt}${notes ? " · " + notes : ""}`);
    lines.push(`  C${si} -->|"${edgeLab}"| C${ti}`);
  }
  const clsProt = [];
  const clsSup = [];
  const clsAnt = [];
  const clsBg = [];
  list.forEach((e, i) => {
    const cr = String(e?.cast_role ?? "").trim();
    if (cr === "protagonist_core") clsProt.push(`C${i}`);
    else if (cr === "antagonist") clsAnt.push(`C${i}`);
    else if (["supporting_major", "supporting_minor"].includes(cr)) clsSup.push(`C${i}`);
    else clsBg.push(`C${i}`);
  });
  if (clsProt.length) lines.push(`  class ${clsProt.join(",")} chP`);
  if (clsSup.length) lines.push(`  class ${clsSup.join(",")} chS`);
  if (clsAnt.length) lines.push(`  class ${clsAnt.join(",")} chA`);
  if (clsBg.length) lines.push(`  class ${clsBg.join(",")} chB`);
  return mermaidFactionInit() + lines.join("\n");
}

function refreshCharRelationNetworkViz() {
  const host = $("charRelationNetworkHost");
  const stats = $("charRelationStats");
  if (!host) return;
  const parsed = tryParseCharacterEntitiesRelations();
  if (!parsed) {
    if (stats) stats.textContent = "";
    return;
  }
  if (stats) {
    const nEnt = parsed.entities.filter((e) => e && typeof e === "object" && String(e.id ?? "").trim()).length;
    const nEdge = countCharacterGraphEdges(parsed.entities, parsed.relations);
    stats.textContent = `${nEnt} 个实体 · ${nEdge} 条可绘制关系边（端点均存在于 entities）`;
  }
  // P2-10: Use interactive vis.js network instead of static Mermaid
  renderCharacterNetworkFromData(parsed.entities, parsed.relations, "charRelationNetworkHost");
}

/** 从当前表单刷新主角团 / 配角卡片；在「人物关系网络」页时刷新关系图 */
function refreshCharactersVizFromForm() {
  const parsed = tryParseCharacterEntitiesRelations();
  if (!parsed) return;
  const { entities } = parsed;
  const pro = entities.filter((e) => String(e?.cast_role ?? "").trim() === "protagonist_core");
  const sup = entities.filter((e) =>
    ["supporting_major", "supporting_minor", "antagonist"].includes(String(e?.cast_role ?? "").trim())
  );
  if (!shouldSkipCharRosterReRender("charProtagonists"))
    renderCharCastSubgrid("charProtagonists", "vizCharProtagonists", "charProtagonistsEmpty", pro, "protagonists");
  if (!shouldSkipCharRosterReRender("charSupporting"))
    renderCharCastSubgrid("charSupporting", "vizCharSupporting", "charSupportingEmpty", sup, "supporting");
  if (state.activeView === "charRelations") refreshCharRelationNetworkViz();
}

let _charVizTimer;
function scheduleCharactersVizFromForm() {
  clearTimeout(_charVizTimer);
  _charVizTimer = setTimeout(() => refreshCharactersVizFromForm(), 200);
}

function setupCharRosterInlineEditors() {
  const bindPanel = (viewId, panelId) => {
    const v = $(viewId);
    if (!v) return;
    v.addEventListener("input", (ev) => {
      if (!ev.target.closest("[data-char-edit-card]")) return;
      if (!isWorldviewPanelEditEnabled(panelId)) return;
      scheduleCharRosterPersist(panelId);
    });
    v.addEventListener("change", (ev) => {
      if (!ev.target.closest("[data-char-edit-card]")) return;
      if (!isWorldviewPanelEditEnabled(panelId)) return;
      if (ev.target.matches('select[data-char-field="cast_role"]')) scheduleCharRosterPersist(panelId);
    });
    v.addEventListener("click", (ev) => {
      const del = ev.target.closest("[data-char-delete-entity]");
      if (!del) return;
      if (!isWorldviewPanelEditEnabled(panelId)) return;
      ev.preventDefault();
      ev.stopPropagation();  // prevent card click from opening detail panel
      const eid = del.getAttribute("data-char-delete-entity");
      if (!eid || !confirm("确定从卡司删除该角色？相关关系边将一并删除。")) return;
      deleteCharacterEntityById(eid);
    });
  };
  bindPanel("view-charProtagonists", "charProtagonists");
  bindPanel("view-charSupporting", "charSupporting");
  $("btnCharProtagonistAdd")?.addEventListener("click", () => {
    if (!isWorldviewPanelEditEnabled("charProtagonists")) return;
    appendCharacterEntity("protagonist_core");
  });
  $("btnCharSupportingAdd")?.addEventListener("click", () => {
    if (!isWorldviewPanelEditEnabled("charSupporting")) return;
    appendCharacterEntity("supporting_major");
  });
}

function hasWorldsInSelect() {
  const sel = $("worldSelect");
  if (!sel || !sel.options.length) return false;
  const v = sel.value;
  return Boolean(v && v.trim());
}

function updateEmptyState() {
  const main = $("mainArea");
  const empty = $("emptyState");
  if (!main || !empty) return;
  const has = hasWorldsInSelect();
  main.classList.toggle("main--empty", !has);
  const layout = document.querySelector(".layout");
  if (layout) layout.classList.toggle("layout--no-world", !has);
  const sel = $("worldSelect");
  if (sel) sel.disabled = !has;
}

async function createWorldFlow() {
  const name = prompt("新世界名称？", "我的世界观");
  if (!name || !name.trim()) return;
  const data = await api("/api/worlds", {
    method: "POST",
    body: JSON.stringify({ name: name.trim() }),
  });
  await refreshWorldSelect(data.world.meta.id);
  updateEmptyState();
  await loadWorld(data.world.meta.id);
  toast("世界已创建");
}

async function renameCurrentWorldFlow() {
  if (!state.world) return toast("请先选择世界");
  const cur = state.world.meta.name;
  const name = prompt("新的世界显示名称？", cur);
  if (!name || !name.trim()) return;
  const trimmed = name.trim();
  if (trimmed === cur) return;
  const w = await api(`/api/worlds/${state.world.meta.id}`, {
    method: "PATCH",
    body: JSON.stringify({ name: trimmed }),
  });
  state.world = w;
  worldToForm(w);
  setDirty(false);
  await refreshWorldSelect(w.meta.id);
  refreshContextPanel();
  refreshOutlineHeader();
  refreshFilesView();
  refreshSearchView();
  refreshWorldTabTitle();
  toast("已重命名（目录 id 未变）");
}

async function deleteCurrentWorldFlow() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  const name = state.world.meta.name;
  if (
    !confirm(
      `确定删除世界「${name}」？\n目录：worlds/${id}/\n将删除 world.json、world.md、大纲与对话记录等全部文件，且不可恢复。`
    )
  )
    return;
  await api(`/api/worlds/${id}`, { method: "DELETE" });
  toast("世界已删除");
  state.messages = [];
  state.charMessages = [];
  state.storyMessages = [];
  renderMessages();
  renderCharMessages();
  renderStoryMessages();
  await refreshWorldSelect();
  updateEmptyState();
  if (hasWorldsInSelect()) await loadWorld($("worldSelect").value);
  else {
    state.world = null;
    worldToForm(null);
    setDirty(false);
    refreshWorldTabTitle();
  }
}

/** 派系图：不压缩宽度、略放大字号，便于阅读 */
function mermaidFactionInit() {
  return (
    "%%{init:" +
    JSON.stringify({
      flowchart: {
        useMaxWidth: false,
        padding: 22,
        nodeSpacing: 56,
        rankSpacing: 58,
        curve: "basis",
      },
      themeVariables: {
        fontSize: "16px",
        fontFamily: "system-ui, 'Noto Sans SC', sans-serif",
      },
    }) +
    "}%%\n"
  );
}

function mermaidEscape(s) {
  return String(s || "")
    .replace(/"/g, "'")
    .replace(/[[\]]/g, " ")
    .replace(/\n/g, " ")
    .replace(/\|/g, "·")
    .slice(0, 56);
}


/** 职业晋升：相邻境界相同 professions[].id 视为同线晋升；跨多境为虚线 */
function buildProfessionPromotionMermaid(tiers, ps) {
  const init = mermaidFactionInit();
  const tierList = Array.isArray(tiers) ? tiers : [];
  const byTier = Array.isArray(ps?.by_tier) ? ps.by_tier : [];
  const n = tierList.length;
  if (!n) return init + 'flowchart TB\n  promoEmpty["（无境界数据）"]';

  const lines = ["flowchart TB"];
  lines.push("  classDef profNode fill:#eef2ff,color:#1e293b,stroke:#6366f1,stroke-width:1.2px");
  lines.push("  classDef profFaction fill:#fffbeb,color:#92400e,stroke:#f59e0b,stroke-width:1.2px");
  lines.push("  classDef profGhost fill:#f1f5f9,color:#64748b,stroke:#94a3b8,stroke-dasharray:4 3");

  const factionClassNodes = [];
  const normalClassNodes = [];
  const ghostClassNodes = [];
  const idToOccurrences = new Map();

  for (let i = 0; i < n; i++) {
    const tierName = (tierList[i]?.name || "").trim() || `境 ${i + 1}`;
    const profs = (byTier[i]?.professions) || [];
    const seenRid = new Set();
    const rows = [];
    for (let j = 0; j < profs.length; j++) {
      const p = profs[j] || {};
      const rawId = String(p.id ?? "").trim();
      if (rawId) {
        if (seenRid.has(rawId)) continue;
        seenRid.add(rawId);
      }
      rows.push({ p, rawId });
    }

    const subLabel = mermaidEscape(`${i + 1}·${tierName}`);
    lines.push(`  subgraph sg${i}["${subLabel}"]`);
    if (!rows.length) {
      const eid = `sg${i}_empty`;
      lines.push(`    ${eid}["（本境无职业）"]`);
      ghostClassNodes.push(eid);
    } else {
      rows.forEach((row, k) => {
        const nodeId = `pr${i}_${k}`;
        const { p, rawId } = row;
        const nm = (p.name || "").trim();
        const dispName = mermaidEscape(nm || rawId || "未命名");
        const idPart = rawId ? mermaidEscape(rawId.slice(0, 44)) : "无id";
        let label = `${dispName}<br/>id·${idPart}`;
        const fac = String(p.exclusive_faction_id ?? "").trim();
        if (fac) label += `<br/>派系 ${mermaidEscape(fac.slice(0, 26))}`;
        lines.push(`    ${nodeId}["${label}"]`);
        if (fac) factionClassNodes.push(nodeId);
        else normalClassNodes.push(nodeId);

        if (rawId) {
          const arr = idToOccurrences.get(rawId) || [];
          arr.push({ tierIdx: i, nodeId });
          idToOccurrences.set(rawId, arr);
        }
      });
    }
    lines.push("  end");
  }

  let edgeCount = 0;
  idToOccurrences.forEach((occ) => {
    occ.sort((a, b) => a.tierIdx - b.tierIdx);
    for (let k = 1; k < occ.length; k++) {
      const prev = occ[k - 1];
      const cur = occ[k];
      const gap = cur.tierIdx - prev.tierIdx;
      if (gap < 1) continue;
      if (gap === 1) {
        lines.push(`  ${prev.nodeId} -->|"晋升"| ${cur.nodeId}`);
        edgeCount++;
      } else if (gap > 1) {
        const gl = mermaidEscape(`跨${gap}境`);
        lines.push(`  ${prev.nodeId} -.->|"${gl}"| ${cur.nodeId}`);
        edgeCount++;
      }
    }
  });

  if (ghostClassNodes.length) lines.push(`  class ${ghostClassNodes.join(",")} profGhost`);
  if (normalClassNodes.length) lines.push(`  class ${normalClassNodes.join(",")} profNode`);
  if (factionClassNodes.length) lines.push(`  class ${factionClassNodes.join(",")} profFaction`);

  if (!idToOccurrences.size) {
    lines.push('  promoHint["（各境职业均未填写 id，无法推断晋升线）"]');
  } else if (edgeCount === 0) {
    lines.push('  promoHint2["相邻境界暂无相同 id；多境复用同一 id 即可显示晋升箭头"]');
  }

  return init + lines.join("\n");
}

function refreshProfessionPromotionViz() {
  const host = $("vizProfessionPromoHost");
  if (!host) return;
  const w = state.world;
  if (!w?.power_system?.tiers?.length) {
    host.innerHTML = "";
    return;
  }
  const tiers = w.power_system.tiers;
  const ps = w.power_system.profession_system || {};
  void drawMermaidHost(host, buildProfessionPromotionMermaid(tiers, ps));
}

const TIER_BLOCK_ICONS = {
  caps: "bolt",
  lims: "gavel",
  ex: "emoji_objects",
  mean: "diamond",
  fx: "flare",
  bind: "link",
};

function tierBlockHead(title, variant) {
  const ic = TIER_BLOCK_ICONS[variant] || "label";
  return `<header class="tier-viz-block__head">
    <span class="ms tier-viz-block__ic" aria-hidden="true">${ic}</span>
    <h4 class="tier-viz-h">${escapeHtml(title)}</h4>
  </header>`;
}

/** 看板：列表字段块（带图标头） */
function htmlStrListBlock(title, items, emptyHint, variant) {
  const arr = Array.isArray(items) ? items.map((x) => String(x).trim()).filter(Boolean) : [];
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  if (!arr.length) {
    return `<section class="tier-viz-block${vcls}"${dataV}>
      ${tierBlockHead(title, variant)}
      <div class="tier-viz-block__body"><p class="tier-viz-empty">${escapeHtml(emptyHint)}</p></div>
    </section>`;
  }
  return `<section class="tier-viz-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body">
      <ul class="tier-viz-ul">${arr.map((x) => `<li class="tier-viz-li"><span class="tier-viz-li-text">${escapeHtml(x)}</span></li>`).join("")}</ul>
    </div>
  </section>`;
}

function htmlProseBlock(title, text, emptyHint, variant) {
  const t = (text || "").trim();
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  if (!t) {
    return `<section class="tier-viz-block${vcls}"${dataV}>
      ${tierBlockHead(title, variant)}
      <div class="tier-viz-block__body"><p class="tier-viz-empty">${escapeHtml(emptyHint)}</p></div>
    </section>`;
  }
  return `<section class="tier-viz-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body"><p class="tier-viz-prose">${escapeHtml(t).replace(/\n/g, "<br/>")}</p></div>
  </section>`;
}

// escapeAttr is already defined above (line ~309) — skip duplicate for ES module compatibility

/** 物品档位卡片内：可编辑字段（与 collectItemGradesFromViz 的 data-item-field 对应） */
function htmlItemGradeEditableField(fieldKey, title, value, placeholder, variant) {
  const v = (value ?? "").toString();
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  const ph = escapeHtml(placeholder || "");
  const rows = fieldKey === "examples" ? 4 : 5;
  return `<section class="tier-viz-block item-grade-edit-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body">
      <textarea class="item-grade-edit-ta" rows="${rows}" data-item-field="${escapeHtml(
    fieldKey
  )}" spellcheck="true" placeholder="${ph}">${escapeHtml(v)}</textarea>
    </div>
  </section>`;
}

function collectItemGradesFromViz() {
  const root = $("vizItemGradesRoot");
  if (!root) return null;
  const cards = [...root.querySelectorAll(".item-grade-viz[data-item-grade-index]")].sort(
    (a, b) =>
      Number.parseInt(a.getAttribute("data-item-grade-index") || "0", 10) -
      Number.parseInt(b.getAttribute("data-item-grade-index") || "0", 10)
  );
  if (!cards.length) return null;
  return cards.map((card) => {
    const valOf = (field) =>
      (
        card.querySelector(`textarea[data-item-field="${field}"],input[data-item-field="${field}"]`)
          ?.value ?? ""
      ).toString();
    const name = valOf("name").trim() || "未命名档位";
    const examples = valOf("examples")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    return {
      name,
      rarity_narrative: valOf("rarity_narrative").trim(),
      typical_effects: valOf("typical_effects").trim(),
      binding_rules: valOf("binding_rules").trim(),
      examples,
    };
  });
}

let _itemGradeVizSyncTimer;
function scheduleSyncItemGradesFromVizToStateAndJson() {
  clearTimeout(_itemGradeVizSyncTimer);
  _itemGradeVizSyncTimer = setTimeout(() => {
    const g = collectItemGradesFromViz();
    if (g == null || !state.world) return;
    state.world.item_quality_system = state.world.item_quality_system || {};
    state.world.item_quality_system.grades = g;
    const ta = $("itemGradesJson");
    if (ta) ta.value = JSON.stringify(g, null, 2);
    setDirty(true);
  }, 200);
}

function scheduleItemGradesVizFromForm() {
  try {
    const grades = JSON.parse($("itemGradesJson")?.value || "[]");
    if (!state.world || !Array.isArray(grades)) return;
    const w = structuredClone(state.world);
    w.item_quality_system = w.item_quality_system || {};
    w.item_quality_system.grades = grades;
    renderItemGradeDashboardModules(w);
    applyAllWorldviewEditModes();
  } catch (_) {
    /* JSON 未完成输入时不刷新卡片 */
  }
}

function deletePowerTier(idx) {
  if (!state.world?.power_system?.tiers) return;
  const tier = state.world.power_system.tiers[idx];
  if (!tier) return;
  const name = tier.name || `境 ${idx + 1}`;
  if (!confirm(`确定删除境界「${name}」吗？此操作不可撤销。`)) return;
  state.world.power_system.tiers.splice(idx, 1);
  setDirty(true);
  toast(`已删除境界「${name}」`);
  // Re-render the system tab
  if (typeof renderPowerTierSystemModules === 'function') renderPowerTierSystemModules(state.world);
  if (typeof renderPowerTierSkillTreeModules === 'function') renderPowerTierSkillTreeModules(state.world);
}
window.deletePowerTier = deletePowerTier;

/** 境界体系卡片：可编辑字段（data-power-field） */
function htmlPowerTierEditableField(fieldKey, title, value, placeholder, variant, rows) {
  const v = (value ?? "").toString();
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  const ph = escapeHtml(placeholder || "");
  const r = rows || 4;
  return `<section class="tier-viz-block power-tier-edit-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body">
      <textarea class="power-tier-edit-ta" rows="${r}" data-power-field="${escapeHtml(
    fieldKey
  )}" spellcheck="true" placeholder="${ph}">${escapeHtml(v)}</textarea>
    </div>
  </section>`;
}

function collectPowerTiersFromViz() {
  const sysRoot = $("vizPowerSystemModules");
  if (!sysRoot) return null;
  const sysCards = [...sysRoot.querySelectorAll(".power-tier-viz--editable[data-power-tier-index]")].sort(
    (a, b) =>
      Number.parseInt(a.getAttribute("data-power-tier-index") || "0", 10) -
      Number.parseInt(b.getAttribute("data-power-tier-index") || "0", 10)
  );
  if (!sysCards.length) return null;
  const treeRoot = $("vizPowerSkillTreeModules");
  let base = [];
  try {
    const p = JSON.parse($("powerTiersJson")?.value || "[]");
    if (Array.isArray(p)) base = structuredClone(p);
  } catch {
    base = Array.isArray(state.world?.power_system?.tiers)
      ? structuredClone(state.world.power_system.tiers)
      : [];
  }
  const strOf = (card, f) =>
    (
      card.querySelector(`textarea[data-power-field="${f}"],input[data-power-field="${f}"]`)?.value ?? ""
    ).toString();
  const splitLines = (card, f) =>
    strOf(card, f)
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  return sysCards.map((card) => {
    const idx = Number.parseInt(card.getAttribute("data-power-tier-index") || "0", 10);
    const prev = base[idx] && typeof base[idx] === "object" ? base[idx] : {};
    const name = strOf(card, "name").trim() || `境 ${idx + 1}`;
    const description = strOf(card, "description").trim();
    let skill_tree = Array.isArray(prev.skill_tree) ? prev.skill_tree : [];
    let subclass_paths = Array.isArray(prev.subclass_paths) ? prev.subclass_paths : [];
    const treeCard = treeRoot?.querySelector(
      `.power-tier-viz--trees[data-power-tier-index="${idx}"]`
    );
    if (treeCard) {
      const skTxt = treeCard.querySelector('[data-power-tree-part="skill_tree"]')?.value ?? "";
      try {
        const parsed = JSON.parse(skTxt.trim() || "[]");
        if (Array.isArray(parsed)) skill_tree = parsed;
      } catch (_) {
        /* 保持原 skill_tree */
      }
      const scTxt = treeCard.querySelector('[data-power-tree-part="subclass_paths"]')?.value ?? "";
      try {
        const parsed = JSON.parse(scTxt.trim() || "[]");
        if (Array.isArray(parsed)) subclass_paths = parsed;
      } catch (_) {
        /* 保持原 subclass_paths */
      }
    }
    return {
      ...prev,
      name,
      description,
      typical_capabilities: splitLines(card, "typical_capabilities"),
      limitations: splitLines(card, "limitations"),
      activation_rules: strOf(card, "activation_rules").trim(),
      examples: splitLines(card, "examples"),
      skill_tree,
      subclass_paths,
    };
  });
}

let _powerTierVizSyncTimer;
function scheduleSyncPowerTiersFromVizToStateAndJson() {
  clearTimeout(_powerTierVizSyncTimer);
  _powerTierVizSyncTimer = setTimeout(() => {
    const tiers = collectPowerTiersFromViz();
    if (tiers == null || !state.world) return;
    state.world.power_system = state.world.power_system || {};
    state.world.power_system.tiers = tiers;
    const ta = $("powerTiersJson");
    if (ta) ta.value = JSON.stringify(tiers, null, 2);
    setDirty(true);
    document.querySelectorAll("#vizPowerSkillTreeModules .power-tier-viz--trees").forEach((el) => {
      const idx = Number.parseInt(el.getAttribute("data-power-tier-index") || "0", 10);
      const tn = tiers[idx]?.name;
      const titleEl = el.querySelector(".viz-module-title");
      if (titleEl && tn != null) titleEl.textContent = tn || `境 ${idx + 1}`;
    });
    updatePowerTierSkillTreePreviews(tiers);
    updatePowerProfessionPreviews(tiers, state.world.power_system.profession_system);
    refreshPowerProfessionCountBadge(state.world);
    document.querySelectorAll("#vizPowerProfessionModules .power-tier-viz--professions").forEach((el) => {
      const idx = Number.parseInt(el.getAttribute("data-power-tier-index") || "0", 10);
      const tn = tiers[idx]?.name;
      const titleEl = el.querySelector(".viz-module-title");
      if (titleEl && tn != null) titleEl.textContent = tn || `境 ${idx + 1}`;
    });
  }, 220);
}

function collectHistoryEventsFromViz() {
  const root = $("historyMajorTimeline");
  if (!root) return null;
  const rows = [...root.querySelectorAll(".hist-tl-row--editable[data-history-event-index]")].sort(
    (a, b) =>
      Number.parseInt(a.getAttribute("data-history-event-index") || "0", 10) -
      Number.parseInt(b.getAttribute("data-history-event-index") || "0", 10)
  );
  if (!rows.length) return null;
  let base = [];
  try {
    const p = JSON.parse($("historyJson")?.value || "[]");
    if (Array.isArray(p)) base = structuredClone(p);
  } catch {
    base = Array.isArray(state.world?.history?.events)
      ? structuredClone(state.world.history.events)
      : [];
  }
  const val = (row, f) =>
    (row.querySelector(`[data-hist-field="${f}"]`)?.value ?? "").toString();
  const splitLines = (row, f) =>
    val(row, f)
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  return rows.map((row) => {
    const idx = Number.parseInt(row.getAttribute("data-history-event-index") || "0", 10);
    const prev = base[idx] && typeof base[idx] === "object" ? base[idx] : {};
    return {
      ...prev,
      when: val(row, "when").trim(),
      title: val(row, "title").trim(),
      summary: val(row, "summary").trim(),
      consequences: splitLines(row, "consequences"),
      linked_faction_ids: splitLines(row, "linked_faction_ids"),
    };
  });
}

let _histTimelineSyncTimer;
function scheduleSyncHistoryEventsFromVizToStateAndJson() {
  clearTimeout(_histTimelineSyncTimer);
  _histTimelineSyncTimer = setTimeout(() => {
    const events = collectHistoryEventsFromViz();
    if (events == null || !state.world) return;
    state.world.history = state.world.history || {};
    state.world.history.events = events;
    const ta = $("historyJson");
    if (ta) ta.value = JSON.stringify(events, null, 2);
    setDirty(true);
    void drawMermaidHost($("vizHistoryHost"), buildHistoryMermaid(events));
  }, 220);
}

function clampRefPercent(n) {
  const x = Number(n);
  if (Number.isFinite(x)) return Math.min(100, Math.max(0, Math.round(x)));
  return 55;
}

function htmlSkillTreeSection(title, nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  if (!list.length) return "";
  const lis = list
    .map((node) => {
      const pr = (node.prereq_ids || []).filter(Boolean).join("、");
      const br = node.branch
        ? `<span class="skill-branch">${escapeHtml(String(node.branch))}</span>`
        : "";
      const sum = (node.summary || "").trim();
      return `<li class="skill-node-li"><code class="skill-id">${escapeHtml(
        (node.id || "").toString()
      )}</code> <strong>${escapeHtml((node.name || "").toString())}</strong> ${br}${
        pr ? `<div class="muted tiny skill-prereq">前置：${escapeHtml(pr)}</div>` : ""
      }${
        sum
          ? `<div class="skill-sum">${escapeHtml(sum).replace(/\n/g, "<br/>")}</div>`
          : ""
      }</li>`;
    })
    .join("");
  return `<div class="skill-tree-section"><h4 class="skill-tree-h">${escapeHtml(title)}</h4><ul class="skill-tree-ul">${lis}</ul></div>`;
}

function htmlSubclassPaths(subs) {
  const list = Array.isArray(subs) ? subs : [];
  if (!list.length) return "";
  const cards = list
    .map((sc) => {
      const title = `${(sc.name || sc.id || "子类").toString()} · 技能树`;
      const inner = htmlSkillTreeSection(title, sc.skill_tree);
      const tag = (sc.tagline || "").toString().trim();
      const fl = (sc.flavor || "").toString().trim();
      return `<div class="subclass-card"><div class="subclass-card-head"><strong>${escapeHtml(
        (sc.name || sc.id || "").toString()
      )}</strong>${
        tag ? `<span class="muted tiny subclass-tagline">${escapeHtml(tag)}</span>` : ""
      }</div>${
        fl ? `<p class="subclass-flavor">${escapeHtml(fl).replace(/\n/g, "<br/>")}</p>` : ""
      }${inner}</div>`;
    })
    .join("");
  return `<div class="subclass-paths-wrap"><h4 class="skill-tree-h">子类职业</h4><div class="subclass-cards">${cards}</div></div>`;
}

/** 通用技能树：仅预览区内部 HTML（无外层标题，便于嵌入分栏） */
function htmlSkillTreePreviewInner(nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  if (!list.length) {
    return `<div class="skill-tree-preview-empty muted tiny">尚无节点。JSON 中每项建议含 id、name、summary、prereq_ids（前置节点 id 数组）、branch。</div>`;
  }
  const lis = list
    .map((node) => {
      const pr = (node.prereq_ids || []).filter(Boolean).join("、");
      const br = node.branch
        ? `<span class="skill-branch">${escapeHtml(String(node.branch))}</span>`
        : "";
      const sum = (node.summary || "").trim();
      return `<li class="skill-node-li"><code class="skill-id">${escapeHtml(
        (node.id || "").toString()
      )}</code> <strong>${escapeHtml((node.name || "").toString())}</strong> ${br}${
        pr ? `<div class="muted tiny skill-prereq">前置：${escapeHtml(pr)}</div>` : ""
      }${
        sum
          ? `<div class="skill-sum">${escapeHtml(sum).replace(/\n/g, "<br/>")}</div>`
          : ""
      }</li>`;
    })
    .join("");
  return `<ul class="skill-tree-ul skill-tree-ul--preview">${lis}</ul>`;
}

function professionMapFromList(list) {
  const m = Object.create(null);
  for (const p of list || []) {
    const id = String(p?.id ?? "").trim();
    if (id) m[id] = p;
  }
  return m;
}

function resolveFactionLabel(w, fid) {
  const id = String(fid ?? "").trim();
  if (!id) return "";
  const ent = w?.factions?.entities?.find((e) => String(e?.id ?? "").trim() === id);
  if (ent && (ent.name || "").trim()) return `${String(ent.name).trim()}（${id}）`;
  return id;
}

function htmlProfessionsPreviewInner(professions, world) {
  const list = Array.isArray(professions) ? professions : [];
  if (!list.length) {
    return `<div class="skill-tree-preview-empty muted tiny">尚无职业。JSON 每项建议含 id、name、可选 tagline、flavor、exclusive_faction_id（派系 id）、notes。</div>`;
  }
  return list
    .map((p) => {
      const fid = String(p.exclusive_faction_id ?? "").trim();
      const fac = fid
        ? `<span class="profession-fac-badge" title="派系专属职业">派系：${escapeHtml(resolveFactionLabel(world, fid))}</span>`
        : "";
      const tg = (p.tagline || "").toString().trim();
      const fl = (p.flavor || "").toString().trim();
      const notes = (p.notes || "").toString().trim();
      return `<div class="profession-card--preview"><div class="profession-card-head"><code class="skill-id">${escapeHtml(
        (p.id || "").toString()
      )}</code> <strong>${escapeHtml((p.name || "").toString())}</strong>${fac ? ` ${fac}` : ""}</div>${
        tg ? `<span class="muted tiny subclass-tagline">${escapeHtml(tg)}</span>` : ""
      }${
        fl ? `<p class="subclass-flavor">${escapeHtml(fl).replace(/\n/g, "<br/>")}</p>` : ""
      }${
        notes ? `<p class="muted tiny">${escapeHtml(notes).replace(/\n/g, "<br/>")}</p>` : ""
      }</div>`;
    })
    .join("");
}

function htmlSubclassPathsPreviewInner(subs, tierProfessions, world) {
  const list = Array.isArray(subs) ? subs : [];
  const pmap = professionMapFromList(tierProfessions);
  if (!list.length) {
    return `<div class="skill-tree-preview-empty muted tiny">尚无子类。每项含 id、name、可选 tagline、flavor、profession_id（对齐本境职业 id）、skill_tree。</div>`;
  }
  const cards = list
    .map((sc) => {
      const inner = htmlSkillTreePreviewInner(sc.skill_tree);
      const tag = (sc.tagline || "").toString().trim();
      const fl = (sc.flavor || "").toString().trim();
      const pid = String(sc.profession_id ?? "").trim();
      let profLine = "";
      if (pid) {
        const hit = pmap[pid];
        const cls = hit ? "subclass-prof-line" : "subclass-prof-line subclass-prof-line--warn";
        const txt = hit
          ? `职业体系：${escapeHtml((hit.name || pid).toString())}（id：${escapeHtml(pid)}）`
          : `profession_id：${escapeHtml(pid)}（本境职业表中未找到）`;
        profLine = `<div class="muted tiny ${cls}">← ${txt}</div>`;
      }
      return `<div class="subclass-card subclass-card--preview"><div class="subclass-card-head"><strong>${escapeHtml(
        (sc.name || sc.id || "").toString()
      )}</strong>${
        tag ? `<span class="muted tiny subclass-tagline">${escapeHtml(tag)}</span>` : ""
      }</div>${profLine}${
        fl ? `<p class="subclass-flavor">${escapeHtml(fl).replace(/\n/g, "<br/>")}</p>` : ""
      }${inner}</div>`;
    })
    .join("");
  return `<div class="subclass-cards subclass-cards--preview">${cards}</div>`;
}

function updatePowerTierSkillTreePreviews(tiers) {
  if (!Array.isArray(tiers)) return;
  const root = $("vizPowerSkillTreeModules");
  if (!root) return;
  const w = state.world;
  const byProf = w?.power_system?.profession_system?.by_tier;
  tiers.forEach((tier, idx) => {
    const card = root.querySelector(`.power-tier-viz--trees[data-power-tier-index="${idx}"]`);
    if (!card) return;
    const tierProfs = (byProf && byProf[idx] && byProf[idx].professions) || [];
    const g = card.querySelector('[data-skill-preview="general"]');
    if (g) {
      g.innerHTML = `<div class="skill-tree-preview-surface">${htmlSkillTreePreviewInner(tier.skill_tree)}</div>`;
    }
    const s = card.querySelector('[data-skill-preview="subclasses"]');
    if (s) {
      s.innerHTML = `<div class="skill-tree-preview-surface skill-tree-preview-surface--sub">${htmlSubclassPathsPreviewInner(
        tier.subclass_paths,
        tierProfs,
        w
      )}</div>`;
    }
  });
}

function updatePowerProfessionPreviews(tiers, professionSystem) {
  if (!Array.isArray(tiers)) return;
  const root = $("vizPowerProfessionModules");
  if (!root) return;
  const w = state.world;
  const byProf = professionSystem?.by_tier || [];
  tiers.forEach((tier, idx) => {
    const card = root.querySelector(`.power-tier-viz--professions[data-power-tier-index="${idx}"]`);
    if (!card) return;
    const wrap = card.querySelector('[data-profession-preview="list"]');
    if (!wrap) return;
    const profs = (byProf[idx] && byProf[idx].professions) || [];
    wrap.innerHTML = `<div class="profession-preview-surface">${htmlProfessionsPreviewInner(profs, w)}</div>`;
  });
}

/** 从助手回复里的 Markdown 代码块解析 attribute_system（支持根级包一层 attribute_system 或直接 summary+stats）。 */
function parseAttributeSystemFromAssistantReply(reply) {
  if (!reply || typeof reply !== "string") return null;
  const re = /```(?:json)?\s*([\s\S]*?)```/gi;
  const blocks = [];
  let m;
  while ((m = re.exec(reply)) !== null) blocks.push(m[1].trim());
  for (let i = blocks.length - 1; i >= 0; i--) {
    try {
      const obj = JSON.parse(blocks[i]);
      if (!obj || typeof obj !== "object") continue;
      if (obj.attribute_system && typeof obj.attribute_system === "object") {
        return obj.attribute_system;
      }
      if (
        Array.isArray(obj.stats) &&
        !obj.tiers &&
        !obj.grades &&
        !obj.entities &&
        !obj.regions &&
        !obj.geography &&
        !obj.events &&
        !obj.factions
      ) {
        if (
          obj.stats.length > 0 ||
          typeof obj.summary === "string" ||
          typeof obj.design_notes === "string" ||
          (Array.isArray(obj.tier_average_profiles) && obj.tier_average_profiles.length > 0)
        ) {
          return obj;
        }
      }
    } catch (_) {
      /* 非 JSON 块 */
    }
  }
  return null;
}

function normalizeAttrStatFromExtract(row, idx) {
  if (!row || typeof row !== "object") return null;
  const id = String(row.id ?? row.key ?? `stat_${idx}`).trim().slice(0, 80);
  const name = String(row.name ?? row.title ?? row.label ?? id).trim().slice(0, 200);
  if (!name) return null;
  const abbreviation = String(row.abbreviation ?? row.abbr ?? "").trim().slice(0, 32);
  const intro = String(row.intro ?? row.brief ?? "").trim().slice(0, 800);
  const description = String(row.description ?? row.desc ?? "").trim().slice(0, 4000);
  const scale = String(row.scale ?? "").trim().slice(0, 200);
  const typical_use = String(row.typical_use ?? row.use ?? "").trim().slice(0, 200);
  const rawRef = row.reference_percent ?? row.percent ?? row.reference;
  let reference_percent = 55;
  if (typeof rawRef === "number" && Number.isFinite(rawRef)) {
    reference_percent = Math.min(100, Math.max(0, Math.round(rawRef)));
  } else if (rawRef != null && String(rawRef).trim()) {
    const n = parseFloat(String(rawRef).trim());
    if (Number.isFinite(n)) reference_percent = Math.min(100, Math.max(0, Math.round(n)));
  }
  return {
    id: id || `stat_${idx}`,
    name,
    abbreviation,
    intro,
    description,
    scale,
    typical_use,
    reference_percent,
    radar_icon: String(row.radar_icon ?? row.icon_glyph ?? row.radarGlyph ?? "").trim().slice(0, 64),
  };
}

function normalizeTierAverageFromExtract(row, idx) {
  if (!row || typeof row !== "object") return null;
  const tier_name = String(row.tier_name ?? row.name ?? row.tier ?? "").trim().slice(0, 200);
  if (!tier_name) return null;
  const raw = row.averages ?? row.values ?? row.means ?? {};
  const averages = {};
  if (raw && typeof raw === "object") {
    for (const [k, v] of Object.entries(raw)) {
      const key = String(k).trim().slice(0, 80);
      if (!key) continue;
      const n = typeof v === "number" ? v : parseFloat(String(v).trim());
      if (!Number.isFinite(n)) continue;
      averages[key] = Math.min(100, Math.max(0, Math.round(n)));
    }
  }
  return { tier_name, averages };
}

/** 将解析结果合并进 state.world.attribute_system；有变更则返回 true。 */
function mergeAttributeSystemFromAssistantReply(reply) {
  if (!state.world || !reply) return false;
  const extracted = parseAttributeSystemFromAssistantReply(reply);
  if (!extracted || typeof extracted !== "object") return false;
  const cur = state.world.attribute_system || {
    summary: "",
    design_notes: "",
    stats: [],
    tier_average_profiles: [],
  };
  const summary =
    typeof extracted.summary === "string" ? extracted.summary.trim() : (cur.summary ?? "").trim();
  const design_notes =
    typeof extracted.design_notes === "string"
      ? extracted.design_notes.trim()
      : (cur.design_notes ?? "").trim();
  let stats = Array.isArray(cur.stats) ? [...cur.stats] : [];
  if (Array.isArray(extracted.stats) && extracted.stats.length > 0) {
    stats = extracted.stats.map((row, i) => normalizeAttrStatFromExtract(row, i)).filter(Boolean);
  }
  let tier_average_profiles = Array.isArray(cur.tier_average_profiles)
    ? [...cur.tier_average_profiles]
    : [];
  if (Array.isArray(extracted.tier_average_profiles) && extracted.tier_average_profiles.length > 0) {
    tier_average_profiles = extracted.tier_average_profiles
      .map((row, i) => normalizeTierAverageFromExtract(row, i))
      .filter(Boolean);
  }
  const meaningful =
    (summary && summary.length > 0) ||
    (design_notes && design_notes.length > 0) ||
    (stats && stats.length > 0) ||
    (tier_average_profiles && tier_average_profiles.length > 0);
  if (!meaningful) return false;
  const prev = JSON.stringify(cur);
  const next = { summary, design_notes, stats, tier_average_profiles };
  if (JSON.stringify(next) === prev) return false;
  state.world.attribute_system = next;
  return true;
}

/** 雷达轴端 Material Symbols ligature；stats 可设 radar_icon，否则按 id/name 启发式 */
function pickAttrStatGlyph(stat) {
  const raw = ((stat.radar_icon || stat.icon_glyph || "") + "").trim();
  if (raw && /^[a-z0-9_]+$/i.test(raw)) return raw.slice(0, 64);
  const t = [stat.id, stat.name, stat.abbreviation || ""].join(" ").toLowerCase();
  const rules = [
    [/str|力量|体能|体格|筋骨|体质/, "fitness_center"],
    [/dex|敏捷|灵巧|反射|速度|身手/, "directions_run"],
    [/con|耐力|坚韧|生存|抗性|hp/, "shield_moon"],
    [/int|智力|学识|推理|奥术|知识/, "psychology"],
    [/wis|感知|洞察|察觉|直感|灵觉/, "visibility"],
    [/cha|魅力|社交|威压|亲和|仪态/, "groups_3"],
    [/理智|san|精神崩溃/, "neurology"],
    [/意志|决心|专注|自律/, "center_focus_strong"],
    [/幸运|luck|命运/, "casino"],
    [/感知|察觉|侦查/, "search"],
    [/魅力|说服|欺瞒/, "theater_comedy"],
    [/敏捷|隐匿|潜行/, "nights_stay"],
    [/力量|运动|运动技能/, "exercise"],
  ];
  for (const [re, g] of rules) {
    if (re.test(t)) return g;
  }
  return "bubble_chart";
}

function bindAttrRadarAxisTooltips(svgEl, tipEl, stats, drawableProfiles) {
  if (!svgEl || !tipEl) return;
  const hide = () => {
    tipEl.hidden = true;
    tipEl.innerHTML = "";
  };
  svgEl.querySelectorAll(".radar-axis-hit").forEach((line) => {
    line.addEventListener("pointerenter", (ev) => {
      const i = parseInt(line.getAttribute("data-axis-idx") || "-1", 10);
      if (i < 0 || !stats[i]) return;
      const s = stats[i];
      const rows = [
        `<div class="attr-radar-tip-title">${escapeHtml((s.name || s.id || "").toString())}</div>`,
        `<div class="attr-radar-tip-row"><span class="attr-radar-tip-k">参照轮廓</span><span class="attr-radar-tip-v">${clampRefPercent(
          s.reference_percent
        )} / 100</span></div>`,
      ];
      drawableProfiles.forEach((prof) => {
        const av = prof.averages && typeof prof.averages === "object" ? prof.averages : {};
        const raw = av[s.id];
        const lab = String(prof.tier_name || "").trim() || "境界";
        const v =
          typeof raw === "number" && Number.isFinite(raw) ? `${clampRefPercent(raw)} / 100` : "—";
        rows.push(
          `<div class="attr-radar-tip-row"><span class="attr-radar-tip-k">${escapeHtml(lab)} 平均</span><span class="attr-radar-tip-v">${escapeHtml(
            v
          )}</span></div>`
        );
      });
      tipEl.innerHTML = rows.join("");
      tipEl.hidden = false;
      tipEl.style.left = `${ev.clientX + 12}px`;
      tipEl.style.top = `${ev.clientY + 12}px`;
    });
    line.addEventListener("pointermove", (ev) => {
      if (tipEl.hidden) return;
      tipEl.style.left = `${ev.clientX + 12}px`;
      tipEl.style.top = `${ev.clientY + 12}px`;
    });
    line.addEventListener("pointerleave", hide);
    line.addEventListener("pointercancel", hide);
  });
}

function migrateGlobalLandmarksResourcesIntoRegions(w) {
  const g = w.geography;
  if (!g || !Array.isArray(g.regions) || !g.regions.length) return;
  const gloLm = Array.isArray(g.landmarks) ? g.landmarks.map((x) => String(x).trim()).filter(Boolean) : [];
  const gloRes = Array.isArray(g.resources) ? g.resources.map((x) => String(x).trim()).filter(Boolean) : [];
  const anyRegionHas = g.regions.some(
    (r) =>
      (Array.isArray(r.landmarks) && r.landmarks.length > 0) ||
      (Array.isArray(r.resources) && r.resources.length > 0)
  );
  if (!anyRegionHas && (gloLm.length || gloRes.length)) {
    const r0 = g.regions[0];
    if (!Array.isArray(r0.landmarks)) r0.landmarks = [];
    if (!Array.isArray(r0.resources)) r0.resources = [];
    r0.landmarks.push(...gloLm);
    r0.resources.push(...gloRes);
    g.landmarks = [];
    g.resources = [];
  }
}

function renderAttributePanel(w) {
  const host = $("vizAttributeRadarHost");
  const chips = $("attrStatChips");
  const introsEl = $("attrStatIntros");
  if (!host) return;
  if (!w) {
    host.innerHTML = "";
    if (chips) chips.innerHTML = "";
    if (introsEl) introsEl.innerHTML = "";
    return;
  }
  const stats = (w.attribute_system && w.attribute_system.stats) || [];
  if (!stats.length) {
    host.innerHTML = `<div class="viz-empty">在下方 JSON 中添加 stats（每项含 id、name、abbreviation、intro、reference_percent 等）</div>`;
    if (chips) chips.innerHTML = "";
    if (introsEl) introsEl.innerHTML = "";
    return;
  }
  const profiles = ((w.attribute_system && w.attribute_system.tier_average_profiles) || []).filter((p) =>
    Boolean(p && String(p.tier_name || "").trim())
  );
  const drawableProfiles = profiles.filter((prof) => {
    const av = prof.averages && typeof prof.averages === "object" ? prof.averages : {};
    return stats.some((s) => {
      const raw = av[s.id];
      return typeof raw === "number" && Number.isFinite(raw);
    });
  });
  const n = stats.length;
  const R = 92;
  const angles = stats.map((_, i) => (-Math.PI / 2) + (2 * Math.PI * i) / n);
  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = (R * g) / 4;
    rings += `<circle cx="0" cy="0" r="${rr.toFixed(2)}" class="radar-ring" />`;
  }
  const tierHueCycle = [168, 318, 32, 268, 200, 130];
  let tierPolygons = "";
  drawableProfiles.forEach((prof, ti) => {
    const av = prof.averages && typeof prof.averages === "object" ? prof.averages : {};
    const tierPts = angles
      .map((ang, i) => {
        const sid = stats[i].id;
        const raw = av[sid];
        const v =
          typeof raw === "number" && Number.isFinite(raw) ? clampRefPercent(raw) : 0;
        const pct = v / 100;
        const r = R * pct;
        return `${(r * Math.cos(ang)).toFixed(2)},${(r * Math.sin(ang)).toFixed(2)}`;
      })
      .join(" ");
    const hue = tierHueCycle[ti % tierHueCycle.length];
    tierPolygons += `<polygon class="radar-poly radar-poly--tier" points="${tierPts}" fill="hsla(${hue},62%,52%,0.12)" stroke="hsl(${hue},48%,36%)" stroke-width="1.32" stroke-linejoin="round" />`;
  });
  const refPts = angles
    .map((ang, i) => {
      const pct = clampRefPercent(stats[i].reference_percent) / 100;
      const r = R * pct;
      return `${(r * Math.cos(ang)).toFixed(2)},${(r * Math.sin(ang)).toFixed(2)}`;
    })
    .join(" ");
  let axisVisible = "";
  let axisHits = "";
  let axisIcons = "";
  let axisLabels = "";
  const R_icon = R + 12;
  const R_text = R + 30;
  for (let i = 0; i < n; i++) {
    const ang = angles[i];
    const xe = (R * Math.cos(ang)).toFixed(2);
    const ye = (R * Math.sin(ang)).toFixed(2);
    axisVisible += `<line x1="0" y1="0" x2="${xe}" y2="${ye}" class="radar-axis-visible" />`;
    axisHits += `<line x1="0" y1="0" x2="${xe}" y2="${ye}" class="radar-axis-hit" data-axis-idx="${i}" stroke-linecap="round" />`;
    const glyph = pickAttrStatGlyph(stats[i]);
    const iix = (R_icon * Math.cos(ang)).toFixed(2);
    const iiy = (R_icon * Math.sin(ang)).toFixed(2);
    axisIcons += `<text x="${iix}" y="${iiy}" class="radar-stat-ic" dominant-baseline="central" text-anchor="middle">${glyph}</text>`;
    const lx = R_text * Math.cos(ang);
    const ly = R_text * Math.sin(ang);
    const short = escapeHtml(
      ((stats[i].abbreviation || stats[i].name || "?") + "").toString().slice(0, 6)
    );
    axisLabels += `<text x="${lx.toFixed(2)}" y="${ly.toFixed(2)}" class="radar-label" dominant-baseline="middle" text-anchor="middle">${short}</text>`;
  }
  const gid = "radarFillGrad_" + Math.random().toString(36).slice(2, 11);
  const svgInner = `<svg viewBox="-130 -130 260 260" class="attr-radar-svg" role="img" aria-label="属性维度雷达"><defs><linearGradient id="${gid}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#6366f1" stop-opacity="0.36"/><stop offset="100%" stop-color="#0ea5e9" stop-opacity="0.2"/></linearGradient></defs><g class="radar-rings">${rings}</g>${tierPolygons}<polygon class="radar-poly radar-poly--ref" points="${refPts}" fill="url(#${gid})" stroke="#4338ca" stroke-width="1.65" stroke-linejoin="round"/><g class="radar-axes-visible">${axisVisible}</g><g class="radar-axes-hit">${axisHits}</g><g class="radar-axes-icons">${axisIcons}</g><g class="radar-axes-labels">${axisLabels}</g></svg>`;

  const legParts = [
    `<span class="radar-legend-i radar-legend-i--ref"><span class="radar-legend-dot" aria-hidden="true"></span>参照轮廓</span>`,
  ];
  drawableProfiles.forEach((prof, ti) => {
    const tname = String(prof.tier_name || "").trim();
    const hue = tierHueCycle[ti % tierHueCycle.length];
    legParts.push(
      `<span class="radar-legend-i" style="--legend-tier-h:${hue}"><span class="radar-legend-dot radar-legend-dot--tier" aria-hidden="true"></span>${escapeHtml(
        tname
      )} 平均</span>`
    );
  });
  const legend = `<div class="attr-radar-legend muted tiny">${legParts.join("")}</div>`;
  host.innerHTML = `<div class="attr-radar-stack"><div class="attr-radar-svg-wrap">${svgInner}<div class="attr-radar-tip" hidden aria-live="polite"></div></div>${legend}</div>`;
  const svgEl = host.querySelector(".attr-radar-svg");
  const tipEl = host.querySelector(".attr-radar-tip");
  bindAttrRadarAxisTooltips(svgEl, tipEl, stats, drawableProfiles);

  if (chips) {
    chips.innerHTML = stats
      .map((s) => {
        const intro = ((s.intro || "") + "").trim();
        const desc = ((s.description || "") + "").trim();
        const tip = escapeHtml((intro || desc || "").slice(0, 260));
        const nm = escapeHtml((s.name || s.id || "").toString());
        return `<span class="attr-chip" title="${tip}"><strong>${nm}</strong><span class="attr-chip-pct">${clampRefPercent(
          s.reference_percent
        )}</span></span>`;
      })
      .join("");
  }
  if (introsEl) {
    introsEl.innerHTML = stats
      .map((s) => {
        const nm = escapeHtml((s.name || s.id || "").toString());
        const intro = ((s.intro || "") + "").trim();
        const desc = ((s.description || "") + "").trim();
        const bodyTxt = intro || desc.slice(0, 200) || "（未填 intro，可在 JSON 中补充）";
        const body = escapeHtml(bodyTxt);
        return `<div class="attr-intro-row"><span class="attr-intro-name">${nm}</span><span class="attr-intro-body">${body}</span></div>`;
      })
      .join("");
  }
}

/** 境界 · 体系子页：各境名称、描述、能力/限制/范例（可编辑，与 tiers JSON 同步） */
function renderPowerTierSystemModules(w) {
  const root = $("vizPowerSystemModules");
  if (!root) return;
  root.replaceChildren();
  const tiers = w.power_system?.tiers || [];
  if (!tiers.length) {
    root.innerHTML = `<div class="viz-empty">暂无境界（可在「技能树」子页下方 tiers JSON 中添加）</div>`;
    return;
  }
  const n = tiers.length;
  tiers.forEach((tier, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--power power-tier-viz power-tier-viz--editable";
    block.dataset.powerTierIndex = String(idx);
    const hue = Math.round(198 + (idx / Math.max(n - 1, 1)) * 78);
    block.style.setProperty("--tier-accent-h", String(hue));
    const caps = (Array.isArray(tier.typical_capabilities) ? tier.typical_capabilities : [])
      .map((x) => String(x).trim())
      .filter(Boolean);
    const lims = (Array.isArray(tier.limitations) ? tier.limitations : [])
      .map((x) => String(x).trim())
      .filter(Boolean);
    const exs = (Array.isArray(tier.examples) ? tier.examples : [])
      .map((x) => String(x).trim())
      .filter(Boolean);
    const skCount = (tier.skill_tree || []).length;
    const scCount = (tier.subclass_paths || []).reduce((s, sp) => s + (sp.skill_tree || []).length, 0);
    const totalNodes = skCount + scCount;
    const nameId = `power-tier-name-${idx}`;
    block.innerHTML = `
      <div class="power-tier-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head power-tier-viz-head">
        <span class="viz-module-idx viz-module-idx--power" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <label class="item-grade-name-lbl muted tiny" for="${nameId}">境界名</label>
          <input id="${nameId}" class="item-grade-name-input" type="text" data-power-field="name" value="${escapeAttr(
            tier.name || ""
          )}" placeholder="例如：筑基、第三环…" autocomplete="off" />
          <span class="viz-module-meta muted tiny">下列可直接编辑；列表类一行一条</span>
          ${totalNodes > 0 ? `<span class="power-tier-sk-badge" title="通用技能: ${skCount} + 子类技能: ${scCount}"><span class="ms" style="font-size:14px;vertical-align:-3px">account_tree</span> ${totalNodes} 技能节点</span>` : `<span class="power-tier-sk-badge power-tier-sk-badge--empty">暂无技能树</span>`}
        </div>
        <button class="power-tier-del-btn" onclick="deletePowerTier(${idx})" title="删除此境界（不可撤销）" aria-label="删除境界 ${tier.name||idx+1}"><span class="ms" aria-hidden="true" style="font-size:18px">delete</span></button>
      </div>
      <div class="power-tier-viz-body" role="region" aria-label="境界 ${idx + 1} 体系">
        ${htmlPowerTierEditableField(
          "description",
          "定位与描述",
          tier.description,
          "本境在世界力量阶梯中的位置、读者/玩家如何理解…",
          "mean",
          5
        )}
        <div class="power-tier-viz-grid">
          ${htmlPowerTierEditableField(
            "typical_capabilities",
            "发动能力（典型）",
            caps.join("\n"),
            "每行一条典型能力或表现",
            "caps",
            4
          )}
          ${htmlPowerTierEditableField(
            "limitations",
            "发动限制",
            lims.join("\n"),
            "每行一条限制或代价",
            "lims",
            4
          )}
          ${htmlPowerTierEditableField(
            "activation_rules",
            "\u{1F4CB} 发动规则（作者书写）",
            tier.activation_rules || "",
            "角色必须 100% 满足的条件才能使用本境界能力。该规则将在故事 Agent 决策前自动校验。\n例如：完成刻痕仪式 + 凝痕节点稳定 ≥ 3 天 + 雾蚀浓度 ≥ 中等",
            "rules",
            4
          )}
          ${htmlPowerTierEditableField(
            "examples",
            "例子",
            exs.join("\n"),
            "每行一条叙事或规则范例",
            "ex",
            4
          )}
        </div>
      </div>`;
    root.appendChild(block);
  });
}

/** 境界 · 技能树子页：左栏可视化预览 + 右栏 JSON；防抖保存后仅刷新预览不打断输入 */
function renderPowerTierSkillTreeModules(w) {
  const root = $("vizPowerSkillTreeModules");
  if (!root) return;
  root.replaceChildren();
  const tiers = w.power_system?.tiers || [];
  if (!tiers.length) {
    root.innerHTML = `<div class="viz-empty">暂无境界（可在下方 tiers JSON 中添加）</div>`;
    return;
  }
  const n = tiers.length;
  tiers.forEach((tier, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--power power-tier-viz power-tier-viz--trees";
    block.dataset.powerTierIndex = String(idx);
    const hue = Math.round(198 + (idx / Math.max(n - 1, 1)) * 78);
    block.style.setProperty("--tier-accent-h", String(hue));
    const skJson = JSON.stringify(tier.skill_tree ?? [], null, 2);
    const scJson = JSON.stringify(tier.subclass_paths ?? [], null, 2);
    const genPreviewInner = htmlSkillTreePreviewInner(tier.skill_tree ?? []);
    const tierProfs = (w.power_system?.profession_system?.by_tier?.[idx]?.professions) || [];
    const subPreviewInner = htmlSubclassPathsPreviewInner(tier.subclass_paths ?? [], tierProfs, w);
    const genPreview = `<div class="skill-tree-preview-surface">${genPreviewInner}</div>`;
    const subPreview = `<div class="skill-tree-preview-surface skill-tree-preview-surface--sub">${subPreviewInner}</div>`;
    block.innerHTML = `
      <div class="power-tier-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head power-tier-viz-head">
        <span class="viz-module-idx viz-module-idx--power" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <span class="viz-module-title">${escapeHtml(tier.name || `境 ${idx + 1}`)}</span>
          <span class="viz-module-meta muted tiny">左侧为节点预览，右侧编辑 JSON；保存前预览会随输入防抖更新</span>
        </div>
      </div>
      <div class="power-tier-viz-body power-tier-skill-tree-body" role="region" aria-label="境界 ${idx + 1} 技能树">
        <section class="power-tier-skill-band" aria-label="通用技能树">
          <div class="power-tier-skill-split">
            <div class="power-tier-skill-col power-tier-skill-col--viz">
              <div class="power-tier-skill-band-head">
                <span class="ms skill-band-ic" aria-hidden="true">account_tree</span>
                <span class="power-tier-skill-band-title">通用技能树</span>
                <span class="power-tier-skill-band-hint muted tiny">节点 · 前置 · 分支</span>
              </div>
              <div class="power-tier-skill-preview-wrap" data-skill-preview="general">${genPreview}</div>
            </div>
            <div class="power-tier-skill-col power-tier-skill-col--json">
              <div class="power-tier-json-edit-head">
                <span class="ms skill-band-ic" aria-hidden="true">data_object</span>
                <span>skill_tree</span>
                <span class="muted tiny power-tier-json-lang">JSON</span>
              </div>
              <textarea id="power-sk-${idx}" class="power-tier-json-ta" rows="11" spellcheck="false" data-power-tree-part="skill_tree" aria-label="通用技能树 JSON">${escapeHtml(
                skJson
              )}</textarea>
            </div>
          </div>
        </section>
        <section class="power-tier-skill-band power-tier-skill-band--sub" aria-label="子类流派">
          <div class="power-tier-skill-split">
            <div class="power-tier-skill-col power-tier-skill-col--viz">
              <div class="power-tier-skill-band-head">
                <span class="ms skill-band-ic" aria-hidden="true">diversity_3</span>
                <span class="power-tier-skill-band-title">子类流派</span>
                <span class="power-tier-skill-band-hint muted tiny">各流派独立 skill_tree</span>
              </div>
              <div class="power-tier-skill-preview-wrap" data-skill-preview="subclasses">${subPreview}</div>
            </div>
            <div class="power-tier-skill-col power-tier-skill-col--json">
              <div class="power-tier-json-edit-head">
                <span class="ms skill-band-ic" aria-hidden="true">hub</span>
                <span>subclass_paths</span>
                <span class="muted tiny power-tier-json-lang">JSON</span>
              </div>
              <textarea id="power-sc-${idx}" class="power-tier-json-ta" rows="11" spellcheck="false" data-power-tree-part="subclass_paths" aria-label="子类流派 JSON">${escapeHtml(
                scJson
              )}</textarea>
            </div>
          </div>
        </section>
      </div>`;
    root.appendChild(block);
  });
}

function collectProfessionByTierFromDom(tiers) {
  const psRoot = $("vizPowerProfessionModules");
  const list = Array.isArray(tiers) ? tiers : state.world?.power_system?.tiers || [];
  if (!list.length) return [];
  return list.map((t, idx) => {
    let professions = [];
    const card = psRoot?.querySelector(`.power-tier-viz--professions[data-power-tier-index="${idx}"]`);
    const ta = card?.querySelector('[data-profession-part="professions_json"]');
    if (ta) {
      try {
        const p = JSON.parse((ta.value || "").trim() || "[]");
        if (Array.isArray(p)) professions = p;
      } catch (_) {
        const prev = state.world?.power_system?.profession_system?.by_tier?.[idx]?.professions;
        if (Array.isArray(prev)) professions = structuredClone(prev);
      }
    } else {
      const prev = state.world?.power_system?.profession_system?.by_tier?.[idx]?.professions;
      if (Array.isArray(prev)) professions = structuredClone(prev);
    }
    const name = (t.name || "").trim() || `境 ${idx + 1}`;
    return { tier_name: name, professions };
  });
}

let _powerProfessionSyncTimer;
function scheduleSyncProfessionFromVizToState() {
  clearTimeout(_powerProfessionSyncTimer);
  _powerProfessionSyncTimer = setTimeout(() => {
    if (!state.world) return;
    state.world.power_system = state.world.power_system || {};
    state.world.power_system.profession_system = state.world.power_system.profession_system || {};
    state.world.power_system.profession_system.summary = ($("powerProfessionSummary")?.value ?? "").trim();
    state.world.power_system.profession_system.design_notes = ($("powerProfessionDesign")?.value ?? "").trim();
    state.world.power_system.profession_system.by_tier = collectProfessionByTierFromDom(
      state.world.power_system.tiers
    );
    setDirty(true);
    const tiers = state.world.power_system.tiers || [];
    document.querySelectorAll("#vizPowerProfessionModules .power-tier-viz--professions").forEach((el) => {
      const idx = Number.parseInt(el.getAttribute("data-power-tier-index") || "0", 10);
      const tn = tiers[idx]?.name;
      const titleEl = el.querySelector(".viz-module-title");
      if (titleEl && tn != null) titleEl.textContent = tn || `境 ${idx + 1}`;
    });
    updatePowerProfessionPreviews(tiers, state.world.power_system.profession_system);
    updatePowerTierSkillTreePreviews(tiers);
    refreshProfessionPromotionViz();
  }, 220);
}

function renderPowerProfessionModules(w) {
  const root = $("vizPowerProfessionModules");
  if (!root) return;
  root.replaceChildren();
  const tiers = w.power_system?.tiers || [];
  const ps = w.power_system?.profession_system || {};
  const byTier = Array.isArray(ps.by_tier) ? ps.by_tier : [];
  if (!tiers.length) {
    root.innerHTML = `<div class="viz-empty">暂无境界（请先在「体系」或 tiers JSON 中添加境界表）</div>`;
    refreshProfessionPromotionViz();
    return;
  }
  const n = tiers.length;
  tiers.forEach((tier, idx) => {
    const profs = (byTier[idx] && byTier[idx].professions) || [];
    const j = JSON.stringify(profs, null, 2);
    const prevInner = htmlProfessionsPreviewInner(profs, w);
    const block = document.createElement("div");
    block.className = "viz-module viz-module--power power-tier-viz power-tier-viz--professions";
    block.dataset.powerTierIndex = String(idx);
    const hue = Math.round(198 + (idx / Math.max(n - 1, 1)) * 78);
    block.style.setProperty("--tier-accent-h", String(hue));
    block.innerHTML = `
      <div class="power-tier-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head power-tier-viz-head">
        <span class="viz-module-idx viz-module-idx--power" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <span class="viz-module-title">${escapeHtml(tier.name || `境 ${idx + 1}`)}</span>
          <span class="viz-module-meta muted tiny">左侧预览；右栏为本境 professions 数组 JSON</span>
        </div>
      </div>
      <div class="power-tier-viz-body power-tier-skill-tree-body" role="region" aria-label="境界 ${idx + 1} 职业">
        <div class="power-tier-skill-split">
          <div class="power-tier-skill-col power-tier-skill-col--viz">
            <div class="power-tier-skill-band-head">
              <span class="ms skill-band-ic" aria-hidden="true">badge</span>
              <span class="power-tier-skill-band-title">本境职业</span>
              <span class="power-tier-skill-band-hint muted tiny">派系专属填 exclusive_faction_id</span>
            </div>
            <div class="power-tier-skill-preview-wrap" data-profession-preview="list"><div class="profession-preview-surface">${prevInner}</div></div>
          </div>
          <div class="power-tier-skill-col power-tier-skill-col--json">
            <div class="power-tier-json-edit-head">
              <span class="ms skill-band-ic" aria-hidden="true">data_object</span>
              <span>professions</span>
              <span class="muted tiny power-tier-json-lang">JSON</span>
            </div>
            <textarea id="power-pr-${idx}" class="power-tier-json-ta" rows="11" spellcheck="false" data-profession-part="professions_json" aria-label="本境职业 JSON 数组">${escapeHtml(
              j
            )}</textarea>
          </div>
        </div>
      </div>`;
    root.appendChild(block);
  });
  refreshProfessionPromotionViz();
}

function renderPowerTierDashboardModules(w) {
  renderPowerTierSystemModules(w);
  renderPowerTierSkillTreeModules(w);
  renderPowerProfessionModules(w);
}

function setGeoSubView(which) {
  if (which !== "regions" && which !== "overview") return;
  state.geoSubView = which;
  const reg = $("geoSubRegions");
  const ov = $("geoSubOverview");
  if (reg) reg.classList.toggle("is-hidden", which !== "regions");
  if (ov) ov.classList.toggle("is-hidden", which !== "overview");
  document.querySelectorAll("[data-geo-sub]").forEach((b) => {
    const on = b.dataset.geoSub === which;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (which === "regions") requestAnimationFrame(() => refreshGeoNetworkViz());
  if (which === "overview") requestAnimationFrame(() => refreshGeoMarkdownPreviews());
}

function setPowerSubView(which) {
  if (which !== "system" && which !== "trees" && which !== "professions") return;
  state.powerSubView = which;
  const sys = $("powerSubSystem");
  const tr = $("powerSubTrees");
  const pr = $("powerSubProfessions");
  if (sys) sys.classList.toggle("is-hidden", which !== "system");
  if (tr) tr.classList.toggle("is-hidden", which !== "trees");
  if (pr) pr.classList.toggle("is-hidden", which !== "professions");
  document.querySelectorAll("[data-power-sub]").forEach((b) => {
    const on = b.dataset.powerSub === which;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (which === "professions") requestAnimationFrame(() => refreshProfessionPromotionViz());
  refreshPowerProfessionCountBadge(state.world);
}

function setEcologySubView(which) {
  if (which !== "overview" && which !== "biomes" && which !== "species") return;
  state.ecologySubView = which;
  const ov = $("ecologySubOverview");
  const bio = $("ecologySubBiomes");
  const sp = $("ecologySubSpecies");
  if (ov) ov.classList.toggle("is-hidden", which !== "overview");
  if (bio) bio.classList.toggle("is-hidden", which !== "biomes");
  if (sp) sp.classList.toggle("is-hidden", which !== "species");
  document.querySelectorAll("[data-ecology-sub]").forEach((b) => {
    const on = b.dataset.ecologySub === which;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (which === "overview") requestAnimationFrame(() => refreshEcologyMarkdownPreviews());
  if (which === "biomes" || which === "species") requestAnimationFrame(() => renderEcologyVizFromForm());
}

/** 物品：每档位卡片式展示（无 Mermaid 逻辑图）；各栏可在卡片内直接编辑 */
function renderItemGradeDashboardModules(w) {
  const root = $("vizItemGradesRoot");
  if (!root) return;
  root.replaceChildren();
  const grades = w.item_quality_system?.grades || [];
  if (!grades.length) {
    root.innerHTML = `<div class="viz-empty">暂无档位（可在下方 JSON 中添加 grades 数组）</div>`;
    return;
  }
  const nG = grades.length;
  grades.forEach((grade, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--item item-grade-viz item-grade-viz--editable";
    block.dataset.itemGradeIndex = String(idx);
    const hue = Math.round(268 + (idx / Math.max(nG - 1, 1)) * 52);
    block.style.setProperty("--tier-accent-h", String(hue));
    const nameId = `item-grade-name-${idx}`;
    const exLines = (Array.isArray(grade.examples) ? grade.examples : []).map((x) => String(x).trim()).filter(Boolean);
    block.innerHTML = `
      <div class="item-grade-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head item-grade-viz-head">
        <span class="viz-module-idx viz-module-idx--item" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <label class="item-grade-name-lbl muted tiny" for="${nameId}">档位名</label>
          <input id="${nameId}" class="item-grade-name-input" type="text" data-item-field="name" value="${escapeAttr(
            grade.name || ""
          )}" placeholder="例如：凡品、稀有…" autocomplete="off" />
          <span class="viz-module-meta muted tiny">下列可直接编辑；「例子」一行一条</span>
        </div>
      </div>
      <div class="item-grade-viz-body" role="region" aria-label="档位 ${idx + 1} 详情">
        ${htmlItemGradeEditableField(
          "rarity_narrative",
          "含义（稀有叙事）",
          grade.rarity_narrative,
          "稀有度在故事里的呈现、获取氛围…",
          "mean"
        )}
        ${htmlItemGradeEditableField(
          "typical_effects",
          "典型效果",
          grade.typical_effects,
          "该档常见机制或叙事效果…",
          "fx"
        )}
        ${htmlItemGradeEditableField(
          "examples",
          "例子",
          exLines.join("\n"),
          "每行一条示例名称或短描述",
          "ex"
        )}
        ${htmlItemGradeEditableField(
          "binding_rules",
          "绑定 / 规则",
          grade.binding_rules,
          "灵魂绑定、使用限制、职业限制等…",
          "bind"
        )}
      </div>`;
    root.appendChild(block);
  });
}

function buildHistoryMermaid(events) {
  const init = mermaidFactionInit();
  const list = Array.isArray(events) ? events : [];
  if (!list.length) return init + 'flowchart TB\n  h0["（无事件）"]';
  const lines = [
    "flowchart TB",
    "  classDef hOld fill:#f1f5f9,color:#475569,stroke:#94a3b8",
    "  classDef hMid fill:#dbeafe,color:#1e40af,stroke:#3b82f6",
    "  classDef hNew fill:#ccfbf1,color:#115e59,stroke:#0d9488",
  ];
  const maxShow = 18;
  const truncated = list.length > maxShow;
  const slice = truncated ? list.slice(0, maxShow) : list;
  const nVis = slice.length;
  const clsFor = (i) => {
    if (nVis <= 1) return "hMid";
    const r = i / (nVis - 1);
    if (r < 0.35) return "hOld";
    if (r < 0.75) return "hMid";
    return "hNew";
  };
  slice.forEach((e, i) => {
    const when = (e.when || "").trim();
    const title = (e.title || "事件").trim();
    const head = mermaidEscape(`${when} ${title}`.trim().slice(0, 44));
    lines.push(`  H${i}["${head}"]`);
    lines.push(`  class H${i} ${clsFor(i)}`);
  });
  for (let i = 0; i < slice.length - 1; i++) {
    const cons = (slice[i].consequences || [])[0];
    const edge = cons ? mermaidEscape(String(cons).trim().slice(0, 22)) : "";
    if (edge) lines.push(`  H${i} -->|"${edge}"| H${i + 1}`);
    else lines.push(`  H${i} --> H${i + 1}`);
  }
  if (truncated) {
    const extra = list.length - maxShow;
    lines.push(`  Hmore["… 另有 ${extra} 条（见 JSON）"]`);
    lines.push("  class Hmore hOld");
    lines.push(`  H${slice.length - 1} --> Hmore`);
  }
  return init + lines.join("\n");
}

function uid(prefix) {
  return prefix + Math.random().toString(36).slice(2, 10);
}

function gidGeo(i) {
  return `g${i}`;
}

/** 区域列表 + 可选 relations（target_id 指向其他区域 id）→ Mermaid 网络图 */
function buildGeographyMermaid(regions, worldLabel) {
  const regs = Array.isArray(regions) ? regions : [];
  const init = mermaidFactionInit();
  if (!regs.length) {
    return init + 'flowchart TB\n  geoEmpty["（暂无区域）"]';
  }
  const hub = mermaidEscape(String(worldLabel || "地理总览").slice(0, 22));
  const lines = [
    "flowchart TB",
    "  classDef mGeoHub fill:#0d9488,color:#fff,stroke:#0f766e,stroke-width:2px",
    "  classDef mGeoReg fill:#ecfdf5,color:#064e3b,stroke:#5eead4",
    "  classDef mGeoExt fill:#fffbeb,color:#92400e,stroke:#f59e0b,stroke-dasharray:4 3",
    `  GHUB["${hub}"]`,
  ];
  regs.forEach((r, i) => {
    const label = mermaidEscape(String(r.name || r.id || `区域${i + 1}`).slice(0, 24));
    lines.push(`  ${gidGeo(i)}["${label}"]`);
    lines.push(`  class ${gidGeo(i)} mGeoReg`);
  });
  lines.push("  class GHUB mGeoHub");
  regs.forEach((r, i) => {
    const edge = mermaidEscape(
      String(r.terrain || r.climate || "子区域").slice(0, 18)
    );
    lines.push(`  GHUB -->|"${edge}"| ${gidGeo(i)}`);
  });
  const idToIdx = new Map();
  regs.forEach((r, i) => {
    const rid = String(r.id || "").trim();
    if (rid) idToIdx.set(rid, i);
  });
  const pairSeen = new Set();
  let unk = 0;
  regs.forEach((r, i) => {
    (r.relations || []).forEach((rel) => {
      const tid = String(rel?.target_id || "").trim();
      if (!tid || tid === String(r.id || "").trim()) return;
      const lab = mermaidEscape(
        `${rel.type || "关联"}${rel.notes ? "·" + rel.notes : ""}`.slice(0, 28)
      );
      const j = idToIdx.get(tid);
      if (j != null && j !== i) {
        const a = Math.min(i, j);
        const b = Math.max(i, j);
        const key = `${a}-${b}`;
        if (pairSeen.has(key)) return;
        pairSeen.add(key);
        lines.push(`  ${gidGeo(a)} -->|"${lab}"| ${gidGeo(b)}`);
      } else {
        const nk = `gU${unk}`;
        unk += 1;
        const tlab = mermaidEscape(`${tid.slice(0, 16)}（未建档）`);
        lines.push(`  ${nk}["${tlab}"]`);
        lines.push(`  class ${nk} mGeoExt`);
        lines.push(`  ${gidGeo(i)} -.->|"${lab}"| ${nk}`);
      }
    });
  });
  return init + lines.join("\n");
}

function getRegionsForGeoViz() {
  const root = $("regionCards");
  if (root) {
    if (root.querySelector(".region-card")) return collectRegionsFromDom();
    return [];
  }
  return state.world?.geography?.regions || [];
}

/** 大陆 / 区域卡片左侧图示（Material Symbols 名称） */
function pickRegionGlyph(name, terrain, summary, idx) {
  const t = [name, terrain, summary].map((x) => (x || "").toString().trim()).join(" ");
  const lower = t.toLowerCase();
  const rules = [
    [/海|洋|岛|港|湾|潮|渔|舰|波|舟|渊|滨海|海岸/, "waves"],
    [/湖|河|川|沼|湿地|溪|流|池|淀|江|漕|渡口/, "water"],
    [/雪|冰|寒|极地|冻|霜|雹|凛冬|冰川/, "severe_cold"],
    [/沙|漠|荒|戈壁|旱|风尘|流沙/, "wb_sunny"],
    [/山|峰|高原|岭|崖|峡|巅|岩|峦|雪域.*山/, "landscape"],
    [/森|林|木|竹|苔|乔|灌|绿荫|雨林/, "forest"],
    [/城|市|镇|坊|都|邑|宫|堡|郭|京畿|城邦/, "location_city"],
    [/草|原|牧|田|农|耕|坪|甸|沃野|麦/, "park"],
    [/谷|盆地|洼地/, "terrain"],
    [/火|熔|岩|浆|火山|硫磺|地热/, "local_fire_department"],
    [/云|天|空|雷|岚|霄|罡|浮空|天穹/, "air"],
    [/洞|穴|地下|隧|矿坑|地底|幽窟/, "layers"],
    [/平|川|陆|广|中原|沃壤/, "map"],
  ];
  for (const [re, g] of rules) {
    if (re.test(t) || re.test(lower)) return g;
  }
  const fallbacks = [
    "travel_explore",
    "public",
    "map",
    "explore",
    "add_location_alt",
    "place",
    "terrain",
  ];
  return fallbacks[idx % fallbacks.length];
}

function syncRegionCardIcon(card) {
  if (!card) return;
  const ic = card.querySelector(".region-viz-ic");
  if (!ic) return;
  const root = card.parentElement;
  const idx = root ? [...root.querySelectorAll(".region-card")].indexOf(card) : 0;
  const name = card.querySelector(".region-name")?.value || "";
  const terrain = card.querySelector(".region-terrain")?.value || "";
  const summary = card.querySelector(".region-summary")?.value || "";
  ic.textContent = pickRegionGlyph(name, terrain, summary, Math.max(0, idx));
}

let _geoVizTimer;
function scheduleGeoVizRefresh() {
  clearTimeout(_geoVizTimer);
  _geoVizTimer = setTimeout(() => refreshGeoNetworkViz(), 240);
}

let _geoMdPreviewTimer = null;
function scheduleGeoMarkdownPreviews() {
  clearTimeout(_geoMdPreviewTimer);
  _geoMdPreviewTimer = setTimeout(() => refreshGeoMarkdownPreviews(), 140);
}

/** 总览 / 气候 / 地图：与助手区相同的 Markdown 解析 + 消毒，用于右侧预览 */
function refreshGeoMarkdownPreviews() {
  const pairs = [
    ["geoSummary", "geoSummaryPreview"],
    ["geoClimate", "geoClimatePreview"],
    ["geoMap", "geoMapPreview"],
  ];
  for (const [srcId, preId] of pairs) {
    const src = $(srcId);
    const pre = $(preId);
    if (!pre) continue;
    const raw = (src?.value ?? "").toString();
    if (!raw.trim()) {
      pre.innerHTML = '<p class="muted tiny" style="margin:0">（空）</p>';
      continue;
    }
    pre.innerHTML = renderAssistantMarkdownHtml(raw);
  }
}

/** 生态页：地理区域 id → 显示名（优先当前「大陆/区域」表单，其次已加载 world） */
function getEcologyRegionLookup() {
  const m = new Map();
  try {
    for (const r of collectRegionsFromDom()) {
      const id = String(r.id || "").trim();
      if (id) m.set(id, String(r.name || "").trim() || id);
    }
  } catch {
    /* ignore */
  }
  const wr = state.world?.geography?.regions || [];
  for (const r of wr) {
    if (!r || typeof r !== "object") continue;
    const id = String(r.id || "").trim();
    if (!id || m.has(id)) continue;
    m.set(id, String(r.name || "").trim() || id);
  }
  return m;
}

function parseEcologyBiomesSpeciesJson() {
  let biomes = [];
  let species = [];
  try {
    const b = JSON.parse($("ecologyBiomesJson")?.value || "[]");
    biomes = Array.isArray(b) ? b : [];
  } catch {
    biomes = [];
  }
  try {
    const s = JSON.parse($("ecologySpeciesJson")?.value || "[]");
    species = Array.isArray(s) ? s : [];
  } catch {
    species = [];
  }
  return { biomes, species };
}

function ecologyPlainText(v) {
  return v == null ? "" : String(v).trim();
}

function ecologyMarkdownOrEmpty(raw) {
  const t = ecologyPlainText(raw);
  if (!t) return '<p class="muted tiny" style="margin:0">（空）</p>';
  return renderAssistantMarkdownHtml(t);
}

let _ecologyMdTimer = null;
function scheduleEcologyMarkdownPreviews() {
  clearTimeout(_ecologyMdTimer);
  _ecologyMdTimer = setTimeout(() => refreshEcologyMarkdownPreviews(), 140);
}

function refreshEcologyMarkdownPreviews() {
  const pairs = [
    ["ecologySummary", "ecologySummaryPreview"],
    ["ecologyDesignNotes", "ecologyDesignNotesPreview"],
  ];
  for (const [srcId, preId] of pairs) {
    const src = $(srcId);
    const pre = $(preId);
    if (!pre) continue;
    const raw = (src?.value ?? "").toString();
    if (!ecologyPlainText(raw)) {
      pre.innerHTML = '<p class="muted tiny" style="margin:0">（空）</p>';
      continue;
    }
    pre.innerHTML = renderAssistantMarkdownHtml(raw);
  }
}

let _ecologyVizTimer = null;
function scheduleEcologyVizFromForm() {
  clearTimeout(_ecologyVizTimer);
  _ecologyVizTimer = setTimeout(() => renderEcologyVizFromForm(), 160);
}

function renderEcologyVizFromForm() {
  const biomeRoot = $("vizEcologyBiomes");
  const speciesRoot = $("vizEcologySpecies");
  const emptyBio = $("ecologyBiomeEmpty");
  const emptySp = $("ecologySpeciesEmpty");
  if (!biomeRoot || !speciesRoot) return;
  const { biomes, species } = parseEcologyBiomesSpeciesJson();
  const regionMap = getEcologyRegionLookup();

  biomeRoot.replaceChildren();
  if (!biomes.length) {
    if (emptyBio) emptyBio.hidden = false;
  } else {
    if (emptyBio) emptyBio.hidden = true;
    biomes.forEach((b, idx) => {
      if (!b || typeof b !== "object") return;
      const card = document.createElement("article");
      card.className = "ecology-biome-card";
      card.style.setProperty("--eco-biome-hue", String((152 + idx * 47) % 360));
      const bid = ecologyPlainText(b.id);
      const bname = ecologyPlainText(b.name) || "未命名生境";
      const linked = Array.isArray(b.linked_region_ids) ? b.linked_region_ids : [];
      const pills = linked
        .map((rid) => {
          const id = ecologyPlainText(rid);
          if (!id) return "";
          const nm = escapeHtml(regionMap.get(id) || id);
          const idEsc = escapeHtml(id);
          return `<span class="ecology-pill ecology-pill--region" title="${idEsc}"><span class="ecology-pill-dot" aria-hidden="true"></span>${nm}</span>`;
        })
        .filter(Boolean)
        .join("");

      const extraBits = [];
      if (ecologyPlainText(b.climate_habitat))
        extraBits.push(
          `<div class="ecology-biome-extra"><span class="ecology-biome-extra-label">生境气候</span><div class="ecology-biome-extra-body msg-body msg-body--md">${ecologyMarkdownOrEmpty(
            b.climate_habitat
          )}</div></div>`
        );
      if (ecologyPlainText(b.hazards))
        extraBits.push(
          `<div class="ecology-biome-extra ecology-biome-extra--hazard"><span class="ecology-biome-extra-label">风险</span><div class="ecology-biome-extra-body msg-body msg-body--md">${ecologyMarkdownOrEmpty(
            b.hazards
          )}</div></div>`
        );
      if (ecologyPlainText(b.notes))
        extraBits.push(
          `<div class="ecology-biome-extra"><span class="ecology-biome-extra-label">备注</span><div class="ecology-biome-extra-body msg-body msg-body--md">${ecologyMarkdownOrEmpty(
            b.notes
          )}</div></div>`
        );

      card.innerHTML = `
        <div class="ecology-biome-card-top">
          <div class="ecology-biome-icon" aria-hidden="true"><span class="ms">park</span></div>
          <div class="ecology-biome-title-block">
            <h4 class="ecology-biome-name">${escapeHtml(bname)}</h4>
            ${bid ? `<code class="ecology-biome-id">${escapeHtml(bid)}</code>` : ""}
          </div>
        </div>
        ${
          pills
            ? `<div class="ecology-biome-regions"><span class="ecology-biome-regions-label muted tiny">关联区域</span><div class="ecology-pill-row">${pills}</div></div>`
            : ""
        }
        <div class="ecology-biome-summary msg-body msg-body--md">${ecologyMarkdownOrEmpty(b.summary)}</div>
        ${extraBits.join("")}`;
      biomeRoot.appendChild(card);
    });
  }

  const biomeNameById = new Map();
  for (const b of biomes) {
    if (b && typeof b === "object") {
      const id = ecologyPlainText(b.id);
      if (id) biomeNameById.set(id, ecologyPlainText(b.name) || id);
    }
  }

  speciesRoot.replaceChildren();
  if (!species.length) {
    if (emptySp) emptySp.hidden = false;
  } else {
    if (emptySp) emptySp.hidden = true;
    species.forEach((s, idx) => {
      if (!s || typeof s !== "object") return;
      const el = document.createElement("article");
      el.className = "ecology-species-card";
      el.style.setProperty("--eco-spec-hue", String((210 + idx * 53) % 360));
      const sid = ecologyPlainText(s.id);
      const sname = ecologyPlainText(s.name) || "未命名物种";
      const biomeId = ecologyPlainText(s.biome_id);
      const biomeLabel = biomeId ? biomeNameById.get(biomeId) || biomeId : "";
      const traits = Array.isArray(s.traits) ? s.traits : [];
      const traitHtml = traits
        .map((t) => ecologyPlainText(t))
        .filter(Boolean)
        .map((t) => `<span class="ecology-chip">${escapeHtml(t)}</span>`)
        .join("");
      const skills = Array.isArray(s.notable_skills) ? s.notable_skills : [];
      const skList = skills
        .map((x) => {
          if (x && typeof x === "object") return ecologyPlainText((x).name ?? (x).summary ?? JSON.stringify(x));
          return ecologyPlainText(x);
        })
        .filter(Boolean)
        .map(
          (x) =>
            `<li><span class="ms ecology-skill-ic" aria-hidden="true">auto_awesome</span><span class="ecology-skill-txt">${escapeHtml(
              x
            )}</span></li>`
        )
        .join("");
      const dial = ecologyPlainText(s.encounter_dialogue);
      const danger = ecologyPlainText(s.danger_notes);

      el.innerHTML = `
        <header class="ecology-species-head">
          <div class="ecology-species-avatar" aria-hidden="true"><span class="ms">pets</span></div>
          <div class="ecology-species-head-text">
            <h4 class="ecology-species-name">${escapeHtml(sname)}</h4>
            <div class="ecology-species-meta">
              ${sid ? `<code class="ecology-species-id">${escapeHtml(sid)}</code>` : ""}
              ${
                biomeId
                  ? `<span class="ecology-species-biome-badge" title="biome_id: ${escapeHtml(biomeId)}"><span class="ms">park</span>${escapeHtml(
                      biomeLabel
                    )}</span>`
                  : ""
              }
            </div>
          </div>
        </header>
        ${
          traitHtml
            ? `<div class="ecology-species-traits"><span class="muted tiny ecology-block-label">特征</span><div class="ecology-chip-row">${traitHtml}</div></div>`
            : ""
        }
        ${
          skList
            ? `<div class="ecology-species-skills"><span class="muted tiny ecology-block-label">行为与「物种技能」</span><ul class="ecology-skill-list">${skList}</ul></div>`
            : ""
        }
        ${
          dial
            ? `<blockquote class="ecology-encounter"><span class="ecology-encounter-label muted tiny">遭遇台词 / 旁白</span><div class="ecology-encounter-body msg-body msg-body--md">${renderAssistantMarkdownHtml(
                dial
              )}</div></blockquote>`
            : ""
        }
        ${
          danger
            ? `<div class="ecology-danger"><span class="ms ecology-danger-ic" aria-hidden="true">warning</span><div class="ecology-danger-body msg-body msg-body--md muted tiny">${renderAssistantMarkdownHtml(
                danger
              )}</div></div>`
            : ""
        }`;
      speciesRoot.appendChild(el);
    });
  }
}

function refreshEcologyGenerateMarkdown(raw) {
  const out = $("ecologyGenerateOut");
  if (!out) return;
  const t = ecologyPlainText(raw);
  if (!t) {
    out.innerHTML = '<p class="muted tiny" style="margin:0">（尚无生成结果）</p>';
    return;
  }
  out.innerHTML = renderAssistantMarkdownHtml(t);
}

function refreshGeoNetworkViz() {
  const regs = getRegionsForGeoViz();
  const label = state.world?.meta?.name || "地理总览";
  const def = buildGeographyMermaid(regs, label);
  void drawMermaidHost($("geoNetworkHost"), def);
}

function renderRegionCards(regions) {
  const root = $("regionCards");
  if (!root) return;
  root.replaceChildren();
  const list = Array.isArray(regions) && regions.length ? regions : [];
  list.forEach((r, idx) => {
    const card = document.createElement("div");
    card.className = "region-card";
    const hue = (idx * 53) % 360;
    const relJson = JSON.stringify(r.relations || [], null, 2);
    const lmLines = (Array.isArray(r.landmarks) ? r.landmarks : []).map((x) => String(x).trim()).filter(Boolean);
    const resLines = (Array.isArray(r.resources) ? r.resources : []).map((x) => String(x).trim()).filter(Boolean);
    const glyph = pickRegionGlyph(r.name, r.terrain, r.summary || r.desc, idx);
    card.style.setProperty("--rv-hue", String(hue));
    card.innerHTML = `
      <div class="region-card-head">
        <div class="region-viz" role="img" aria-label="区域类型图示">
          <span class="ms region-viz-ic" aria-hidden="true">${glyph}</span>
        </div>
        <div class="region-fields">
          <div class="region-name-row">
            <input type="hidden" class="region-id" />
            <input type="text" class="region-name" placeholder="大陆 / 区域名称" />
            <button type="button" class="ghost btn-icon remove-region" title="移除此区域">
              <span class="ms" aria-hidden="true">close</span>
            </button>
          </div>
          <div class="region-field region-field-span-2">
            <label class="region-field-label">区域概述</label>
            <textarea class="region-summary" rows="3" placeholder="地貌、政权、文化带、与其他区的关系…"></textarea>
          </div>
          <div class="region-field">
            <label class="region-field-label">地形 / 地貌</label>
            <input type="text" class="region-terrain" placeholder="丘陵、河网、冰原…" />
          </div>
          <div class="region-field">
            <label class="region-field-label">局地气候</label>
            <input type="text" class="region-climate" placeholder="冬雨型、干热谷风…（可选）" />
          </div>
          <div class="region-field region-field-span-2">
            <label class="region-field-label">旅行 / 叙事备注</label>
            <textarea class="region-notes" rows="2" placeholder="风险点、关卡、调查钩子…（可选）"></textarea>
          </div>
          <div class="region-field">
            <label class="region-field-label">地标 <span class="region-field-hint">每行一条</span></label>
            <textarea class="region-landmarks" rows="3" placeholder="辉石城、古渡…"></textarea>
          </div>
          <div class="region-field">
            <label class="region-field-label">资源 <span class="region-field-hint">每行一条</span></label>
            <textarea class="region-resources" rows="3" placeholder="木材、精铁矿…"></textarea>
          </div>
          <div class="region-field region-field-span-2 region-field--relations">
            <label class="region-field-label">与其它区域的关联 <code class="region-code-tag">relations</code></label>
            <textarea class="region-relations-json" rows="3" spellcheck="false" placeholder='[{"target_id":"other-region-id","type":"邻接","notes":""}]'></textarea>
          </div>
        </div>
      </div>`;
    card.querySelector(".region-id").value = r.id || uid("r");
    card.querySelector(".region-name").value = r.name || "";
    card.querySelector(".region-summary").value = r.summary || r.desc || "";
    card.querySelector(".region-terrain").value = r.terrain || "";
    card.querySelector(".region-climate").value = r.climate || "";
    card.querySelector(".region-notes").value = r.notes || "";
    card.querySelector(".region-landmarks").value = lmLines.join("\n");
    card.querySelector(".region-resources").value = resLines.join("\n");
    card.querySelector(".region-relations-json").value = relJson;
    root.appendChild(card);
  });
  scheduleGeoVizRefresh();
  applyAllWorldviewEditModes();
}

function collectRegionsFromDom() {
  const root = $("regionCards");
  if (!root) return [];
  return [...root.querySelectorAll(".region-card")]
    .map((card) => {
      let relations = [];
      try {
        relations = JSON.parse(card.querySelector(".region-relations-json")?.value || "[]");
        if (!Array.isArray(relations)) relations = [];
      } catch {
        relations = [];
      }
      const splitField = (sel) =>
        (card.querySelector(sel)?.value ?? "")
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean);
      return {
        id: card.querySelector(".region-id")?.value?.trim() || uid("r"),
        name: card.querySelector(".region-name")?.value?.trim() || "",
        summary: card.querySelector(".region-summary")?.value?.trim() || "",
        terrain: card.querySelector(".region-terrain")?.value?.trim() || "",
        climate: card.querySelector(".region-climate")?.value?.trim() || "",
        notes: card.querySelector(".region-notes")?.value?.trim() || "",
        landmarks: splitField(".region-landmarks"),
        resources: splitField(".region-resources"),
        relations,
      };
    })
    .filter(
      (r) =>
        r.name ||
        r.summary ||
        r.terrain ||
        r.climate ||
        r.notes ||
        (Array.isArray(r.landmarks) && r.landmarks.length) ||
        (Array.isArray(r.resources) && r.resources.length) ||
        (Array.isArray(r.relations) && r.relations.length > 0)
    );
}

function syncFactionCardBrief(card, entity) {
  if (!card || !entity) return;
  const g = card.querySelector(".faction-intro-goals");
  const tr = card.querySelector(".faction-intro-territory");
  const nm = card.querySelector(".faction-intro-name");
  if (g) g.textContent = (entity.goals || "").trim() || "（未填写）";
  if (tr) tr.textContent = (entity.territory || "").trim() || "（未填写）";
  if (nm) nm.textContent = (entity.name || "").trim() || "（未命名）";
}

function renderFactionCards(entities) {
  const root = $("factionCards");
  if (!root) return;
  root.replaceChildren();
  const list = Array.isArray(entities) && entities.length ? entities.map((e) => ({ ...e })) : [];
  list.forEach((e, idx) => {
    const card = document.createElement("div");
    card.className = "faction-card";
    const hue = (idx * 47 + 200) % 360;
    const relJson = JSON.stringify(e.relations || [], null, 2);
    const kf = (e.key_figures || []).join("\n");
    const relCount = (e.relations || []).filter((r) => r?.target_id && r.target_id !== e.id).length;
    card.innerHTML = `
      <div class="faction-card-stack">
        <div class="faction-card-toolbar">
          <p class="faction-viz-legend muted tiny">
            关系图可缩放（滚轮或按钮）。实线 → 已建档派系；虚线 → 仅 id。
          </p>
          <button type="button" class="ghost btn-icon remove-faction" title="移除此派系">×</button>
        </div>
        <div class="faction-intro-viz" style="--fv-hue:${hue}">
          <div class="faction-intro-viz-head">
            <span class="ms faction-intro-ic" aria-hidden="true">shield</span>
            <span class="faction-intro-name"></span>
          </div>
          <div class="faction-brief-line">
            <span class="faction-brief-k">目标</span>
            <p class="faction-intro-goals faction-brief-body"></p>
          </div>
          <div class="faction-brief-line">
            <span class="faction-brief-k">地盘</span>
            <p class="faction-intro-territory faction-brief-body"></p>
          </div>
        </div>
        <div class="faction-viz-wrap" style="--fv-hue:${hue}">
          <div class="faction-viz-caption">
            <span>关系网络</span>
            <span class="faction-viz-badge">${relCount} 条</span>
          </div>
          <div class="faction-viz-host" role="img" aria-label="派系关系示意"></div>
        </div>
        <div class="faction-fields">
          <div class="row-tight">
            <input type="text" class="faction-id mono" placeholder="id（英文）" />
            <input type="text" class="faction-name" placeholder="派系名称" />
          </div>
          <label class="muted tiny">目标 / 宗旨</label>
          <textarea class="faction-goals" rows="2" placeholder="派系简介：宗旨、立场…"></textarea>
          <label class="muted tiny">地盘 / 势力范围</label>
          <textarea class="faction-territory" rows="2" placeholder="控制区、据点、影响范围…"></textarea>
          <label class="muted tiny">关键人物（每行一人）</label>
          <textarea class="faction-figures" rows="2"></textarea>
          <label class="muted tiny">relations（JSON）</label>
          <textarea class="faction-relations-json json-editor-tiny" rows="2" spellcheck="false"></textarea>
        </div>
      </div>`;
    card.querySelector(".faction-id").value = e.id || uid("f");
    card.querySelector(".faction-name").value = e.name || "";
    card.querySelector(".faction-goals").value = e.goals || "";
    card.querySelector(".faction-territory").value = e.territory || "";
    card.querySelector(".faction-figures").value = kf;
    card.querySelector(".faction-relations-json").value = relJson;
    syncFactionCardBrief(card, e);
    root.appendChild(card);
    const host = card.querySelector(".faction-viz-host");
    if (host) renderSingleFactionNetwork(list[idx], list, host);
  });
  const fj = $("factionsJson");
  if (fj) fj.value = JSON.stringify(list, null, 2);
  refreshFactionChatViz();
}

function collectFactionsFromDom() {
  const root = $("factionCards");
  if (!root) return [];
  return [...root.querySelectorAll(".faction-card")].map((card) => {
    const id = card.querySelector(".faction-id")?.value?.trim() || uid("f");
    const name = card.querySelector(".faction-name")?.value?.trim() || "";
    const goals = card.querySelector(".faction-goals")?.value?.trim() || "";
    const territory = card.querySelector(".faction-territory")?.value?.trim() || "";
    const figTxt = card.querySelector(".faction-figures")?.value || "";
    const key_figures = figTxt
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    let relations = [];
    try {
      relations = JSON.parse(card.querySelector(".faction-relations-json")?.value || "[]");
      if (!Array.isArray(relations)) relations = [];
    } catch {
      relations = [];
    }
    return { id, name, goals, territory, key_figures, relations };
  });
}

/** 对话区派系要人快照：优先读派系页 DOM（未保存的编辑），否则读 state.world */
function factionsSnapshotForChatViz() {
  if (!state.world) return [];
  const root = $("factionCards");
  if (root?.querySelector(".faction-card")) return collectFactionsFromDom();
  return state.world.factions?.entities || [];
}

function refreshFactionChatViz() {
  const host = $("factionChatViz");
  if (!host) return;
  const list = factionsSnapshotForChatViz();
  if (!list.length) {
    host.className = "faction-chat-viz faction-chat-viz--empty";
    host.textContent = state.world
      ? "当前无派系实体。可用下方「写派系」「派系要人」发起对话；保存或开启「对话后同步」后将写入 factions。"
      : "选择或创建世界后，此处显示各派系要人快照（与派系页卡片一致）。";
    return;
  }
  host.className = "faction-chat-viz";
  host.innerHTML = list
    .map((e) => {
      const figs = Array.isArray(e.key_figures) ? e.key_figures.filter(Boolean) : [];
      const n = figs.length;
      const show = figs.slice(0, 4);
      const more = n > 4 ? `<li class="muted tiny">… 共 ${n} 人</li>` : "";
      const lis = show
        .map((f) => {
          const s = String(f);
          const t = s.length > 48 ? `${s.slice(0, 48)}…` : s;
          return `<li>${escapeHtml(t)}</li>`;
        })
        .join("");
      const title = escapeHtml((e.name || e.id || "未命名").slice(0, 22));
      return `<div class="faction-chat-viz-card">
        <div class="faction-chat-viz-card__name"><span class="ms" aria-hidden="true">groups</span><span>${title}</span><span class="faction-chat-viz-badge">${n} 要人</span></div>
        ${
          n
            ? `<ul class="faction-chat-viz-figures">${lis}${more}</ul>`
            : `<p class="muted tiny" style="margin:0">暂无 key_figures，可点「派系要人」请助手扩写。</p>`
        }
      </div>`;
    })
    .join("");
}

let _factionVizTimer;
function refreshAllFactionViz() {
  const root = $("factionCards");
  if (!root) return;
  const all = collectFactionsFromDom();
  const fj = $("factionsJson");
  if (fj) fj.value = JSON.stringify(all, null, 2);
  [...root.querySelectorAll(".faction-card")].forEach((card, idx) => {
    const e = all[idx];
    if (e) syncFactionCardBrief(card, e);
    const badge = card.querySelector(".faction-viz-badge");
    if (badge && e) {
      const n = (e.relations || []).filter((r) => r?.target_id && r.target_id !== e.id).length;
      badge.textContent = `${n} 条`;
    }
    const host = card.querySelector(".faction-viz-host");
    if (host && e) renderSingleFactionNetwork(e, all, host);
  });
  // Also refresh the global network
  const globalHost = $("vizFactionHost");
  if (globalHost) renderFactionGlobalNetwork(all, "vizFactionHost");
  refreshFactionChatViz();
  applyAllWorldviewEditModes();
}

function scheduleFactionVizRefresh() {
  clearTimeout(_factionVizTimer);
  _factionVizTimer = setTimeout(() => refreshAllFactionViz(), 220);
}

function renderCultureCards(entities) {
  const root = $("cultureCards");
  if (!root) return;
  root.replaceChildren();
  const list = Array.isArray(entities) && entities.length ? entities.map((e) => ({ ...e })) : [];
  list.forEach((e) => {
    const card = document.createElement("div");
    card.className = "faction-card culture-card";
    const relJson = JSON.stringify(e.relations || [], null, 2);
    const sites = (e.sacred_sites || []).join("\n");
    const kf = (e.key_figures || []).join("\n");
    const kind = ["culture", "religion", "syncretic"].includes(e.kind) ? e.kind : "culture";
    const relCount = (e.relations || []).filter((r) => r?.target_id && r.target_id !== e.id).length;
    card.innerHTML = `
      <div class="faction-card-stack">
        <div class="faction-card-toolbar">
          <p class="faction-viz-legend muted tiny">relations 的 target_id 指向另一文化实体 id</p>
          <button type="button" class="ghost btn-icon remove-culture" title="移除此条目">×</button>
        </div>
        <div class="faction-viz-wrap culture-viz-wrap">
          <div class="faction-viz-caption">
            <span>关系网络</span>
            <span class="faction-viz-badge">${relCount} 条</span>
          </div>
          <div class="culture-viz-host" role="img" aria-label="文化关系示意"></div>
        </div>
        <div class="faction-fields">
          <div class="row-tight">
            <input type="text" class="culture-id mono" placeholder="id" />
            <input type="text" class="culture-name" placeholder="名称" />
            <select class="culture-kind">
              <option value="culture">文化</option>
              <option value="religion">宗教</option>
              <option value="syncretic">融合</option>
            </select>
          </div>
          <label class="muted tiny">概述</label>
          <textarea class="culture-summary" rows="2" placeholder="人群、分布、叙事角色…"></textarea>
          <label class="muted tiny">观念 / 教义</label>
          <textarea class="culture-tenets" rows="2"></textarea>
          <label class="muted tiny">仪式 / 节日 / 禁忌</label>
          <textarea class="culture-practices" rows="2"></textarea>
          <label class="muted tiny">圣地或中心（每行一处）</label>
          <textarea class="culture-sites" rows="2"></textarea>
          <label class="muted tiny">关键人物（每行一人）</label>
          <textarea class="culture-figures" rows="2"></textarea>
          <label class="muted tiny">relations（JSON）</label>
          <textarea class="culture-relations-json json-editor-tiny" rows="2" spellcheck="false"></textarea>
        </div>
      </div>`;
    card.querySelector(".culture-id").value = e.id || uid("c");
    card.querySelector(".culture-name").value = e.name || "";
    card.querySelector(".culture-kind").value = kind;
    card.querySelector(".culture-summary").value = e.summary || "";
    card.querySelector(".culture-tenets").value = e.tenets || "";
    card.querySelector(".culture-practices").value = e.practices || "";
    card.querySelector(".culture-sites").value = sites;
    card.querySelector(".culture-figures").value = kf;
    card.querySelector(".culture-relations-json").value = relJson;
    root.appendChild(card);
    const host = card.querySelector(".culture-viz-host");
    if (host) renderSingleCultureNetwork(e, list, host);
  });
  const cj = $("culturesJson");
  if (cj) cj.value = JSON.stringify(list, null, 2);
  scheduleCultureVizRefresh();
  applyAllWorldviewEditModes();
}

function collectCulturesFromDom() {
  const root = $("cultureCards");
  if (!root) return [];
  return [...root.querySelectorAll(".culture-card")].map((card) => {
    const id = card.querySelector(".culture-id")?.value?.trim() || uid("c");
    const name = card.querySelector(".culture-name")?.value?.trim() || "";
    const kind = card.querySelector(".culture-kind")?.value || "culture";
    const summary = card.querySelector(".culture-summary")?.value?.trim() || "";
    const tenets = card.querySelector(".culture-tenets")?.value?.trim() || "";
    const practices = card.querySelector(".culture-practices")?.value?.trim() || "";
    const sitesTxt = card.querySelector(".culture-sites")?.value || "";
    const sacred_sites = sitesTxt
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const figTxt = card.querySelector(".culture-figures")?.value || "";
    const key_figures = figTxt
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    let relations = [];
    try {
      relations = JSON.parse(card.querySelector(".culture-relations-json")?.value || "[]");
      if (!Array.isArray(relations)) relations = [];
    } catch {
      relations = [];
    }
    return {
      id,
      name,
      kind,
      summary,
      tenets,
      practices,
      sacred_sites,
      key_figures,
      relations,
    };
  });
}

let _cultureVizTimer;
function scheduleCultureVizRefresh() {
  clearTimeout(_cultureVizTimer);
  _cultureVizTimer = setTimeout(() => refreshCultureGlobalViz(), 200);
}

function refreshCultureGlobalViz() {
  const host = $("vizCulturesHost");
  if (!host) return;
  const entities = collectCulturesFromDom();
  const cj = $("culturesJson");
  if (cj) cj.value = JSON.stringify(entities, null, 2);
  renderCultureGlobalNetwork(entities, "vizCulturesHost");
  // Also refresh per-card culture networks
  const root = $("cultureCards");
  if (root) {
    [...root.querySelectorAll(".culture-card")].forEach((card, idx) => {
      const e = entities[idx];
      if (!e) return;
      const cardHost = card.querySelector(".culture-viz-host");
      if (cardHost) renderSingleCultureNetwork(e, entities, cardHost);
      const badge = card.querySelector(".faction-viz-badge");
      if (badge) {
        const n = (e.relations || []).filter((r) => r?.target_id && r.target_id !== e.id).length;
        badge.textContent = `${n} 条`;
      }
    });
  }
}

function renderStatStrip(w) {
  const el = $("statStrip");
  if (!el) return;
  if (!w) {
    el.innerHTML = "";
    return;
  }
  const g = w.geography || {};
  const lm = (g.landmarks || []).length;
  const rs = (g.resources || []).length;
  const pt = (w.power_system?.tiers || []).length;
  const ig = (w.item_quality_system?.grades || []).length;
  const at = (w.attribute_system?.stats || []).length;
  const fc = (w.factions?.entities || []).length;
  const cu = (w.cultures?.entities || []).length;
  const ev = (w.history?.events || []).length;
  const eb = (w.ecology?.biomes || []).length;
  const es = (w.ecology?.species || []).length;
  const econ =
    (w.economy?.currencies?.length || 0) +
    (w.economy?.markets?.length || 0) +
    (w.economy?.trade_routes?.length || 0) +
    (w.economy?.trade_goods?.length || 0);
  const wlabel = escapeHtml((w.meta?.name || w.meta?.id || "世界").toString().slice(0, 24));
  const pill = (icon, t) =>
    `<span class="pill"><span class="ms pill-ic" aria-hidden="true">${icon}</span>${t}</span>`;
  el.innerHTML = [
    pill("auto_stories", wlabel),
    pill("place", `地标 ${lm}`),
    pill("forest", `资源 ${rs}`),
    pill("bolt", `境界 ${pt}`),
    pill("bubble_chart", `属性 ${at}`),
    pill("diamond", `品质 ${ig}`),
    pill("groups", `派系 ${fc}`),
    pill("diversity_3", `文化 ${cu}`),
    pill("event", `事件 ${ev}`),
    pill("forest", `生态 ${eb}/${es}`),
    pill("payments", `经济 ${econ}`),
    pill("recent_actors", `人物 ${(w.characters?.entities || []).length}`),
    pill("tag", `v${w.meta?.version ?? 0}`),
  ].join("");
}

const STORY_THINKING_LABELS = {
  chat: "AI 正在思考回复…",
  sync: "正在将对话整理为结构化设定…",
  "generate-macro": "AI 正在生成全书粗纲…",
  "generate-beats": "AI 正在生成章节细纲…",
  "generate-manuscript": "AI 正在撰写本章文稿…",
};

const STORY_GEN_BUTTON_IDS = [
  "btnStoryGenMacro",
  "btnStoryGenBeats",
  "btnStoryGenManuscript",
  "btnStoryChatGenManuscript",
  "btnStorySend",
];

function resolveStoryThinkingPanel() {
  if (state.activeView === "storyChat") return "story";
  if (isStoryPanelView(state.activeView)) return "storyWb";
  return "story";
}

const STORY_GEN_ASIDE_ALL = [
  ["storyChapterNav", "storyWbAsideGenHint", "storyWbAsideGenHintText"],
  ["storyChatChapterNav", "storyChatAsideGenHint", "storyChatAsideGenHintText"],
];

function storyGenAsideForActiveView() {
  if (state.activeView === "storyChat") return STORY_GEN_ASIDE_ALL[1];
  if (isStoryPanelView(state.activeView)) return STORY_GEN_ASIDE_ALL[0];
  return null;
}

function resetStoryGenerationUi() {
  state.storyGen = null;
  for (const id of ["storyChatThinking", "storyWbThinking"]) {
    const strip = $(id);
    if (!strip) continue;
    strip.hidden = true;
    strip.classList.remove("thinking-strip--visible");
    const stepsEl = strip.querySelector(".thinking-steps");
    if (stepsEl) stepsEl.remove();
    const lab = strip.querySelector(".thinking-label");
    if (lab) lab.textContent = "AI 正在思考…";
  }
  for (const [navId, hintId] of STORY_GEN_ASIDE_ALL) {
    const nav = $(navId);
    const hint = $(hintId);
    if (nav) {
      nav.setAttribute("aria-busy", "false");
      nav.classList.remove("story-chapter-nav--busy");
      nav.querySelectorAll(".story-ch-nav-btn").forEach((btn) => {
        btn.classList.remove("story-ch-nav-btn--generating");
        btn.disabled = false;
      });
    }
    if (hint) {
      hint.hidden = true;
      hint.classList.remove("story-wb-aside-gen-hint--visible");
    }
  }
  for (const id of STORY_GEN_BUTTON_IDS) {
    const btn = $(id);
    if (btn) btn.disabled = false;
  }
  document.querySelectorAll(".story-wb-layout").forEach((layout) => {
    layout.classList.remove("story-wb-layout--generating");
  });
  document.querySelectorAll(".story-preview--generating").forEach((el) => {
    el.classList.remove("story-preview--generating");
  });
}

function applyStoryGenerationUi(gen) {
  if (!gen) {
    resetStoryGenerationUi();
    return;
  }
  const message = gen.message || STORY_THINKING_LABELS[gen.phase] || STORY_THINKING_LABELS.chat;
  const chapterIds = new Set(gen.chapterIds || []);
  const activeAside = storyGenAsideForActiveView();

  const showChatStrip = gen.panel === "story" && state.activeView === "storyChat";
  const showWbStrip = gen.panel === "storyWb" && isStoryPanelView(state.activeView);
  for (const [stripId, show] of [
    ["storyChatThinking", showChatStrip],
    ["storyWbThinking", showWbStrip],
  ]) {
    const strip = $(stripId);
    if (!strip) continue;
    strip.hidden = !show;
    strip.classList.toggle("thinking-strip--visible", show);
    const lab = strip.querySelector(".thinking-label");
    if (lab && show) lab.textContent = message;
  }

  for (const [navId, hintId, hintTextId] of STORY_GEN_ASIDE_ALL) {
    const nav = $(navId);
    const hint = $(hintId);
    const hintTxt = $(hintTextId);
    const isActiveAside = activeAside && activeAside[0] === navId;
    if (nav) {
      const busy = !!isActiveAside;
      nav.setAttribute("aria-busy", busy ? "true" : "false");
      nav.classList.toggle("story-chapter-nav--busy", busy);
      nav.querySelectorAll(".story-ch-nav-btn").forEach((btn) => {
        const cid = btn.dataset.storyChapterId || "";
        const isChapterTarget = busy && chapterIds.size > 0 && chapterIds.has(cid);
        btn.classList.toggle("story-ch-nav-btn--generating", isChapterTarget);
        btn.disabled = busy;
      });
    }
    if (hint) {
      const showHint = !!isActiveAside;
      hint.hidden = !showHint;
      hint.classList.toggle("story-wb-aside-gen-hint--visible", showHint);
    }
    if (hintTxt && isActiveAside) hintTxt.textContent = message;
  }

  const previewOn = new Set(gen.previewIds || []);
  for (const id of ["storyMacroPreview", "storyBeatPreview", "storyManuscriptPreview"]) {
    const el = $(id);
    if (el) el.classList.toggle("story-preview--generating", previewOn.has(id));
  }

  for (const id of STORY_GEN_BUTTON_IDS) {
    const btn = $(id);
    if (btn) btn.disabled = true;
  }
  document.querySelectorAll(".story-wb-layout").forEach((layout) => {
    layout.classList.toggle("story-wb-layout--generating", true);
  });
}

let _storyGenToken = 0;

function beginStoryGeneration(phase, opts = {}) {
  _storyGenToken += 1;
  const panel = opts.panel || resolveStoryThinkingPanel();
  state.storyGen = {
    token: _storyGenToken,
    phase,
    panel,
    message: opts.message || STORY_THINKING_LABELS[phase] || STORY_THINKING_LABELS.chat,
    chapterIds: (opts.chapterIds || []).map((x) => String(x).trim()).filter(Boolean),
    previewIds: opts.previewIds || [],
  };
  applyStoryGenerationUi(state.storyGen);
  return _storyGenToken;
}

function endStoryGeneration(opts = {}) {
  if (opts.token != null && state.storyGen && opts.token !== state.storyGen.token) return;
  resetStoryGenerationUi();
}

function showGenerationStep(evt) {
  const stripId =
    state.activeView === "storyChat" ? "storyChatThinking" : "storyWbThinking";
  const strip = $(stripId);
  if (!strip || strip.hidden) return;
  const lab = strip.querySelector(".thinking-label");
  if (lab && evt.label) lab.textContent = evt.label;

  const total = evt.total || 3;
  const index = evt.index || 1;
  const phase = evt.phase;

  let stepsEl = strip.querySelector(".thinking-steps");
  if (!stepsEl) {
    stepsEl = document.createElement("div");
    stepsEl.className = "thinking-steps";
    strip.appendChild(stepsEl);
  }

  const LABELS_BY_TOTAL = {
    3: ["撰写", "审校", "完成"],
    4: ["撰写", "审校", "润色", "完成"],
  };
  const stepLabels = LABELS_BY_TOTAL[total] || LABELS_BY_TOTAL[3];

  let html = "";
  for (let i = 1; i <= total; i++) {
    let cls = "thinking-step-dot";
    if (i < index || phase === "done") {
      cls += " thinking-step-dot--done";
    } else if (i === index) {
      cls += " thinking-step-dot--active";
    }
    html += `<span class="${cls}" title="${stepLabels[i - 1]}"></span>`;
    if (i < total) {
      const sepDone = i < index || phase === "done";
      html += `<span class="thinking-step-sep${sepDone ? " thinking-step-sep--done" : ""}"></span>`;
    }
  }
  html += `<span class="thinking-step-label-text">${stepLabels[index - 1] || ""}</span>`;
  stepsEl.innerHTML = html;

  if (phase === "done") {
    setTimeout(() => {
      const s = strip.querySelector(".thinking-steps");
      if (s) s.remove();
      if (lab) lab.textContent = "AI 正在思考…";
    }, 2500);
  }
}

function setThinking(phase, opts = {}) {
  const WORLD_STRIPS = ["chatThinking", "charChatThinking"];
  if (!phase) {
    for (const id of WORLD_STRIPS) {
      const strip = $(id);
      if (!strip) continue;
      strip.hidden = true;
      strip.classList.remove("thinking-strip--visible");
    }
    return;
  }
  let panel = opts.panel;
  if (!panel) {
    if (state.activeView === "charChat") panel = "char";
    else panel = "world";
  }
  const el = panel === "char" ? $("charChatThinking") : $("chatThinking");
  for (const id of WORLD_STRIPS) {
    const strip = $(id);
    if (!strip || strip === el) continue;
    strip.hidden = true;
    strip.classList.remove("thinking-strip--visible");
  }
  if (!el) return;
  const lab = el.querySelector(".thinking-label");
  el.hidden = false;
  el.classList.add("thinking-strip--visible");
  if (lab) {
    const custom = opts.message;
    if (custom) lab.textContent = custom;
    else if (phase === "sync") lab.textContent = "正在将对话整理为结构化设定…";
    else lab.textContent = "模型正在思考回复…";
  }
}

function renderHistoryMajorTimeline(events) {
  const el = $("historyMajorTimeline");
  if (!el) return;
  const list = Array.isArray(events) ? events : [];
  if (!list.length) {
    el.innerHTML = `<div class="viz-empty">暂无事件，可在下方 JSON 中添加，或在时间轴卡片中编辑（有事件后）</div>`;
    return;
  }
  el.innerHTML = list
    .map((e, i) => {
      const cons = (Array.isArray(e.consequences) ? e.consequences : [])
        .map((x) => String(x).trim())
        .filter(Boolean);
      const links = (Array.isArray(e.linked_faction_ids) ? e.linked_faction_ids : [])
        .map((x) => String(x).trim())
        .filter(Boolean);
      const whenId = `hist-when-${i}`;
      const titleId = `hist-title-${i}`;
      return `<div class="hist-tl-row hist-tl-row--editable" data-history-event-index="${i}">
        <div class="hist-tl-axis"><span class="hist-tl-dot"></span>${
          i < list.length - 1 ? '<span class="hist-tl-line"></span>' : ""
        }</div>
        <div class="hist-tl-card hist-tl-card--editable">
          <label class="hist-field-lbl muted tiny" for="${whenId}">时间 / 年代</label>
          <input id="${whenId}" type="text" class="hist-field-input" data-hist-field="when" value="${escapeAttr(
            (e.when ?? "").toString()
          )}" placeholder="如：第三纪 末叶" autocomplete="off" />
          <label class="hist-field-lbl muted tiny" for="${titleId}">标题</label>
          <input id="${titleId}" type="text" class="hist-field-input" data-hist-field="title" value="${escapeAttr(
            (e.title ?? "").toString()
          )}" placeholder="事件名" autocomplete="off" />
          <label class="muted tiny hist-field-lbl">摘要</label>
          <textarea class="hist-field-ta" rows="3" data-hist-field="summary" spellcheck="true" placeholder="叙事摘要…">${escapeHtml(
            (e.summary ?? "").toString()
          )}</textarea>
          <label class="muted tiny hist-field-lbl">后果（一行一条）</label>
          <textarea class="hist-field-ta" rows="2" data-hist-field="consequences" spellcheck="true" placeholder="每行一条后果">${escapeHtml(
            cons.join("\n")
          )}</textarea>
          <label class="muted tiny hist-field-lbl">关联派系 id（一行一个）</label>
          <textarea class="hist-field-ta" rows="2" data-hist-field="linked_faction_ids" spellcheck="false" placeholder="与 factions.entities[].id 对应">${escapeHtml(
            links.join("\n")
          )}</textarea>
        </div>
      </div>`;
    })
    .join("");
}

let _factionBriefTimer;
function scheduleFactionGlobalBriefPreview() {
  clearTimeout(_factionBriefTimer);
  _factionBriefTimer = setTimeout(updateFactionGlobalBriefPreview, 140);
}

function updateFactionGlobalBriefPreview() {
  const el = $("factionGlobalBrief");
  const ta = $("factionSummary");
  if (!el || !ta) return;
  const t = ta.value.trim();
  if (!t) {
    el.innerHTML = `<span class="muted tiny">（在下方「派系总览」中填写后，此处显示可读预览）</span>`;
    return;
  }
  el.innerHTML = `<div class="faction-brief-prose">${escapeHtml(t).replace(/\n/g, "<br/>")}</div>`;
}

let _histJsonTimer;
function scheduleHistoryVizFromForm() {
  clearTimeout(_histJsonTimer);
  _histJsonTimer = setTimeout(() => {
    let events = [];
    try {
      events = JSON.parse($("historyJson")?.value || "[]");
    } catch {
      return;
    }
    if (!Array.isArray(events)) return;
    if (state.world) {
      state.world.history = state.world.history || {};
      state.world.history.events = events;
    }
    renderHistoryMajorTimeline(events);
    void drawMermaidHost($("vizHistoryHost"), buildHistoryMermaid(events));
    applyAllWorldviewEditModes();
  }, 280);
}

/** 派系关系图容器：缩放（按钮 + 滚轮）+ 左键拖拽平移 */
function initMermaidZoom(wrap, opts = {}) {
  if (!wrap) return;
  const surface = wrap.querySelector(".mermaid-zoom-surface");
  const viewport = wrap.querySelector(".mermaid-zoom-viewport");
  const pctEl = wrap.querySelector(".mzoom-pct");
  if (!surface || !viewport) return;

  if (opts.resetPan) {
    wrap.dataset.mzoomTx = "0";
    wrap.dataset.mzoomTy = "0";
  }

  const clamp = (s) => Math.min(2.6, Math.max(0.35, s));
  const apply = () => {
    let scale = parseFloat(wrap.dataset.mzoomScale || "1");
    if (Number.isNaN(scale)) scale = 1;
    scale = clamp(scale);
    wrap.dataset.mzoomScale = String(scale);
    let tx = parseFloat(wrap.dataset.mzoomTx || "0");
    let ty = parseFloat(wrap.dataset.mzoomTy || "0");
    if (Number.isNaN(tx)) tx = 0;
    if (Number.isNaN(ty)) ty = 0;
    wrap.dataset.mzoomTx = String(tx);
    wrap.dataset.mzoomTy = String(ty);
    surface.style.transformOrigin = "0 0";
    surface.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    if (pctEl) pctEl.textContent = `${Math.round(scale * 100)}%`;
  };

  if (wrap.dataset.mzoomHandlers !== "1") wrap.dataset.mzoomScale = "1";
  apply();

  if (wrap.dataset.mzoomHandlers === "1") return;
  wrap.dataset.mzoomHandlers = "1";

  wrap.addEventListener("click", (e) => {
    const t = e.target;
    if (!t.closest) return;
    let s = parseFloat(wrap.dataset.mzoomScale || "1");
    if (Number.isNaN(s)) s = 1;
    if (t.closest(".mzoom-in")) wrap.dataset.mzoomScale = String(clamp(s * 1.14));
    else if (t.closest(".mzoom-out")) wrap.dataset.mzoomScale = String(clamp(s / 1.14));
    else if (t.closest(".mzoom-reset")) {
      wrap.dataset.mzoomScale = "1";
      wrap.dataset.mzoomTx = "0";
      wrap.dataset.mzoomTy = "0";
      viewport.scrollTo(0, 0);
    } else return;
    apply();
  });

  viewport.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      let s = parseFloat(wrap.dataset.mzoomScale || "1");
      if (Number.isNaN(s)) s = 1;
      wrap.dataset.mzoomScale = String(clamp(s * (e.deltaY < 0 ? 1.06 : 0.94)));
      apply();
    },
    { passive: false }
  );

  const onDocMove = (ev) => {
    const session = wrap.__mzoomPanSession;
    if (!session) return;
    const dx = ev.clientX - session.sx;
    const dy = ev.clientY - session.sy;
    wrap.dataset.mzoomTx = String(session.tx0 + dx);
    wrap.dataset.mzoomTy = String(session.ty0 + dy);
    apply();
  };

  const onDocUp = () => {
    wrap.__mzoomPanSession = null;
    viewport.classList.remove("is-dragging");
    document.removeEventListener("mousemove", onDocMove);
    document.removeEventListener("mouseup", onDocUp);
  };

  viewport.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    if (e.target.closest(".mermaid-zoom-toolbar")) return;
    const tx0 = parseFloat(wrap.dataset.mzoomTx || "0");
    const ty0 = parseFloat(wrap.dataset.mzoomTy || "0");
    wrap.__mzoomPanSession = {
      sx: e.clientX,
      sy: e.clientY,
      tx0: Number.isNaN(tx0) ? 0 : tx0,
      ty0: Number.isNaN(ty0) ? 0 : ty0,
    };
    viewport.classList.add("is-dragging");
    e.preventDefault();
    document.addEventListener("mousemove", onDocMove);
    document.addEventListener("mouseup", onDocUp);
  });
}

async function drawMermaidHost(host, def) {
  if (!host) return;
  host.innerHTML = "";
  if (!def || !window.mermaid) return;
  const id = "mmd" + Math.random().toString(36).slice(2, 11);
  const zoomWrap = host.closest("[data-mermaid-zoom]");
  try {
    if (typeof mermaid.render === "function") {
      const { svg } = await mermaid.render(id, def);
      host.innerHTML = svg;
      initMermaidZoom(zoomWrap, { resetPan: true });
      return;
    }
  } catch (_) {
    /* fall through */
  }
  try {
    host.innerHTML = `<pre class="mermaid">${def.replace(/</g, "&lt;")}</pre>`;
    const node = host.querySelector("pre");
    if (node && typeof mermaid.run === "function") await mermaid.run({ nodes: [node] });
    initMermaidZoom(zoomWrap, { resetPan: true });
  } catch (_) {
    host.innerHTML = "";
  }
}

function refreshContextPanel() {
  const rawEl = $("contextRawJson");
  const powSys = $("vizPowerSystemModules");
  const powTrees = $("vizPowerSkillTreeModules");
  const powProf = $("vizPowerProfessionModules");
  const itemMods = $("vizItemGradesRoot");
  const fac = $("vizFactionHost");
  const his = $("vizHistoryHost");
  const cult = $("vizCulturesHost");

  const geoPanel = $("geoNetworkHost");

  if (!state.world) {
    renderStatStrip(null);
    if (powSys) powSys.innerHTML = "";
    if (powTrees) powTrees.innerHTML = "";
    if (powProf) powProf.innerHTML = "";
    const profPromo = $("vizProfessionPromoHost");
    if (profPromo) profPromo.innerHTML = "";
    if (itemMods) itemMods.innerHTML = "";
    if (geoPanel) geoPanel.innerHTML = "";
    if (fac) fac.innerHTML = "";
    if (cult) cult.innerHTML = "";
    if (his) his.innerHTML = "";
    renderHistoryMajorTimeline([]);
    const fgb = $("factionGlobalBrief");
    if (fgb) fgb.innerHTML = "";
    if (rawEl) rawEl.textContent = "";
    const rlo = $("referenceLintOut");
    if (rlo) rlo.innerHTML = "";
    renderAttributePanel(null);
    void refreshSnapshotPanel();
    applyAllWorldviewEditModes();
    return;
  }

  const w = state.world;
  renderStatStrip(w);
  renderPowerTierDashboardModules(w);
  renderItemGradeDashboardModules(w);
  renderAttributePanel(w);

  refreshGeoNetworkViz();
  if (fac) renderFactionGlobalNetwork(w.factions?.entities, "vizFactionHost");
  const cultHost = $("vizCulturesHost");
  if (cultHost) renderCultureGlobalNetwork(w.cultures?.entities || [], "vizCulturesHost");
  const ev = w.history?.events || [];
  renderHistoryMajorTimeline(ev);
  void drawMermaidHost(his, buildHistoryMermaid(ev));

  if (rawEl) rawEl.textContent = JSON.stringify(w, null, 2);
  void refreshSnapshotPanel();
  void refreshTokenUsagePanel();
  // Refresh token usage when the details panel is reopened
  const tokenDetails = $("ctxTokenUsage");
  if (tokenDetails && !tokenDetails._tokenToggleBound) {
    tokenDetails._tokenToggleBound = true;
    tokenDetails.addEventListener("toggle", () => {
      if (tokenDetails.open) void refreshTokenUsagePanel();
    });
  }
  applyAllWorldviewEditModes();
}

async function refreshSnapshotPanel() {
  const leftSel = $("snapshotDiffLeft");
  const rightSel = $("snapshotDiffRight");
  const rbSel = $("snapshotRollbackSel");
  const wrap = $("snapshotDiffWrap");
  const pre = $("snapshotDiffPre");
  const meta = $("snapshotDiffMeta");
  const btnDiff = $("btnSnapshotDiff");
  const btnRb = $("btnSnapshotRollback");
  const btnDel = $("btnSnapshotDelete");
  if (!leftSel || !rightSel || !rbSel) return;

  if (!state.world?.meta?.id) {
    leftSel.innerHTML = "";
    rightSel.innerHTML = "";
    rbSel.innerHTML = "";
    if (wrap) wrap.hidden = true;
    if (pre) pre.textContent = "";
    if (meta) meta.textContent = "";
    if (btnDiff) btnDiff.disabled = true;
    if (btnRb) btnRb.disabled = true;
    return;
  }

  const id = state.world.meta.id;
  const cv = state.world.meta?.version ?? "?";
  try {
    const data = await api(`/api/worlds/${id}/snapshots`);
    const snaps = Array.isArray(data.snapshots) ? data.snapshots : [];

    leftSel.innerHTML = "";
    rightSel.innerHTML = "";
    rbSel.innerHTML = "";

    const optCurrent = document.createElement("option");
    optCurrent.value = "current";
    optCurrent.textContent = `当前 v${cv}`;
    rightSel.appendChild(optCurrent);

    for (const s of snaps) {
      const v = s.version;
      const ts = (s.updated_at || "").toString().slice(0, 19);
      const label = `v${v}${ts ? " · " + ts : ""}`;

      const ol = document.createElement("option");
      ol.value = String(v);
      ol.textContent = label;
      leftSel.appendChild(ol);

      const or = document.createElement("option");
      or.value = String(v);
      or.textContent = label;
      rightSel.appendChild(or);

      const obr = document.createElement("option");
      obr.value = String(v);
      obr.textContent = `v${v}`;
      rbSel.appendChild(obr);
    }

    if (leftSel.options.length) {
      leftSel.selectedIndex = 0;
    }
    rightSel.selectedIndex = 0;

    const has = snaps.length > 0;
    if (btnDiff) btnDiff.disabled = !has;
    if (btnRb) btnRb.disabled = !has;
    if (btnDel) btnDel.disabled = !has;
    if (!has && wrap) {
      wrap.hidden = true;
      if (meta) meta.textContent = "";
      if (pre) pre.innerHTML = "";
    }
  } catch {
    leftSel.innerHTML = "";
    rightSel.innerHTML = "";
    rbSel.innerHTML = "";
    if (btnDiff) btnDiff.disabled = true;
    if (btnRb) btnRb.disabled = true;
  }
}

function renderSnapshotDiffFromApi(body) {
  const wrap = $("snapshotDiffWrap");
  const pre = $("snapshotDiffPre");
  const meta = $("snapshotDiffMeta");
  if (!wrap || !pre) return;
  wrap.hidden = false;
  const left = body.left ?? "";
  const right = body.right ?? "";
  const trunc = body.truncated ? "（已截断）" : "";
  if (meta) meta.textContent = `左：${left} → 右：${right} ${trunc}`.trim();
  const lines = body.lines || [];
  pre.innerHTML = lines
    .map((ln) => {
      const k = ln.kind === "add" ? "add" : ln.kind === "rem" ? "rem" : "ctx";
      return `<span class="diff-line diff-line--${k}">${escapeHtml(String(ln.text ?? ""))}</span>`;
    })
    .join("");
}

async function runSnapshotDiff() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  const left = $("snapshotDiffLeft")?.value;
  const right = $("snapshotDiffRight")?.value;
  if (!left || !right) return toast("请选择对比两端");
  try {
    const params = new URLSearchParams({ left, right });
    const res = await api(`/api/worlds/${id}/snapshots/diff?${params.toString()}`);
    renderSnapshotDiffFromApi(res);
  } catch (e) {
    toast("diff 失败：" + (e?.message || e));
  }
}

async function runSnapshotRollback() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  const v = parseInt($("snapshotRollbackSel")?.value || "", 10);
  if (!Number.isFinite(v) || v < 1) return toast("请选择有效快照版本");
  if (
    !confirm(
      `确定回滚到 v${v} 的快照？当前表单未保存的修改将丢失，落盘后版本号 +1。`
    )
  )
    return;
  try {
    await api(`/api/worlds/${id}/snapshots/rollback`, {
      method: "POST",
      body: JSON.stringify({ snapshot_version: v }),
    });
    await loadWorld(id);
    toast("已回滚并落盘");
    void refreshSnapshotPanel();
  } catch (e) {
    toast("回滚失败：" + (e?.message || e));
  }
}

async function deleteSnapshot() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  const v = parseInt($("snapshotRollbackSel")?.value || "", 10);
  if (!Number.isFinite(v) || v < 1) return toast("请选择有效快照版本");
  if (!confirm(`确定删除 v${v} 的快照？此操作不可撤销。`)) return;
  try {
    await api(`/api/worlds/${id}/snapshots/${v}`, { method: "DELETE" });
    toast(`已删除 v${v} 快照`);
    void refreshSnapshotPanel();
  } catch (e) {
    toast("删除失败：" + (e?.message || e));
  }
}

async function clearSnapshots() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  if (!confirm("确定清空版本快照历史？将保留最新一份，其余全部删除。此操作不可撤销。")) return;
  try {
    const res = await api(`/api/worlds/${id}/snapshots`, { method: "DELETE" });
    toast(`已清空 ${res.deleted ?? 0} 个快照`);
    void refreshSnapshotPanel();
  } catch (e) {
    toast("清空失败：" + (e?.message || e));
  }
}

async function switchView(name) {
  const route = resolveStoryPanelRoute(name);
  name = route.panel;
  if (route.storySubView) state.storySubView = route.storySubView;
  if (route.activeStoryNav) state.activeStoryNav = route.activeStoryNav;
  if (route.storyOutlineSub) state.storyOutlineSub = route.storyOutlineSub;
  state.activeView = name;
  syncNavActiveButtons();
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("active", p.id === `view-${name}`);
  });
  if (name === "files") refreshFilesView();
  if (name === "search") refreshSearchView();
  if (name === "story" || name === "storyChat" || isStoryPanelView(name)) {
    resetStoryGenerationUi();
  }
  if (name === "story") {
    state.storyUnitLabel = storyUnitLabelForMode(state.world?.meta?.creative_mode || $("genreMode")?.value);
    storyMetaToForm();
    await refreshStoryPanel();
    setStorySubView(state.storySubView || "overview");
  }
  if (name === "cultures") scheduleCultureVizRefresh();
  updateCultureHint();
  if (name === "chat") refreshFactionChatViz();
  if (name === "charChat") renderCharMessages();
  if (name === "storyChat") {
    void refreshStoryChaptersAligned();
    renderStoryMessages();
  }
  if (isCharacterPanelView(name)) scheduleCharactersVizFromForm();
  if (name === "charKnowledge") renderKnowledgePanel();
  if (name === "powers") setPowerSubView(state.powerSubView || "system");
  if (name === "geo") setGeoSubView(state.geoSubView || "overview");
  if (name === "ecology") {
    requestAnimationFrame(() => setEcologySubView(state.ecologySubView || "overview"));
  }
  refreshContextPanel();
}

/** 对话后同步若写入了 economy，切换到「经济」页以便立即看到表单与 JSON（须已 worldToForm） */
function navigateToEconomyAfterSyncIfNeeded(updatedSections) {
  if (!Array.isArray(updatedSections) || !updatedSections.includes("economy")) return;
  requestAnimationFrame(() => {
    switchView("economy");
    $("view-economy")?.querySelector(".card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

/** 情节构建同步后跳转到对应情节子栏 */
function navigateToCharactersAfterSyncIfNeeded(updatedSections) {
  if (!Array.isArray(updatedSections) || !updatedSections.includes("characters")) return;
  requestAnimationFrame(() => {
    switchView("charData");
    $("view-charData")?.querySelector(".card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function navigateToStoryAfterSyncIfNeeded(updatedSections) {
  if (!Array.isArray(updatedSections) || !updatedSections.includes("story")) return;
  if (state.activeView === "storyChat") {
    void refreshStoryChaptersAligned();
    return;
  }
  requestAnimationFrame(() => {
    const fs = state.world?.story?.foreshadowing;
    if (Array.isArray(fs) && fs.length) switchView("storyForeshadow");
    else if (state.world?.story?.chapters?.length) switchView("storyOutline");
    else switchView("storyOverview");
    $("view-story")?.querySelector(".story-workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function storyUnitLabelForMode(mode) {
  const m = (mode || "").trim().toLowerCase();
  if (m === "game") return "章节";
  if (m === "coc" || m === "dnd") return "跑团会话";
  return "章";
}

function stripAuthorOnlyMarkdown(md) {
  const t = (md ?? "").toString();
  const m = t.match(/^##\s*作者备注\s*$/m);
  if (!m || m.index == null) return t;
  return t.slice(0, m.index).trim();
}

function updateStoryMarkdownPreview(previewId, text, authorView) {
  const el = $(previewId);
  if (!el) return;
  const raw = authorView ? text : stripAuthorOnlyMarkdown(text);
  el.innerHTML = renderAssistantMarkdownHtml(raw);
}

function sortedStoryChapters() {
  const arr = state.world?.story?.chapters;
  if (!Array.isArray(arr)) return [];
  return [...arr].sort((a, b) => (a.order || 0) - (b.order || 0) || String(a.id).localeCompare(String(b.id)));
}

function storyMetaToForm() {
  const s = state.world?.story || {};
  const unit = state.storyUnitLabel || storyUnitLabelForMode($("genreMode")?.value);
  if ($("storyUnitLine")) $("storyUnitLine").textContent = `情节单元：${unit}`;
  if ($("storySummary")) $("storySummary").value = s.summary ?? "";
  if ($("storyDesignNotes")) $("storyDesignNotes").value = s.design_notes ?? "";
  if ($("storyChaptersJson"))
    $("storyChaptersJson").value = JSON.stringify(s.chapters ?? [], null, 2);
  if ($("storyForeshadowJson"))
    $("storyForeshadowJson").value = JSON.stringify(s.foreshadowing ?? [], null, 2);
  const n = s.narrator || {};
  if ($("storyNarratorPerson")) $("storyNarratorPerson").value = n.person || "third_person_limited";
  if ($("storyNarratorVoice")) $("storyNarratorVoice").value = n.voice_notes ?? "";
  const wd = s.writing_defaults || {};
  if ($("storyAttachPrev")) $("storyAttachPrev").value = String(wd.attach_prev_chapters ?? 3);
  if ($("storyToggleKG")) $("storyToggleKG").checked = wd.enable_narrative_kg !== false;
  if ($("storyToggleConsistency")) $("storyToggleConsistency").checked = wd.enable_consistency_check !== false;
  if ($("storyToggleSentiment")) $("storyToggleSentiment").checked = wd.enable_sentiment_track !== false;
  if ($("storyTogglePolisher")) $("storyTogglePolisher").checked = wd.enable_polisher !== false;
  if ($("storyPolishMaxRounds")) $("storyPolishMaxRounds").value = String(wd.polish_max_rounds ?? 2);
  if ($("storyChatTogglePolisher")) $("storyChatTogglePolisher").checked = wd.enable_polisher !== false;
  if ($("storyChatPolishMaxRounds")) $("storyChatPolishMaxRounds").value = String(wd.polish_max_rounds ?? 2);
  if ($("storyToggleChunking")) $("storyToggleChunking").checked = wd.enable_scene_chunking !== false;
  if ($("storyChatToggleChunking")) $("storyChatToggleChunking").checked = wd.enable_scene_chunking !== false;
  if ($("storyToggleUnified")) $("storyToggleUnified").checked = wd.enable_unified_extractors === true;
  if ($("storyChatToggleUnified")) $("storyChatToggleUnified").checked = wd.enable_unified_extractors === true;
  if ($("storyToggleAgents")) $("storyToggleAgents").checked = wd.enable_character_agents === true;
  if ($("storyChatToggleAgents")) $("storyChatToggleAgents").checked = wd.enable_character_agents === true;
  if ($("storyAgentMaxRounds")) $("storyAgentMaxRounds").value = String(wd.agent_max_rounds ?? 4);
  if ($("storyChatAgentMaxRounds")) $("storyChatAgentMaxRounds").value = String(wd.agent_max_rounds ?? 4);
  // Update agent panel visual state
  _updateAgentPanelUI(wd.enable_character_agents === true);
  // Sync agent toggles between panels
  _bindAgentToggleSync();
  if ($("storyToggleKnowledge")) $("storyToggleKnowledge").checked = wd.enable_knowledge_track !== false;
  if ($("storyToggleDecisions")) $("storyToggleDecisions").checked = wd.enable_decision_track !== false;
  if ($("storyTogglePhysical")) $("storyTogglePhysical").checked = wd.enable_physical_state_track !== false;
  if ($("storyToggleTimeline")) $("storyToggleTimeline").checked = wd.enable_personal_timeline_track !== false;
  void refreshUsageStats();
  refreshStoryNarratorSelect(n.character_id || "");
  refreshStoryChapterSelects();
  syncStoryChatWritingControlsFromForm();
  renderStoryChapterNav();
  renderChapterStatusList();
  renderStoryForeshadowTimeline(s.foreshadowing ?? []);
  renderRuntimeStates();
  void updateRagStatusDot();
  updateStoryWbStats();
  updateStoryWbTitle();
}

function refreshStoryNarratorSelect(selectedId) {
  const ents = state.world?.characters?.entities || [];
  let html = '<option value="">（不绑定 POV 角色）</option>';
  for (const e of ents) {
    if (!e || typeof e !== "object") continue;
    const id = String(e.id ?? "").trim();
    if (!id) continue;
    const name = String(e.name ?? id).trim();
    const selAttr = id === selectedId ? " selected" : "";
    html += `<option value="${escapeAttr(id)}"${selAttr}>${escapeHtml(name)} · ${escapeHtml(id)}</option>`;
  }
  for (const id of ["storyNarratorCharacter", "storyChatNarratorCharacter"]) {
    const sel = $(id);
    if (sel) sel.innerHTML = html;
  }
}

function syncStoryChatWritingControlsFromForm() {
  const sn = state.world?.story?.narrator || {};
  const wd = state.world?.story?.writing_defaults || {};
  if ($("storyChatNarratorPerson")) $("storyChatNarratorPerson").value = sn.person || "third_person_limited";
  if ($("storyChatAttachPrev")) $("storyChatAttachPrev").value = String(wd.attach_prev_chapters ?? 3);
  const cid = (sn.character_id || "").trim();
  if ($("storyChatNarratorCharacter")) $("storyChatNarratorCharacter").value = cid;
}

const STORY_CHAPTER_NAV_IDS = ["storyChapterNav", "storyChatChapterNav"];

function storyChatActiveChapterId() {
  return (
    state.storyActiveChapterId ||
    $("storyChatChapterSelect")?.value ||
    $("storyBeatChapterSelect")?.value ||
    $("storyMsChapterSelect")?.value ||
    $("storyWriteChapterSelect")?.value ||
    // Don't blindly fall back to chapter 1 — it causes confusion.
    // Return "" so callers can show a helpful error.
    ""
  );
}

function lastStoryUserMessage() {
  for (let i = state.storyMessages.length - 1; i >= 0; i--) {
    if (state.storyMessages[i]?.role === "user") return (state.storyMessages[i].content || "").trim();
  }
  return "";
}

function storyWritingParamsFromUI(useChatStrip) {
  const prefix = useChatStrip ? "storyChat" : "story";
  return {
    person: $(`${prefix}NarratorPerson`)?.value || $("storyNarratorPerson")?.value || null,
    character_id:
      $(`${prefix}NarratorCharacter`)?.value || $("storyNarratorCharacter")?.value || null,
    attach_prev_chapters: parseInt(
      $(`${prefix}AttachPrev`)?.value ?? $("storyAttachPrev")?.value ?? "3",
      10
    ),
    writing_prompt: (
      (useChatStrip ? $("storyChatWritingPrompt")?.value : $("storyWritePrompt")?.value) ?? ""
    ).trim(),
  };
}

function storyChapterOptionLabel(c, displayRow) {
  const title = (
    displayRow?.title ||
    (c.title || "").trim() ||
    displayRow?.beat_title ||
    c.id
  ).trim();
  const status = (c.status || "planned").trim();
  const beatMark = displayRow?.has_beat === false ? "" : " · 有细纲";
  return `${c.order}. ${title}（${status}${beatMark}）`;
}

// ── Agent Panel UI ──────────────────────────────────────────────

let _agentToggleSyncBound = false;

function _updateAgentPanelUI(active) {
  const panels = document.querySelectorAll('.agent-panel');
  panels.forEach(p => p.classList.toggle('active', active));
  const statusEls = [
    $("storyAgentStatus"), $("storyChatAgentStatus"),
  ];
  statusEls.forEach(el => {
    if (el) {
      el.textContent = active ? '已激活' : '未激活';
      el.className = active ? 'agent-status-active tiny' : 'agent-status-idle tiny';
    }
  });
}

function _bindAgentToggleSync() {
  if (_agentToggleSyncBound) return;
  _agentToggleSyncBound = true;
  const writeToggle = $("storyToggleAgents");
  const chatToggle = $("storyChatToggleAgents");
  const writeRounds = $("storyAgentMaxRounds");
  const chatRounds = $("storyChatAgentMaxRounds");

  const sync = (srcToggle, dstToggle, srcRounds, dstRounds) => {
    if (!srcToggle || !dstToggle) return;
    srcToggle.addEventListener('change', () => {
      dstToggle.checked = srcToggle.checked;
      _updateAgentPanelUI(srcToggle.checked);
      if (srcRounds && dstRounds) dstRounds.value = srcRounds.value;
    });
  };

  sync(writeToggle, chatToggle, writeRounds, chatRounds);
  sync(chatToggle, writeToggle, chatRounds, writeRounds);

  if (writeRounds && chatRounds) {
    writeRounds.addEventListener('change', () => { chatRounds.value = writeRounds.value; });
    chatRounds.addEventListener('change', () => { writeRounds.value = chatRounds.value; });
  }
}

function refreshStoryChapterSelects(chaptersDisplay) {
  const chapters = sortedStoryChapters();
  const displayMap = new Map();
  if (Array.isArray(chaptersDisplay)) {
    for (const row of chaptersDisplay) {
      if (row?.id) displayMap.set(String(row.id), row);
    }
  }
  const opts = chapters
    .map((c) => {
      const row = displayMap.get(c.id);
      return `<option value="${escapeAttr(c.id)}">${escapeHtml(storyChapterOptionLabel(c, row))}</option>`;
    })
    .join("");
  const empty = '<option value="">（请先新建章节）</option>';
  for (const id of [
    "storyBeatChapterSelect",
    "storyMsChapterSelect",
    "storyWriteChapterSelect",
    "storyChatChapterSelect",
    "storyAuditChapterSelect",
    "storyPolishChapterSelect",
  ]) {
    const el = $(id);
    if (!el) continue;
    el.innerHTML = chapters.length ? opts : empty;
  }
  const active =
    $("storyChatChapterSelect")?.value ||
    state.storyActiveChapterId ||
    chapters[0]?.id ||
    "";
  // Ensure active is a valid chapter in the current world (prevents stale IDs after world switch)
  const validActive = active && chapters.some(c => c.id === active) ? active : (chapters[0]?.id || "");
  if (validActive) {
    for (const id of [
      "storyBeatChapterSelect",
      "storyMsChapterSelect",
      "storyWriteChapterSelect",
      "storyChatChapterSelect",
      "storyAuditChapterSelect",
      "storyPolishChapterSelect",
    ]) {
      const el = $(id);
      if (el && [...el.options].some((o) => o.value === validActive)) el.value = validActive;
    }
    state.storyActiveChapterId = validActive;
  }
  syncStoryChatWritingControlsFromForm();
  refreshStoryChatContextLine();
  refreshStoryChatBeatTitleHint(validActive);
}

async function refreshStoryChaptersAligned() {
  if (!state.world?.meta?.id) return;
  const preserved = storyChatActiveChapterId();
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story`);
    if (res.story) state.world.story = res.story;
    if (res.unit_label) state.storyUnitLabel = res.unit_label;
    storyMetaToForm();
    if ($("storyChaptersJson"))
      $("storyChaptersJson").value = JSON.stringify(state.world.story?.chapters ?? [], null, 2);
    refreshStoryChapterSelects(res.chapters_display);
    renderStoryChapterNav(preserved || state.storyActiveChapterId);
    if (preserved) await selectStoryChapter(preserved);
    if (Array.isArray(res.chapter_sync_notes) && res.chapter_sync_notes.length) {
      toast("章节已与细纲对齐：" + res.chapter_sync_notes.join("；"));
    }
  } catch (e) {
    refreshStoryChapterSelects();
    refreshStoryChatContextLine();
    toast("加载章节列表失败：" + (e?.message || e));
  }
  // 若审校面板当前可见，自动加载数据
  if (state.storySubView === "audit" && state.storyActiveChapterId) {
    void refreshSentimentArc();
    void renderConsistencyReport(state.storyActiveChapterId);
    void loadPolishedManuscript(state.storyActiveChapterId);
  }
  // 若大纲面板当前可见，自动加载粗纲或细纲数据
  if (state.storySubView === "outline") {
    if (state.storyOutlineSub === "macro" || !state.storyOutlineSub) void loadStoryMacro();
    if (state.storyOutlineSub === "beats" && state.storyActiveChapterId) void loadStoryBeat();
  }
}

function refreshStoryChatBeatTitleHint(chapterId) {
  const hint = $("storyChatBeatTitleHint");
  if (!hint) return;
  const cid = (chapterId || storyChatActiveChapterId() || "").trim();
  if (!cid) {
    hint.textContent = "请先在左侧「情节」总览新建章节，或保存 world.json 中的 chapters。";
    return;
  }
  const ch = sortedStoryChapters().find((c) => c.id === cid);
  const title = (ch?.title || "").trim();
  hint.textContent = title
    ? `细纲/索引标题：${title}（id=${cid}）`
    : `章节 id=${cid}（细纲文件若有 # 标题将自动同步为章节名）`;
}

function updateStoryWbTitle() {
  const h = $("storyWbTitle");
  if (!h) return;
  const nav = state.activeStoryNav || STORY_SUB_TO_NAV[state.storySubView] || "storyOverview";
  const lab = STORY_NAV_LABELS[nav] || "情节";
  h.innerHTML = `<span class="ms h2-ic" aria-hidden="true">auto_stories</span>情节 · ${escapeHtml(lab)}`;
}

function updateStoryEditorWordCount(taId, wcId) {
  const ta = $(taId);
  const wc = $(wcId);
  if (!ta || !wc) return;
  const n = (ta.value || "").replace(/\s/g, "").length;
  wc.textContent = `${n.toLocaleString()} 字`;
}

function refreshStoryEditorWordCounts() {
  updateStoryEditorWordCount("storyMacroEdit", "storyMacroWc");
  updateStoryEditorWordCount("storyBeatEdit", "storyBeatWc");
  updateStoryEditorWordCount("storyManuscriptEdit", "storyManuscriptWc");
}

function setStoryOutlineSub(name) {
  state.storyOutlineSub = name;
  document.querySelectorAll("#storyOutlineSubtabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.outlineSub === name);
  });
  for (const [key, pid] of Object.entries({
    macro: "storyPaneMacro",
    beats: "storyPaneBeats",
    auxiliary: "storyPaneAuxiliary",
  })) {
    $(pid)?.classList.toggle("hidden", key !== name);
  }
  if (name === "macro") void loadStoryMacro();
  if (name === "beats") {
    // Sync beats chapter select to active chapter before loading
    const beatSel = $("storyBeatChapterSelect");
    if (beatSel && state.storyActiveChapterId) {
      if ([...beatSel.options].some(o => o.value === state.storyActiveChapterId)) {
        beatSel.value = state.storyActiveChapterId;
      }
    }
    void loadStoryBeat();
  }
  if (name === "auxiliary") refreshOutlineHeader();
}

function setStorySubView(name) {
  state.storySubView = name;
  state.activeStoryNav = STORY_SUB_TO_NAV[name] || state.activeStoryNav || "storyOverview";
  syncNavActiveButtons();
  updateStoryWbTitle();
  document.querySelectorAll("[data-story-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.storyTab === name);
  });
  refreshStoryEditorWordCounts();
  const panes = {
    overview: "storyPaneOverview",
    outline: "storyPaneOutline",
    chapter: "storyPaneChapter",
    foreshadow: "storyPaneForeshadow",
    write: "storyPaneWrite",
    audit: "storyPaneAudit",
    stats: "storyPaneStats",
    agent: "storyPaneAgent",
  };
  for (const [key, pid] of Object.entries(panes)) {
    $(pid)?.classList.toggle("hidden", key !== name);
  }
  if (name === "outline") setStoryOutlineSub(state.storyOutlineSub || "macro");
  if (name === "chapter") void loadStoryManuscript();
  if (name === "write") renderRuntimeStates();
  if (name === "stats") void renderStoryStats();
  if (name === "agent") void refreshAgentPanel();
  if (name === "audit") {
    // Sync audit chapter select to active chapter
    const auditSel = $("storyAuditChapterSelect");
    if (auditSel && state.storyActiveChapterId) auditSel.value = state.storyActiveChapterId;
    const polishSel = $("storyPolishChapterSelect");
    if (polishSel && state.storyActiveChapterId) polishSel.value = state.storyActiveChapterId;
    void refreshSentimentArc();
    const activeCh = sortedStoryChapters().find(c => c.id === state.storyActiveChapterId);
    if (activeCh) {
      renderConsistencyReport(activeCh.id);
      void loadPolishedManuscript(activeCh.id);
    }
  }
  if (name === "foreshadow") {
    const items = parseStoryForeshadowingFromForm();
    if (items) renderStoryForeshadowTimeline(items);
  }
  refreshStoryChatContextLine();
  refreshStoryContextPanel();
}

async function refreshStoryPanel() {
  if (!state.world?.meta?.id) return;
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story`);
    if (res.story) state.world.story = res.story;
    state.storyUnitLabel = res.unit_label || storyUnitLabelForMode(state.world.meta.creative_mode);
    if (res.legacy_imported) toast("已从 outlines/plot_outline.md 导入粗纲");
    storyMetaToForm();
    refreshStoryChapterSelects(res.chapters_display);
    if (Array.isArray(res.chapter_sync_notes) && res.chapter_sync_notes.length) {
      toast("章节已与细纲对齐：" + res.chapter_sync_notes.join("；"));
    }
  } catch (e) {
    toast("加载情节失败：" + (e?.message || e));
  }
}

async function loadStoryMacro() {
  if (!state.world?.meta?.id) return;
  const res = await api(`/api/worlds/${state.world.meta.id}/story/macro-outline`);
  if ($("storyMacroEdit")) $("storyMacroEdit").value = res.content || "";
  updateStoryMarkdownPreview("storyMacroPreview", res.content || "", true);
  refreshStoryEditorWordCounts();
}

async function loadStoryBeat() {
  const sel = $("storyBeatChapterSelect");
  let cid = sel?.value;
  // Fall back to active chapter id when select has no value
  if (!cid && state.storyActiveChapterId) {
    cid = state.storyActiveChapterId;
    // If the select exists and has the active chapter as an option, sync it
    if (sel && [...sel.options].some(o => o.value === cid)) {
      sel.value = cid;
    }
  }
  if (!cid || !state.world?.meta?.id) return;
  const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/beat`);
  if ($("storyBeatEdit")) $("storyBeatEdit").value = res.content || "";
  updateStoryMarkdownPreview("storyBeatPreview", res.content || "", true);
  refreshStoryEditorWordCounts();
}

async function loadStoryManuscript() {
  const cid = $("storyMsChapterSelect")?.value;
  if (!cid || !state.world?.meta?.id) return;
  const res = await api(
    `/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/manuscript`
  );
  if ($("storyManuscriptEdit")) $("storyManuscriptEdit").value = res.content || "";
  const author = $("storyAuthorView")?.checked ?? true;
  updateStoryMarkdownPreview("storyManuscriptPreview", res.content || "", author);
  renderChapterSummaryCard(cid);
  refreshStoryEditorWordCounts();
}


// ── 章节摘要卡片渲染 ──────────────────────────────────────

function renderChapterSummaryCard(chapterId) {
  const card = $("storyChapterSummaryCard");
  if (!card) return;
  const ch = (state.world?.story?.chapters || []).find(c => c.id === chapterId);
  if (!ch || !ch.summary_card) {
    card.classList.add("hidden");
    return;
  }
  const sc = ch.summary_card;
  card.classList.remove("hidden");
  if ($("storySummaryCardEvents")) $("storySummaryCardEvents").textContent = sc.main_events || "";
  if ($("storySummaryCardHook")) {
    const hook = sc.ending_hook || "";
    $("storySummaryCardHook").innerHTML = hook ? `<span class="ms" aria-hidden="true">push_pin</span> 结尾钩子：${escapeHtml(hook)}` : "";
  }
  const statesEl = $("storySummaryCardStates");
  if (statesEl) {
    if (sc.character_state_changes && sc.character_state_changes.length) {
      statesEl.innerHTML = sc.character_state_changes.map(s =>
        `<div class="story-summary-state-item">
          <span class="ms" aria-hidden="true">person</span>
          <span><strong>${escapeHtml(s.name || s.char_id || '?')}</strong>
          ${s.location_before && s.location_after ? `：${escapeHtml(s.location_before)} → ${escapeHtml(s.location_after)}` : ''}
          ${s.emotion_before && s.emotion_after ? ` · 情绪 ${escapeHtml(s.emotion_before)} → ${escapeHtml(s.emotion_after)}` : ''}
          ${s.goal_change && s.goal_change !== '无变化' ? ` · 目标：${escapeHtml(s.goal_change)}` : ''}
          </span>
        </div>`
      ).join("");
    } else {
      statesEl.innerHTML = '<p class="muted tiny">无角色状态变化</p>';
    }
  }
  // 伏笔标签
  const footer = card.querySelector(".story-summary-card-footer");
  if (footer) {
    let tagsHtml = "";
    if (sc.foreshadowing_planted && sc.foreshadowing_planted.length) {
      tagsHtml += sc.foreshadowing_planted.map(id =>
        `<span class="story-summary-fs-tag story-summary-fs-tag--planted">埋设:${escapeHtml(id)}</span>`
      ).join("");
    }
    if (sc.foreshadowing_resolved && sc.foreshadowing_resolved.length) {
      tagsHtml += sc.foreshadowing_resolved.map(id =>
        `<span class="story-summary-fs-tag story-summary-fs-tag--resolved">回收:${escapeHtml(id)}</span>`
      ).join("");
    }
    let tagsEl = footer.querySelector(".story-summary-fs-tags");
    if (!tagsEl) {
      tagsEl = document.createElement("span");
      tagsEl.className = "story-summary-fs-tags";
      footer.appendChild(tagsEl);
    }
    tagsEl.innerHTML = tagsHtml;
  }
}


// ── Layer 3: 一致性审校报告渲染 ──────────────────────────────

async function renderConsistencyReport(chapterId) {
  const container = $("storyAuditConsistency");
  if (!container) return;
  if (!chapterId) {
    container.innerHTML = '<p class="muted tiny">请选择一个章节查看审校报告</p>';
    return;
  }
  const ch = (state.world?.story?.chapters || []).find(c => c.id === chapterId);
  let cr = ch?.consistency_report;
  // Fallback: 从磁盘加载（世界重载后内存中可能为 null）
  if (!cr && state.world?.meta?.id) {
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/consistency-report/${chapterId}`);
      if (res.consistency_report) {
        cr = res.consistency_report;
        // 回填到内存模型
        if (ch) ch.consistency_report = cr;
      }
    } catch (_) { /* silent */ }
  }
  if (!cr) {
    container.innerHTML = '<p class="muted tiny">该章节尚无审校报告。请先生成文稿。</p>';
    return;
  }
  const verdictLabels = { clean: "通过", minor_issues: "有小问题", needs_review: "需人工复核" };
  const verdictColors = { clean: "#16a34a", minor_issues: "#eab308", needs_review: "#dc2626" };
  const sevIcons = { critical: "🔴", warning: "🟡", info: "🔵" };
  const catLabels = {
    position: "位置", personality: "性格", item_state: "物品",
    pov: "视角", foreshadowing: "伏笔", emotional_continuity: "情感连续", timeline: "时间线"
  };
  let html = `<div class="story-audit-header">
    <span class="story-audit-verdict" style="color:${verdictColors[cr.verdict] || '#666'}">
      审校结果：${verdictLabels[cr.verdict] || cr.verdict}（${cr.total_issues || 0} 个问题）
    </span>
    <span class="muted tiny">检查时间：${cr.checked_at || '?'}</span>
  </div>`;
  if (cr.issues && cr.issues.length) {
    html += '<ul class="story-audit-issues">';
    for (const iss of cr.issues) {
      html += `<li class="story-audit-issue">
        <span class="story-audit-issue-head">
          ${sevIcons[iss.severity] || '⚪'} [${catLabels[iss.category] || iss.category}] ${escapeHtml(iss.description)}
        </span>`;
      if (iss.excerpt) html += `<div class="story-audit-excerpt muted tiny">原文：${escapeHtml(iss.excerpt)}</div>`;
      if (iss.suggestion) html += `<div class="story-audit-suggestion">建议：${escapeHtml(iss.suggestion)}</div>`;
      html += '</li>';
    }
    html += '</ul>';
  } else {
    html += '<p class="muted tiny">✓ 未发现一致性问题。</p>';
  }
  container.innerHTML = html;
}


// ── Layer 3: 情感弧线 ────────────────────────────────────────

async function refreshSentimentArc() {
  if (!state.world?.meta?.id) return;
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story/sentiment-arc`);
    const chartContainer = $("storySentimentChart");
    if (chartContainer && res.chart_data && res.chart_data.length) {
      chartContainer.innerHTML = buildSentimentChartHtml(res.chart_data);
    } else if (chartContainer) {
      chartContainer.innerHTML = '<p class="muted tiny">暂无情感数据。请先生成至少一章文稿。</p>';
    }
    // Update logs list
    const logsEl = $("storySentimentLogs");
    if (logsEl && res.sentiment_logs && res.sentiment_logs.length) {
      const toneLabels = { positive: "正面", negative: "负面", tense: "紧张", calm: "平静", mixed: "混合" };
      const toneColors = { positive: "#16a34a", negative: "#dc2626", tense: "#f59e0b", calm: "#6366f1", mixed: "#a855f7" };
      const transitionLabels = {
        smooth: "平滑过渡", abrupt: "突兀转折", intentional_contrast: "刻意对比", first_chapter: "首章"
      };
      logsEl.innerHTML = res.sentiment_logs.map(log => {
        const segs = (log.segments || []).map(s =>
          `<span class="sentiment-seg" style="background:${toneColors[s.tone] || '#e2e8f0'}18;color:${toneColors[s.tone] || '#64748b'};border-color:${toneColors[s.tone] || '#e2e8f0'}40" title="${s.label || '?'}: ${toneLabels[s.tone] || s.tone} · 强度 ${s.intensity}/10">${s.label || '?'} ${toneLabels[s.tone] || s.tone} ${'★'.repeat(Math.min(s.intensity || 5, 5))}</span>`
        ).join(" ");
        const overallTone = toneLabels[log.overall_tone] || log.overall_tone || '?';
        const overallColor = toneColors[log.overall_tone] || '#64748b';
        const endTone = toneLabels[log.ending_tone] || log.ending_tone || '?';
        const endColor = toneColors[log.ending_tone] || '#64748b';
        const trans = transitionLabels[log.transition_from_prev] || log.transition_from_prev || '?';
        return `<div class="sentiment-log-item">
          <strong>${escapeHtml(log.title || log.chapter_id)}</strong>
          <div class="sentiment-log-meta">
            <span class="sentiment-tag" style="background:${overallColor}18;color:${overallColor};border:1px solid ${overallColor}40">整体 ${overallTone}</span>
            <span class="sentiment-tag" style="background:${endColor}18;color:${endColor};border:1px solid ${endColor}40">结尾 ${endTone}</span>
            <span class="sentiment-tag muted">过渡 ${trans}</span>
          </div>
          <div class="sentiment-segs">${segs}</div>
        </div>`;
      }).join("");
    } else if (logsEl) {
      logsEl.innerHTML = '<p class="muted tiny" style="padding:8px 14px">暂无情感数据</p>';
    }
  } catch (e) {
    console.error("refreshSentimentArc failed:", e);
  }
}

function buildSentimentChartHtml(chartData) {
  const toneLabels = { positive: "正面", negative: "负面", tense: "紧张", calm: "平静", mixed: "混合" };
  const maxVal = 5;
  const bars = chartData.map((pt, i) => {
    const hPct = (pt.tone_value / maxVal) * 100;
    const shortTitle = pt.title.length > 6 ? pt.title.slice(0, 6) + '..' : pt.title;
    return `<div class="sc-bar-col" title="${escapeHtml(pt.title)} · ${toneLabels[pt.overall_tone] || pt.overall_tone} · 强度 ${pt.avg_intensity}">
      <div class="sc-bar-val">${pt.tone_value}</div>
      <div class="sc-bar-fill" style="height:${hPct}%;background:${pt.tone_color};box-shadow:0 2px 6px ${pt.tone_color}40"></div>
      <div class="sc-bar-intensity" title="平均强度 ${pt.avg_intensity}">${'★'.repeat(Math.round(pt.avg_intensity / 2))}</div>
      <div class="sc-bar-label">${escapeHtml(shortTitle)}</div>
      <div class="sc-bar-tone">${toneLabels[pt.overall_tone] || pt.overall_tone}</div>
    </div>`;
  }).join("");

  return `<div class="sentiment-chart-wrap">
    <div class="sc-legend">
      <span class="sc-legend-item"><i style="background:#16a34a"></i>正面</span>
      <span class="sc-legend-item"><i style="background:#6366f1"></i>平静</span>
      <span class="sc-legend-item"><i style="background:#a855f7"></i>混合</span>
      <span class="sc-legend-item"><i style="background:#f59e0b"></i>紧张</span>
      <span class="sc-legend-item"><i style="background:#dc2626"></i>负面</span>
    </div>
    <div class="sc-bars">${bars}</div>
  </div>`;
}


// ── Agent 决策分析面板 ──────────────────────────────────────

async function refreshAgentPanel() {
  if (!state.world?.meta?.id) return;
  const wid = state.world.meta.id;

  // Populate chapter select
  const sel = $("storyAgentChapterSelect");
  if (sel) {
    const chapters = sortedStoryChapters();
    sel.innerHTML = chapters.map(c =>
      `<option value="${c.id}" ${c.id === state.storyActiveChapterId ? 'selected' : ''}>第${c.order}章 ${escapeHtml(c.title || c.id)}</option>`
    ).join("");
  }
  const chId = sel?.value || state.storyActiveChapterId;
  if (!chId) return;

  try {
    // Fetch agent decisions
    const decRes = await api(`/api/worlds/${wid}/story/agent-decisions/${chId}`);
    // Fetch agent states
    const statesRes = await api(`/api/worlds/${wid}/agents`);

    // Render quality chart (multi-chapter trend)
    _renderAgentQualityChart(wid);

    // Render decision sequence
    _renderAgentDecisionList(decRes);

    // Render deviation tracking
    _renderAgentDeviationList(decRes);

    // Render agent states overview
    _renderAgentStatesList(statesRes);
  } catch (e) {
    console.error("refreshAgentPanel failed:", e);
    const grid = $("storyAgentGrid");
    if (grid) grid.innerHTML = '<p class="muted tiny" style="padding:16px">Agent 数据暂不可用。请先生成至少一章，或检查 Agent 系统是否启用。</p>';
  }
}

async function _renderAgentQualityChart(wid) {
  const container = $("agentQualityChart");
  if (!container) return;
  try {
    // Try to get quality history for POV character
    const povId = state.world?.story?.narrator?.character_id || "ch_yunhe";
    const res = await api(`/api/worlds/${wid}/agents/${povId}/quality-history`);
    const chapters = res.chapters || [];
    if (!chapters.length) {
      container.innerHTML = '<p class="muted tiny">暂无质量数据。请生成章节以积累评分。</p>';
      return;
    }
    const grades = {A:5, B:4, C:3, D:2, F:1};
    const gradeColors = {A:"#16a34a", B:"#6366f1", C:"#f59e0b", D:"#f97316", F:"#dc2626"};
    container.innerHTML = '<div class="agent-quality-bars">' +
      chapters.slice(-12).map(ch => {
        const g = ch.grade || '?';
        const color = gradeColors[g] || '#94a3b8';
        const h = Math.max(8, (ch.overall || 0) * 0.8);
        return `<div class="aq-bar-col" title="${ch.chapter_id}: ${ch.overall}分 ${g}级\n节奏:${ch.scores?.pacing||0} 弧光:${ch.scores?.character_arc||0} 对话:${ch.scores?.dialog||0}">
          <div class="aq-bar-grade" style="color:${color}">${g}</div>
          <div class="aq-bar-fill" style="height:${h}%;background:${color}20;border-top:3px solid ${color}"></div>
          <div class="aq-bar-label">${(ch.chapter_id||'').replace('ch','')||'?'}</div>
        </div>`;
      }).join("") +
      '<div class="aq-legend">' +
      Object.entries(gradeColors).map(([g,c]) => `<span style="color:${c};margin:0 4px">${g}级</span>`).join("") +
      '</div></div>';
  } catch (e) {
    container.innerHTML = '<p class="muted tiny">质量数据加载失败</p>';
  }
}

function _renderAgentDecisionList(decRes) {
  const container = $("agentDecisionList");
  if (!container) return;
  const chars = decRes?.characters || {};
  const charIds = Object.keys(chars);
  if (!charIds.length) {
    container.innerHTML = '<p class="muted tiny">该章节暂无 Agent 决策数据。</p>';
    return;
  }
  const toneLabels = {"positive":"正面","negative":"负面","tense":"紧张","calm":"平静","mixed":"混合"};
  container.innerHTML = charIds.map(cid => {
    const cd = chars[cid];
    const decs = cd.decisions || [];
    const name = decs[0]?.character_id || cid;
    return `<div class="ad-char-block">
      <div class="ad-char-name">&#x1F9E0; ${escapeHtml(name)} <span class="muted tiny">(${cd.count} 个决策)</span></div>
      ${decs.slice(0, 4).map((d,i) => `
        <div class="ad-decision">
          <span class="ad-round">R${(d.decision_round||0)+1}</span>
          ${d.intended_speech ? `<span class="ad-speech">"${escapeHtml(d.intended_speech)}"</span>` : ''}
          ${d.intended_action ? `<span class="ad-action">${escapeHtml(d.intended_action)}</span>` : ''}
          ${d.emotional_shift ? `<span class="ad-emotion">${escapeHtml(d.emotional_shift)}</span>` : ''}
          ${d.hidden_intent ? `<span class="ad-intent" title="隐藏意图">${escapeHtml(d.hidden_intent)}</span>` : ''}
        </div>
      `).join("")}
    </div>`;
  }).join("");
}

function _renderAgentDeviationList(decRes) {
  const container = $("agentDeviationList");
  if (!container) return;
  // Deviation data comes from the quality history
  container.innerHTML = '<p class="muted tiny">节拍偏离数据在每次生成时记录到终端日志。查看终端 <code>[MCW-AGENT]</code> 输出获取详细信息。</p>';
}

function _renderAgentStatesList(statesRes) {
  const container = $("agentStatesList");
  if (!container) return;
  const agents = statesRes?.agents || {};
  const ids = Object.keys(agents);
  if (!ids.length) {
    container.innerHTML = '<p class="muted tiny">暂无 Agent 状态。请先启用角色 Agent 并生成至少一章。</p>';
    return;
  }
  container.innerHTML = ids.map(cid => {
    const a = agents[cid];
    const pressureColor = a.pressure_level > 60 ? '#dc2626' : a.pressure_level > 30 ? '#f59e0b' : '#16a34a';
    return `<div class="as-card">
      <div class="as-card-head">
        <strong>${escapeHtml(a.name || cid)}</strong>
        <span class="as-pressure" style="color:${pressureColor}">压力 ${a.pressure_level}</span>
      </div>
      <div class="as-card-body">
        <div class="as-row"><span>情绪</span><span>${escapeHtml(a.emotional_state || '—')}</span></div>
        <div class="as-row"><span>目标</span><span>${escapeHtml(a.current_goal || '—')}</span></div>
        <div class="as-row"><span>位置</span><span>${escapeHtml(a.current_location || '—')}</span></div>
        <div class="as-row"><span>决策总数</span><span>${a.total_decisions_made || 0}</span></div>
        <div class="as-row"><span>后遗症</span><span>${a.active_aftermaths_count || 0} 项活跃</span></div>
        <div class="as-row"><span>最后章节</span><span>${a.last_chapter || '—'}</span></div>
      </div>
    </div>`;
  }).join("");
}

// ── 角色运行时状态渲染 ──────────────────────────────────────

function renderRuntimeStates() {
  const container = $("storyRuntimeStates");
  const list = $("storyRuntimeList");
  if (!container || !list) return;
  const entities = state.world?.characters?.entities || [];
  const states = entities.filter(e => e && e.runtime_state && Object.keys(e.runtime_state).length > 1);
  if (!states.length) {
    container.classList.add("hidden");
    return;
  }
  container.classList.remove("hidden");
  list.innerHTML = states.map(e => {
    const rs = e.runtime_state || {};
    return `<div class="story-runtime-item">
      <span class="story-runtime-item-name">${escapeHtml(e.name || e.id || '?')}</span>
      <span class="story-runtime-item-loc"><span class="ms" aria-hidden="true">location_on</span> ${escapeHtml(rs.current_location || '—')}</span>
      <span class="story-runtime-item-emotion"><span class="ms" aria-hidden="true">mood</span> ${escapeHtml(rs.emotional_state || '—')}</span>
      <span class="story-runtime-item-goal"><span class="ms" aria-hidden="true">flag</span> ${escapeHtml(rs.current_goal || '—')}</span>
      ${rs.last_updated_chapter ? `<span class="muted tiny" style="grid-column:2">更新于 ${escapeHtml(rs.last_updated_chapter)}</span>` : ""}
    </div>`;
  }).join("");
}


// ── RAG 状态与故事上下文面板 ──────────────────────────────────────

	async function updateRagStatusDot() {
	  const dot = $("storyRagStatus");
	  const ctxDot = $("ctxRagDot");
	  const ctxBody = $("ctxRagStatusBody");
	  if (!dot && !ctxDot) return;

	  if (!state.world?.meta?.id) {
	    if (dot) { dot.className = "rag-status-dot rag-status-dot--empty"; dot.textContent = "○ 无索引"; dot.title = "RAG 索引状态"; }
	    if (ctxDot) { ctxDot.className = "rag-dot rag-dot--empty"; }
	    if (ctxBody) ctxBody.textContent = "请先选择世界";
	    return;
	  }

	  if (dot) { dot.className = "rag-status-dot rag-status-dot--indexing"; dot.textContent = "◌ 检查中…"; }
	  if (ctxDot) { ctxDot.className = "rag-dot rag-dot--indexing"; }

	  try {
	    const stats = await api(`/api/worlds/${state.world.meta.id}/story/rag/stats`);
	    const ready = stats.ready;
	    const total = stats.total_chunks || 0;
	    const chapters = stats.indexed_chapters || 0;

	    if (dot) {
	      dot.className = ready ? "rag-status-dot rag-status-dot--ready" : "rag-status-dot rag-status-dot--empty";
	      dot.textContent = ready ? `● ${total} 块 · ${chapters} 章` : "○ 无索引";
	      dot.title = ready ? `RAG 就绪：${total} 个向量块，${chapters} 个章节已索引` : "RAG 索引为空，请先生成章节文稿以构建索引";
	    }
	    if (ctxDot) {
	      ctxDot.className = ready ? "rag-dot rag-dot--ready" : "rag-dot rag-dot--empty";
	    }
	    if (ctxBody) {
	      if (ready) {
	        const sourceCounts = stats.source_counts || {};
	        const lines = [];
	        if (sourceCounts.manuscript) lines.push(`手稿：${sourceCounts.manuscript} 块`);
	        if (sourceCounts.character) lines.push(`人物：${sourceCounts.character} 块`);
	        if (sourceCounts.world_md) lines.push(`世界观：${sourceCounts.world_md} 块`);
	        lines.push(`共 ${total} 块 · ${chapters} 章`);
	        if (stats.chapter_ids && stats.chapter_ids.length) {
	          lines.push("已索引：" + stats.chapter_ids.join("、"));
	        }
	        ctxBody.innerHTML = lines.map(l => `<div class="ctx-rag-stat-line">${escapeHtml(l)}</div>`).join("");
	      } else {
	        ctxBody.innerHTML = '<div class="ctx-rag-stat-line muted">暂无索引。生成章节文稿后自动构建语义检索。</div>';
	      }
	    }
	  } catch (e) {
	    if (dot) { dot.className = "rag-status-dot rag-status-dot--error"; dot.textContent = "⚠ 错误"; dot.title = "RAG 状态获取失败：" + (e?.message || e); }
	    if (ctxDot) { ctxDot.className = "rag-dot rag-dot--error"; }
	    if (ctxBody) ctxBody.textContent = "状态获取失败";
	  }
	}


// ═══════════════════════════════════════════════════════════════
// Layer 4: 润色者 — GUI
// ═══════════════════════════════════════════════════════════════

async function loadPolishedManuscript(chapterId) {
	const view = $("storyPolishView");
	if (!view) return;
	if (!chapterId || !state.world?.meta?.id) {
		view.innerHTML = '<div class="story-polish-empty"><span class="ms" aria-hidden="true">auto_awesome</span><p class="muted tiny">请选择一个章节查看润色稿</p></div>';
		return;
	}
	view.innerHTML = '<p class="muted tiny" style="padding:16px;text-align:center"><span class="ms spinning">progress_activity</span> 加载润色稿…</p>';

	try {
		const res = await api(`/api/worlds/${state.world.meta.id}/story/manuscript/${encodeURIComponent(chapterId)}/polished`);

		if (!res.polished_text) {
			view.innerHTML = '<div class="story-polish-empty"><span class="ms" aria-hidden="true">auto_awesome</span><p class="muted tiny">该章节暂无润色稿。<br>请先在写作设置中开启润色者，然后生成文稿。</p></div>';
			return;
		}

		// Fetch original manuscript for diff
		let originalText = "";
		try {
			const origRes = await api(`/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(chapterId)}/manuscript`);
			originalText = origRes.content || "";
		} catch (_) { /* original not available */ }

		const polishedText = res.polished_text;
		const trace = res.polish_issue_tracking;
		const rounds = res.polish_rounds || 0;

		let html = "";

		// ── Card 1: Loop indicator + issue badges ──
		if ((trace && trace.max_rounds) || (trace && trace.rounds && trace.rounds.length)) {
			html += '<div class="story-audit-card">';
			if (trace && trace.max_rounds) {
				html += buildPolishLoopIndicator(trace);
			}
			if (trace && trace.rounds && trace.rounds.length) {
				html += buildPolishIssueTracking(trace);
			}
			html += '</div>';
		}

		// ── Card 2: Diff view (original | polished) ──
		html += '<div class="story-audit-card story-polish-diff-card">';
		html += '<div class="story-audit-card-head"><span class="story-audit-card-icon ms" aria-hidden="true">difference</span><span>原稿 vs 润色稿</span><span class="muted tiny" style="margin-left:12px">共 ' + rounds + ' 轮润色</span></div>';
		if (originalText) {
			html += buildPolishDiffView(originalText, polishedText);
		} else {
			html += '<div class="story-polish-single-col"><div class="story-polish-col-body">' + escapeHtml(polishedText) + '</div></div>';
		}
		html += '</div>';

		// ── Card 3: Polish notes (separate card below diff) ──
		const notesHtml = extractPolishNotes(polishedText);
		if (notesHtml) {
			html += '<div class="story-audit-card story-polish-notes-card">';
			html += '<div class="story-audit-card-head"><span class="story-audit-card-icon ms" aria-hidden="true">lightbulb</span><span>润色说明</span></div>';
			html += notesHtml;
			html += '</div>';
		}

		view.innerHTML = html;
	} catch (e) {
		view.innerHTML = '<p class="muted tiny" style="padding:16px;color:#dc2626">加载润色稿失败：' + escapeHtml(e.message || String(e)) + '</p>';
	}
}

function buildPolishLoopIndicator(trace) {
	const maxRounds = trace.max_rounds || 2;
	const actualRounds = trace.actual_rounds || 0;
	const reason = trace.termination_reason || "";
	const reasonLabels = {
		clean: "审校无问题",
		info_only: "仅剩轻微建议",
		critical_only_new: "严重问题需手动处理",
		max_rounds: "已达最大轮数",
		no_fixable_issues: "无可修复问题",
	};
	const reasonLabel = reasonLabels[reason] || reason;
	const reasonClass = reason === "clean" ? "clean" : reason === "info_only" ? "info" : "warn";

	let dots = "";
	for (let i = 1; i <= maxRounds; i++) {
		let cls = "";
		if (i <= actualRounds && reason === "clean" && i === actualRounds) cls = "done";
		else if (i <= actualRounds) cls = "active";
		dots += '<span class="story-polish-loop-dot ' + cls + '"></span>';
	}

	return (
		'<div class="story-polish-loop-indicator">' +
		'<span class="ms" aria-hidden="true">cycle</span>' +
		'<span>' + actualRounds + ' / ' + maxRounds + ' 轮</span>' +
		'<span class="story-polish-loop-dots">' + dots + '</span>' +
		'<span class="story-polish-loop-reason ' + reasonClass + '">' + escapeHtml(reasonLabel) + '</span>' +
		'</div>'
	);
}

function buildPolishIssueTracking(trace) {
	const lastRound = trace.rounds[trace.rounds.length - 1];
	if (!lastRound || !lastRound.classification) return "";

	const cls = lastRound.classification;
	let badges = "";

	if (cls.fixed && cls.fixed.length) {
		badges += '<span class="story-polish-issue-badge fixed"><span class="ms">check_circle</span>已修复 ' + cls.fixed.length + '</span>';
	}
	if (cls.persistent && cls.persistent.length) {
		badges += '<span class="story-polish-issue-badge persistent"><span class="ms">sync</span>持续中 ' + cls.persistent.length + '</span>';
	}
	if (cls.regression && cls.regression.length) {
		badges += '<span class="story-polish-issue-badge regression"><span class="ms">warning</span>新引入 ' + cls.regression.length + '</span>';
	}

	return badges ? '<div class="story-polish-issue-track">' + badges + '</div>' : "";
}

function buildPolishDiffView(originalText, polishedText) {
	const origParas = originalText.split(/\n+/).filter(p => p.trim());
	const polParas = polishedText.split(/\n+/).filter(p => p.trim());
	const notesIdx = polParas.findIndex(p => p.trim() === "## 润色说明");
	const polBody = notesIdx >= 0 ? polParas.slice(0, notesIdx) : polParas;

	const maxLen = Math.max(origParas.length, polBody.length);
	let origHtml = "";
	let polHtml = "";

	for (let i = 0; i < maxLen; i++) {
		const o = i < origParas.length ? origParas[i].trim() : "";
		const p = i < polBody.length ? polBody[i].trim() : "";

		if (o === p) {
			origHtml += '<p style="margin:4px 0">' + escapeHtml(o) + '</p>';
			polHtml += '<p style="margin:4px 0">' + escapeHtml(p) + '</p>';
		} else {
			if (o) origHtml += '<p style="margin:4px 0"><del>' + escapeHtml(o) + '</del></p>';
			if (p) polHtml += '<p style="margin:4px 0"><ins>' + escapeHtml(p) + '</ins></p>';
			if (!o && p) origHtml += '<p style="margin:4px 0;color:#94a3b8;font-style:italic">（无对应段落）</p>';
			if (!p && o) polHtml += '<p style="margin:4px 0;color:#94a3b8;font-style:italic">（已删除）</p>';
		}
	}

	return (
		'<div class="story-polish-diff">' +
		'<div class="story-polish-col">' +
		'<div class="story-polish-col-head"><span class="ms" aria-hidden="true">description</span>原稿</div>' +
		'<div class="story-polish-col-body">' + (origHtml || '<p class="muted tiny">（空）</p>') + '</div>' +
		'</div>' +
		'<div class="story-polish-col">' +
		'<div class="story-polish-col-head"><span class="ms" aria-hidden="true">auto_awesome</span>润色稿</div>' +
		'<div class="story-polish-col-body">' + (polHtml || '<p class="muted tiny">（空）</p>') + '</div>' +
		'</div>' +
		'</div>'
	);
}

function extractPolishNotes(polishedText) {
	const marker = "## 润色说明";
	const idx = polishedText.indexOf(marker);
	if (idx < 0) return "";

	const notesSection = polishedText.slice(idx);
	const lines = notesSection.split("\n").filter(l => l.trim() && l.trim() !== marker);
	if (!lines.length) return "";

	let notesHtml = '<div class="story-polish-notes-body">';
	for (const line of lines) {
		const trimmed = line.trim();
		if (!trimmed) continue;
		notesHtml += '<div class="story-polish-note-item">' + escapeHtml(trimmed) + '</div>';
	}
	notesHtml += '</div>';
	return notesHtml;
}

async function _saveWritingDefaultsFromForm() {
  if (!state.world?.meta?.id) return;
  const body = {
    enable_narrative_kg: $("storyToggleKG")?.checked,
    enable_consistency_check: $("storyToggleConsistency")?.checked,
    enable_sentiment_track: $("storyToggleSentiment")?.checked,
    enable_polisher: $("storyTogglePolisher")?.checked ?? $("storyChatTogglePolisher")?.checked,
    polish_max_rounds: parseInt(
      $("storyPolishMaxRounds")?.value || $("storyChatPolishMaxRounds")?.value || "2", 10
    ),
    enable_scene_chunking: $("storyToggleChunking")?.checked ?? $("storyChatToggleChunking")?.checked,
    enable_unified_extractors: $("storyToggleUnified")?.checked ?? $("storyChatToggleUnified")?.checked,
    enable_character_agents: $("storyToggleAgents")?.checked ?? $("storyChatToggleAgents")?.checked ?? false,
    agent_max_rounds: parseInt(
      $("storyAgentMaxRounds")?.value || $("storyChatAgentMaxRounds")?.value || "4", 10
    ),
  };
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story/writing-defaults`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    if (res.changed && state.world?.story?.writing_defaults) {
      Object.assign(state.world.story.writing_defaults, body);
    }
  } catch (e) {
    console.warn("保存写作设置失败", e);
  }
}

async function refreshUsageStats() {
  if (!state.world?.meta?.id) return;
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story/usage-stats`);
    const hooks = res.hooks || [];
    const total = res.estimated_total_per_chapter || 0;
    const chCount = res.chapter_count || 0;
    const projTotal = res.estimated_project_total || 0;

    const formatTokens = (n) => {
      if (n >= 10000) return `${(n / 1000).toFixed(0)}k`;
      if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
      return String(n);
    };

    const totalText = `预估本章 ~${formatTokens(total)} tokens`;
    const enabledHooks = hooks.filter(h => h.enabled);
    const detailParts = enabledHooks.map(h => `${h.label} ${formatTokens(h.estimated_tokens)}`);
    const detailText = detailParts.join(' · ');
    const projText = chCount > 0 ? `（${chCount} 章合计 ~${formatTokens(projTotal)} tokens）` : '';

    for (const [barId, totalId, detailId] of [
      ['storyBudgetBar', 'storyBudgetTotal', 'storyBudgetDetail'],
      ['storyChatBudgetBar', 'storyChatBudgetTotal', 'storyChatBudgetDetail'],
    ]) {
      const bar = $(barId);
      const totalEl = $(totalId);
      const detailEl = $(detailId);
      if (bar) bar.style.display = 'flex';
      if (totalEl) totalEl.textContent = `${totalText} ${projText}`;
      if (detailEl) detailEl.textContent = detailText;
    }
  } catch (_) {
    // Budget fetch is non-critical
  }
}

async function savePolishToggle(sourceId) {
	if (!state.world?.meta?.id) return;
	// Read from the control that triggered the change; fall back to either set
	const fromChat = sourceId && sourceId.startsWith("storyChat");
	const enabled = fromChat
		? ($("storyChatTogglePolisher")?.checked ?? true)
		: ($("storyTogglePolisher")?.checked ?? true);
	const maxRounds = parseInt(
		(fromChat ? $("storyChatPolishMaxRounds")?.value : $("storyPolishMaxRounds")?.value) || "2",
		10
	);
	try {
		const res = await api(`/api/worlds/${state.world.meta.id}/story/writing-defaults`, {
			method: "PATCH",
			body: JSON.stringify({ enable_polisher: enabled, polish_max_rounds: maxRounds }),
		});
		if (res.changed && state.world?.story?.writing_defaults) {
			state.world.story.writing_defaults.enable_polisher = enabled;
			state.world.story.writing_defaults.polish_max_rounds = maxRounds;
		}
		// Keep both UI locations in sync
		if (fromChat) {
			if ($("storyTogglePolisher")) $("storyTogglePolisher").checked = enabled;
			if ($("storyPolishMaxRounds")) $("storyPolishMaxRounds").value = String(maxRounds);
		} else {
			if ($("storyChatTogglePolisher")) $("storyChatTogglePolisher").checked = enabled;
			if ($("storyChatPolishMaxRounds")) $("storyChatPolishMaxRounds").value = String(maxRounds);
		}
	} catch (e) {
		console.warn("保存润色设置失败", e);
	}
	void refreshUsageStats();
}
	function refreshStoryContextPanel() {
	  const prevBody = $("ctxPrevSummaryBody");
	  if (prevBody) {
	    const chapters = sortedStoryChapters();
	    const activeId = state.storyActiveChapterId;
	    const activeIdx = chapters.findIndex(c => c.id === activeId);
	    if (activeIdx > 0) {
	      let found = null;
	      for (let i = activeIdx - 1; i >= Math.max(0, activeIdx - 5); i--) {
	        const pc = chapters[i];
	        if (pc.summary_card && pc.summary_card.main_events) { found = pc; break; }
	      }
	      if (found) {
	        prevBody.innerHTML = `<strong>第${found.order}章 ${escapeHtml(found.title || found.id)}</strong><br>${escapeHtml(found.summary_card.main_events)}`;
	      } else {
	        const prev = chapters[activeIdx - 1];
	        prevBody.textContent = `第${prev.order}章 ${escapeHtml(prev.title || prev.id)}（暂无摘要）`;
	      }
	    } else if (activeIdx === 0) {
	      prevBody.textContent = "已是第一章，无前章摘要。";
	    } else {
	      prevBody.textContent = "—";
	    }
	  }

	  const ctxList = $("ctxRuntimeList");
	  if (ctxList) {
	    const entities = state.world?.characters?.entities || [];
	    const states = entities.filter(e => e && e.runtime_state && Object.keys(e.runtime_state).length > 1);
	    if (states.length) {
	      ctxList.innerHTML = states.map(e => {
	        const rs = e.runtime_state || {};
	        return `<div class="ctx-runtime-item">
	          <span class="ctx-runtime-item-name">${escapeHtml(e.name || e.id || '?')}</span>
	          <span class="ctx-runtime-item-loc">${escapeHtml(rs.current_location || '—')}</span>
	          <span class="ctx-runtime-item-emotion">${escapeHtml(rs.emotional_state || '—')}</span>
	          <span class="ctx-runtime-item-goal">${escapeHtml(rs.current_goal || '—')}</span>
	        </div>`;
	      }).join("");
	    } else {
	      ctxList.innerHTML = '<p class="muted tiny">暂无运行时状态数据</p>';
	    }
	  }

	  void updateRagStatusDot();
	}
function collectStoryMetaForWorld(w) {
  if (!w.story) w.story = {};
  w.story.summary = ($("storySummary")?.value ?? "").trim();
  w.story.design_notes = ($("storyDesignNotes")?.value ?? "").trim();
  w.story.unit_label = storyUnitLabelForMode(w.meta.creative_mode || $("genreMode")?.value);
  const parseJson = (txt, label) => {
    try {
      return JSON.parse(txt || "[]");
    } catch (e) {
      throw new Error(`${label} JSON 无效：${e.message}`);
    }
  };
  w.story.chapters = parseJson($("storyChaptersJson")?.value, "story.chapters");
  w.story.foreshadowing = document.querySelector("#storyForeshadowList .story-fs-card")
    ? collectStoryForeshadowingFromDom()
    : parseJson($("storyForeshadowJson")?.value, "story.foreshadowing");
  if (!w.story.narrator) w.story.narrator = {};
  w.story.narrator.character_id = ($("storyNarratorCharacter")?.value ?? "").trim();
  w.story.narrator.person = $("storyNarratorPerson")?.value || "third_person_limited";
  w.story.narrator.voice_notes = ($("storyNarratorVoice")?.value ?? "").trim();
  if (!w.story.writing_defaults) w.story.writing_defaults = {};
  const ap = parseInt($("storyAttachPrev")?.value ?? "3", 10);
  w.story.writing_defaults.attach_prev_chapters = Number.isFinite(ap)
    ? Math.max(0, Math.min(5, ap))
    : 3;
  w.story.writing_defaults.enable_narrative_kg = $("storyToggleKG")?.checked ?? true;
  w.story.writing_defaults.enable_consistency_check = $("storyToggleConsistency")?.checked ?? true;
  w.story.writing_defaults.enable_sentiment_track = $("storyToggleSentiment")?.checked ?? true;
}

function bindStoryEditorPreview(textareaId, previewId, authorCheckboxId) {
  const ta = $(textareaId);
  if (!ta) return;
  const run = () => {
    const author = authorCheckboxId ? ($(authorCheckboxId)?.checked ?? true) : true;
    updateStoryMarkdownPreview(previewId, ta.value, author);
  };
  ta.addEventListener("input", run);
  if (authorCheckboxId) $(authorCheckboxId)?.addEventListener("change", run);
}

function initStoryPanelBindings() {
  document.querySelectorAll("#storyOutlineSubtabs button").forEach((b) => {
    b.addEventListener("click", () => setStoryOutlineSub(b.dataset.outlineSub || "macro"));
  });
  bindStoryEditorPreview("storyMacroEdit", "storyMacroPreview");
  bindStoryEditorPreview("storyBeatEdit", "storyBeatPreview");
  bindStoryEditorPreview("storyManuscriptEdit", "storyManuscriptPreview", "storyAuthorView");
  $("storyBeatChapterSelect")?.addEventListener("change", () => {
    const cid = $("storyBeatChapterSelect")?.value;
    if (cid) state.storyActiveChapterId = cid;
    renderStoryChapterNav(cid);
    void loadStoryBeat();
  });
  $("storyMsChapterSelect")?.addEventListener("change", () => {
    const cid = $("storyMsChapterSelect")?.value;
    if (cid) state.storyActiveChapterId = cid;
    renderStoryChapterNav(cid);
    void loadStoryManuscript();
  });

  $("btnStoryAddChapterSide")?.addEventListener("click", () => $("btnStoryAddChapter")?.click());
  $("btnStoryAddChapterChat")?.addEventListener("click", () => $("btnStoryAddChapter")?.click());
  let _lastCheckCid = null;
  for (const navId of STORY_CHAPTER_NAV_IDS) {
    $(navId)?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-story-chapter-id]");
      if (!btn?.dataset.storyChapterId) return;
      const cid = btn.dataset.storyChapterId;
      const nav = btn.closest(".story-chapter-nav");

      const clickedOnCb = e.target.closest(".story-ch-cb");
      if (e.shiftKey && _lastCheckCid && _lastCheckCid !== cid) {
        e.preventDefault();
        const allBtns = [...(nav || document).querySelectorAll("[data-story-chapter-id]")];
        const lastBtn = allBtns.find(b => b.dataset.storyChapterId === _lastCheckCid);
        const thisIdx = allBtns.indexOf(btn);
        const lastIdx = allBtns.indexOf(lastBtn);
        if (thisIdx >= 0 && lastIdx >= 0) {
          const [lo, hi] = [Math.min(thisIdx, lastIdx), Math.max(thisIdx, lastIdx)];
          const targetState = lastBtn ? !(lastBtn.querySelector(".story-ch-cb")?.checked ?? false) : true;
          for (let i = lo; i <= hi; i++) {
            const bc = allBtns[i]?.querySelector(".story-ch-cb");
            if (bc) bc.checked = targetState;
          }
        }
      } else if (clickedOnCb) {
        // Click on checkbox: let browser toggle it, don't navigate
      } else if (!e.shiftKey) {
        void selectStoryChapter(cid);
        return;
      }
      _lastCheckCid = cid;
      refreshBatchBar();
    });
  }
  $("btnStoryChatOpenChapter")?.addEventListener("click", () => {
    const cid = storyChatActiveChapterId();
    if (!cid) return toast("请先在左侧选择章节");
    void selectStoryChapter(cid, "chapter");
  });
  $("storyForeshadowList")?.addEventListener("input", scheduleStoryForeshadowSync);
  $("storyForeshadowList")?.addEventListener("change", scheduleStoryForeshadowSync);
  $("storyForeshadowList")?.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-fs-remove]");
    if (!rm) return;
    const idx = parseInt(rm.dataset.fsRemove ?? "", 10);
    const items = collectStoryForeshadowingFromDom().filter((_, i) => i !== idx);
    syncStoryForeshadowJson(items);
    renderStoryForeshadowTimeline(items);
    updateStoryWbStats();
    setDirty(true);
  });
  $("storyForeshadowJson")?.addEventListener("input", scheduleStoryForeshadowFromJson);
  // P2: Foreshadow filter events
  document.querySelectorAll(".story-fs-badge-filter").forEach(badge => {
    badge.addEventListener("click", () => {
      const filterVal = badge.dataset.fsFilter || "";
      if (_foreshadowFilter.status === filterVal) {
        _foreshadowFilter.status = ""; // toggle off
      } else {
        _foreshadowFilter.status = filterVal;
      }
      document.querySelectorAll(".story-fs-badge-filter").forEach(b => {
        b.classList.toggle("story-fs-badge-filter--active", b.dataset.fsFilter === _foreshadowFilter.status);
      });
      const items = document.querySelector("#storyForeshadowList .story-fs-card")
        ? collectStoryForeshadowingFromDom()
        : (state.world?.story?.foreshadowing || []);
      renderStoryForeshadowTimeline(items);
    });
  });
  $("storyFsChapterFilter")?.addEventListener("change", () => {
    _foreshadowFilter.chapter = $("storyFsChapterFilter")?.value || "";
    const items = document.querySelector("#storyForeshadowList .story-fs-card")
      ? collectStoryForeshadowingFromDom()
      : (state.world?.story?.foreshadowing || []);
    renderStoryForeshadowTimeline(items);
  });
  $("btnStoryFsClearFilter")?.addEventListener("click", () => {
    _foreshadowFilter = { status: "", chapter: "" };
    document.querySelectorAll(".story-fs-badge-filter").forEach(b => b.classList.remove("story-fs-badge-filter--active"));
    if ($("storyFsChapterFilter")) $("storyFsChapterFilter").value = "";
    const items = document.querySelector("#storyForeshadowList .story-fs-card")
      ? collectStoryForeshadowingFromDom()
      : (state.world?.story?.foreshadowing || []);
    renderStoryForeshadowTimeline(items);
  });

  $("btnStoryAddForeshadow")?.addEventListener("click", () => {
    let list = document.querySelector("#storyForeshadowList .story-fs-card")
      ? collectStoryForeshadowingFromDom()
      : parseStoryForeshadowingFromForm() ?? [];
    const chapters = sortedStoryChapters();
    list.push({
      id: newStoryForeshadowId(),
      label: "",
      planted_chapter_id: chapters[0]?.id || "",
      payoff_chapter_id: "",
      reader_known: false,
      status: "open",
      notes: "",
    });
    syncStoryForeshadowJson(list);
    renderStoryForeshadowTimeline(list);
    updateStoryWbStats();
    setDirty(true);
  });
  $("storyChaptersJson")?.addEventListener("input", () => {
    if (state.world?.story) {
      try {
        state.world.story.chapters = JSON.parse($("storyChaptersJson")?.value || "[]");
      } catch {
        return;
      }
    }
    refreshStoryChapterSelects();
    renderStoryChapterNav();
    updateStoryWbStats();
    const items = parseStoryForeshadowingFromForm();
    if (items) renderStoryForeshadowTimeline(items);
    setDirty(true);
  });

  $("btnStorySaveMacro")?.addEventListener("click", async () => {
    if (!state.world) return toast("请先选择世界");
    try {
      await api(`/api/worlds/${state.world.meta.id}/story/macro-outline`, {
        method: "PUT",
        body: JSON.stringify({ content: $("storyMacroEdit")?.value ?? "" }),
      });
      toast("粗纲已保存");
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  });

  $("btnStorySaveBeat")?.addEventListener("click", async () => {
    const cid = $("storyBeatChapterSelect")?.value;
    if (!cid || !state.world) return;
    try {
      await api(`/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/beat`, {
        method: "PUT",
        body: JSON.stringify({ content: $("storyBeatEdit")?.value ?? "" }),
      });
      toast("细纲已保存");
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  });

  $("btnStorySaveManuscript")?.addEventListener("click", async () => {
    const cid = $("storyMsChapterSelect")?.value;
    if (!cid || !state.world) return;
    try {
      const res = await api(
        `/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/manuscript`,
        {
          method: "PUT",
          body: JSON.stringify({ content: $("storyManuscriptEdit")?.value ?? "" }),
        }
      );
      toast(`文稿已保存（约 ${res.word_count ?? 0} 字）`);
      await refreshStoryPanel();
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  });

  $("btnStoryAddChapter")?.addEventListener("click", async () => {
    if (!state.world) return toast("请先选择世界");
    const title = prompt("新章节标题（可留空）") || "";
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters`, {
        method: "POST",
        body: JSON.stringify({ title }),
      });
      state.world = res.world;
      storyMetaToForm();
      const newId = res.chapter?.id;
      if (newId) void selectStoryChapter(newId);
      setDirty(true);
      toast("已新建章节");
    } catch (e) {
      toast("新建失败：" + e.message);
    }
  });

  $("btnStoryImportLegacy")?.addEventListener("click", async () => {
    if (!state.world) return;
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/import-legacy-outline`, {
        method: "POST",
        body: "{}",
      });
      if (res.ok && $("storyMacroEdit")) $("storyMacroEdit").value = res.content || "";
      toast(res.ok ? "已导入旧情节总纲" : "未找到可导入文件");
      if (res.ok) {
        switchView("storyOutline");
        setStoryOutlineSub("macro");
      }
    } catch (e) {
      toast("导入失败：" + e.message);
    }
  });

  $("btnStoryGenMacro")?.addEventListener("click", async () => {
    if (!state.world) return;
    const promptText =
      ($("storyGenMacroHint")?.value ?? "").trim() || "请根据当前世界设定撰写全书粗纲。";
    const genToken = beginStoryGeneration("generate-macro", {
      panel: "storyWb",
      previewIds: ["storyMacroPreview"],
    });
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/generate/macro-outline`, {
        method: "POST",
        body: JSON.stringify({
          prompt: promptText,
          include_markdown_context: false,
          creative_mode: $("genreMode")?.value || null,
          persist: true,
        }),
      });
      state.world = res.world;
      if ($("storyMacroEdit")) $("storyMacroEdit").value = res.reply || "";
      updateStoryMarkdownPreview("storyMacroPreview", res.reply || "", true);
      storyMetaToForm();
      setDirty(false);
      toast("粗纲已生成并落盘");
    } catch (e) {
      toast("生成失败：" + e.message);
    } finally {
      endStoryGeneration({ token: genToken });
    }
  });

  $("btnStoryGenBeats")?.addEventListener("click", async () => {
    if (!state.world) return;
    const cid = $("storyBeatChapterSelect")?.value;
    const ids = cid ? [cid] : sortedStoryChapters().map((c) => c.id);
    if (!ids.length) return toast("请先新建章节");
    const promptText = ($("storyGenBeatsHint")?.value ?? "").trim() || "请撰写本章细纲。";
    const genToken = beginStoryGeneration("generate-beats", {
      panel: "storyWb",
      chapterIds: ids,
      previewIds: ["storyBeatPreview"],
    });
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/generate/chapter-beats`, {
        method: "POST",
        body: JSON.stringify({
          chapter_ids: ids,
          prompt: promptText,
          creative_mode: $("genreMode")?.value || null,
          persist: true,
        }),
      });
      state.world = res.world;
      storyMetaToForm();
      if (cid && res.beats?.[cid] && $("storyBeatEdit")) {
        $("storyBeatEdit").value = res.beats[cid];
        updateStoryMarkdownPreview("storyBeatPreview", res.beats[cid], true);
      }
      setDirty(false);
      toast("细纲已生成");
    } catch (e) {
      toast("生成失败：" + e.message);
    } finally {
      endStoryGeneration({ token: genToken });
    }
  });

  $("btnStoryGenManuscript")?.addEventListener("click", () => {
    void generateStoryManuscriptFromUI({ useChatStrip: false, navigate: true });
  });

  $("btnStoryChatGenManuscript")?.addEventListener("click", () => {
    void generateStoryManuscriptFromUI({ useChatStrip: true, navigate: false });
  });

  // Layer 4: Polisher toggle & max rounds
  $("storyTogglePolisher")?.addEventListener("change", () => void savePolishToggle("storyTogglePolisher"));
  $("storyPolishMaxRounds")?.addEventListener("change", () => void savePolishToggle("storyPolishMaxRounds"));
  $("storyChatTogglePolisher")?.addEventListener("change", () => void savePolishToggle("storyChatTogglePolisher"));
  $("storyChatPolishMaxRounds")?.addEventListener("change", () => void savePolishToggle("storyChatPolishMaxRounds"));
  $("storyToggleChunking")?.addEventListener("change", () => void _saveWritingDefaultsFromForm());
  $("storyChatToggleChunking")?.addEventListener("change", () => void _saveWritingDefaultsFromForm());
  $("storyToggleUnified")?.addEventListener("change", () => void _saveWritingDefaultsFromForm());
  $("storyChatToggleUnified")?.addEventListener("change", () => void _saveWritingDefaultsFromForm());
  // Toggle checkboxes: save to backend + refresh budget estimate
  for (const id of ["storyToggleKG", "storyToggleConsistency", "storyToggleSentiment",
                     "storyTogglePolisher", "storyPolishMaxRounds"]) {
    $(id)?.addEventListener("change", () => {
      void _saveWritingDefaultsFromForm();
      void refreshUsageStats();
    });
  }

  // Knowledge detection toggle
  $("storyToggleKnowledge")?.addEventListener("change", () => void saveKnowledgeToggle());
  $("storyToggleDecisions")?.addEventListener("change", () => void saveKnowledgeToggle());
  $("storyTogglePhysical")?.addEventListener("change", () => void saveKnowledgeToggle());
  $("storyToggleTimeline")?.addEventListener("change", () => void saveKnowledgeToggle());
  $("storyToggleSpeech")?.addEventListener("change", () => void saveKnowledgeToggle());
  $("storyToggleAftermath")?.addEventListener("change", () => void saveKnowledgeToggle());
  $("charKnowledgeFilterChar")?.addEventListener("change", () => renderKnowledgePanel());
  $("btnClearKnowledge")?.addEventListener("click", () => void clearKnowledgeGraph());
  $("btnExtractAllKnowledge")?.addEventListener("click", () => void extractAllKnowledge());
  // Tab switching
  document.querySelectorAll(".knowledge-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".knowledge-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const show = tab.dataset.knowledgeTab;
      const allLists = ["charKnowledgeList", "charDecisionsList", "charPhysicalList", "charTimelineList", "charSpeechList", "charAftermathList"];
      const tabMap = { knowledge: "charKnowledgeList", decisions: "charDecisionsList", physical: "charPhysicalList", timeline: "charTimelineList", speech: "charSpeechList", aftermath: "charAftermathList" };
      allLists.forEach(id => {
        const el = $(id);
        if (el) el.classList.toggle("hidden", tabMap[show] !== id);
      });
      if (show === "decisions") renderDecisionsPanel();
      if (show === "physical") renderPhysicalStatesPanel();
      if (show === "timeline") renderTimelinePanel();
    });
  });

}

/** 将 profession_system.by_tier 按当前 tiers 顺序与 tier_name 对齐，避免模型输出顺序与境界表不一致导致卡片错位 */
function alignProfessionSystemToTiers(tiers, ps) {
  const src = ps && typeof ps === "object" ? ps : {};
  const raw = Array.isArray(src.by_tier) ? src.by_tier : [];
  if (!Array.isArray(tiers) || !tiers.length) {
    return {
      summary: String(src.summary ?? "").trim(),
      design_notes: String(src.design_notes ?? "").trim(),
      by_tier: raw,
    };
  }
  const nameMap = new Map();
  const display = new Map();
  for (const b of raw) {
    if (!b || typeof b !== "object") continue;
    const tn = String(b.tier_name ?? "").trim();
    const key = tn ? tn.toLowerCase() : "__anon__";
    if (!display.has(key)) display.set(key, tn || key);
    const list = Array.isArray(b.professions) ? b.professions : [];
    const prev = nameMap.get(key) || [];
    nameMap.set(key, prev.concat(list));
  }
  const aligned = [];
  for (const t of tiers) {
    const name = String(t?.name ?? "").trim();
    const k = name.toLowerCase();
    let profs = [];
    if (name && nameMap.has(k)) {
      profs = nameMap.get(k) || [];
      nameMap.delete(k);
    }
    aligned.push({ tier_name: name, professions: structuredClone(profs) });
  }
  for (const [k, profs] of nameMap) {
    if (k === "__anon__" && (!profs || !profs.length)) continue;
    aligned.push({ tier_name: display.get(k) || k, professions: structuredClone(profs || []) });
  }
  return {
    summary: String(src.summary ?? "").trim(),
    design_notes: String(src.design_notes ?? "").trim(),
    by_tier: aligned,
  };
}

function visibleProfessionCountForTiers(tiers, professionSystem) {
  const byTier = Array.isArray(professionSystem?.by_tier) ? professionSystem.by_tier : [];
  const n = Array.isArray(tiers) ? tiers.length : 0;
  return byTier.slice(0, n).reduce((s, b) => s + (Array.isArray(b?.professions) ? b.professions.length : 0), 0);
}

function refreshPowerProfessionCountBadge(w) {
  const badge = $("powerProfessionCount");
  if (!badge) return;
  const tiers = w?.power_system?.tiers || [];
  const total = visibleProfessionCountForTiers(tiers, w?.power_system?.profession_system);
  badge.textContent = total;
  badge.style.display = total > 0 ? "" : "none";
}

function refreshPowerUiFromWorld(w) {
  if (!w?.power_system) return;
  if (Array.isArray(w.power_system.tiers)) {
    w.power_system.profession_system = alignProfessionSystemToTiers(
      w.power_system.tiers,
      w.power_system.profession_system || {}
    );
  }
  if ($("powerTiersJson")) $("powerTiersJson").value = JSON.stringify(w.power_system?.tiers ?? [], null, 2);
  if ($("powerProfessionSummary"))
    $("powerProfessionSummary").value = w.power_system?.profession_system?.summary ?? "";
  if ($("powerProfessionDesign"))
    $("powerProfessionDesign").value = w.power_system?.profession_system?.design_notes ?? "";
  renderPowerTierDashboardModules(w);
  updatePowerTierSkillTreePreviews(w.power_system?.tiers || []);
  updatePowerProfessionPreviews(w.power_system?.tiers || [], w.power_system?.profession_system || {});
  refreshPowerProfessionCountBadge(w);
  requestAnimationFrame(() => refreshProfessionPromotionViz());
}

function worldToForm(w) {
  if (!w) {
    $("geoSummary").value = "";
    $("geoClimate").value = "";
    $("geoMap").value = "";
    $("powerSummary").value = "";
    if ($("powerRealmDesign")) $("powerRealmDesign").value = "";
    if ($("powerSkillTreeDesign")) $("powerSkillTreeDesign").value = "";
    $("powerTiersJson").value = "[]";
    if ($("powerProfessionSummary")) $("powerProfessionSummary").value = "";
    if ($("powerProfessionDesign")) $("powerProfessionDesign").value = "";
    $("itemSummary").value = "";
    $("itemGradesJson").value = "[]";
    $("factionSummary").value = "";
    $("factionsJson").value = "[]";
    $("cultureSummary").value = "";
    $("culturesJson").value = "[]";
    $("historySummary").value = "";
    $("historyJson").value = "[]";
    if ($("economySummary")) $("economySummary").value = "";
    if ($("economyDesignNotes")) $("economyDesignNotes").value = "";
    if ($("economyLaborNotes")) $("economyLaborNotes").value = "";
    if ($("economyTaxationNotes")) $("economyTaxationNotes").value = "";
    if ($("economyVolatilityNotes")) $("economyVolatilityNotes").value = "";
    if ($("economyCurrenciesJson")) $("economyCurrenciesJson").value = "[]";
    if ($("economyMarketsJson")) $("economyMarketsJson").value = "[]";
    if ($("economyTradeRoutesJson")) $("economyTradeRoutesJson").value = "[]";
    if ($("economyTradeGoodsJson")) $("economyTradeGoodsJson").value = "[]";
    if ($("attrSummary")) $("attrSummary").value = "";
    if ($("attrDesignNotes")) $("attrDesignNotes").value = "";
    if ($("attrStatsJson")) $("attrStatsJson").value = "[]";
    if ($("attrTierProfilesJson")) $("attrTierProfilesJson").value = "[]";
    if ($("ecologySummary")) $("ecologySummary").value = "";
    if ($("ecologyDesignNotes")) $("ecologyDesignNotes").value = "";
    if ($("ecologyBiomesJson")) $("ecologyBiomesJson").value = "[]";
    if ($("ecologySpeciesJson")) $("ecologySpeciesJson").value = "[]";
    if ($("ecologyGenerateHint")) $("ecologyGenerateHint").value = "";
    if ($("ecologyGenerateOut")) $("ecologyGenerateOut").innerHTML = "";
    if ($("charEntitiesJson")) $("charEntitiesJson").value = "[]";
    if ($("charRelationsJson")) $("charRelationsJson").value = "[]";
    if ($("charIncludeMd")) $("charIncludeMd").checked = false;
    if ($("charAutoSyncPanels")) $("charAutoSyncPanels").checked = true;
    if ($("storySummary")) $("storySummary").value = "";
    if ($("storyDesignNotes")) $("storyDesignNotes").value = "";
    if ($("storyChaptersJson")) $("storyChaptersJson").value = "[]";
    if ($("storyForeshadowJson")) $("storyForeshadowJson").value = "[]";
    state.charMessages = [];
    renderCharMessages();
    renderCharCastSubgrid("charProtagonists", "vizCharProtagonists", "charProtagonistsEmpty", [], "protagonists");
    renderCharCastSubgrid("charSupporting", "vizCharSupporting", "charSupportingEmpty", [], "supporting");
    const gm = $("genreMode");
    if (gm) gm.value = "";
    renderRegionCards([]);
    renderFactionCards([]);
    renderCultureCards([]);
    refreshGeoMarkdownPreviews();
    refreshEcologyMarkdownPreviews();
    renderEcologyVizFromForm();
    refreshEcologyGenerateMarkdown("");
    updateGenreModeHint();
    updateCultureHint();
    updateFactionGlobalBriefPreview();
    refreshFactionChatViz();
    refreshContextPanel();
    refreshFilesView();
    refreshSearchView();
    refreshOutlineHeader();
    return;
  }
  $("geoSummary").value = w.geography?.summary ?? "";
  $("geoClimate").value = w.geography?.climate_notes ?? "";
  $("geoMap").value = w.geography?.map_notes ?? "";

  migrateGlobalLandmarksResourcesIntoRegions(w);
  $("powerSummary").value = w.power_system?.summary ?? "";
  if ($("powerRealmDesign"))
    $("powerRealmDesign").value = w.power_system?.realm_design_notes ?? "";
  if ($("powerSkillTreeDesign"))
    $("powerSkillTreeDesign").value = w.power_system?.skill_tree_design_notes ?? "";
  refreshPowerUiFromWorld(w);

  $("itemSummary").value = w.item_quality_system?.summary ?? "";
  $("itemGradesJson").value = JSON.stringify(w.item_quality_system?.grades ?? [], null, 2);

  $("factionSummary").value = w.factions?.summary ?? "";
  $("factionsJson").value = JSON.stringify(w.factions?.entities ?? [], null, 2);

  $("cultureSummary").value = w.cultures?.summary ?? "";
  $("culturesJson").value = JSON.stringify(w.cultures?.entities ?? [], null, 2);

  $("historySummary").value = w.history?.summary ?? "";
  $("historyJson").value = JSON.stringify(w.history?.events ?? [], null, 2);

  const eco = w.economy || {};
  if ($("economySummary")) $("economySummary").value = eco.summary ?? "";
  if ($("economyDesignNotes")) $("economyDesignNotes").value = eco.design_notes ?? "";
  if ($("economyLaborNotes")) $("economyLaborNotes").value = eco.labor_notes ?? "";
  if ($("economyTaxationNotes")) $("economyTaxationNotes").value = eco.taxation_notes ?? "";
  if ($("economyVolatilityNotes")) $("economyVolatilityNotes").value = eco.volatility_notes ?? "";
  if ($("economyCurrenciesJson"))
    $("economyCurrenciesJson").value = JSON.stringify(eco.currencies ?? [], null, 2);
  if ($("economyMarketsJson")) $("economyMarketsJson").value = JSON.stringify(eco.markets ?? [], null, 2);
  if ($("economyTradeRoutesJson"))
    $("economyTradeRoutesJson").value = JSON.stringify(eco.trade_routes ?? [], null, 2);
  if ($("economyTradeGoodsJson"))
    $("economyTradeGoodsJson").value = JSON.stringify(eco.trade_goods ?? [], null, 2);

  if ($("attrSummary")) $("attrSummary").value = w.attribute_system?.summary ?? "";
  if ($("attrDesignNotes")) $("attrDesignNotes").value = w.attribute_system?.design_notes ?? "";
  if ($("attrStatsJson"))
    $("attrStatsJson").value = JSON.stringify(w.attribute_system?.stats ?? [], null, 2);
  if ($("attrTierProfilesJson"))
    $("attrTierProfilesJson").value = JSON.stringify(
      w.attribute_system?.tier_average_profiles ?? [],
      null,
      2
    );

  if ($("ecologySummary")) $("ecologySummary").value = w.ecology?.summary ?? "";
  if ($("ecologyDesignNotes")) $("ecologyDesignNotes").value = w.ecology?.design_notes ?? "";
  if ($("ecologyBiomesJson"))
    $("ecologyBiomesJson").value = JSON.stringify(w.ecology?.biomes ?? [], null, 2);
  if ($("ecologySpeciesJson"))
    $("ecologySpeciesJson").value = JSON.stringify(w.ecology?.species ?? [], null, 2);

  const ch = w.characters || {};
  if ($("charEntitiesJson"))
    $("charEntitiesJson").value = JSON.stringify(ch.entities ?? [], null, 2);
  if ($("charRelationsJson"))
    $("charRelationsJson").value = JSON.stringify(ch.relations ?? [], null, 2);

  renderRegionCards(w.geography?.regions);
  renderFactionCards(w.factions?.entities);
  renderCultureCards(w.cultures?.entities);

  refreshGeoMarkdownPreviews();
  refreshEcologyMarkdownPreviews();
  renderEcologyVizFromForm();

  const gm = $("genreMode");
  if (gm) gm.value = w.meta?.creative_mode || "";
  updateGenreModeHint();
  updateCultureHint();
  updateFactionGlobalBriefPreview();
  refreshFactionChatViz();
  scheduleCharactersVizFromForm();

  const st = w.story || {};
  state.storyUnitLabel = st.unit_label || storyUnitLabelForMode(w.meta?.creative_mode);
  if ($("storySummary")) $("storySummary").value = st.summary ?? "";
  if ($("storyDesignNotes")) $("storyDesignNotes").value = st.design_notes ?? "";
  if ($("storyChaptersJson")) $("storyChaptersJson").value = JSON.stringify(st.chapters ?? [], null, 2);
  if ($("storyForeshadowJson"))
    $("storyForeshadowJson").value = JSON.stringify(st.foreshadowing ?? [], null, 2);
  const sn = st.narrator || {};
  if ($("storyNarratorPerson")) $("storyNarratorPerson").value = sn.person || "third_person_limited";
  if ($("storyNarratorVoice")) $("storyNarratorVoice").value = sn.voice_notes ?? "";
  const swd = st.writing_defaults || {};
  if ($("storyAttachPrev")) $("storyAttachPrev").value = String(swd.attach_prev_chapters ?? 3);
  refreshStoryNarratorSelect(sn.character_id || "");
  refreshStoryChapterSelects();
  syncStoryChatWritingControlsFromForm();
  renderStoryChapterNav();
  renderStoryForeshadowTimeline(st.foreshadowing ?? []);
  updateStoryWbStats();
  if ($("storyUnitLine")) $("storyUnitLine").textContent = `情节单元：${state.storyUnitLabel}`;
}

function formToWorld() {
  if (!state.world) return null;
  const w = structuredClone(state.world);
  const gm = $("genreMode");
  if (gm) w.meta.creative_mode = gm.value?.trim() || null;
  w.geography.summary = $("geoSummary").value.trim();
  w.geography.climate_notes = $("geoClimate").value.trim();
  w.geography.map_notes = $("geoMap").value.trim();
  w.geography.regions = collectRegionsFromDom();
  const flatLm = [];
  const flatRes = [];
  for (const r of w.geography.regions || []) {
    if (Array.isArray(r.landmarks)) flatLm.push(...r.landmarks.map((x) => String(x).trim()).filter(Boolean));
    if (Array.isArray(r.resources)) flatRes.push(...r.resources.map((x) => String(x).trim()).filter(Boolean));
  }
  w.geography.landmarks = [...new Set(flatLm)];
  w.geography.resources = [...new Set(flatRes)];

  w.power_system.summary = $("powerSummary").value.trim();
  w.power_system.realm_design_notes = ($("powerRealmDesign")?.value ?? "").trim();
  w.power_system.skill_tree_design_notes = ($("powerSkillTreeDesign")?.value ?? "").trim();
  w.item_quality_system.summary = $("itemSummary").value.trim();
  w.factions.summary = $("factionSummary").value.trim();
  w.cultures.summary = $("cultureSummary").value.trim();
  w.history.summary = $("historySummary").value.trim();

  const parseJson = (txt, label) => {
    try {
      return JSON.parse(txt || "[]");
    } catch (e) {
      throw new Error(`${label} JSON 无效：${e.message}`);
    }
  };

  const tiersFromViz = collectPowerTiersFromViz();
  const tiersResolved =
    tiersFromViz != null ? tiersFromViz : parseJson($("powerTiersJson").value, "境界 tiers");
  w.power_system.tiers = tiersResolved;
  w.power_system.profession_system = w.power_system.profession_system || {};
  w.power_system.profession_system.summary = ($("powerProfessionSummary")?.value ?? "").trim();
  w.power_system.profession_system.design_notes = ($("powerProfessionDesign")?.value ?? "").trim();
  w.power_system.profession_system.by_tier = collectProfessionByTierFromDom(tiersResolved);
  const gradesFromViz = collectItemGradesFromViz();
  w.item_quality_system.grades =
    gradesFromViz != null
      ? gradesFromViz
      : parseJson($("itemGradesJson").value, "物品档位");
  const fc = document.querySelectorAll("#factionCards .faction-card");
  w.factions.entities =
    fc.length > 0
      ? collectFactionsFromDom()
      : parseJson($("factionsJson")?.value || "[]", "派系");
  const cc = document.querySelectorAll("#cultureCards .culture-card");
  w.cultures.entities =
    cc.length > 0
      ? collectCulturesFromDom()
      : parseJson($("culturesJson")?.value || "[]", "文化/宗教");
  const eventsFromViz = collectHistoryEventsFromViz();
  w.history.events =
    eventsFromViz != null ? eventsFromViz : parseJson($("historyJson").value, "历史事件");

  if (!w.attribute_system)
    w.attribute_system = { summary: "", design_notes: "", stats: [], tier_average_profiles: [] };
  w.attribute_system.summary = ($("attrSummary")?.value ?? "").trim();
  w.attribute_system.design_notes = ($("attrDesignNotes")?.value ?? "").trim();
  w.attribute_system.stats = parseJson($("attrStatsJson")?.value || "[]", "人物属性 stats");
  w.attribute_system.tier_average_profiles = parseJson(
    $("attrTierProfilesJson")?.value || "[]",
    "境界平均属性 tier_average_profiles"
  );

  if (!w.ecology) w.ecology = { summary: "", design_notes: "", biomes: [], species: [] };
  w.ecology.summary = ($("ecologySummary")?.value ?? "").trim();
  w.ecology.design_notes = ($("ecologyDesignNotes")?.value ?? "").trim();
  w.ecology.biomes = parseJson($("ecologyBiomesJson")?.value || "[]", "生态 biomes");
  w.ecology.species = parseJson($("ecologySpeciesJson")?.value || "[]", "生态 species");

  if (!w.economy)
    w.economy = {
      summary: "",
      design_notes: "",
      currencies: [],
      markets: [],
      trade_routes: [],
      trade_goods: [],
      labor_notes: "",
      taxation_notes: "",
      volatility_notes: "",
    };
  w.economy.summary = ($("economySummary")?.value ?? "").trim();
  w.economy.design_notes = ($("economyDesignNotes")?.value ?? "").trim();
  w.economy.labor_notes = ($("economyLaborNotes")?.value ?? "").trim();
  w.economy.taxation_notes = ($("economyTaxationNotes")?.value ?? "").trim();
  w.economy.volatility_notes = ($("economyVolatilityNotes")?.value ?? "").trim();
  w.economy.currencies = parseJson($("economyCurrenciesJson")?.value || "[]", "经济 currencies");
  w.economy.markets = parseJson($("economyMarketsJson")?.value || "[]", "经济 markets");
  w.economy.trade_routes = parseJson($("economyTradeRoutesJson")?.value || "[]", "经济 trade_routes");
  w.economy.trade_goods = parseJson($("economyTradeGoodsJson")?.value || "[]", "经济 trade_goods");

  if (!w.characters) w.characters = { summary: "", design_notes: "", entities: [], relations: [] };
  w.characters.entities = parseJson($("charEntitiesJson")?.value || "[]", "人物 entities");
  w.characters.relations = parseJson($("charRelationsJson")?.value || "[]", "人物 relations");

  if (!w.story) {
    w.story = {
      summary: "",
      design_notes: "",
      unit_label: "",
      chapters: [],
      foreshadowing: [],
    };
  }
  collectStoryMetaForWorld(w);

  return w;
}

function refreshWorldTabTitle() {
  const suffix = "Magic Creater World — 世界观工作台";
  if (!state.world?.meta?.id) {
    document.title = suffix;
    return;
  }
  const n = (state.world.meta.name || "").trim() || state.world.meta.id;
  document.title = `${n} — ${suffix}`;
}

function refreshOutlineHeader() {
  const line = $("storyOutlineVersionLine") || $("outlineVersionLine");
  if (!line) return;
  if (!state.world) {
    line.textContent = "请先选择或新建世界。";
    return;
  }
  const m = state.world.meta;
  line.textContent = `当前依据：world.json · ${m.name} · v${m.version} · ${m.id}`;
}

function updateOutlineMarkdownPreview(text) {
  const el = $("outlinePreview");
  if (!el) return;
  el.innerHTML = renderAssistantMarkdownHtml((text ?? "").toString());
}

function refreshStoryChatContextLine() {
  const line = $("storyChatContextLine");
  if (!line) return;
  const cid = storyChatActiveChapterId();
  if (!cid) {
    line.textContent = "当前章节：（未选；对话与撰写将默认使用列表中第一章）";
    return;
  }
  const ch = sortedStoryChapters().find((c) => c.id === cid);
  const unit = state.storyUnitLabel || "章";
  line.textContent = ch
    ? `当前${unit}：${ch.order}. ${(ch.title || "").trim() || ch.id} · ${ch.status || "planned"}（id=${cid}）`
    : `当前章节 id=${cid}（未在 chapters 索引中，请保存或同步）`;
  refreshStoryChatBeatTitleHint(cid);
}

function parseStoryMdBlocks(text) {
  const blocks = [];
  const re = /```([^\n`]+)\s*\n([\s\S]*?)```/g;
  let m;
  const raw = (text ?? "").toString();
  while ((m = re.exec(raw))) {
    const tag = (m[1] || "").trim().toLowerCase();
    const content = (m[2] || "").trim();
    if (!content) continue;
    if (tag === "story-macro") blocks.push({ kind: "macro", chapterId: "", content });
    else if (tag.startsWith("story-beat:"))
      blocks.push({ kind: "beat", chapterId: tag.slice("story-beat:".length).trim(), content });
    else if (tag.startsWith("story-manuscript:"))
      blocks.push({
        kind: "manuscript",
        chapterId: tag.slice("story-manuscript:".length).trim(),
        content,
      });
    else if (tag === "story-foreshadow")
      blocks.push({ kind: "foreshadow", chapterId: "", content });
  }
  return blocks;
}

function parseStoryForeshadowOperations(text) {
  const ops = [];
  const re = /```story-foreshadow\s*\n([\s\S]*?)```/gi;
  let m;
  const raw = (text ?? "").toString();
  while ((m = re.exec(raw))) {
    const body = (m[1] || "").trim();
    if (!body) continue;
    try {
      const data = JSON.parse(body);
      if (Array.isArray(data)) ops.push(...data.filter((x) => x && typeof x === "object"));
      else if (data && typeof data === "object" && Array.isArray(data.operations))
        ops.push(...data.operations.filter((x) => x && typeof x === "object"));
    } catch {
      /* ignore */
    }
  }
  return ops;
}

async function applyStoryForeshadowOperations(operations) {
  if (!state.world?.meta?.id || !operations?.length) return null;
  const res = await api(`/api/worlds/${state.world.meta.id}/story/foreshadowing/apply`, {
    method: "POST",
    body: JSON.stringify({ operations, persist: true }),
  });
  state.world = res.world;
  syncStoryForeshadowJson(res.world?.story?.foreshadowing ?? []);
  renderStoryForeshadowTimeline(res.world?.story?.foreshadowing ?? []);
  setDirty(false);
  return res;
}

async function autoApplyStoryArtifactsFromReply(text, serverAutoApplied) {
  const applied = [];
  const serverDid = Array.isArray(serverAutoApplied) && serverAutoApplied.length > 0;
  if (!serverDid) {
    const blocks = parseStoryMdBlocks(text).filter((b) => b.kind !== "foreshadow");
    for (const block of blocks) {
      await applyStoryMdBlock(block);
      applied.push(block.kind);
    }
    const fsOps = parseStoryForeshadowOperations(text);
    if (fsOps.length) {
      const res = await applyStoryForeshadowOperations(fsOps);
      if (res?.applied?.length) applied.push(...res.applied);
    }
  } else if (state.world?.story?.foreshadowing) {
    renderStoryForeshadowTimeline(state.world.story.foreshadowing);
    syncStoryForeshadowJson(state.world.story.foreshadowing);
  }
  return applied;
}

function storyChatActionsIncludeManuscript(actions) {
  if (!Array.isArray(actions)) return false;
  return actions.some((a) => a?.tool === "generate_manuscript");
}

async function generateStoryManuscriptFromUI(opts = {}) {
  if (!state.world) return toast("请先选择世界");
  const useChat = opts.useChatStrip === true;
  const cid =
    opts.chapterId ||
    (useChat ? $("storyChatChapterSelect")?.value : $("storyWriteChapterSelect")?.value) ||
    storyChatActiveChapterId();
  if (!cid) return toast("请选择章节");

  // Check if manuscript already exists → offer polish-only option
  const wid = state.world.meta.id;
  let existingMs = "";
  try {
    const checkRes = await api(`/api/worlds/${wid}/story/chapters/${encodeURIComponent(cid)}/manuscript`);
    existingMs = (checkRes.content || "").trim();
  } catch (_) { /* no existing manuscript */ }

  let polishOnly = false;
  if (existingMs && !opts.skipConfirm) {
    const ch = (state.world.story?.chapters || []).find(c => c.id === cid);
    const chTitle = ch?.title || cid;
    const choice = confirm(
      `「${chTitle}」已有文稿（约 ${existingMs.length.toLocaleString()} 字）。\n\n` +
      `点「确定」重新撰写全文（从零生成）\n点「取消」仅重新润色现有文稿`
    );
    if (choice) {
      // OK = full regenerate
    } else {
      // Cancel = polish only
      polishOnly = true;
    }
  }

  if (polishOnly) {
    // ── Polish-only path ──
    const genToken = beginStoryGeneration("polish-only", {
      panel: useChat ? "story" : "storyWb",
      chapterIds: [cid],
      previewIds: ["storyManuscriptPreview"],
    });
    try {
      const res = await api(`/api/worlds/${wid}/story/generate/polish-only`, {
        method: "POST",
        body: JSON.stringify({ chapter_id: cid, persist: true }),
      });
      state.world = res.world;
      storyMetaToForm();
      state.storyActiveChapterId = cid;
      if ($("storyMsChapterSelect")) $("storyMsChapterSelect").value = cid;
      if ($("storyManuscriptEdit")) $("storyManuscriptEdit").value = res.reply || "";
      updateStoryMarkdownPreview("storyManuscriptPreview", res.reply || "", $("storyAuthorView")?.checked ?? true);
      setDirty(false);
      const pr = res.polish_rounds || 0;
      toast(`已润色完成（${pr} 轮，约 ${(res.reply || "").length.toLocaleString()} 字）`);
      if (opts.navigate !== false) switchView("storyChapter");
    } catch (e) {
      toast("润色失败：" + e.message);
    } finally {
      endStoryGeneration({ token: genToken });
    }
    return;
  }

  const wp = storyWritingParamsFromUI(useChat);
  const lastUser = opts.lastUserMessage ?? lastStoryUserMessage();
  const prompt = wp.writing_prompt || "请撰写本章正文。";
  const panel = useChat ? "story" : "storyWb";
  const genToken = beginStoryGeneration("generate-manuscript", {
    panel,
    chapterIds: [cid],
    previewIds: ["storyManuscriptPreview"],
  });
  const useStream = opts.stream !== false;
  try {
    const requestBody = {
      chapter_id: cid,
      prompt,
      last_user_message: lastUser,
      person: wp.person,
      character_id: wp.character_id,
      attach_prev_chapters: wp.attach_prev_chapters,
      creative_mode: $("genreMode")?.value || null,
      persist: true,
    };

    if (useStream) {
      // ── Streaming path ──
      const resp = await fetch(
        `/api/worlds/${state.world.meta.id}/story/generate/manuscript/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
        }
      );
      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(errText || `HTTP ${resp.status}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let fullText = "";
      let buffer = "";
      let polishRounds = 0;
      const previewEl = $("storyManuscriptPreview");
      const editEl = $("storyManuscriptEdit");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "step") {
              showGenerationStep(event);
            } else if (event.type === "text") {
              fullText += event.content;
              if (editEl) editEl.value = fullText;
              if (previewEl) {
                updateStoryMarkdownPreview(
                  "storyManuscriptPreview",
                  fullText,
                  $("storyAuthorView")?.checked ?? true
                );
              }
            } else if (event.type === "hook_errors") {
              for (const err of event.errors || []) {
                toast(`⚠️ ${err}`);
              }
            } else if (event.type === "done") {
              state.world = event.world;
              polishRounds = event.polish_rounds || 0;
              if (event.timing_breakdown && Array.isArray(event.timing_breakdown)) {
                const timingContainerId = useChat ? "timingBreakdownChat" : "timingBreakdownWrite";
                showTimingBreakdown(event.timing_breakdown, timingContainerId);
              }
              // Refresh sentiment arc after generation (may have been updated by post-hooks)
              void refreshSentimentArc();
              // Replace streamed text with polished version when available
              if (event.polished_text) {
                fullText = event.polished_text;
                if (editEl) editEl.value = fullText;
                if (previewEl) {
                  updateStoryMarkdownPreview(
                    "storyManuscriptPreview",
                    fullText,
                    $("storyAuthorView")?.checked ?? true
                  );
                }
              }
            } else if (event.type === "error") {
              throw new Error(event.message || "stream error");
            }
          } catch (parseErr) {
            // SSE parsing error — skip malformed events
          }
        }
      }

      storyMetaToForm();
      state.storyActiveChapterId = cid;
      for (const selId of [
        "storyBeatChapterSelect",
        "storyMsChapterSelect",
        "storyWriteChapterSelect",
        "storyChatChapterSelect",
      ]) {
        const el = $(selId);
        if (el) el.value = cid;
      }
      if ($("storyMsChapterSelect")) $("storyMsChapterSelect").value = cid;
      setDirty(false);
      const polishMsg = polishRounds > 0 ? `，已润色 ${polishRounds} 轮` : "";
      toast(`文稿已生成（约 ${fullText.length} 字${polishMsg}）`);
      if (opts.navigate !== false) switchView("storyChapter");
    } else {
      // ── Non-streaming path (fallback) ──
      const res = await api(`/api/worlds/${state.world.meta.id}/story/generate/manuscript`, {
        method: "POST",
        body: JSON.stringify(requestBody),
      });
      state.world = res.world;
      storyMetaToForm();
      state.storyActiveChapterId = cid;
      for (const selId of [
        "storyBeatChapterSelect",
        "storyMsChapterSelect",
        "storyWriteChapterSelect",
        "storyChatChapterSelect",
      ]) {
        const el = $(selId);
        if (el) el.value = cid;
      }
      if ($("storyMsChapterSelect")) $("storyMsChapterSelect").value = cid;
      if ($("storyManuscriptEdit")) $("storyManuscriptEdit").value = res.reply || "";
      updateStoryMarkdownPreview(
        "storyManuscriptPreview",
        res.reply || "",
        $("storyAuthorView")?.checked ?? true
      );
      setDirty(false);
      const pRounds = res.polish_rounds || 0;
      const pMsg = pRounds > 0 ? `，已润色 ${pRounds} 轮` : "";
      toast(`文稿已生成（约 ${res.reply?.length ?? 0} 字${pMsg}）`);
      if (res.hook_errors && res.hook_errors.length > 0) {
        for (const err of res.hook_errors) {
          toast(`⚠️ ${err}`);
        }
      }
      if (res.timing_breakdown && Array.isArray(res.timing_breakdown)) {
        const timingContainerId = useChat ? "timingBreakdownChat" : "timingBreakdownWrite";
        showTimingBreakdown(res.timing_breakdown, timingContainerId);
      }
      // Refresh sentiment arc after generation
      void refreshSentimentArc();
      if (opts.navigate !== false) switchView("storyChapter");
    }
  } catch (e) {
    toast("生成失败：" + e.message);
  } finally {
    endStoryGeneration({ token: genToken });
  }
}

async function applyStoryMdBlock(block) {
  if (!state.world?.meta?.id || !block?.content) return;
  const wid = state.world.meta.id;
  if (block.kind === "macro") {
    await api(`/api/worlds/${wid}/story/macro-outline`, {
      method: "PUT",
      body: JSON.stringify({ content: block.content }),
    });
    if ($("storyMacroEdit")) $("storyMacroEdit").value = block.content;
    updateStoryMarkdownPreview("storyMacroPreview", block.content, true);
    switchView("storyOutline");
    setStoryOutlineSub("macro");
    toast("已写入粗纲");
    return;
  }
  const cid = block.chapterId;
  if (!cid) return toast("代码块缺少章节 id");
  if (block.kind === "beat") {
    const beatRes = await api(`/api/worlds/${wid}/story/chapters/${encodeURIComponent(cid)}/beat`, {
      method: "PUT",
      body: JSON.stringify({ content: block.content }),
    });
    if (beatRes.chapter && state.world?.story?.chapters) {
      const idx = state.world.story.chapters.findIndex((c) => c.id === cid);
      if (idx >= 0) state.world.story.chapters[idx] = beatRes.chapter;
      refreshStoryChapterSelects();
    }
    state.storyActiveChapterId = cid;
    if ($("storyBeatChapterSelect")) $("storyBeatChapterSelect").value = cid;
    if ($("storyBeatEdit")) $("storyBeatEdit").value = block.content;
    updateStoryMarkdownPreview("storyBeatPreview", block.content, true);
    switchView("storyOutline");
    setStoryOutlineSub("beats");
    renderStoryChapterNav(cid);
    toast("已写入细纲");
    return;
  }
  if (block.kind === "manuscript") {
    const res = await api(`/api/worlds/${wid}/story/chapters/${encodeURIComponent(cid)}/manuscript`, {
      method: "PUT",
      body: JSON.stringify({ content: block.content }),
    });
    state.storyActiveChapterId = cid;
    if ($("storyMsChapterSelect")) $("storyMsChapterSelect").value = cid;
    if ($("storyManuscriptEdit")) $("storyManuscriptEdit").value = block.content;
    updateStoryMarkdownPreview(
      "storyManuscriptPreview",
      block.content,
      $("storyAuthorView")?.checked ?? true
    );
    await refreshStoryPanel();
    switchView("storyChapter");
    toast(`已写入文稿（约 ${res.word_count ?? 0} 字）`);
  }
}

function fillStoryChatPromptTemplate(text, opts = {}) {
  const inp = $("storyChatInput");
  if (!inp) return;
  const cur = (inp.value || "").trim();
  if (opts.mode === "append" && cur) inp.value = `${cur}\n\n${text}`;
  else inp.value = text;
  inp.focus();
}

function renderStoryMessages() {
  const box = $("storyMessages");
  if (!box) return;
  box.innerHTML = "";
  for (let mi = 0; mi < state.storyMessages.length; mi++) {
    const m = state.storyMessages[mi];
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    const roleIc = m.role === "user" ? "person" : "smart_toy";
    let extra = "";
    if (m.role === "assistant") {
      const blocks = parseStoryMdBlocks(m.content);
      if (blocks.length) {
        extra =
          '<div class="story-md-apply-row">' +
          blocks
            .map((b, bi) => {
              const lab =
                b.kind === "macro"
                  ? "写入粗纲"
                  : b.kind === "beat"
                    ? `写入细纲 · ${escapeHtml(b.chapterId)}`
                    : `写入文稿 · ${escapeHtml(b.chapterId)}`;
              return `<button type="button" class="ghost tiny story-md-apply" data-msg-index="${mi}" data-block-index="${bi}">${lab}</button>`;
            })
            .join("") +
          "</div>";
      }
    }
    const body =
      m.role === "assistant"
        ? renderAssistantMarkdownHtml(m.content)
        : escapeHtml(m.content).replaceAll("\n", "<br/>");
    const bodyClass =
      m.role === "assistant" ? "msg-body msg-body--assistant msg-body--md" : "msg-body msg-body--user";
    div.innerHTML = `<div class="role"><span class="ms role-ic" aria-hidden="true">${roleIc}</span>${m.role}</div><div class="${bodyClass}">${body}</div>${extra}`;
    div.innerHTML = div.innerHTML.replace('<div class="role"', '<div class="role"');
    box.appendChild(div);
  }
  box.querySelectorAll(".story-md-apply").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mi = parseInt(btn.dataset.msgIndex ?? "", 10);
      const bi = parseInt(btn.dataset.blockIndex ?? "", 10);
      const msg = state.storyMessages[mi];
      if (!msg) return;
      const blocks = parseStoryMdBlocks(msg.content);
      const block = blocks[bi];
      if (block) void applyStoryMdBlock(block);
    });
  });
  box.scrollTop = box.scrollHeight;
}

function newStoryForeshadowId() {
  return `fs_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function parseStoryForeshadowingFromForm() {
  try {
    const raw = JSON.parse($("storyForeshadowJson")?.value || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return null;
  }
}

function syncStoryForeshadowJson(items) {
  const list = Array.isArray(items) ? items : [];
  if ($("storyForeshadowJson")) $("storyForeshadowJson").value = JSON.stringify(list, null, 2);
  if (state.world?.story) state.world.story.foreshadowing = list;
}

function chapterIndexMap(chapters) {
  const map = new Map();
  chapters.forEach((c, i) => {
    if (c?.id) map.set(String(c.id), i);
  });
  return map;
}

function storyForeshadowChapterSelectHtml(field, index, selectedId, chapters) {
  let html = `<select data-fs-field="${field}" data-fs-index="${index}"><option value="">（未指定）</option>`;
  for (const c of chapters) {
    const id = String(c.id ?? "").trim();
    if (!id) continue;
    html += `<option value="${escapeAttr(id)}"${id === selectedId ? " selected" : ""}>${escapeHtml(
      String(c.order)
    )}. ${escapeHtml(c.title || id)}</option>`;
  }
  return html + "</select>";
}

let _foreshadowFilter = { status: "", chapter: "" };

function renderStoryForeshadowTimeline(items) {
  const host = $("storyForeshadowTimeline");
  const listEl = $("storyForeshadowList");
  if (!host || !listEl) return;
  const chapters = sortedStoryChapters();
  const rawList = Array.isArray(items) ? items : [];

  // Apply filters
  const fStatus = _foreshadowFilter.status;
  const fChapter = _foreshadowFilter.chapter;
  const list = rawList.filter(fs => {
    if (fStatus && String(fs.status || "open") !== fStatus) return false;
    if (fChapter && String(fs.planted_chapter_id || "") !== fChapter && String(fs.payoff_chapter_id || "") !== fChapter) return false;
    return true;
  });

  // Update chapter filter dropdown
  const chFilter = $("storyFsChapterFilter");
  if (chFilter) {
    const curVal = chFilter.value;
    chFilter.innerHTML = '<option value="">全部章节</option>' +
      chapters.map(c => `<option value="${escapeAttr(String(c.id))}"${String(c.id) === curVal ? " selected" : ""}>${escapeHtml(String(c.order))}. ${escapeHtml((c.title || c.id).slice(0, 16))}</option>`).join("");
  }
  const clearBtn = $("btnStoryFsClearFilter");
  if (clearBtn) clearBtn.style.display = (fStatus || fChapter) ? "" : "none";

  const idxMap = chapterIndexMap(chapters);
  const cols = Math.max(chapters.length, 1);

  if (!chapters.length) {
    host.innerHTML =
      '<div class="story-fs-grid story-fs-grid--empty">请先新建章节，再沿章节轴编排伏笔。</div>';
  } else {
    let grid = `<div class="story-fs-grid" style="grid-template-columns: minmax(72px, 0.9fr) repeat(${cols}, minmax(48px, 1fr))">`;
    grid += '<div class="story-fs-corner">伏笔</div>';
    for (const ch of chapters) {
      const t = String(ch.title || ch.id).trim();
      grid += `<div class="story-fs-ch" title="${escapeAttr(t)}">${escapeHtml(t.slice(0, 8) || ch.id)}</div>`;
    }
    if (!list.length) {
      grid +=
        '<div class="story-fs-grid story-fs-grid--empty" style="grid-column: 1 / -1">暂无伏笔，点击「+ 添加伏笔」。</div>';
    } else {
      for (const fs of list) {
        const label = String(fs.label || fs.id || "未命名").trim();
        const planted = String(fs.planted_chapter_id || "").trim();
        const payoff = String(fs.payoff_chapter_id || "").trim();
        const pi = planted && idxMap.has(planted) ? idxMap.get(planted) : -1;
        const pj = payoff && idxMap.has(payoff) ? idxMap.get(payoff) : -1;
        const status = String(fs.status || "open");
        const barClass =
          pi < 0 && pj < 0
            ? "story-fs-bar--orphan"
            : status === "resolved"
              ? "story-fs-bar--status-resolved"
              : status === "partial"
                ? "story-fs-bar--status-partial"
                : "";
        grid += `<div class="story-fs-row-label" title="${escapeAttr(label)}">${escapeHtml(label)}</div>`;
        for (let c = 0; c < cols; c++) {
          let inner = "";
          if (pi >= 0 || pj >= 0) {
            const lo = pi >= 0 && pj >= 0 ? Math.min(pi, pj) : pi >= 0 ? pi : pj;
            const hi = pi >= 0 && pj >= 0 ? Math.max(pi, pj) : lo;
            if (c >= lo && c <= hi) inner = `<span class="story-fs-bar ${barClass}"></span>`;
          }
          grid += `<div class="story-fs-track">${inner}</div>`;
        }
      }
    }
    grid += "</div>";
    host.innerHTML = grid;
  }

  const statusOpts = [
    ["open", "未回收"],
    ["partial", "部分揭晓"],
    ["resolved", "已回收"],
  ];
  if (!list.length) {
    listEl.innerHTML = '<p class="muted tiny">暂无伏笔条目。</p>';
    return;
  }
  listEl.innerHTML = list
    .map((fs, i) => {
      const id = String(fs.id || newStoryForeshadowId());
      const planted = String(fs.planted_chapter_id || "");
      const payoff = String(fs.payoff_chapter_id || "");
      const status = String(fs.status || "open");
      const opts = statusOpts
        .map(([v, lab]) => `<option value="${v}"${v === status ? " selected" : ""}>${lab}</option>`)
        .join("");
      return `<article class="story-fs-card" data-fs-index="${i}">
        <div class="story-fs-card-head">
          <input type="text" data-fs-field="label" data-fs-index="${i}" value="${escapeAttr(
            (fs.label ?? "").toString()
          )}" placeholder="伏笔名称" autocomplete="off" />
          <label class="muted tiny"><input type="checkbox" data-fs-field="reader_known" data-fs-index="${i}"${
            fs.reader_known ? " checked" : ""
          } /> 读者已知</label>
          <button type="button" class="ghost tiny" data-fs-remove="${i}">删除</button>
        </div>
        <div class="story-fs-card-grid">
          <label>埋设章节 ${storyForeshadowChapterSelectHtml("planted_chapter_id", i, planted, chapters)}</label>
          <label>回收章节 ${storyForeshadowChapterSelectHtml("payoff_chapter_id", i, payoff, chapters)}</label>
          <label>状态 <select data-fs-field="status" data-fs-index="${i}">${opts}</select></label>
        </div>
        <label class="muted tiny">备注</label>
        <textarea rows="2" data-fs-field="notes" data-fs-index="${i}" spellcheck="true">${escapeHtml(
          (fs.notes ?? "").toString()
        )}</textarea>
        <input type="hidden" data-fs-field="id" data-fs-index="${i}" value="${escapeAttr(id)}" />
      </article>`;
    })
    .join("");
}

function collectStoryForeshadowingFromDom() {
  const cards = document.querySelectorAll("#storyForeshadowList .story-fs-card");
  const out = [];
  cards.forEach((card) => {
    const i = card.dataset.fsIndex;
    const get = (field) => {
      const el = card.querySelector(`[data-fs-field="${field}"][data-fs-index="${i}"]`);
      if (!el) return "";
      if (el.type === "checkbox") return el.checked;
      return el.value;
    };
    out.push({
      id: String(get("id") || newStoryForeshadowId()).trim(),
      label: String(get("label") || "").trim(),
      planted_chapter_id: String(get("planted_chapter_id") || "").trim(),
      payoff_chapter_id: String(get("payoff_chapter_id") || "").trim(),
      reader_known: !!get("reader_known"),
      status: get("status") || "open",
      notes: String(get("notes") || "").trim(),
    });
  });
  return out;
}

let _storyFsTimer;
function scheduleStoryForeshadowSync() {
  clearTimeout(_storyFsTimer);
  _storyFsTimer = setTimeout(() => {
    const items = collectStoryForeshadowingFromDom();
    syncStoryForeshadowJson(items);
    renderStoryForeshadowTimeline(items);
    updateStoryWbStats();
    setDirty(true);
  }, 220);
}

function scheduleStoryForeshadowFromJson() {
  clearTimeout(_storyFsTimer);
  _storyFsTimer = setTimeout(() => {
    const items = parseStoryForeshadowingFromForm();
    if (items === null) return;
    renderStoryForeshadowTimeline(items);
    if (state.world?.story) state.world.story.foreshadowing = items;
    updateStoryWbStats();
  }, 280);
}

function updateStoryWbStats() {
  const chapters = sortedStoryChapters();
  const fs = parseStoryForeshadowingFromForm() ?? state.world?.story?.foreshadowing ?? [];
  const open = (Array.isArray(fs) ? fs : []).filter((x) => (x.status || "open") !== "resolved").length;
  const unit = state.storyUnitLabel || "章";
  const text = `${chapters.length} 个${unit} · ${Array.isArray(fs) ? fs.length : 0} 条伏笔（${open} 条未回收）`;
  for (const id of ["storyWbStats", "storyChatWbStats"]) {
    const el = $(id);
    if (el) el.textContent = text;
  }
}

function renderChapterStatusList() {
  const host = $("storyChapterStatusList");
  if (!host) return;
  const chapters = sortedStoryChapters();
  if (!chapters.length) {
    host.innerHTML = "";
    return;
  }
  const STATUS_OPTS = [
    ["planned", "规划中"], ["outline", "大纲"], ["drafting", "草稿"],
    ["revising", "修订中"], ["locked", "已锁定"], ["done", "已完成"], ["archived", "归档"],
  ];
  const DOT_COLORS = { planned: "#94a3b8", outline: "#a78bfa", drafting: "#f59e0b", revising: "#8b5cf6", locked: "#10b981", done: "#22c55e", archived: "#9ca3af" };
  host.innerHTML = `<div class="story-ch-status-list-head">
    <span class="ms" aria-hidden="true">checklist</span>章节状态
    <span class="muted tiny">${chapters.length} 章</span>
  </div>` +
    chapters.map(c => {
      const opts = STATUS_OPTS.map(([v, lab]) => `<option value="${v}"${c.status === v ? " selected" : ""}>${lab}</option>`).join("");
      const actual = c.word_count || 0;
      const target = c.target_word_count || 0;
      const wcDisplay = target > 0
        ? `<span class="story-ch-status-wc muted tiny">${actual.toLocaleString()} / <strong>${target.toLocaleString()}</strong> 字</span>`
        : `<span class="story-ch-status-wc muted tiny">${actual.toLocaleString()} 字</span>`;
      return `<div class="story-ch-status-row">
        <span class="story-ch-status-dot" style="background:${DOT_COLORS[c.status] || '#94a3b8'}" title="${c.status}"></span>
        <span class="story-ch-status-order">${c.order}.</span>
        <span class="story-ch-status-title">${escapeHtml(c.title || c.id)}</span>
        ${wcDisplay}
        <input type="number" class="story-ch-target-wc" data-chapter-id="${escapeAttr(c.id)}" value="${target || ''}" placeholder="目标" min="0" step="500" style="width:5em" title="目标字数（0=不限制）" aria-label="目标字数" />
        <select class="story-ch-status-sel" data-chapter-id="${escapeAttr(c.id)}" aria-label="状态">${opts}</select>
      </div>`;
    }).join("");
  // Wire up change events
  host.querySelectorAll(".story-ch-status-sel").forEach(sel => {
    sel.addEventListener("change", async () => {
      const cid = sel.dataset.chapterId;
      const newStatus = sel.value;
      try {
        const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/batch`, {
          method: "POST",
          body: JSON.stringify({ action: "status", chapter_ids: [cid], new_status: newStatus }),
        });
        state.world = res.world;
        renderStoryChapterNav();
        renderChapterStatusList();
        setDirty(false);
      } catch (e) { toast("更新失败：" + e.message); }
    });
  });
  // Wire up target word count inputs
  host.querySelectorAll(".story-ch-target-wc").forEach(inp => {
    inp.addEventListener("change", async () => {
      const cid = inp.dataset.chapterId;
      const target = Math.max(0, parseInt(inp.value, 10) || 0);
      const ch = (state.world?.story?.chapters || []).find(c => c.id === cid);
      if (!ch) return;
      ch.target_word_count = target;
      setDirty(true);
      renderChapterStatusList();
      renderStoryChapterNav();
    });
  });
}

function renderStoryChapterNav(activeId) {
  const chapters = sortedStoryChapters();
  const unit = state.storyUnitLabel || "章";
  for (const labelId of ["storyAsideUnitLabel", "storyChatAsideUnitLabel"]) {
    const el = $(labelId);
    if (el) el.textContent = unit;
  }
  if ($("storyChatUnitLine")) $("storyChatUnitLine").textContent = `情节单元：${unit}`;
  const aid = activeId || state.storyActiveChapterId || chapters[0]?.id || "";
  if (aid) state.storyActiveChapterId = aid;

  const STATUS_DOTS = {
    planned: " story-ch-status-dot--planned", outline: " story-ch-status-dot--outline",
    drafting: " story-ch-status-dot--drafting", revising: " story-ch-status-dot--revising",
    locked: " story-ch-status-dot--locked", done: " story-ch-status-dot--done",
    archived: " story-ch-status-dot--archived",
  };
  const STATUS_LABELS = { planned: "规划中", outline: "大纲", drafting: "草稿", revising: "修订中", locked: "已锁定", done: "已完成", archived: "归档" };
  const emptyHtml = `<p class="muted tiny">尚无${unit}，点 + 新建</p>`;
  const listHtml = chapters.length
    ? chapters
        .map((c) => {
          const id = String(c.id);
          const active = id === aid ? " active" : "";
          const title = (c.title || "").trim() || id;
          const sl = STATUS_LABELS[c.status] || c.status || STATUS_LABELS.planned;
          const dotClass = STATUS_DOTS[c.status] || STATUS_DOTS.planned;
          const actual = c.word_count || 0;
          const target = c.target_word_count || 0;
          const wc = target > 0
            ? ` <span class="story-ch-status-label">${actual.toLocaleString()}/${target.toLocaleString()} 字</span>`
            : actual > 0 ? ` <span class="story-ch-status-label">${actual.toLocaleString()} 字</span>` : "";
          const summaryDot = c.summary_card ? ' <span class="story-ch-status-dot" style="background:#0d9488" title="有摘要卡片"></span>' : "";
          const cr = c.consistency_report;
          const crBadge = cr
            ? ` <span class="story-ch-consistency-badge" style="background:${cr.verdict === 'clean' ? '#16a34a' : cr.verdict === 'minor_issues' ? '#eab308' : '#dc2626'}" title="审校：${cr.total_issues || 0} 个问题 · ${cr.verdict}">${cr.total_issues || 0}</span>`
            : "";
          return `<button type="button" class="story-ch-nav-btn${active}" data-story-chapter-id="${escapeAttr(id)}" title="${escapeAttr(title)} · ${sl}">
        <input type="checkbox" class="story-ch-cb" data-cb-id="${escapeAttr(id)}" title="选择" aria-label="选择${escapeAttr(title)}" />
        <span class="story-ch-order">${escapeHtml(String(c.order))}</span><span class="story-ch-status-dot${dotClass}" title="${sl}"></span>${summaryDot}${crBadge}${escapeHtml(title)}${wc}
      </button>`;
        })
        .join("")
    : emptyHtml;
  let anyNav = false;
  for (const navId of STORY_CHAPTER_NAV_IDS) {
    const nav = $(navId);
    if (!nav) continue;
    anyNav = true;
    nav.innerHTML = listHtml;
  }
  if (!anyNav) return;
  // Batch bar
  refreshBatchBar();
  const sel = $("storyChatChapterSelect");
  if (sel && aid && [...sel.options].some((o) => o.value === aid)) sel.value = aid;
  refreshStoryChatContextLine();
  if (state.storyGen) applyStoryGenerationUi(state.storyGen);
}

// ── P2: Batch operations ──────────────────────────────────────────

function getSelectedChapterIds() {
  const ids = [];
  for (const navId of STORY_CHAPTER_NAV_IDS) {
    const nav = $(navId);
    if (!nav) continue;
    nav.querySelectorAll(".story-ch-cb:checked").forEach(cb => {
      ids.push(cb.dataset.cbId);
    });
  }
  return [...new Set(ids)];
}

function refreshBatchBar() {
  const ids = getSelectedChapterIds();
  const bars = document.querySelectorAll(".story-batch-bar");
  bars.forEach(bar => {
    bar.classList.toggle("story-batch-bar--show", ids.length > 0);
    const countEl = bar.querySelector(".story-batch-count");
    if (countEl) countEl.textContent = `已选 ${ids.length} 章`;
  });
  // Highlight selected nav buttons
  for (const navId of STORY_CHAPTER_NAV_IDS) {
    const nav = $(navId);
    if (!nav) continue;
    nav.querySelectorAll(".story-ch-nav-btn").forEach(btn => {
      const cb = btn.querySelector(".story-ch-cb");
      btn.classList.toggle("story-ch-nav-btn--sel", cb && cb.checked);
    });
  }
}

async function batchSetStatus(newStatus) {
  const ids = getSelectedChapterIds();
  if (!ids.length) return;
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/batch`, {
      method: "POST",
      body: JSON.stringify({ action: "status", chapter_ids: ids, new_status: newStatus }),
    });
    state.world = res.world;
    storyMetaToForm();
    renderStoryChapterNav();
    toast(`已将 ${ids.length} 章设为「${newStatus}」`);
  } catch (e) { toast("批量状态更新失败：" + e.message); }
}

async function batchDeleteChapters() {
  const ids = getSelectedChapterIds();
  if (!ids.length) return;
  if (!confirm(`确定删除选中的 ${ids.length} 个章节？此操作不可撤销。`)) return;
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/batch`, {
      method: "POST",
      body: JSON.stringify({ action: "delete", chapter_ids: ids }),
    });
    state.world = res.world;
    // Clear active chapter if it was deleted
    if (ids.includes(state.storyActiveChapterId)) {
      state.storyActiveChapterId = "";
    }
    storyMetaToForm();
    renderStoryChapterNav();
    toast(`已删除 ${ids.length} 章`);
  } catch (e) { toast("批量删除失败：" + e.message); }
}

async function batchRenumber() {
  const ids = getSelectedChapterIds();
  if (!ids.length) return;
  const start = parseInt(prompt("起始编号：", "1") || "", 10);
  if (isNaN(start) || start < 1) return;
  const chapters = sortedStoryChapters();
  const orders = ids.map((id, i) => ({ id, order: start + i }));
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/batch`, {
      method: "POST",
      body: JSON.stringify({ action: "reorder", orders }),
    });
    state.world = res.world;
    storyMetaToForm();
    renderStoryChapterNav();
    toast(`已重编号 ${ids.length} 章（从 ${start} 开始）`);
  } catch (e) { toast("重编号失败：" + e.message); }
}

async function selectStoryChapter(chapterId, subView) {
  if (!chapterId) return;
  state.storyActiveChapterId = chapterId;
  renderStoryChapterNav(chapterId);
  for (const selId of [
    "storyBeatChapterSelect",
    "storyMsChapterSelect",
    "storyWriteChapterSelect",
    "storyChatChapterSelect",
    "storyPolishChapterSelect",
    "storyAuditChapterSelect",
  ]) {
    const el = $(selId);
    if (el) el.value = chapterId;
  }
  refreshStoryChatContextLine();
  refreshStoryChatBeatTitleHint(chapterId);
  refreshStoryContextPanel();
  if (state.activeView === "storyChat" && !subView) return;
  if (subView === "beats") {
    await switchView("storyOutline");
    setStoryOutlineSub("beats");
  } else if (subView === "chapter") {
    await switchView("storyChapter");
    void loadStoryManuscript();
  } else if (subView === "write") {
    await switchView("storyWrite");
  } else if (subView === "audit") {
    setStorySubView("audit");
    void refreshSentimentArc();
    void renderConsistencyReport(chapterId);
    void loadPolishedManuscript(chapterId);
  } else if (subView) setStorySubView(subView);
  else if (state.storySubView === "outline" && state.storyOutlineSub === "beats") void loadStoryBeat();
  else if (state.storySubView === "chapter") void loadStoryManuscript();
  else if (state.storySubView === "audit") {
    void refreshSentimentArc();
    void renderConsistencyReport(chapterId);
    void loadPolishedManuscript(chapterId);
  }
}

function refreshFilesView() {
  const dir = $("filesDirHint");
  if (dir)
    dir.textContent = state.world ? `worlds/${state.world.meta.id}/` : "—";
  const dump = $("filesDump");
  if (dump) dump.textContent = state.world ? JSON.stringify(state.world, null, 2) : "（无）";
}

function refreshSearchView() {
  const wid = state.world?.meta?.id ?? null;
  if (wid !== _searchPanelWorldId) {
    _searchPanelWorldId = wid;
    const inp = $("worldSearchQ");
    if (inp) inp.value = "";
    const sr = $("worldSearchResults");
    if (sr) {
      sr.innerHTML = "";
      sr.classList.add("muted");
    }
  }
  const hint = $("searchPathHint");
  if (hint) {
    hint.textContent = state.world
      ? `检索范围：worlds/${state.world.meta.id}/world.json 与 world.md（磁盘已保存内容；未保存的编辑请先保存世界）`
      : "请先选择或新建世界。";
  }
}

async function runReferenceLintFlow(opts = {}) {
  const quietToast = Boolean(opts.quietToast);
  const skipClearFixPanel = Boolean(opts.skipClearFixPanel);
  const out = $("referenceLintOut");
  if (!skipClearFixPanel) {
    const fixOut = $("referenceLintFixOut");
    if (fixOut) fixOut.innerHTML = "";
  }
  if (!state.world?.meta?.id) {
    if (out) out.innerHTML = "";
    return;
  }
  if (out) {
    out.classList.add("muted");
    out.innerHTML = "<p>校验中…</p>";
  }
  try {
    const data = await api(`/api/worlds/${state.world.meta.id}/lint-references`);
    const warns = data.warnings || [];
    if (out) {
      if (!warns.length) {
        out.innerHTML = "<p>未发现引用问题。</p>";
        out.classList.add("muted");
      } else {
        out.classList.remove("muted");
        out.innerHTML =
          `<ul>${warns.map((w) => `<li>${escapeHtml(String(w))}</li>`).join("")}</ul>` +
          (data.truncated ? '<p class="muted tiny" style="margin:8px 0 0">（已达单条报告上限）</p>' : "");
      }
    }
    if (!quietToast) {
      toast(warns.length ? `引用校验：${warns.length} 条提示` : "引用校验：未发现引用问题");
    } else if (warns.length) {
      toast(`保存完成；引用校验有 ${warns.length} 条提示（见「数据」→「引用一致性」）`);
    }
  } catch (e) {
    const msg = e?.message || String(e);
    if (out) {
      out.classList.add("muted");
      out.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    if (!quietToast) toast("引用校验失败：" + msg);
  }
}

function formatReferenceLintFollowupHtml(lint) {
  if (!lint || lint.ok) return "";
  const w = lint.warnings || [];
  if (!w.length) return "";
  return (
    '<p class="muted tiny" style="margin:8px 0 4px">自动修复后仍可能存在的提示（需人工）：</p>' +
    `<ul style="margin:0;padding-left:1.1em">${w.map((x) => `<li>${escapeHtml(String(x))}</li>`).join("")}</ul>`
  );
}

async function runReferenceFixPreview() {
  const fixOut = $("referenceLintFixOut");
  if (!state.world?.meta?.id) {
    if (fixOut) fixOut.innerHTML = "";
    return toast("请先选择世界");
  }
  if (fixOut) {
    fixOut.classList.add("muted");
    fixOut.innerHTML = "<p>生成预览…</p>";
  }
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/fix-references`, {
      method: "POST",
      body: JSON.stringify({ dry_run: true }),
    });
    const lines = res.would_apply || [];
    const cnt = typeof res.apply_count === "number" ? res.apply_count : lines.length;
    if (fixOut) {
      const noSteps = !lines.length;
      fixOut.classList.toggle("muted", noSteps && res.lint_after && res.lint_after.ok);
      const head = noSteps
        ? `<p class="tiny" style="margin:0 0 6px">预览：<strong>0</strong> 步变更（当前规则下无需自动修复）。</p>`
        : `<p class="tiny" style="margin:0 0 6px">预览：<strong>${cnt}</strong> 步（未写盘），应用后将执行：</p><ul style="margin:0;padding-left:1.1em">${lines
            .map((l) => `<li>${escapeHtml(String(l))}</li>`)
            .join("")}</ul>`;
      fixOut.innerHTML = head + formatReferenceLintFollowupHtml(res.lint_after);
    }
    toast(
      lines.length ? `预览：${lines.length} 步自动修复（未写盘）` : "预览：当前无需自动修复项"
    );
  } catch (e) {
    const msg = e?.message || String(e);
    if (fixOut) {
      fixOut.classList.add("muted");
      fixOut.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    toast("预览自动修复失败：" + msg);
  }
}

async function runReferenceFixApply() {
  const fixOut = $("referenceLintFixOut");
  if (!state.world?.meta?.id) {
    if (fixOut) fixOut.innerHTML = "";
    return toast("请先选择世界");
  }
  if (
    !confirm(
      "将按预览相同规则修改磁盘上的 world.json 并升级版本保存；表单中未保存的更改将丢失。是否继续？"
    )
  ) {
    return;
  }
  if (fixOut) {
    fixOut.classList.add("muted");
    fixOut.innerHTML = "<p>正在应用…</p>";
  }
  const id = state.world.meta.id;
  try {
    const res = await api(`/api/worlds/${id}/fix-references`, {
      method: "POST",
      body: JSON.stringify({ dry_run: false }),
    });
    if (!res.saved) {
      if (fixOut) {
        fixOut.classList.add("muted");
        fixOut.innerHTML =
          "<p>未写盘：当前磁盘 world 在本规则下无需修改（或已与修复结果一致）。可先运行校验查看剩余提示。</p>";
      }
      toast("引用自动修复：无需写盘");
      return;
    }
    await loadWorld(id);
    const applied = res.applied || [];
    if (fixOut) {
      fixOut.classList.remove("muted");
      fixOut.innerHTML =
        `<p class="tiny" style="margin:0 0 6px">已应用 <strong>${applied.length}</strong> 步并落盘：</p><ul style="margin:0;padding-left:1.1em">${applied
          .map((l) => `<li>${escapeHtml(String(l))}</li>`)
          .join("")}</ul>` + formatReferenceLintFollowupHtml(res.lint);
    }
    await runReferenceLintFlow({ quietToast: true, skipClearFixPanel: true });
    toast(`引用自动修复已落盘（${applied.length} 步）`);
  } catch (e) {
    const msg = e?.message || String(e);
    if (fixOut) {
      fixOut.classList.add("muted");
      fixOut.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    toast("应用自动修复失败：" + msg);
  }
}

function renderWorldSearchResults(data) {
  const box = $("worldSearchResults");
  if (!box) return;
  const j = data.json_hits || [];
  const m = data.markdown_hits || [];
  const tj = data.total_json ?? j.length;
  const tm = data.total_md ?? m.length;
  const parts = [];
  parts.push(
    `<p class="muted tiny" style="margin:0 0 8px">JSON 命中 <strong>${tj}</strong> · world.md 行 <strong>${tm}</strong></p>`
  );
  if (j.length) {
    parts.push('<div class="search-hit-group"><strong class="search-hit-group-title">world.json 路径</strong><ul class="search-hit-list">');
    for (const h of j) {
      const sn = escapeHtml(h.snippet || "").replace(/\n/g, "<br/>");
      parts.push(
        `<li class="search-hit-li"><code class="search-path">${escapeHtml(h.path || "")}</code><div class="search-snippet">${sn}</div></li>`
      );
    }
    parts.push("</ul></div>");
  }
  if (m.length) {
    parts.push('<div class="search-hit-group"><strong class="search-hit-group-title">world.md</strong><ul class="search-hit-list">');
    for (const h of m) {
      parts.push(
        `<li class="search-hit-li"><span class="search-line-no">L${h.line}</span><div class="search-snippet">${escapeHtml(h.text || "")}</div></li>`
      );
    }
    parts.push("</ul></div>");
  }
  if (!j.length && !m.length) {
    parts.push('<p class="muted" style="margin:0">无命中（可换关键词或先保存并导出 world.md）。</p>');
  }
  box.classList.remove("muted");
  box.innerHTML = parts.join("");
}

async function runWorldSearchFlow() {
  if (!state.world) return toast("请先选择世界");
  const inp = $("worldSearchQ");
  const q = (inp?.value || "").trim();
  if (!q) return toast("请输入关键词");
  const box = $("worldSearchResults");
  if (box) {
    box.classList.add("muted");
    box.innerHTML = "<p>搜索中…</p>";
  }
  try {
    const u = new URLSearchParams({ q });
    const data = await api(`/api/worlds/${state.world.meta.id}/search?${u.toString()}`);
    renderWorldSearchResults(data);
    toast(`命中 JSON ${data.total_json ?? 0} · MD ${data.total_md ?? 0}`);
  } catch (e) {
    const msg = e?.message || String(e);
    if (box) {
      box.classList.add("muted");
      box.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    toast("搜索失败：" + msg);
  }
}

async function refreshWorldSelect(selectedId) {
  const data = await api("/api/worlds");
  const sel = $("worldSelect");
  sel.innerHTML = "";
  const raw = data.worlds || [];
  const rows = raw.map((x) =>
    typeof x === "string"
      ? { id: x, name: x }
      : { id: x?.id ?? "", name: ((x?.name ?? "") + "").trim() || x?.id || "" }
  );
  if (!rows.length) {
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "— 请先创建世界 —";
    sel.appendChild(ph);
    sel.value = "";
    updateEmptyState();
    return;
  }
  for (const { id, name } of rows) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = name && name !== id ? `${name} · ${id}` : id;
    opt.title = id;
    sel.appendChild(opt);
  }
  if (selectedId && rows.some((r) => r.id === selectedId)) sel.value = selectedId;
  else if (rows[0]) sel.value = rows[0].id;
  sel.disabled = false;
  updateEmptyState();
}

async function loadWorld(id) {
  if (!id) return;
  const data = await api(`/api/worlds/${id}`);
  const w = data.world != null ? data.world : data;
  state.world = w;
  const inc = $("includeMd");
  if (inc && typeof data.has_nonempty_world_md === "boolean") {
    inc.checked = data.has_nonempty_world_md;
  }
  const charInc = $("charIncludeMd");
  if (charInc && typeof data.has_nonempty_world_md === "boolean") {
    charInc.checked = data.has_nonempty_world_md;
  }
  worldToForm(w);
  resetStoryGenerationUi();
  setDirty(false);
  refreshContextPanel();
  refreshOutlineHeader();
  refreshFilesView();
  refreshSearchView();
  refreshWorldTabTitle();
  // If story panel is open, refresh story data for the new world
  if (state.storySubView) {
    await refreshStoryChaptersAligned();
  }
}

async function refreshFactionRelationsFromPanel() {
  if (!state.world) return toast("请先选择世界");
  const btn = $("btnRefreshFactionRelations");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    const gm = ($("genreMode")?.value || "").trim() || null;
    const res = await api(`/api/worlds/${state.world.meta.id}/refresh/faction-relations`, {
      method: "POST",
      body: JSON.stringify({ persist: true, creative_mode: gm }),
    });
    if (res.ok === false) {
      toast("派系关系修订失败：" + (res.error || "模型输出无法解析"));
      return;
    }
    state.world = res.world;
    worldToForm(res.world);
    setDirty(false);
    refreshContextPanel();
    let msg = "派系关系网络已更新并保存";
    if (res.persisted === false) {
      msg =
        (res.warnings || []).some((w) => String(w).includes("无派系实体"))
          ? "当前无派系实体，未调用模型"
          : "派系 relations 已合并（未写盘）";
    }
    if (Array.isArray(res.warnings) && res.warnings.length) {
      msg += " — " + res.warnings.slice(0, 5).join("；");
    }
    toast(msg);
  } catch (e) {
    toast("派系关系修订失败：" + (e?.message || e));
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

async function refreshCultureRelationsFromPanel() {
  if (!state.world) return toast("请先选择世界");
  const btn = $("btnRefreshCultureRelations");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    const gm = ($("genreMode")?.value || "").trim() || null;
    const res = await api(`/api/worlds/${state.world.meta.id}/refresh/culture-relations`, {
      method: "POST",
      body: JSON.stringify({ persist: true, creative_mode: gm }),
    });
    if (res.ok === false) {
      toast("文化关系修订失败：" + (res.error || "模型输出无法解析"));
      return;
    }
    state.world = res.world;
    worldToForm(res.world);
    setDirty(false);
    refreshContextPanel();
    let msg = "文化/宗教关系网络已更新并保存";
    if (res.persisted === false) {
      msg =
        (res.warnings || []).some((w) => String(w).includes("无文化"))
          ? "当前无文化/宗教实体，未调用模型"
          : "文化 relations 已合并（未写盘）";
    }
    if (Array.isArray(res.warnings) && res.warnings.length) {
      msg += " — " + res.warnings.slice(0, 5).join("；");
    }
    toast(msg);
  } catch (e) {
    toast("文化关系修订失败：" + (e?.message || e));
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

async function init() {
  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "neutral",
      fontFamily: "system-ui, 'Noto Sans SC', sans-serif",
    });
  }
  if (typeof marked !== "undefined" && typeof marked.use === "function") {
    try {
      marked.use({ gfm: true, breaks: true });
    } catch (_) {
      /* 旧版 marked 无 use 时忽略 */
    }
  }

  resetStoryGenerationUi();
  ensureWorldviewEditModeToolbars();
  setupCharRosterInlineEditors();

  // 情节工作台：子页标签栏交互
  document.querySelectorAll("[data-story-tab]").forEach((btn) => {
    btn.addEventListener("click", () => setStorySubView(btn.dataset.storyTab));
  });

  // 情节编辑器：字数统计
  ["storyMacroEdit", "storyBeatEdit", "storyManuscriptEdit"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => refreshStoryEditorWordCounts());
  });
  refreshStoryEditorWordCounts();

  try {
    const cfg = await api("/api/config");
    const chatModel = cfg.default_model;
    const syncModel = cfg.structure_sync_model ?? cfg.default_model;
    const badge = $("apiHint");
    if (cfg.has_api_key) {
      badge.textContent = chatModel;
      badge.title = `对话模型：${chatModel} | 同步模型：${syncModel}`;
    } else {
      badge.textContent = "未配置 PARATERA_API_KEY";
      badge.title = "对话 / 同步将不可用";
    }
  } catch {
    $("apiHint").textContent = "无法连接 API";
  }

  await refreshWorldSelect();
  updateEmptyState();
  if (hasWorldsInSelect()) await loadWorld($("worldSelect").value);
  else {
    state.world = null;
    refreshContextPanel();
    refreshOutlineHeader();
    refreshWorldTabTitle();
  }

  const sh = $("syncHint");
  if (sh) {
    sh.textContent =
      "默认关闭「仅当前页模块」：助手一次可同步多个板块。若开启，仅在当前导航对应模块写入（地理/生态/境界/物品/属性/文化·宗教/派系/历史/**经济**/**人物卡司** 等），其它模块输出会被丢弃。在「人物生成」或左侧「主角团 / 重要配角 / 人物关系网络 / 卡司数据」任一页开启时，scope 为 **characters**；在「经济」页开启时，scope 为 **economy**。";
  }
  updateGenreModeHint();
  updateCultureHint();

  $("btnAddRegion")?.addEventListener("click", () => {
    const cur = collectRegionsFromDom();
    cur.push({ id: uid("r"), name: "", summary: "", terrain: "", relations: [] });
    renderRegionCards(cur);
    setDirty(true);
    scheduleGeoVizRefresh();
  });
  $("btnAddFaction")?.addEventListener("click", () => {
    let cur = collectFactionsFromDom();
    if (!cur.length && state.world?.factions?.entities?.length) {
      cur = JSON.parse(JSON.stringify(state.world.factions.entities));
    }
    cur.push({
      id: uid("f"),
      name: "新派系",
      goals: "",
      territory: "",
      key_figures: [],
      relations: [],
    });
    renderFactionCards(cur);
    setDirty(true);
  });
  $("btnAddCulture")?.addEventListener("click", () => {
    let cur = collectCulturesFromDom();
    if (!cur.length && state.world?.cultures?.entities?.length) {
      cur = JSON.parse(JSON.stringify(state.world.cultures.entities));
    }
    cur.push({
      id: uid("c"),
      name: "新条目",
      kind: "culture",
      summary: "",
      tenets: "",
      practices: "",
      sacred_sites: [],
      key_figures: [],
      relations: [],
    });
    renderCultureCards(cur);
    setDirty(true);
  });
  $("btnRefreshFactionRelations")?.addEventListener("click", () =>
    void refreshFactionRelationsFromPanel()
  );
  $("btnRefreshCultureRelations")?.addEventListener("click", () =>
    void refreshCultureRelationsFromPanel()
  );
  $("regionCards")?.addEventListener("click", (ev) => {
    if (!ev.target.closest(".remove-region")) return;
    ev.target.closest(".region-card")?.remove();
    setDirty(true);
    scheduleGeoVizRefresh();
  });
  $("factionCards")?.addEventListener("click", (ev) => {
    if (!ev.target.closest(".remove-faction")) return;
    ev.target.closest(".faction-card")?.remove();
    setDirty(true);
    scheduleFactionVizRefresh();
  });
  $("cultureCards")?.addEventListener("click", (ev) => {
    if (!ev.target.closest(".remove-culture")) return;
    ev.target.closest(".culture-card")?.remove();
    setDirty(true);
    scheduleCultureVizRefresh();
  });

  document.querySelectorAll(".nav button").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  $("worldSelect").addEventListener("change", async (e) => {
    if (!e.target.value) return;
    if (state.dirty && !confirm("有未保存更改，确定切换世界？")) {
      e.target.value = state.world?.meta?.id ?? "";
      return;
    }
    await loadWorld(e.target.value);
  });

  document.querySelectorAll("[data-power-sub]").forEach((btn) => {
    btn.addEventListener("click", () => setPowerSubView(btn.dataset.powerSub));
  });
  setPowerSubView(state.powerSubView || "system");

  document.querySelectorAll("[data-geo-sub]").forEach((btn) => {
    btn.addEventListener("click", () => setGeoSubView(btn.dataset.geoSub));
  });
  setGeoSubView(state.geoSubView || "overview");

  document.querySelectorAll("[data-ecology-sub]").forEach((btn) => {
    btn.addEventListener("click", () => setEcologySubView(btn.dataset.ecologySub));
  });
  setEcologySubView(state.ecologySubView || "overview");

  $("btnSnapshotDiff")?.addEventListener("click", () => void runSnapshotDiff());
  $("btnSnapshotRollback")?.addEventListener("click", () => void runSnapshotRollback());
  $("btnSnapshotDelete")?.addEventListener("click", () => void deleteSnapshot());
  $("btnSnapshotClear")?.addEventListener("click", () => void clearSnapshots());
  $("btnReferenceLint")?.addEventListener("click", () => void runReferenceLintFlow({ quietToast: false }));
  $("btnReferenceLintFixPreview")?.addEventListener("click", () => void runReferenceFixPreview());
  $("btnReferenceLintFixApply")?.addEventListener("click", () => void runReferenceFixApply());

  $("btnNewWorld").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));
  $("btnRenameWorld")?.addEventListener("click", () =>
    renameCurrentWorldFlow().catch((e) => toast(e.message))
  );
  $("btnDeleteWorld")?.addEventListener("click", () =>
    deleteCurrentWorldFlow().catch((e) => toast(e.message))
  );
  $("btnEmptyCreate").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));

  const markDirty = () => setDirty(true);
  ["geoSummary", "geoClimate", "geoMap"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleGeoMarkdownPreviews();
    });
  });
  [
    "powerSummary",
    "powerRealmDesign",
    "powerSkillTreeDesign",
    "powerTiersJson",
    "itemSummary",
    "itemGradesJson",
    "factionSummary",
    "factionsJson",
    "cultureSummary",
    "culturesJson",
    "historySummary",
    "historyJson",
    "economySummary",
    "economyDesignNotes",
    "economyLaborNotes",
    "economyTaxationNotes",
    "economyVolatilityNotes",
    "economyCurrenciesJson",
    "economyMarketsJson",
    "economyTradeRoutesJson",
    "economyTradeGoodsJson",
    "attrSummary",
    "attrDesignNotes",
    "attrStatsJson",
    "attrTierProfilesJson",
  ].forEach((id) => $(id).addEventListener("input", markDirty));
  ["charEntitiesJson", "charRelationsJson"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleCharactersVizFromForm();
    });
  });
  ["ecologySummary", "ecologyDesignNotes"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleEcologyMarkdownPreviews();
    });
  });
  ["ecologyBiomesJson", "ecologySpeciesJson"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleEcologyVizFromForm();
    });
  });
  $("powerProfessionSummary")?.addEventListener("input", () => {
    markDirty();
    scheduleSyncProfessionFromVizToState();
  });
  $("powerProfessionDesign")?.addEventListener("input", () => {
    markDirty();
    scheduleSyncProfessionFromVizToState();
  });
  $("historyJson")?.addEventListener("input", scheduleHistoryVizFromForm);
  function scheduleAttrVizFromForm() {
    try {
      const stats = JSON.parse($("attrStatsJson")?.value || "[]");
      const tierp = JSON.parse($("attrTierProfilesJson")?.value || "[]");
      if (!state.world || !Array.isArray(stats)) return;
      const w = structuredClone(state.world);
      w.attribute_system = w.attribute_system || {};
      w.attribute_system.stats = stats;
      w.attribute_system.tier_average_profiles = Array.isArray(tierp) ? tierp : [];
      renderAttributePanel(w);
    } catch (_) {
      /* JSON 未完成输入时不刷新 */
    }
  }
  $("attrStatsJson")?.addEventListener("input", scheduleAttrVizFromForm);
  $("attrTierProfilesJson")?.addEventListener("input", scheduleAttrVizFromForm);
  $("powerTiersJson")?.addEventListener("input", () => {
    try {
      const tiers = JSON.parse($("powerTiersJson").value || "[]");
      if (!state.world || !Array.isArray(tiers)) return;
      state.world.power_system = state.world.power_system || {};
      state.world.power_system.tiers = tiers;
      state.world.power_system.profession_system = alignProfessionSystemToTiers(
        tiers,
        state.world.power_system.profession_system || {}
      );
      refreshPowerUiFromWorld(state.world);
      applyAllWorldviewEditModes();
    } catch (_) {}
  });
  $("itemGradesJson")?.addEventListener("input", scheduleItemGradesVizFromForm);
  $("view-items")?.addEventListener("input", (ev) => {
    if (!ev.target.closest?.("#vizItemGradesRoot [data-item-field]")) return;
    scheduleSyncItemGradesFromVizToStateAndJson();
  });
  $("view-powers")?.addEventListener("input", (ev) => {
    if (ev.target.closest?.("#vizPowerProfessionModules [data-profession-part]")) {
      scheduleSyncProfessionFromVizToState();
      return;
    }
    if (
      !ev.target.closest?.(
        "#vizPowerSystemModules [data-power-field], #vizPowerSkillTreeModules [data-power-tree-part]"
      )
    )
      return;
    scheduleSyncPowerTiersFromVizToStateAndJson();
  });
  $("view-history")?.addEventListener("input", (ev) => {
    if (!ev.target.closest?.(".hist-tl-row--editable [data-hist-field]")) return;
    scheduleSyncHistoryEventsFromVizToStateAndJson();
  });
  $("factionSummary")?.addEventListener("input", scheduleFactionGlobalBriefPreview);

  $("genreMode")?.addEventListener("change", () => {
    if (state.world) {
      state.storyUnitLabel = storyUnitLabelForMode($("genreMode")?.value);
      if ($("storyUnitLine")) $("storyUnitLine").textContent = `情节单元：${state.storyUnitLabel}`;
    }
    markDirty();
    updateGenreModeHint();
    updateCultureHint();
  });

  $("regionCards")?.addEventListener("input", (ev) => {
    markDirty();
    const card = ev.target.closest(".region-card");
    if (card) syncRegionCardIcon(card);
    scheduleGeoVizRefresh();
    scheduleEcologyVizFromForm();
  });
  $("factionCards")?.addEventListener("input", () => {
    markDirty();
    scheduleFactionVizRefresh();
  });
  $("cultureCards")?.addEventListener("input", () => {
    markDirty();
    scheduleCultureVizRefresh();
  });
  $("culturesJson")?.addEventListener("input", () => {
    markDirty();
    scheduleCultureVizRefresh();
  });

  async function persistWorldFromForm() {
    if (!state.world) {
      toast("请先选择世界");
      return;
    }
    let body;
    try {
      body = formToWorld();
    } catch (e) {
      toast(e.message);
      return;
    }
    const saved = await api(`/api/worlds/${body.meta.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    state.world = saved;
    worldToForm(saved);
    setDirty(false);
    refreshContextPanel();
    refreshOutlineHeader();
    toast("已保存");
    void runReferenceLintFlow({ quietToast: true });
  }

  $("btnSaveWorld").addEventListener("click", () =>
    persistWorldFromForm().catch((e) => toast("保存失败：" + e.message))
  );

  $("btnQuitApp")?.addEventListener("click", async () => {
    const warn = state.dirty
      ? "有未保存更改，确定仍要退出？本地服务将停止，未保存内容将丢失。"
      : "确定退出？将停止本地服务并尝试关闭本页。";
    if (!confirm(warn)) return;
    const btn = $("btnQuitApp");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch("/api/shutdown", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!r.ok) {
        const t = await r.text();
        let detail = r.statusText;
        try {
          const j = JSON.parse(t || "{}");
          if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
          else if (t) detail = t;
        } catch {
          if (t) detail = t;
        }
        throw new Error(detail);
      }
    } catch (e) {
      if (btn) btn.disabled = false;
      toast("退出失败：" + (e?.message || e));
      return;
    }
    document.body.innerHTML = `<main class="shutdown-screen" role="status"><p class="shutdown-title">服务已停止</p><p class="shutdown-hint">可关闭本浏览器标签页；若浏览器未自动关闭窗口，请手动关闭。</p></main>`;
    requestAnimationFrame(() => {
      try {
        window.open("", "_self");
        window.close();
      } catch (_) {
        /* 用户直接打开的标签页可能不允许脚本关闭，保留占位页即可 */
      }
    });
  });

  document.addEventListener("keydown", (e) => {
    const mac =
      /Mac|iPhone|iPod|iPad/i.test(navigator.platform || "") ||
      (navigator.userAgent && navigator.userAgent.includes("Mac"));
    const mod = mac ? e.metaKey : e.ctrlKey;
    if (!mod || (e.key !== "s" && e.key !== "S")) return;
    e.preventDefault();
    void persistWorldFromForm().catch((err) => toast("保存失败：" + err.message));
  });

  $("btnCopyWorldId")?.addEventListener("click", async () => {
    if (!state.world?.meta?.id) return toast("无世界");
    try {
      await navigator.clipboard.writeText(state.world.meta.id);
      toast("已复制世界 ID");
    } catch {
      toast("复制失败（浏览器可能未授权剪贴板）");
    }
  });

  $("btnExportMd").addEventListener("click", async () => {
    if (!state.world) return toast("无世界");
    await api(`/api/worlds/${state.world.meta.id}/export-md`, { method: "POST" });
    toast("已导出 world.md");
  });

  $("btnWorldSearch")?.addEventListener("click", () => void runWorldSearchFlow());
  $("worldSearchQ")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void runWorldSearchFlow();
    }
  });

  async function submitChatFromUI() {
    if (!state.world) return toast("请先选择世界");
    const text = $("chatInput").value.trim();
    if (!text) return;
    const mode = $("genreMode").value || null;
    const includeMd = $("includeMd").checked;
    const chat_guides = [];
    if ($("guideSkillTrees")?.checked) chat_guides.push("skill_trees");
    if ($("guideProfessions")?.checked) chat_guides.push("profession_system");
    if ($("guideAttributes")?.checked) chat_guides.push("attribute_system");
    if ($("guideEcology")?.checked) chat_guides.push("ecology");
    if ($("guideEconomy")?.checked) chat_guides.push("economy");
    const userMsg = text;
    state.messages.push({ role: "user", content: text });
    $("chatInput").value = "";
    renderMessages();
    setThinking("chat", { panel: "world" });
    const autoSyncRequested = $("autoSyncPanels")?.checked ?? false;
    const syncScopeAtSend = syncScopeForRequest();
    const prMaxAtSend = parseInt($("proofreaderMaxRetries")?.value ?? "3") || 0;
    let res;
    try {
      res = await api(`/api/worlds/${state.world.meta.id}/chat`, {
        method: "POST",
        body: JSON.stringify({
          messages: state.messages,
          mode,
          include_markdown_context: includeMd,
          chat_guides,
          auto_sync: autoSyncRequested,
          persist_sync: true,
          sync_scope: syncScopeAtSend,
          proofreader_max_retries: prMaxAtSend,
        }),
      });
    } catch (e) {
      state.messages.pop();
      renderMessages();
      toast("对话失败：" + e.message);
      setThinking(false);
      return;
    }
    state.messages.push({ role: "assistant", content: res.reply });
    renderMessages();
    setThinking(false);
    void refreshTokenUsagePanel();  // update cumulative token display

    let shouldPersist = false;
    let syncUpdatedSections = null;
    const applyAttrFromReply = () => {
      if (mergeAttributeSystemFromAssistantReply(res.reply)) {
        worldToForm(state.world);
        setDirty(true);
        refreshContextPanel();
        refreshOutlineHeader();
        toast("通用人物属性：已从助手回复中的 JSON 合并，雷达与表单已更新");
        shouldPersist = true;
        return true;
      }
      return false;
    };

    if (res.sync) {
      const syncRes = res.sync;
      if (syncRes.ok) {
        state.world = syncRes.world;
        worldToForm(syncRes.world);
        setDirty(!syncRes.persisted);
        refreshContextPanel();
        refreshOutlineHeader();
        syncUpdatedSections = syncRes.updated_sections;
        if (syncRes.merge_warnings?.length) {
          toast("Sync warnings: " + syncRes.merge_warnings.join("; "));
        }
        if (syncRes.updated_sections?.length) {
          toast("Updated: " + syncRes.updated_sections.join(", "));
        } else if (!syncRes.merge_warnings?.length) {
          toast("Sync completed: no structured changes.");
        }
      } else {
        toast("Sync parse failed: " + (syncRes.error || ""));
      }
      applyAttrFromReply();
      if (shouldPersist) {
        try {
          await persistWorldFromForm();
        } catch (e) {
          toast("Persist failed: " + (e?.message || e));
        }
      }
      navigateToEconomyAfterSyncIfNeeded(syncUpdatedSections);
      return;
    }

    if (!$("autoSyncPanels")?.checked) {
      applyAttrFromReply();
      if (shouldPersist) {
        try {
          await persistWorldFromForm();
        } catch (e) {
          toast("落盘失败：" + (e?.message || e));
        }
      }
      return;
    }

    setThinking("sync", { panel: "world" });
    try {
      const syncScope = syncScopeForRequest();
      const prMax = parseInt($("proofreaderMaxRetries")?.value ?? "3") || 0;
      console.group("[MCW] 结构同步诊断");
      console.log("scope:", syncScope, "proofreader_max_retries:", prMax);
      console.log("architect_reply_len:", res.reply?.length || 0);
      console.log("pre-sync state.world.power_system?.tiers?.length:", state.world?.power_system?.tiers?.length);
      console.log("pre-sync state.world.geography?.regions?.length:", state.world?.geography?.regions?.length);
      const syncRes = await api(
        `/api/worlds/${state.world.meta.id}/sync-panels-from-chat`,
        {
          method: "POST",
          body: JSON.stringify({
            user_message: userMsg,
            assistant_reply: res.reply,
            persist: true,
            scope: syncScope,
            creative_mode: $("genreMode")?.value || null,
            proofreader_max_retries: prMax,
          }),
        }
      );
      console.log("syncRes.ok:", syncRes.ok);
      console.log("syncRes.error:", syncRes.error || "(none)");
      console.log("syncRes.updated_sections:", JSON.stringify(syncRes.updated_sections));
      console.log("syncRes.world.power_system?.tiers?.length:", syncRes.world?.power_system?.tiers?.length);
      console.log("syncRes.world.geography?.regions?.length:", syncRes.world?.geography?.regions?.length);
      console.log("syncRes.patch keys:", Object.keys(syncRes.patch || {}));
      console.log("syncRes.merge_warnings:", syncRes.merge_warnings);
      console.log("syncRes.proofreader_rounds:", syncRes.proofreader_rounds);
      console.log("syncRes.proofreader_final_verdict:", syncRes.proofreader_final_verdict);
      console.log("syncRes.format_proofreader_used:", syncRes.format_proofreader_used);
      console.log("syncRes.format_stages:", syncRes.format_stages);
      if (syncRes.ok) {
        state.world = syncRes.world;
        console.log("post-assign state.world.power_system?.tiers?.length:", state.world?.power_system?.tiers?.length);
        console.log("post-assign state.world.geography?.regions?.length:", state.world?.geography?.regions?.length);
        worldToForm(syncRes.world);
        console.log("post-worldToForm powerTiersJson len:", ($("powerTiersJson")?.value ?? "").length);
        console.log("post-worldToForm factionsJson len:", ($("factionsJson")?.value ?? "").length);
        setDirty(true);
        refreshContextPanel();
        refreshOutlineHeader();
        syncUpdatedSections = syncRes.updated_sections;
        if (Array.isArray(syncRes.updated_sections) && syncRes.updated_sections.length > 0) {
          shouldPersist = true;
        }
        if (syncRes.merge_warnings?.length) {
          toast("校验提示：" + syncRes.merge_warnings.join("；"));
        }
        if (syncRes.format_proofreader_used) {
          toast("JSON 格式已自动修复（" + (syncRes.format_stages || []).join(" → ") + "）");
        }
        if (syncRes.proofreader_rounds > 0) {
          const prStatus =
            syncRes.proofreader_final_verdict === "ok"
              ? "通过"
              : "已用尽重试（仍有遗漏）";
          toast(
            "校对者：" + prStatus + "（" + syncRes.proofreader_rounds + " 轮）"
          );
        }
        const nn = syncRes.normalize_notes;
        if (nn && typeof nn === "object") {
          const nnLines = Object.entries(nn)
            .filter(([, arr]) => Array.isArray(arr) && arr.length)
            .map(([k, arr]) => k + "：" + arr.join("；"));
          if (nnLines.length) {
            toast("结构归一化：" + nnLines.join(" | "));
          }
        }
        if (
          syncRes.scope_applied &&
          syncRes.scope_applied !== "all" &&
          Array.isArray(syncRes.structure_output_keys)
        ) {
          const dropped = syncRes.structure_output_keys.filter(
            (k) => k !== syncRes.scope_applied
          );
          if (dropped.length) {
            toast("已按「仅当前模块」忽略：" + dropped.join("、"));
          }
        }
        if (syncRes.updated_sections?.length) {
          toast("已更新：" + syncRes.updated_sections.join("、"));
        } else if (!syncRes.merge_warnings?.length) {
          toast("同步：本轮无结构化变更（可检查助手是否像闲聊或未写可落盘设定）");
        }
      } else {
        console.log("sync FAILED — ok:false, error:", syncRes.error);
        console.groupEnd();
        toast("同步解析失败：" + (syncRes.error || ""));
      }
    } catch (se) {
      console.error("sync EXCEPTION:", se.message, se);
      console.groupEnd();
      toast("同步未执行：" + se.message);
    } finally {
      setThinking(false);
    }

    applyAttrFromReply();
    if (shouldPersist) {
      try {
        console.log("pre-save state.world.power_system?.tiers?.length:", state.world?.power_system?.tiers?.length);
        await persistWorldFromForm();
        console.log("post-save state.world.power_system?.tiers?.length:", state.world?.power_system?.tiers?.length);
      } catch (e) {
        console.error("persistWorldFromForm failed:", e);
        toast("落盘失败：" + (e?.message || e));
      }
    }
    console.groupEnd();
    navigateToEconomyAfterSyncIfNeeded(syncUpdatedSections);
  }

  async function submitCharChatFromUI() {
    if (!state.world) return toast("请先选择世界");
    const text = ($("charChatInput")?.value ?? "").trim();
    if (!text) return;
    const mode = $("genreMode")?.value || null;
    const includeMd = $("charIncludeMd")?.checked ?? false;
    const chat_guides = [];
    if ($("guideCharacterRoster")?.checked) chat_guides.push("character_roster");
    const userMsg = text;
    state.charMessages.push({ role: "user", content: text });
    if ($("charChatInput")) $("charChatInput").value = "";
    renderCharMessages();
    setThinking("chat", { panel: "char" });
    const autoSyncRequested = $("charAutoSyncPanels")?.checked ?? false;
    const syncScopeAtSend = syncScopeForRequest();
    const prMaxAtSend = parseInt($("proofreaderMaxRetries")?.value ?? "3") || 0;
    let res;
    try {
      res = await api(`/api/worlds/${state.world.meta.id}/character-chat`, {
        method: "POST",
        body: JSON.stringify({
          messages: state.charMessages,
          mode,
          include_markdown_context: includeMd,
          chat_guides,
          auto_sync: autoSyncRequested,
          persist_sync: true,
          sync_scope: syncScopeAtSend,
          proofreader_max_retries: prMaxAtSend,
        }),
      });
    } catch (e) {
      state.charMessages.pop();
      renderCharMessages();
      toast("人物对话失败：" + e.message);
      setThinking(false);
      return;
    }
    state.charMessages.push({ role: "assistant", content: res.reply });
    renderCharMessages();
    setThinking(false);

    let shouldPersist = false;
    let syncUpdatedSections = null;
    if (res.sync) {
      const syncRes = res.sync;
      if (syncRes.ok) {
        state.world = syncRes.world;
        worldToForm(syncRes.world);
        setDirty(!syncRes.persisted);
        refreshContextPanel();
        refreshOutlineHeader();
        syncUpdatedSections = syncRes.updated_sections;
        if (Array.isArray(syncRes.updated_sections) && syncRes.updated_sections.length > 0) {
          shouldPersist = !syncRes.persisted;
        }
        if (syncRes.merge_warnings?.length) {
          toast("Sync warnings: " + syncRes.merge_warnings.join("; "));
        }
        if (syncRes.updated_sections?.length) {
          toast("Updated: " + syncRes.updated_sections.join(", "));
        } else if (!syncRes.merge_warnings?.length) {
          toast("Sync completed: no structured changes.");
        }
      } else {
        toast("Sync parse failed: " + (syncRes.error || ""));
      }
      if (shouldPersist) {
        try {
          await persistWorldFromForm();
        } catch (e) {
          toast("Persist failed: " + (e?.message || e));
        }
      }
      navigateToCharactersAfterSyncIfNeeded(syncUpdatedSections);
      return;
    }
    if (!$("charAutoSyncPanels")?.checked) return;

    setThinking("sync", { panel: "char" });
    try {
      const syncRes = await api(
        `/api/worlds/${state.world.meta.id}/sync-panels-from-chat`,
        {
          method: "POST",
          body: JSON.stringify({
            user_message: userMsg,
            assistant_reply: res.reply,
            persist: true,
            scope: syncScopeForRequest(),
            creative_mode: $("genreMode")?.value || null,
            proofreader_max_retries:
              parseInt($("proofreaderMaxRetries")?.value ?? "3") || 0,
          }),
        }
      );
      if (syncRes.ok) {
        state.world = syncRes.world;
        worldToForm(syncRes.world);
        setDirty(true);
        refreshContextPanel();
        refreshOutlineHeader();
        syncUpdatedSections = syncRes.updated_sections;
        if (Array.isArray(syncRes.updated_sections) && syncRes.updated_sections.length > 0) {
          shouldPersist = true;
        }
        if (syncRes.merge_warnings?.length) {
          toast("校验提示：" + syncRes.merge_warnings.join("；"));
        }
        if (syncRes.proofreader_rounds > 0) {
          const prStatus =
            syncRes.proofreader_final_verdict === "ok"
              ? "通过"
              : "已用尽重试（仍有遗漏）";
          toast(
            "校对者：" + prStatus + "（" + syncRes.proofreader_rounds + " 轮）"
          );
        }
        const nn = syncRes.normalize_notes;
        if (nn && typeof nn === "object") {
          const nnLines = Object.entries(nn)
            .filter(([, arr]) => Array.isArray(arr) && arr.length)
            .map(([k, arr]) => k + "：" + arr.join("；"));
          if (nnLines.length) {
            toast("结构归一化：" + nnLines.join(" | "));
          }
        }
        if (
          syncRes.scope_applied &&
          syncRes.scope_applied !== "all" &&
          Array.isArray(syncRes.structure_output_keys)
        ) {
          const dropped = syncRes.structure_output_keys.filter(
            (k) => k !== syncRes.scope_applied
          );
          if (dropped.length) {
            toast("已按「仅当前模块」忽略：" + dropped.join("、"));
          }
        }
        if (syncRes.updated_sections?.length) {
          toast("已更新：" + syncRes.updated_sections.join("、"));
        } else if (!syncRes.merge_warnings?.length) {
          toast("同步：本轮无结构化变更（可检查助手是否像闲聊或未写可落盘设定）");
        }
      } else {
        toast("同步解析失败：" + (syncRes.error || ""));
      }
    } catch (se) {
      toast("同步未执行：" + se.message);
    } finally {
      setThinking(false);
    }

    if (shouldPersist) {
      try {
        await persistWorldFromForm();
      } catch (e) {
        toast("落盘失败：" + (e?.message || e));
      }
    }
    navigateToEconomyAfterSyncIfNeeded(syncUpdatedSections);
  }

  async function submitStoryChatFromUI() {
    if (!state.world) return toast("请先选择世界");
    const text = ($("storyChatInput")?.value ?? "").trim();
    if (!text) return;
    const mode = $("genreMode")?.value || null;
    const includeFiles = $("storyIncludeFiles")?.checked ?? false;
    const cid = storyChatActiveChapterId();
    const wp = storyWritingParamsFromUI(true);
    const userMsg = text;
    state.storyMessages.push({ role: "user", content: text });
    if ($("storyChatInput")) $("storyChatInput").value = "";
    renderStoryMessages();

    let genToken = beginStoryGeneration("chat", { panel: "story", chapterIds: cid ? [cid] : [] });
    let shouldPersist = false;
    let syncUpdatedSections = null;
    try {
      let res;
      try {
        res = await api(`/api/worlds/${state.world.meta.id}/story-chat`, {
          method: "POST",
          body: JSON.stringify({
            messages: state.storyMessages,
            mode,
            include_markdown_context: false,
            include_story_files: includeFiles,
            active_chapter_id: cid,
            use_tools: true,
            persist_tool_changes: true,
            writing_prompt: wp.writing_prompt,
            person: wp.person,
            character_id: wp.character_id,
            attach_prev_chapters: wp.attach_prev_chapters,
          }),
        });
      } catch (e) {
        state.storyMessages.pop();
        renderStoryMessages();
        toast("情节对话失败：" + e.message);
        return;
      }
      state.storyMessages.push({ role: "assistant", content: res.reply });
      if (res.world) {
        state.world = res.world;
        worldToForm(res.world);
        setDirty(true);
      }
      await refreshStoryChaptersAligned();
      // 章节列表已刷新（可能新增了 Agent 创建的章节），同步更新伏笔视图的下拉选项
      if (state.world?.story?.foreshadowing) {
        renderStoryForeshadowTimeline(state.world.story.foreshadowing);
      }
      renderStoryMessages();

      try {
        const auto = await autoApplyStoryArtifactsFromReply(res.reply, res.auto_applied);
        if (auto.length) toast("已自动落盘：" + auto.slice(0, 4).join("；") + (auto.length > 4 ? "…" : ""));
        if (res.auto_warnings?.length) toast("伏笔提示：" + res.auto_warnings.join("；"));
      } catch (ae) {
        toast("自动落盘失败：" + (ae?.message || ae));
      }

      if (storyChatActionsIncludeManuscript(res.actions) || res.intent === "write_manuscript") {
        await refreshStoryChaptersAligned();
        toast("本章文稿已生成，可点「打开章节文稿」查看");
      }

      if (!$("storyAutoSyncPanels")?.checked) return;

      endStoryGeneration({ token: genToken });
      genToken = beginStoryGeneration("sync", { panel: "story", chapterIds: cid ? [cid] : [] });
      const syncScope =
        state.activeView === "storyChat" || isStoryPanelView(state.activeView)
          ? "story"
          : syncScopeForRequest();
      const syncRes = await api(`/api/worlds/${state.world.meta.id}/sync-panels-from-chat`, {
        method: "POST",
        body: JSON.stringify({
          user_message: userMsg,
          assistant_reply: res.reply,
          persist: true,
          scope: syncScope,
          creative_mode: $("genreMode")?.value || null,
          proofreader_max_retries:
            parseInt($("proofreaderMaxRetries")?.value ?? "3") || 0,
        }),
      });
      if (syncRes.ok) {
        state.world = syncRes.world;
        worldToForm(syncRes.world);
        setDirty(true);
        refreshContextPanel();
        refreshOutlineHeader();
        syncUpdatedSections = syncRes.updated_sections;
        if (Array.isArray(syncRes.updated_sections) && syncRes.updated_sections.length > 0) {
          shouldPersist = true;
        }
        if (syncRes.merge_warnings?.length) {
          toast("校验提示：" + syncRes.merge_warnings.join("；"));
        }
        if (syncRes.proofreader_rounds > 0) {
          const prStatus =
            syncRes.proofreader_final_verdict === "ok"
              ? "通过"
              : "已用尽重试（仍有遗漏）";
          toast(
            "校对者：" + prStatus + "（" + syncRes.proofreader_rounds + " 轮）"
          );
        }
        const nn = syncRes.normalize_notes;
        if (nn && typeof nn === "object") {
          const nnLines = Object.entries(nn)
            .filter(([, arr]) => Array.isArray(arr) && arr.length)
            .map(([k, arr]) => k + "：" + arr.join("；"));
          if (nnLines.length) toast("结构归一化：" + nnLines.join(" | "));
        }
        if (syncRes.updated_sections?.length) {
          toast("已更新：" + syncRes.updated_sections.join("、"));
        } else if (!syncRes.merge_warnings?.length) {
          toast("同步：本轮无结构化变更（可检查助手是否像闲聊或未写可落盘设定）");
        }
      } else {
        toast("同步解析失败：" + (syncRes.error || ""));
      }
    } catch (se) {
      toast("同步未执行：" + (se?.message || se));
    } finally {
      endStoryGeneration({ token: genToken });
    }

    if (shouldPersist) {
      try {
        await persistWorldFromForm();
      } catch (e) {
        toast("落盘失败：" + (e?.message || e));
      }
    }
    navigateToStoryAfterSyncIfNeeded(syncUpdatedSections);
  }

  $("btnSend").addEventListener("click", () => void submitChatFromUI());

  $("chatInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.ctrlKey) return;
    e.preventDefault();
    void submitChatFromUI();
  });

  $("btnCharSend")?.addEventListener("click", () => void submitCharChatFromUI());
  $("charChatInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.ctrlKey) return;
    e.preventDefault();
    void submitCharChatFromUI();
  });

  $("btnStorySend")?.addEventListener("click", () => void submitStoryChatFromUI());
  $("storyChatInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.ctrlKey) return;
    e.preventDefault();
    void submitStoryChatFromUI();
  });

  $("btnOutline").addEventListener("click", async () => {
    if (!state.world) return toast("请先选择世界");
    const prompt = $("outlinePrompt").value.trim();
    if (!prompt) return toast("请输入需求");
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/outline`, {
        method: "POST",
        body: JSON.stringify({
          kind: $("outlineKind").value,
          prompt,
          include_markdown_context: $("outlineIncludeMd").checked,
          creative_mode: $("genreMode")?.value || null,
        }),
      });
      updateOutlineMarkdownPreview(res.reply);
      toast("已写入 " + res.saved);
      await loadWorld(state.world.meta.id);
    } catch (e) {
      toast("大纲失败：" + e.message);
    }
  });

  $("btnEcologyGenerate")?.addEventListener("click", () => {
    void (async () => {
      if (!state.world) return toast("请先选择世界");
      const hint = ($("ecologyGenerateHint")?.value ?? "").trim();
      setThinking("chat");
      try {
        const res = await api(`/api/worlds/${state.world.meta.id}/ecology-generate`, {
          method: "POST",
          body: JSON.stringify({
            hint,
            creative_mode: $("genreMode")?.value || null,
          }),
        });
        const reply = (res.reply ?? "").toString();
        if (out) refreshEcologyGenerateMarkdown(reply);
        const det = $("ecologyGenDetails");
        if (det && reply) det.open = true;
        toast(reply ? "生态生成完成（见上方预览；可复制 JSON 后同步或手填）" : "模型返回为空");
      } catch (e) {
        toast("生态生成失败：" + (e?.message || e));
      } finally {
        setThinking(false);
      }
    })();
  });

  const GEO_CHAT_PROMPT =
    "请为当前世界补充或修订 **地理**（对应 world.json 的 **geography**，便于「对话后同步」落盘）。请用自然语言 + 清晰小节组织，并尽量与下列键名对齐（不必输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 geography.summary**：多大陆/海洋/文明带尺度；不要在这里罗列具体地标或逐条物产表。\n" +
    "2）**全图气候 geography.climate_notes**：气候带、季风、异常气象、季节对旅行的影响。\n" +
    "3）**地图与交通 geography.map_notes**：方位约定、比例、制图说明；主干商路、航道或关隘总览。\n" +
    "4）**分区 geography.regions[]**：每个大陆、王国、海域等可区分单元单独一小节；每区尽量给出稳定 **id**（短 slug，如 `north_realm`），与现有区域 id 一致则沿用。每区包含：\n" +
    "   - **name**、**summary**（地貌/政权/文化带等较长叙述）；\n" +
    "   - **terrain**（地貌关键词）、**climate**（局地气候一句，可选）；\n" +
    "   - **notes**（旅行风险、关卡、调查或叙事钩子，可选）；\n" +
    "   - **landmarks[]**、**resources[]**：各用短名单行或分号列举（一项一名；长说明放进 summary/notes，勿把长段落塞进列表项）；\n" +
    "   - **relations[]**：与其它区的联系，每条写清对方 **target_id**（等于对方区域的 **id**）、**type**（如 邻接/贸易/航道/调查轴）、可选 **notes**。\n" +
    "5）若有尚无法归属到任何区的散点地标或物产，可单独列出并说明稍后将归入哪一区；**优先**写进所属区域的 **landmarks** / **resources**，顶层 **geography.landmarks** / **resources** 仅作补充。\n\n" +
    "若当前 JSON 中已有 regions，请对照修订并说明新增或重命名了哪些 **id**（以便我更新 relations）。";

  const POWER_SYSTEM_CHAT_PROMPT =
    "请为当前世界设计或修订 **境界体系**（对应 world.json 的 **power_system**，勿与 **attribute_system** 混淆；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 power_system.summary**：力量阶梯在世界中的位置、读者/玩家如何理解「境」。\n" +
    "2）**境界设计说明 realm_design_notes**：命名规则、递进与破境代价、与 **attribute_system**（人物卡/雷达）的叙事分界。\n" +
    "3）**技能树跨境说明 skill_tree_design_notes**：节点 **id** 命名、**prereq_ids**（前序须为**同一棵树**内已有节点 id）、本境通用 **skill_tree** 与 **subclass_paths** 专属树如何并存。\n" +
    "4）**各境 power_system.tiers[]**：每境 **name**、**description**；**typical_capabilities[]**、**limitations[]**、**examples[]**（**limitations** 写硬边界、代价、禁忌或反作弊叙事）。\n" +
    "5）每境可选 **skill_tree[]**：节点 **id**（该境该树内唯一）、**name**、**summary**、**prereq_ids**、**branch**（可选）。\n" +
    "6）每境可选 **subclass_paths[]**：**id**、**name**、**tagline**、**flavor**；**profession_id**（须与同境 **profession_system.by_tier** 中某 **professions[].id** 一致）；可含该流派 **skill_tree**（节点 id 建议加前缀以免与境界通用树冲突）。\n" +
    "7）可选 **profession_system**：**summary**、**design_notes**、**by_tier[]**（与 tiers 顺序或 **tier_name** 对齐）；每块 **professions[]** 含 **id**、**name**、**tagline**、**flavor**、**exclusive_faction_id**（须为已有 **factions.entities[].id**）、**notes**。\n\n" +
    "若 JSON 中已有 **tiers**，请对照修订并说明是否新增/重命名了境界或技能节点 **id**（以便我检查 **prereq_ids** 与 **profession_id**）。";

  const SKILL_TREE_CHAT_PROMPT =
    "在已完成 **境界总览（summary）**、**realm_design_notes**、**tiers[]** 各境 name/description/limitations 的前提下，请为当前世界细化 **境界技能树**（仍属 world.json 的 **power_system**）：\n\n" +
    "0）在 **skill_tree_design_notes** 中写清：节点 id 前缀、**prereq_ids** 只引用同树已有 id、通用 **skill_tree** 与各境 **subclass_paths** 专属树如何并存；与 **profession_system** 职业 **id** 如何对照。\n" +
    "1）**power_system.tiers[]** 每一境可有通用 **skill_tree**：节点 **id**、**name**、**summary**、**prereq_ids**、**branch**（可选）。\n" +
    "2）每一境可有 **subclass_paths**：**id**、**name**、**tagline**、**flavor**、可选 **profession_id**（须与同境 **profession_system.by_tier[].professions[].id** 一致）、以及该子类 **skill_tree**（节点 id 建议加前缀）。\n" +
    "3）与已有 **typical_capabilities**、**limitations** 自洽；说明通用节点与子类分叉关系。\n\n" +
    "若尚无境界表，请先补 **tiers** 再补树。输出需便于我开启「对话后同步」写入 power_system。";

  const ITEM_QUALITY_CHAT_PROMPT =
    "请为当前世界设计或修订 **物品品质体系**（world.json 的 **item_quality_system**；便于「对话后同步」落盘）。**顶层键必须为 `item_quality_system`**，勿使用 **`items`**、**`item_grades`** 等别名。请用自然语言 + 清晰小节对齐下列键（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 item_quality_system.summary**：道具/宝物在世界中的定位、各档位的读者或玩家预期、与 **power_system** 境界叙事如何挂钩（不在此写人物六维）。\n" +
    "2）**档位 item_quality_system.grades[]**：每档单独说明；每档必填 **name**（档位名，短字符串）；**rarity_narrative**（稀有度与叙事张力）；**typical_effects**（该档典型效果、词条或玩法方向）；**binding_rules**（绑定、交易、掉落、使用限制、反刷等可裁定规则；DnD 式可类比 attunement 叙事）；**examples**（可选：字符串数组，每项为短例句或样例装备名）。\n" +
    "3）档位之间边界清晰（谁能持有、何时损毁/失控、与剧情冲突点）；与 **geography.regions[].resources** 若有分工，请在叙述中说明（资源短名在地理，档位规则在本节）。\n\n" +
    "若 JSON 中已有 **grades**，请对照修订并说明是否重命名了某档 **name** 或收紧了 **binding_rules**。";

  const PROFESSION_CHAT_PROMPT =
    "请为当前世界设计或修订 **境界职业体系**（world.json 的 **power_system.profession_system**，与 attribute_system 独立）：\n\n" +
    "1）**summary**：职业/流派在世界中的定位（宗门、军团、公会、秘传等）。\n" +
    "2）**design_notes**：各境职业如何递进；**exclusive_faction_id** 何时填写（须为已有 **factions.entities[].id**）；与 **subclass_paths.profession_id** 的命名对齐规则。\n" +
    "3）**by_tier[]**：与 **power_system.tiers** 顺序或 **tier_name** 对齐；每项 **professions[]** 含 **id**（单境内唯一）、**name**、**tagline**、**flavor**、**exclusive_faction_id**（可选）、**notes**。\n" +
    "4）若已写技能树，请说明各 **subclass_paths** 的 **profession_id** 应绑定到哪条职业 **id**。\n\n" +
    "输出需便于我开启「对话后同步」写入 **power_system**（内含 profession_system 与既有 tiers 字段合并）。";

  const ATTR_CHAT_PROMPT =
    "请为当前世界建立或修订「通用人物属性」体系（对应 world.json 的 attribute_system，与境界体系 power_system 独立）：\n\n" +
    "1）**总览**：这套属性服务于什么（叙事节奏 / 跑团检定 / 游戏数值的叙事映射等）。\n" +
    "2）**设计说明**：如何读雷达图、建卡建议、与当前创作载体尺度对齐。\n" +
    "3）**stats 维度列表**：建议 4～8 项；每项给出 id（短 id）、name、abbreviation、**intro**（该维度单独一句话简介，用于看板展示）、description（可较长）、scale、typical_use、reference_percent（0–100，雷达上世界参照强度）。\n" +
    "4）**tier_average_profiles**（可选）：与 **power_system.tiers** 各境 **name** 对齐，每项含 **tier_name** 与 **averages**（对象：键须为 stat 的 **id**，值为 0–100）。雷达上**缺键的维度按 0**；若 averages 与当前 stats 的 id **无一能对齐**则**不绘制该境**。\n\n" +
    "若已有 attribute_system，请对照修订并说明改动理由。输出需便于我开启「对话后同步」写入 attribute_system。\n\n" +
    "请尽量在回复末尾用 **json 代码块**（```json … ```）给出完整 `attribute_system` 对象（含 summary、design_notes、stats、可选 tier_average_profiles），前端会在发送后自动合并到「属性」页并更新雷达。";

  const ECOLOGY_CHAT_PROMPT =
    "请为当前世界补充或修订 **生态与生境**（world.json 的 **ecology**；与 **geography**、**attribute_system** 对齐；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 ecology.summary**：全图生态位、危险带、文明与荒野/超凡力量的交界叙事。\n" +
    "2）**设计说明 ecology.design_notes**：哪些 **geography.regions[].id**、气候/地貌与 **attribute_system.stats** 的叙事刻度如何对应野外压力或魔化生态。\n" +
    "3）**生境群落 ecology.biomes[]**：每项 **id**、**name**、**summary**；**linked_region_ids[]** 只能使用已有 **geography.regions[].id**（无则不要虚构 id）；可选 **climate_habitat**、**hazards**、**notes**。\n" +
    "4）**代表物种 ecology.species[]**：每项 **id**、**name**、**biome_id**（须为 **biomes[].id**）；**traits[]**；**notable_skills[]**（物种行为或叙事向「类技能」短句，**非**境界 **power_system.skill_tree** 节点）；**encounter_dialogue**（一句遭遇旁白或台词，供跑团/DM 使用）；可选 **danger_notes**。\n\n" +
    "若 JSON 中已有 **biomes/species**，请对照修订并说明是否新增或重命名了 **id**（以便我检查 **biome_id** 与 **linked_region_ids**）。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"ecology\": { ... } }`（字段与上述一致）。";

  const ECONOMY_CHAT_PROMPT =
    "请为当前世界补充或修订 **经济与流通**（world.json 的 **economy**；与 **geography.regions**、**factions.entities**、**item_quality_system** 对齐；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 economy.summary**：通货、铸币权、商会与黑市、关税与走私带等宏观叙事。\n" +
    "2）**设计说明 economy.design_notes**：哪些 **regions[].id**、**factions.entities[].id**、物品档位如何牵动现金流与危机。\n" +
    "3）**货币 economy.currencies[]**：每项 **id**、**name**；可选 **symbol**、**issuer_faction_id**（须为已有派系 **id**）、**exchange_notes**。\n" +
    "4）**市场 economy.markets[]**：每项 **id**、**name**；可选 **summary**、**linked_region_ids[]**（仅已有区域 **id**）、**dominant_faction_ids[]**、**notes**。\n" +
    "5）**商路 economy.trade_routes[]**：每项 **id**、**name**、**from_region_id**、**to_region_id**（须为已有区域 **id**）；可选 **summary**、**goods_notes**、**controlling_faction_ids[]**、**notes**。\n" +
    "6）**贸易品 economy.trade_goods[]**：每项 **id**、**name**；可选 **category**（如 strategic|luxury|common|contraband）、**summary**、**notes**。\n" +
    "7）**labor_notes**、**taxation_notes**、**volatility_notes**：劳动力、税收再分配、物价波动与危机等条款式说明。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"economy\": { ... } }`（字段与上述一致）。";

  const FACTIONS_CHAT_PROMPT =
    "请为当前世界新增或修订 **派系**（world.json 的 **factions**；便于「对话后同步」写入）。请用 Markdown，**按派系分块**（每个派系建议用三级标题，正文内显式写出 **id**、**name**、**goals**、**territory** 以便抽取）：\n\n" +
    "1）**factions.summary**（可选）：多派系博弈总览。\n" +
    "2）**factions.entities[]**（核心）：每项必须含 **id**（短英文 slug，全局唯一）、**name**；**goals** 与 **territory** 各为**一整段字符串**（宗旨/立场；控制区、据点、外溢影响），勿把长叙事拆成无键名的散列表。\n" +
    "3）**key_figures**：**字符串数组**，每项一行，如「阿兰 · 外务执事」；**禁止**使用 `{ name, role }` 形式的对象列表（当前 schema 无法落盘）。\n" +
    "4）**relations[]**：派系之间的关系；每项 **target_id** 填**另一派系**的 **id**（不要用中文派系名代替 id）；**type** 只能是英文 **ally** | **enemy** | **neutral** | **complex** 四选一（不要用 rival、联盟、敌对等——若语义如此请映射成 enemy/ally/neutral/complex 后再写），可选 **notes**。\n" +
    "5）若已有 **factions.entities**，请保留既有 **id**，只增补 goals、territory、key_figures、relations；新增派系须用新的唯一 **id**。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"factions\": { \"summary\": \"...\", \"entities\": [ ... ] } }`，结构与上述一致。";

  const FACTION_KEY_PEOPLE_CHAT_PROMPT =
    "请针对当前 **world.json** 中已有 **factions.entities**（请按每个实体的 **id** 逐个点名），为每个派系扩写 **key_figures**：每派系 **3～7** 条，每项**一行字符串**（建议「姓名 · 职务/立场」或「姓名（一句秘密或叙事钩子）」）。\n\n" +
    "**不要**改动各派系 **id** 与 **name**；不要新增不了解的 **relations**，除非同时给出规范的 **target_id** + **type**（**ally|enemy|neutral|complex**）+ 可选 **notes**。\n" +
    "请用 Markdown **按派系 id 分小节**列出便于同步；若提供 JSON，文末单个 **```json** 根对象须为 `{ \"factions\": { \"entities\": [ ... ] } }`，每个实体须含 **id** 与 **key_figures**（字符串数组），其余字段可与已有世界一致并写全以便合并。";

  const CHARACTER_ROSTER_CHAT_PROMPT =
    "请为当前世界补充或修订 **人物卡司**（world.json 的 **characters**；与派系、地理 id 对齐；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**characters.summary**：谁在驱动主线/副线，卡司规模与叙事功能。\n" +
    "2）**characters.design_notes**：与 **factions** 要人、**history**、**geography.regions** 籍贯等 **id** 的对齐与防漂移约定。\n" +
    "3）**characters.entities[]**：每项 **id**、**name**；**cast_role** 取 `protagonist_core`（主角团核心）| `supporting_major` | `supporting_minor` | `antagonist` | `background`；**faction_ids[]** 须对齐已有 **factions.entities[].id**；**home_region_id** 须对齐已有 **geography.regions[].id**；可选 **aliases[]**、**one_line_hook**、**notes**、**notable_skills[]**（人物叙事或玩法向特长短句，**非**境界 **power_system.skill_tree** 节点）。\n" +
    "4）**characters.relations[]**：**source_id**、**target_id**（均为 **entities[].id**）；**relation_type**（如 ally/rival/family/debt/secret）；可选 **visibility**、**notes**。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"characters\": { ... } }`。";

  function fillCharChatPromptTemplate(text, { mode = "replace", enableCharacterGuide = false } = {}) {
    if (!state.world) {
      toast("请先选择世界");
      return;
    }
    if (enableCharacterGuide) {
      const g = $("guideCharacterRoster");
      if (g) g.checked = true;
    }
    const inp = $("charChatInput");
    if (!inp) return;
    const cur = (inp.value || "").trim();
    if (mode === "append" && cur) inp.value = `${cur}\n\n${text}`;
    else inp.value = text;
    inp.focus();
    if (enableCharacterGuide) toast("已开启「人物卡司」引导，提示已填入输入框");
  }

  function fillChatPromptTemplate(
    text,
    {
      mode = "replace",
      enableAttrGuide = false,
      enableSkillTreeGuide = false,
      enableProfessionGuide = false,
      enableEcologyGuide = false,
      enableEconomyGuide = false,
    } = {}
  ) {
    if (!state.world) {
      toast("请先选择世界");
      return;
    }
    if (enableAttrGuide) {
      const g = $("guideAttributes");
      if (g) g.checked = true;
    }
    if (enableEcologyGuide) {
      const e = $("guideEcology");
      if (e) e.checked = true;
    }
    if (enableEconomyGuide) {
      const y = $("guideEconomy");
      if (y) y.checked = true;
    }
    if (enableSkillTreeGuide) {
      const s = $("guideSkillTrees");
      if (s) s.checked = true;
    }
    if (enableProfessionGuide) {
      const p = $("guideProfessions");
      if (p) p.checked = true;
    }
    const inp = $("chatInput");
    if (!inp) return;
    const cur = (inp.value || "").trim();
    if (mode === "append" && cur) inp.value = `${cur}\n\n${text}`;
    else inp.value = text;
    inp.focus();
    if (enableSkillTreeGuide) toast("已开启「境界技能树」引导，提示已填入输入框");
    else if (enableProfessionGuide) toast("已开启「境界职业体系」引导，提示已填入输入框");
    else if (enableAttrGuide) toast("已开启「人物属性」引导，提示已填入输入框");
    else if (enableEcologyGuide) toast("已开启「生态与生境」引导，提示已填入输入框");
    else if (enableEconomyGuide) toast("已开启「经济系统」引导，提示已填入输入框");
  }

  const chips = [
    ["lightbulb", "规划", "请先列出当前世界还缺哪些模块，并给出下一步建议。"],
    ["map", "写地理", GEO_CHAT_PROMPT],
    ["bolt", "写境界体系", POWER_SYSTEM_CHAT_PROMPT],
    [
      "badge",
      "职业体系",
      PROFESSION_CHAT_PROMPT,
      { professionGuide: true, append: true },
    ],
    ["account_tree", "境界技能树", SKILL_TREE_CHAT_PROMPT, { skillTreeGuide: true, append: true }],
    ["bubble_chart", "人物属性", ATTR_CHAT_PROMPT, { attrGuide: true, append: true }],
    ["forest", "写生态", ECOLOGY_CHAT_PROMPT, { ecologyGuide: true, append: true }],
    ["payments", "写经济", ECONOMY_CHAT_PROMPT, { economyGuide: true, append: true }],
    ["diamond", "写物品品质", ITEM_QUALITY_CHAT_PROMPT],
    [
      "diversity_3",
      "文化·宗教",
      "请根据当前世界设定，补充或修订「文化 / 宗教」（对应 world.json 的 cultures 节）。请用自然语言说明：总览氛围；若有多条传统或教团，请分别给出名称、是民俗共同体还是宗教组织（或二者融合）、核心观念或教义、主要仪式/节日/禁忌、圣地或中心、关键人物；若彼此有影响、冲突或融合，请说明关系。若有与现有派系、地理的挂钩，请点名对应势力或地区。输出需便于我随后用「对话后同步」写入 cultures。",
    ],
    ["groups", "写派系", FACTIONS_CHAT_PROMPT],
    [
      "person",
      "派系要人",
      FACTION_KEY_PEOPLE_CHAT_PROMPT,
    ],
    ["history_edu", "写历史", "请写一条重大历史事件及后果，并挂钩现有派系。"],
  ];
  const chipBox = $("promptChips");
  if (chipBox)
    chips.forEach((row) => {
      const [glyph, label, text] = row;
      const meta = row.length > 3 && row[3] ? row[3] : {};
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip-btn";
      b.innerHTML = `<span class="ms chip-glyph" aria-hidden="true">${glyph}</span>${label}`;
      b.addEventListener("click", () => {
        fillChatPromptTemplate(text, {
          mode: meta.append ? "append" : "replace",
          enableAttrGuide: !!meta.attrGuide,
          enableSkillTreeGuide: !!meta.skillTreeGuide,
          enableProfessionGuide: !!meta.professionGuide,
          enableEcologyGuide: !!meta.ecologyGuide,
          enableEconomyGuide: !!meta.economyGuide,
        });
      });
      chipBox.appendChild(b);
    });

  const charChipBox = $("charPromptChips");
  const storyChipBox = $("storyPromptChips");
  if (storyChipBox) {
    const storyChips = [
      [
        "list_alt",
        "全书粗纲",
        "请根据当前 world.json 与卡司，输出全书粗纲（Markdown），并用 ```story-macro 代码块包裹正文以便一键写入。",
      ],
      [
        "format_list_numbered",
        "本章细纲",
        "请为当前选中章节撰写细纲（Markdown），用 ```story-beat:<chapter_id> 代码块，id 与 chapters 一致。",
      ],
      [
        "linear_scale",
        "伏笔表",
        "请建议 5～8 条伏笔：每条说明 label、planted_chapter_id、payoff_chapter_id、status；便于同步进 story.foreshadowing。",
      ],
    ];
    storyChips.forEach((row) => {
      const [glyph, label, text] = row;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip-btn";
      b.innerHTML = `<span class="ms chip-glyph" aria-hidden="true">${glyph}</span>${label}`;
      b.addEventListener("click", () => fillStoryChatPromptTemplate(text));
      storyChipBox.appendChild(b);
    });
  }

  if (charChipBox) {
    const charChips = [
      ["groups", "对齐派系 id", "请列出当前 world.json 中已有 **factions.entities[].id** 与 **geography.regions[].id**，据此设计 3～6 名主要人物：每人给出建议 **id**、**name**、**cast_role**、**faction_ids[]**、**home_region_id**、**one_line_hook**，并说明与现有派系/区域如何挂钩。"],
      ["family_history", "人物关系边", "在已有或拟新增的 **characters.entities[]** 上，补充 **characters.relations[]**：每条 **source_id**、**target_id**、**relation_type**、**notes**；关系要有戏剧功能（债务、秘密、家族、对立、同盟）。"],
      ["military_tech", "主角团张力", "请设计 **cast_role** 为 **protagonist_core** 的主角团（3～5 人）：写清每人 **notable_skills[]**（叙事向短句）、内在目标冲突，以及他们为何被迫同行。"],
      ["person_alert", "反派与压力", "请增加或修订 **antagonist** 与 **supporting_major**：每人 **one_line_hook**、与主角团的 **relations**（rival/debt/secret 等），并挂钩 **history** 或 **factions**。"],
      ["auto_stories", "卡司总览", CHARACTER_ROSTER_CHAT_PROMPT, { charGuide: true, append: false }],
    ];
    charChips.forEach((row) => {
      const [glyph, label, text] = row;
      const meta = row.length > 3 && row[3] ? row[3] : {};
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip-btn";
      b.innerHTML = `<span class="ms chip-glyph" aria-hidden="true">${glyph}</span>${label}`;
      b.addEventListener("click", () => {
        fillCharChatPromptTemplate(text, {
          mode: meta.append ? "append" : "replace",
          enableCharacterGuide: !!meta.charGuide,
        });
      });
      charChipBox.appendChild(b);
    });
  }

  initStoryPanelBindings();
}

/** 助手回复：Markdown → HTML（GFM），经 DOMPurify 消毒 */
function renderAssistantMarkdownHtml(text) {
  const raw = (text ?? "").toString();
  if (typeof marked === "undefined" || typeof marked.parse !== "function") {
    return escapeHtml(raw).replaceAll("\n", "<br/>");
  }
  try {
    const unsafe = marked.parse(raw);
    if (typeof DOMPurify !== "undefined" && typeof DOMPurify.sanitize === "function") {
      return DOMPurify.sanitize(unsafe, { USE_PROFILES: { html: true } });
    }
    return escapeHtml(raw).replaceAll("\n", "<br/>");
  } catch (_) {
    return escapeHtml(raw).replaceAll("\n", "<br/>");
  }
}

function renderMessages() {
  const box = $("messages");
  box.innerHTML = "";
  for (const m of state.messages) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    const roleIc = m.role === "user" ? "person" : "smart_toy";
    const body =
      m.role === "assistant"
        ? renderAssistantMarkdownHtml(m.content)
        : escapeHtml(m.content).replaceAll("\n", "<br/>");
    const bodyClass =
      m.role === "assistant" ? "msg-body msg-body--assistant msg-body--md" : "msg-body msg-body--user";
    div.innerHTML = `<div class="role"><span class="ms role-ic" aria-hidden="true">${roleIc}</span>${m.role}</div><div class="${bodyClass}">${body}</div>`;
    box.appendChild(div);
  }
  box.scrollTop = box.scrollHeight;
}

function renderCharMessages() {
  const box = $("charMessages");
  if (!box) return;
  box.innerHTML = "";
  for (const m of state.charMessages) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    const roleIc = m.role === "user" ? "person" : "smart_toy";
    const body =
      m.role === "assistant"
        ? renderAssistantMarkdownHtml(m.content)
        : escapeHtml(m.content).replaceAll("\n", "<br/>");
    const bodyClass =
      m.role === "assistant" ? "msg-body msg-body--assistant msg-body--md" : "msg-body msg-body--user";
    div.innerHTML = `<div class="role"><span class="ms role-ic" aria-hidden="true">${roleIc}</span>${m.role}</div><div class="${bodyClass}">${body}</div>`;
    box.appendChild(div);
  }
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

// Expose functions referenced by HTML onchange handlers for module compatibility
window.loadStoryBeat = loadStoryBeat;
window.renderConsistencyReport = renderConsistencyReport;
window.loadPolishedManuscript = loadPolishedManuscript;
window.selectStoryChapter = selectStoryChapter;
window.batchSetStatus = batchSetStatus;
window.batchDeleteChapters = batchDeleteChapters;
window.batchRenumber = batchRenumber;

// ── Token Usage Panel ──────────────────────────────────────────

// ── P0: Character Knowledge Panel ────────────────────────────────

function renderKnowledgePanel() {
  const listEl = $("charKnowledgeList");
  const countEl = $("charKnowledgeCount");
  if (!listEl) return;
  const entries = state.world?.character_knowledge?.entries || [];
  if (countEl) countEl.textContent = entries.length ? `${entries.length} 条知识` : "";
  // Update tab counts
  const kTab = $("knowledgeTabCount");
  if (kTab) kTab.textContent = entries.length ? `(${entries.length})` : "";
  const decs = state.world?.character_decisions || [];
  const dTab = $("decisionsTabCount");
  if (dTab) dTab.textContent = decs.length ? `(${decs.length})` : "";
  const tls = state.world?.character_personal_timelines || [];
  const tlTab = $("timelineTabCount");
  if (tlTab) tlTab.textContent = tls.reduce((s, t) => s + (t.events || []).length, 0) || "";

  // Update character filter dropdown
  const charSel = $("charKnowledgeFilterChar");
  if (charSel) {
    const curVal = charSel.value;
    const chars = state.world?.characters?.entities || [];
    charSel.innerHTML = '<option value="">全部角色</option>' +
      chars.map(c => {
        const cid = typeof c === "object" ? (c.id || "") : String(c);
        const cname = typeof c === "object" ? (c.name || cid) : cid;
        const cnt = entries.filter(e => e.character_id === cid).length;
        return `<option value="${escapeAttr(cid)}"${cid === curVal ? " selected" : ""}>${escapeHtml(cname)}${cnt ? ` (${cnt})` : ""}</option>`;
      }).join("");
  }

  // Apply character filter
  const filterChar = charSel?.value || "";
  let filtered = filterChar
    ? entries.filter(e => e.character_id === filterChar)
    : entries;

  if (!filtered.length) {
    listEl.innerHTML = `<div class="knowledge-empty">
      <span class="ms knowledge-empty-icon" aria-hidden="true">psychology</span>
      <p class="muted">暂无知识条目</p>
      <p class="muted tiny">生成章节后，系统将自动检测角色获得或分享了哪些新信息。</p>
    </div>`;
    return;
  }

  const CAT_LABELS = { secret: "秘密", personal_history: "个人历史", world_lore: "世界设定", plan: "计划", suspicion: "怀疑", misunderstanding: "误解" };
  const CAT_ICONS = { secret: "lock", personal_history: "history", world_lore: "public", plan: "tactic", suspicion: "visibility_off", misunderstanding: "error" };
  const CAT_COLORS = { secret: "#7c3aed", personal_history: "#0d9488", world_lore: "#2563eb", plan: "#ea580c", suspicion: "#f59e0b", misunderstanding: "#dc2626" };
  const CERT_LABELS = { knows_for_sure: "确知", strongly_suspects: "强怀疑", vaguely_senses: "隐约感知", believes_wrongly: "错误认知" };
  const CERT_COLORS = { knows_for_sure: "#16a34a", strongly_suspects: "#ea580c", vaguely_senses: "#6366f1", believes_wrongly: "#dc2626" };

  const groupBy = document.querySelector('input[name="knowledgeGroupBy"]:checked')?.value || "character";

  const chars = state.world?.characters?.entities || [];
  const charMap = {};
  chars.forEach(c => {
    const id = typeof c === "object" ? (c.id || "") : String(c);
    charMap[id] = typeof c === "object" ? (c.name || id) : id;
  });

  if (groupBy === "character") {
    // Group by character
    const grouped = {};
    filtered.forEach(e => {
      grouped[e.character_id] = grouped[e.character_id] || [];
      grouped[e.character_id].push(e);
    });

    listEl.innerHTML = Object.entries(grouped).map(([charId, knows]) => {
      const cname = charMap[charId] || charId;
      const cards = knows.map(e => _renderKnowledgeCard(e, charMap, CAT_LABELS, CAT_ICONS, CAT_COLORS, CERT_LABELS, CERT_COLORS)).join("");
      return `<div class="knowledge-char-group">
        <div class="knowledge-char-group-head">
          <span class="ms" aria-hidden="true">person</span>
          <span class="knowledge-char-name">${escapeHtml(cname)}</span>
          <span class="knowledge-char-count">${knows.length} 条</span>
        </div>
        <div class="knowledge-char-cards">${cards}</div>
      </div>`;
    }).join("");
  } else {
    // Group by category
    const grouped = {};
    filtered.forEach(e => {
      grouped[e.category] = grouped[e.category] || [];
      grouped[e.category].push(e);
    });

    const catOrder = ["secret", "suspicion", "plan", "misunderstanding", "personal_history", "world_lore"];
    listEl.innerHTML = catOrder.map(cat => {
      const items = grouped[cat];
      if (!items || !items.length) return "";
      const cards = items.map(e => _renderKnowledgeCard(e, charMap, CAT_LABELS, CAT_ICONS, CAT_COLORS, CERT_LABELS, CERT_COLORS)).join("");
      return `<div class="knowledge-char-group">
        <div class="knowledge-char-group-head">
          <span class="ms" aria-hidden="true" style="color:${CAT_COLORS[cat] || '#888'}">${CAT_ICONS[cat] || "help"}</span>
          <span class="knowledge-char-name">${CAT_LABELS[cat] || cat}</span>
          <span class="knowledge-char-count">${items.length} 条</span>
        </div>
        <div class="knowledge-char-cards">${cards}</div>
      </div>`;
    }).filter(Boolean).join("");
  }
}

function _renderKnowledgeCard(e, charMap, CAT_LABELS, CAT_ICONS, CAT_COLORS, CERT_LABELS, CERT_COLORS) {
  const cname = charMap[e.character_id] || e.character_id;
  const shared = (e.shared_with || []).map(s => {
    const sid = s.character_id || "";
    return charMap[sid] || sid;
  }).filter(Boolean).join("、");

  return `<div class="knowledge-card">
    <div class="knowledge-card-top">
      <span class="knowledge-card-cat" style="background:${CAT_COLORS[e.category] || '#888'}11;color:${CAT_COLORS[e.category] || '#888'};border-color:${CAT_COLORS[e.category] || '#888'}33">
        <span class="ms" aria-hidden="true">${CAT_ICONS[e.category] || "help"}</span>${CAT_LABELS[e.category] || e.category}
      </span>
      <span class="knowledge-card-certainty" style="background:${CERT_COLORS[e.certainty] || '#888'}18;color:${CERT_COLORS[e.certainty] || '#888'}">${CERT_LABELS[e.certainty] || e.certainty}</span>
      ${!e.is_still_true ? '<span class="knowledge-card-stale">已过时</span>' : ""}
    </div>
    <p class="knowledge-card-topic">${escapeHtml(e.topic || e.knowledge_id)}</p>
    <div class="knowledge-card-meta">
      <span>🧑 ${escapeHtml(cname)}</span>
      <span>📖 ${escapeHtml(e.source_chapter || "?")}</span>
    </div>
    ${e.source_detail ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">获得方式</span>${escapeHtml(e.source_detail)}</div>` : ""}
    ${shared ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">已分享</span>${escapeHtml(shared)}</div>` : ""}
    ${e.notes ? `<div class="knowledge-card-detail" style="color:#94a3b8"><span class="knowledge-detail-label">备注</span>${escapeHtml(e.notes)}</div>` : ""}
  </div>`;
}

async function saveKnowledgeToggle() {
  if (!state.world?.meta?.id) return;
  const enabled = $("storyToggleKnowledge")?.checked ?? true;
  const decEnabled = $("storyToggleDecisions")?.checked ?? true;
  const physEnabled = $("storyTogglePhysical")?.checked ?? true;
  const tlEnabled = $("storyToggleTimeline")?.checked ?? true;
  try {
    await api(`/api/worlds/${state.world.meta.id}/story/writing-defaults`, {
      method: "PATCH",
      body: JSON.stringify({ enable_knowledge_track: enabled, enable_decision_track: decEnabled, enable_physical_state_track: physEnabled, enable_personal_timeline_track: tlEnabled }),
    });
    if (state.world.story?.writing_defaults) {
      state.world.story.writing_defaults.enable_knowledge_track = enabled;
      state.world.story.writing_defaults.enable_decision_track = decEnabled;
      state.world.story.writing_defaults.enable_physical_state_track = physEnabled;
      state.world.story.writing_defaults.enable_personal_timeline_track = tlEnabled;
    }
  } catch (e) { console.warn("保存设置失败", e); }
}

async function clearKnowledgeGraph() {
  if (!state.world?.meta?.id) return;
  if (!confirm("确定清空所有角色知识条目？此操作不可撤销。")) return;
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/knowledge-graph/clear`, { method: "POST" });
    state.world = res.world;
    renderKnowledgePanel();
    toast("知识图谱已清空");
  } catch (e) { toast("清空失败：" + e.message); }
}

function renderPhysicalStatesPanel() {
  const listEl = $("charPhysicalList");
  const countEl = $("physicalTabCount");
  if (!listEl) return;
  const states = state.world?.character_physical_states || [];
  if (countEl) countEl.textContent = states.length ? `(${states.length})` : "";

  if (!states.length) {
    listEl.innerHTML = `<div class="knowledge-empty">
      <span class="ms knowledge-empty-icon">fitness_center</span>
      <p class="muted">暂无身体状况数据</p>
      <p class="muted tiny">生成章节后系统自动检测，或点击「从已有章节提取」扫描历史章节。</p>
    </div>`;
    return;
  }

  const FATIGUE_LABELS = { rested: "精力充沛", tired: "疲惫", exhausted: "极度疲劳", collapse_imminent: "即将崩溃" };
  const FATIGUE_COLORS = { rested: "#16a34a", tired: "#ea580c", exhausted: "#dc2626", collapse_imminent: "#991b1b" };
  const SEVERITY_COLORS = { minor: "#f59e0b", moderate: "#ea580c", severe: "#dc2626", critical: "#991b1b" };

  const chars = state.world?.characters?.entities || [];
  const charMap = {};
  chars.forEach(c => {
    const id = typeof c === "object" ? (c.id || "") : String(c);
    charMap[id] = typeof c === "object" ? (c.name || id) : id;
  });

  listEl.innerHTML = states.map(ps => {
    const cname = charMap[ps.character_id] || ps.character_id;
    const injuries = (ps.active_injuries || []).map(inj =>
      `<div class="phys-injury">
        <span class="phys-injury-dot" style="background:${SEVERITY_COLORS[inj.severity] || '#888'}"></span>
        <span>${inj.type || '伤'} · ${inj.location || '?'} · 愈合${inj.healing_progress || '?'}</span>
        ${inj.functional_impact ? `<span class="muted tiny">— ${inj.functional_impact}</span>` : ""}
      </div>`
    ).join("");

    const marks = (ps.permanent_marks || []).map(m =>
      `<div class="phys-mark">${m.type || '疤痕'} · ${m.location || '?'}（${m.origin || '?'}）</div>`
    ).join("");

    const chronic = (ps.chronic_conditions || []).map(c =>
      `<div class="phys-chronic">${c.condition || ''}</div>`
    ).join("");

    return `<div class="phys-card">
      <div class="phys-card-head">
        <span class="ms">person</span>
        <strong>${escapeHtml(cname)}</strong>
        <span class="phys-fatigue" style="color:${FATIGUE_COLORS[ps.fatigue_level] || '#888'}">${FATIGUE_LABELS[ps.fatigue_level] || ps.fatigue_level}</span>
      </div>
      ${ps.general_condition ? `<p class="phys-general">${escapeHtml(ps.general_condition)}</p>` : ""}
      ${injuries ? `<div class="phys-section"><div class="phys-section-title">活跃伤情</div>${injuries}</div>` : ""}
      ${marks ? `<div class="phys-section"><div class="phys-section-title">永久疤痕</div>${marks}</div>` : ""}
      ${chronic ? `<div class="phys-section"><div class="phys-section-title">慢性状态</div>${chronic}</div>` : ""}
    </div>`;
  }).join("");
}

function renderTimelinePanel() {
  const listEl = $("charTimelineList");
  const countEl = $("timelineTabCount");
  if (!listEl) return;
  const timelines = state.world?.character_personal_timelines || [];
  const totalEvents = timelines.reduce((s, tl) => s + (tl.events || []).length, 0);
  if (countEl) countEl.textContent = totalEvents ? `(${totalEvents})` : "";

  if (!totalEvents) {
    listEl.innerHTML = `<div class="knowledge-empty">
      <span class="ms knowledge-empty-icon">timeline</span>
      <p class="muted">暂无个人时间线事件</p>
      <p class="muted tiny">生成章节后系统自动检测，或点击「从已有章节提取」扫描历史章节。</p>
    </div>`;
    return;
  }

  const chars = state.world?.characters?.entities || [];
  const charMap = {};
  chars.forEach(c => {
    const id = typeof c === "object" ? (c.id || "") : String(c);
    charMap[id] = typeof c === "object" ? (c.name || id) : id;
  });

  listEl.innerHTML = timelines.map(tl => {
    const cname = charMap[tl.character_id] || tl.character_id;
    const sorted = (tl.events || []).slice().sort((a, b) => {
      const ao = a.chapter || ""; const bo = b.chapter || "";
      return ao.localeCompare(bo) || (a.relative_timing || "").localeCompare(b.relative_timing || "");
    });
    const eventCards = sorted.map(e => {
      const knownNames = (e.known_by || []).map(kid => charMap[kid] || kid).filter(Boolean).join("、");
      return `<div class="timeline-event">
        <div class="timeline-event-dot"></div>
        <div class="timeline-event-body">
          <div class="timeline-event-head">
            <span class="timeline-event-ch">${escapeHtml(e.chapter)}</span>
            <span class="muted tiny">${escapeHtml(e.relative_timing || "期间")}</span>
          </div>
          <p class="timeline-event-text">${escapeHtml(e.event)}</p>
          ${e.significance ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">意义</span>${escapeHtml(e.significance)}</div>` : ""}
          ${knownNames ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">已知者</span>${escapeHtml(knownNames)}</div>` : ""}
          ${(e.linked_events || []).length > 0 ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">关联</span>${escapeHtml(e.linked_events.join("、"))}</div>` : ""}
        </div>
      </div>`;
    }).join("");

    return `<div class="phys-card">
      <div class="phys-card-head">
        <span class="ms">timeline</span>
        <strong>${escapeHtml(cname)}</strong>
        <span class="muted tiny">${sorted.length} 个事件</span>
      </div>
      <div class="timeline-track">${eventCards}</div>
    </div>`;
  }).join("");
}

async function extractAllKnowledge() {
  if (!state.world?.meta?.id) return;
  const btn = $("btnExtractAllKnowledge");
  if (btn) { btn.disabled = true; btn.textContent = "正在提取…"; }
  try {
    const wid = state.world.meta.id;
    let kTotal = 0, dTotal = 0, pTotal = 0;

    // Run sequentially — each call modifies the world, must pick up prior changes
    const kRes = await api(`/api/worlds/${wid}/knowledge-graph/extract-all`, { method: "POST" });
    state.world = kRes.world;
    kTotal = kRes.total_new || 0;
    btn.textContent = `知识 ${kTotal}…`;

    const dRes = await api(`/api/worlds/${wid}/decisions/extract-all`, { method: "POST" });
    state.world = dRes.world;
    dTotal = dRes.total_new || 0;
    btn.textContent = `决策 ${dTotal}…`;

    // Physical state extraction: scan all non-planned chapters
    const pRes = await api(`/api/worlds/${wid}/physical-states/extract-all`, { method: "POST" });
    state.world = pRes.world || state.world;
    pTotal = pRes.total_new || 0;
    btn.textContent = `身体 ${pTotal}…`;

    const tRes = await api(`/api/worlds/${wid}/personal-timelines/extract-all`, { method: "POST" });
    state.world = tRes.world || state.world;
    const tTotal = tRes.total_new || 0;
    btn.textContent = `时间线 ${tTotal}…`;

    const aRes = await api(`/api/worlds/${wid}/aftermaths/extract-all`, { method: "POST" });
    state.world = aRes.world || state.world;
    const aTotal = aRes.total_new || 0;

    storyMetaToForm();
    renderDecisionsPanel();
    renderPhysicalStatesPanel();
    renderTimelinePanel();
    renderSpeechPanel();
    renderAftermathPanel();

    const parts = [];
    if (kTotal > 0) parts.push(`${kTotal} 条知识`);
    if (dTotal > 0) parts.push(`${dTotal} 个决策`);
    if (pTotal > 0) parts.push(`${pTotal} 个状态`);
    if (tTotal > 0) parts.push(`${tTotal} 个时间线`);
    if (aTotal > 0) parts.push(`${aTotal} 个后遗症`);
    toast(parts.length > 0 ? `已提取 ${parts.join(" + ")}` : "未发现新的内容");
  } catch (e) {
    toast("提取失败：" + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<span class="ms" aria-hidden="true">auto_awesome</span>从已有章节提取'; }
  }
}

function renderSpeechPanel() {
  const listEl = $("charSpeechList");
  const countEl = $("speechTabCount");
  if (!listEl) return;
  const entities = state.world?.characters?.entities || [];
  const withProfiles = entities.filter(e => e && typeof e === "object" && e.speech_profile && typeof e.speech_profile === "object" && Object.keys(e.speech_profile).length > 0);
  if (countEl) countEl.textContent = withProfiles.length ? `(${withProfiles.length})` : "";

  const SENT_OPTS = ["mixed","short","medium","long"];
  const EXPR_OPTS = ["direct","indirect","suppressed","explosive","sarcastic"];
  const CONF_OPTS = ["faces_it","deflects","withdraws","escalates"];
  const EXPR_LABELS = { direct:"直接表达", indirect:"间接暗示", suppressed:"压抑型", explosive:"爆发型", sarcastic:"讽刺型" };
  const CONF_LABELS = { faces_it:"直接面对", deflects:"转移话题", withdraws:"沉默离开", escalates:"升级冲突" };
  const SENT_LABELS = { short:"短句", medium:"中等", long:"长句", mixed:"混合" };

  if (!entities.length) {
    listEl.innerHTML = '<p class="muted tiny">暂无角色数据。</p>';
    return;
  }

  listEl.innerHTML = entities.map(e => {
    if (!e || typeof e !== "object") return "";
    const sp = (e.speech_profile && typeof e.speech_profile === "object") ? e.speech_profile : {};
    const cid = e.id || "";
    const sentSel = SENT_OPTS.map(v => `<option value="${v}"${(sp.avg_sentence_length||"mixed")===v?" selected":""}>${SENT_LABELS[v]||v}</option>`).join("");
    const exprSel = EXPR_OPTS.map(v => `<option value="${v}"${(sp.emotional_expression||"direct")===v?" selected":""}>${EXPR_LABELS[v]||v}</option>`).join("");
    const confSel = CONF_OPTS.map(v => `<option value="${v}"${(sp.confrontation_style||"faces_it")===v?" selected":""}>${CONF_LABELS[v]||v}</option>`).join("");

    return `<div class="speech-card" data-char-id="${escapeAttr(cid)}">
      <div class="speech-card-head">
        <span class="ms">record_voice_over</span>
        <strong>${escapeHtml(e.name || cid)}</strong>
        <button type="button" class="ghost tiny speech-save-btn" data-char-id="${escapeAttr(cid)}">保存风格</button>
      </div>
      <div class="speech-edit-grid">
        <label class="muted tiny">句式 <select class="speech-edit-sent">${sentSel}</select></label>
        <label class="muted tiny">情绪表达 <select class="speech-edit-expr">${exprSel}</select></label>
        <label class="muted tiny">对抗风格 <select class="speech-edit-conf">${confSel}</select></label>
        <label class="muted tiny">啰嗦度 <select class="speech-edit-verb"><option value="normal"${(sp.verbosity||"normal")==="normal"?" selected":""}>正常</option><option value="terse"${sp.verbosity==="terse"?" selected":""}>简短</option><option value="verbose"${sp.verbosity==="verbose"?" selected":""}>啰嗦</option></select></label>
      </div>
      <div class="speech-edit-row">
        <label class="muted tiny">口头禅（逗号分隔）<input type="text" class="speech-edit-tics" value="${escapeAttr((sp.verbal_tics||[]).join("，"))}" placeholder="啧，……算了" /></label>
      </div>
      <div class="speech-edit-row">
        <label class="muted tiny">填充词（逗号分隔）<input type="text" class="speech-edit-filler" value="${escapeAttr((sp.filler_words||[]).join("，"))}" placeholder="那个……，嗯" /></label>
      </div>
      <div class="speech-edit-row">
        <label class="muted tiny">回避话题（逗号分隔）<input type="text" class="speech-edit-avoid" value="${escapeAttr((sp.avoidance_topics||[]).join("，"))}" placeholder="家庭，过去" /></label>
      </div>
      <div class="speech-edit-row">
        <label class="muted tiny">沉默含义 <input type="text" class="speech-edit-silence" value="${escapeAttr(sp.silence_meaning||"")}" placeholder="在思考，不是冷漠" /></label>
        <label class="muted tiny">压力下 <input type="text" class="speech-edit-stress" value="${escapeAttr(sp.under_stress||"")}" placeholder="开始说短句" /></label>
      </div>
    </div>`;
  }).join("");

  // Wire save buttons
  listEl.querySelectorAll(".speech-save-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const cid = btn.dataset.charId;
      const card = btn.closest(".speech-card");
      if (!card) return;
      const ent = (state.world?.characters?.entities || []).find(e => (typeof e === "object" ? e.id : "") === cid);
      if (!ent) return;
      if (!ent.speech_profile || typeof ent.speech_profile !== "object") ent.speech_profile = {};
      ent.speech_profile.avg_sentence_length = card.querySelector(".speech-edit-sent")?.value || "mixed";
      ent.speech_profile.emotional_expression = card.querySelector(".speech-edit-expr")?.value || "direct";
      ent.speech_profile.confrontation_style = card.querySelector(".speech-edit-conf")?.value || "faces_it";
      ent.speech_profile.verbosity = card.querySelector(".speech-edit-verb")?.value || "normal";
      ent.speech_profile.verbal_tics = (card.querySelector(".speech-edit-tics")?.value || "").split(/[,，]/).map(s => s.trim()).filter(Boolean);
      ent.speech_profile.filler_words = (card.querySelector(".speech-edit-filler")?.value || "").split(/[,，]/).map(s => s.trim()).filter(Boolean);
      ent.speech_profile.avoidance_topics = (card.querySelector(".speech-edit-avoid")?.value || "").split(/[,，]/).map(s => s.trim()).filter(Boolean);
      ent.speech_profile.silence_meaning = card.querySelector(".speech-edit-silence")?.value || "";
      ent.speech_profile.under_stress = card.querySelector(".speech-edit-stress")?.value || "";
      setDirty(true);
      toast(`${ent.name || cid} 语言风格已更新`);
    });
  });
}

function renderAftermathPanel() {
  const listEl = $("charAftermathList");
  const countEl = $("aftermathTabCount");
  if (!listEl) return;
  const aftermaths = state.world?.character_aftermaths || [];
  const active = aftermaths.filter(a => a.current_status === "active");
  if (countEl) countEl.textContent = active.length ? `(${active.length})` : "";

  if (!active.length) {
    listEl.innerHTML = `<div class="knowledge-empty">
      <span class="ms knowledge-empty-icon">psychology_alt</span>
      <p class="muted">暂无活跃后遗症</p>
      <p class="muted tiny">角色经历重大事件后系统自动检测。</p>
    </div>`;
    return;
  }

  const FATIGUE = { rested:"精力充沛", tired:"疲惫", exhausted:"极度疲劳", collapse_imminent:"即将崩溃" };
  const chars = state.world?.characters?.entities || [];
  const charMap = {};
  chars.forEach(c => { const id = typeof c === "object" ? (c.id || "") : String(c); charMap[id] = typeof c === "object" ? (c.name || id) : id; });

  listEl.innerHTML = active.map(a => {
    const cname = charMap[a.character_id] || a.character_id;
    return `<div class="aftermath-card ${a.intensity > 7 ? 'aftermath-card--severe' : ''}">
      <div class="aftermath-card-head">
        <span class="ms">psychology_alt</span>
        <strong>${escapeHtml(cname)}</strong>
        <span class="aftermath-badge">强度 ${a.intensity}/10</span>
      </div>
      <div class="aftermath-intensity"><div class="aftermath-intensity-fill" style="width:${a.intensity*10}%;background:${a.intensity>7?'#dc2626':a.intensity>4?'#ea580c':'#f59e0b'}"></div></div>
      <p class="aftermath-source">📖 ${escapeHtml(a.source_event)}（${escapeHtml(a.source_chapter)}）</p>
      ${a.symptoms.length ? `<div class="speech-tags">${a.symptoms.map(s => `<span class="speech-chip speech-chip--aftermath">${escapeHtml(s)}</span>`).join(" ")}</div>` : ""}
      ${a.trigger_conditions.length ? `<div class="speech-tags"><span class="speech-label">触发</span>${a.trigger_conditions.map(t => `<span class="speech-chip speech-chip--avoid">${escapeHtml(t)}</span>`).join(" ")}</div>` : ""}
    </div>`;
  }).join("");
}

function renderDecisionsPanel() {
  const listEl = $("charDecisionsList");
  const countEl = $("decisionsTabCount");
  if (!listEl) return;
  const decisions = state.world?.character_decisions || [];
  if (countEl) countEl.textContent = decisions.length ? `(${decisions.length})` : "";

  if (!decisions.length) {
    listEl.innerHTML = `<div class="knowledge-empty">
      <span class="ms knowledge-empty-icon">tactic</span>
      <p class="muted">暂无关键决策</p>
      <p class="muted tiny">生成章节后系统自动检测，或点击「从已有章节提取」扫描历史章节。</p>
    </div>`;
    return;
  }

  const TYPE_LABELS = {
    moral_choice: "道德抉择", trust_decision: "信任决策", strategic_choice: "战略选择",
    self_revelation: "自我揭示", relationship_choice: "关系决策", sacrifice: "牺牲",
  };
  const TYPE_COLORS = {
    moral_choice: "#7c3aed", trust_decision: "#2563eb", strategic_choice: "#ea580c",
    self_revelation: "#0d9488", relationship_choice: "#db2777", sacrifice: "#dc2626",
  };
  const VERDICT_LABELS = {
    pending: "待定", proved_right: "已证实正确", proved_wrong: "已证实错误",
    ambiguous: "模糊", irrelevant: "已无关",
  };

  const chars = state.world?.characters?.entities || [];
  const charMap = {};
  chars.forEach(c => {
    const id = typeof c === "object" ? (c.id || "") : String(c);
    charMap[id] = typeof c === "object" ? (c.name || id) : id;
  });

  listEl.innerHTML = decisions.slice().reverse().map(d => {
    const cname = charMap[d.character_id] || d.character_id;
    const opts = (d.options_considered || []).join(" | ");
    return `<div class="decision-card">
      <div class="decision-card-top">
        <span class="knowledge-card-cat" style="background:${TYPE_COLORS[d.decision_type] || '#888'}11;color:${TYPE_COLORS[d.decision_type] || '#888'};border-color:${TYPE_COLORS[d.decision_type] || '#888'}33">
          <span class="ms">tactic</span>${TYPE_LABELS[d.decision_type] || d.decision_type}
        </span>
        <span class="decision-verdict">${VERDICT_LABELS[d.outcome_verdict] || d.outcome_verdict}</span>
      </div>
      <p class="knowledge-card-topic">${escapeHtml(d.summary)}</p>
      <div class="knowledge-card-meta">
        <span>🧑 ${escapeHtml(cname)}</span>
        <span>📖 ${escapeHtml(d.chapter)}</span>
        ${d.option_chosen ? `<span>✅ ${escapeHtml(d.option_chosen)}</span>` : ""}
      </div>
      ${d.stated_reason && d.stated_reason !== d.actual_reason
        ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">表面理由</span>${escapeHtml(d.stated_reason)}</div>
           <div class="knowledge-card-detail" style="color:#7c3aed"><span class="knowledge-detail-label">真实动机</span>${escapeHtml(d.actual_reason)}</div>`
        : (d.stated_reason ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">理由</span>${escapeHtml(d.stated_reason)}</div>` : "")}
      ${opts ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">备选</span>${escapeHtml(opts)}</div>` : ""}
      ${(d.immediate_consequences || []).length > 0 ? `<div class="knowledge-card-detail"><span class="knowledge-detail-label">后果</span>${escapeHtml(d.immediate_consequences.join("；"))}</div>` : ""}
    </div>`;
  }).join("");
}

async function refreshTokenUsagePanel() {
  if (!state.world?.meta?.id) return;
  const totalEl = $("ctxTokenTotal");
  const body = $("ctxTokenBody");
  if (!body) return;

  try {
    const data = await api(`/api/worlds/${state.world.meta.id}/token-usage`);
    const t = data.total || {};
    const s = data.session || {};
    const p = data.persisted || {};

    if (totalEl) {
      totalEl.textContent = `${(t.total_tokens || 0).toLocaleString()} tokens`;
    }

    // Show persisted by_label (cumulative) or session by_label as fallback
    const persistedLabels = p.by_label || {};
    const byLabel = Object.keys(persistedLabels).length > 0 ? persistedLabels : (s.by_label || {});
    const labelRows = Object.keys(byLabel).length > 0
      ? Object.entries(byLabel).map(([label, counts]) => {
          const l = label.length > 28 ? label.slice(0, 28) + "…" : label;
          return `<div class="ctx-token-row ctx-token-row--label">
            <span title="${escapeHtml(label)}">${escapeHtml(l)}</span>
            <span>${(counts.total_tokens || 0).toLocaleString()}</span>
          </div>`;
        }).join("")
      : "";

    const pct = t.total_tokens > 0
      ? Math.round(t.prompt_tokens / t.total_tokens * 100)
      : 50;

    const chapters = p.by_chapter || {};
    const chRows = Object.keys(chapters).length > 0
      ? Object.entries(chapters).slice(-5).reverse().map(([chId, chData]) => {
          const ch = state.world?.story?.chapters?.find(c => c.id === chId);
          const chTitle = ch?.title || chId;
          return `<div class="ctx-token-row ctx-token-row--ch">
            <span>${escapeHtml(String(chTitle).slice(0, 24))}</span>
            <span>${(chData.total_tokens || 0).toLocaleString()}</span>
          </div>`;
        }).join("")
      : "";

    body.innerHTML = `
      <div class="ctx-token-grid">
        <div class="ctx-token-row">
          <span>Prompt</span>
          <span>${(t.prompt_tokens || 0).toLocaleString()}</span>
        </div>
        <div class="ctx-token-row">
          <span>Completion</span>
          <span>${(t.completion_tokens || 0).toLocaleString()}</span>
        </div>
        <div class="ctx-token-row ctx-token-row--total">
          <span>合计</span>
          <span>${(t.total_tokens || 0).toLocaleString()}</span>
        </div>
      </div>
      <div class="ctx-token-bar">
        <div class="ctx-token-bar-prompt" style="width:${pct}%"></div>
        <div class="ctx-token-bar-compl" style="width:${100-pct}%"></div>
      </div>
      <p class="muted tiny" style="margin-top:6px">
        当前会话：${(s.total_tokens || 0).toLocaleString()} tokens
      </p>
      ${labelRows ? `<div class="ctx-token-section-title">按任务</div><div class="ctx-token-grid">${labelRows}</div>` : ""}
      ${chRows ? `<div class="ctx-token-section-title">按章节</div><div class="ctx-token-grid">${chRows}</div>` : ""}
    `;
  } catch (_) {
    if (body) body.innerHTML = `<p class="muted tiny">加载失败</p>`;
  }
}

init().catch((e) => toast("初始化失败：" + e.message));
initP2Enhancements();
