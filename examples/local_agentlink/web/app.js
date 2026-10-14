/* Prompt model, authoritative snapshot and display cursor have separate lifetimes. */
"use strict";
const $ = (id) => document.getElementById(id);
const uiToken = document.querySelector('meta[name="agentlink-ui"]').content;
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
let epoch = null, cursor = 0, visibleAfter = 0, rows = [], snapshot = null;
let promptModel = "", promptCursor = 0, promptTimer = null, promptDelay = null;
let dirty = false, stale = false, follow = true, busy = false, gap = false;
let copiedTimer = null;
let pollVersion = 0;
const labels = {waiting: "等待连接", active: "正在接管", finished: "已完成", cancelled: "已取消", disconnected: "连接断开"};

function motionAllowed() { return $("motion").checked && !reduced.matches; }
function stopTyping() {
  clearTimeout(promptDelay); clearInterval(promptTimer);
  promptDelay = promptTimer = null;
}
function reveal() {
  stopTyping();
  if (!dirty) { $("prompt").value = promptModel; promptCursor = Array.from(promptModel).length; }
}
function startTyping() {
  stopTyping();
  if (dirty || !motionAllowed()) { reveal(); return; }
  const chars = Array.from(promptModel);
  promptTimer = setInterval(() => {
    if (document.hidden) return;
    promptCursor = Math.min(chars.length, promptCursor + 60);
    $("prompt").value = chars.slice(0, promptCursor).join("");
    if (promptCursor === chars.length) stopTyping();
  }, 33);
}
function generate(animate = true) {
  if (!snapshot) return;
  stopTyping(); dirty = stale = false;
  promptModel = snapshot.prompt; promptCursor = 0;
  $("prompt-note").textContent = ""; $("copy").disabled = false;
  if (!animate || !motionAllowed()) { reveal(); return; }
  $("prompt").value = "少女祈祷中...";
  promptDelay = setTimeout(() => { $("prompt").value = ""; startTyping(); }, 600);
}
function renderLog() {
  const log = $("log"), oldScroll = log.scrollTop;
  const nodes = rows.map(event => {
    const row = document.createElement("div"); row.className = "event" + (event.phase === "failed" ? " failed" : "");
    const strong = document.createElement("strong"); strong.textContent = `${event.operation} · ${event.phase}`;
    const time = document.createElement("time"); time.textContent = event.time.slice(11, 19);
    const p = document.createElement("p"); p.textContent = event.message;
    if (Object.keys(event.details).length) p.textContent += "\n" + JSON.stringify(event.details);
    row.append(strong, time, p); return row;
  });
  log.replaceChildren(...nodes);
  if (!nodes.length) { const p = document.createElement("p"); p.textContent = "等待新的操作记录"; log.append(p); }
  log.scrollTop = follow ? log.scrollHeight : oldScroll;
  $("log-note").textContent = gap ? "部分日志已超出保留窗口。当前显示最新记录。" : "清空显示保留原始日志、工程结果和撤回记录。";
}
function accept(next) {
  const previous = snapshot;
  snapshot = next;
  document.body.dataset.state = next.status;
  $("status").textContent = labels[next.status] + (next.agentName ? ` · ${next.agentName}` : "");
  $("identity").textContent = `${next.agentName || "等待外部 Agent"} · 当前工程 demo · 会话 ${next.sessionId.slice(0, 8)}`;
  $("revision").textContent = `revision ${next.projectRevision}`;
  $("cancel").disabled = busy || next.status !== "active";
  $("new-session").disabled = busy || next.status === "active";
  $("reload").disabled = next.status !== "finished";
  $("progress").hidden = next.status === "waiting" || next.status === "cancelled";
  if (next.percent === null) { $("bar").removeAttribute("value"); $("percent").textContent = "未知进度"; }
  else { $("bar").value = next.percent; $("percent").textContent = `${next.percent}%`; }
  $("error").hidden = !(next.error || next.journal.error);
  $("error").textContent = next.error || next.journal.error || "";
  if (!previous) generate();
  else if (previous.sessionId !== next.sessionId) {
    if (dirty) { stale = true; reveal(); $("copy").disabled = true; $("prompt-note").textContent = "手工 Prompt 已过期，请重新生成。"; }
    else generate();
  } else if (previous.projectRevision !== next.projectRevision && !dirty) {
    promptModel = next.prompt; reveal();
  }
  if (epoch !== next.journal.epoch) {
    epoch = next.journal.epoch; cursor = visibleAfter = 0; rows = []; gap = false;
  }
  gap ||= next.journal.gap;
  let changed = false;
  for (const event of next.journal.events) {
    if (event.seq <= Math.max(cursor, visibleAfter)) continue;
    if (event.phase === "progress") {
      const i = rows.findIndex(row => row.sessionId === event.sessionId && row.operation === event.operation && row.phase === "progress");
      if (i >= 0) rows.splice(i, 1);
    }
    rows.push(event); changed = true;
  }
  cursor = Math.max(cursor, next.journal.seq);
  rows = rows.slice(-400);
  if (changed || !previous) renderLog();
  if (!previous || previous.projectRevision !== next.projectRevision) renderClips();
}
function renderClips() {
  $("clips").replaceChildren(...snapshot.clips.map(clip => {
    const div = document.createElement("div"); div.className = "clip";
    div.textContent = `${clip.name} · 轨道 ${clip.track} · ${clip.start}–${clip.end}s`;
    div.title = clip.runId ? `Agent runId: ${clip.runId}` : "用户已有片段"; return div;
  }));
}
async function fetchJSON(path, method = "GET") {
  const response = await fetch(path, {method, headers: {"X-AgentLink-UI": uiToken}, cache: "no-store"});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "请求失败");
  return result;
}
async function poll() {
  const version = pollVersion;
  try { if (!busy) { const next = await fetchJSON(`/snapshot?after=${cursor}&epoch=${encodeURIComponent(epoch || "")}`); if (version === pollVersion) accept(next); } }
  catch (error) { document.body.dataset.state = "disconnected"; $("status").textContent = labels.disconnected; $("error").hidden = false; $("error").textContent = error.message; }
  finally { setTimeout(poll, document.hidden ? 1000 : 333); }
}
async function action(path) {
  if (busy) return;
  ++pollVersion;
  busy = true;
  for (const id of ["cancel", "new-session", "cleanup"]) $(id).disabled = true;
  try { await fetchJSON(path, "POST"); accept(await fetchJSON(`/snapshot?after=${cursor}&epoch=${encodeURIComponent(epoch || "")}`)); }
  catch (error) { $("error").hidden = false; $("error").textContent = error.message; }
  finally { busy = false; $("cleanup").disabled = false; if (snapshot) { $("cancel").disabled = snapshot.status !== "active"; $("new-session").disabled = snapshot.status === "active"; } }
}
$("prompt").addEventListener("beforeinput", () => { reveal(); dirty = true; });
$("prompt").addEventListener("input", () => { dirty = true; });
$("regenerate").onclick = () => generate();
$("copy").onclick = async () => {
  if (stale) return;
  reveal();
  try { await navigator.clipboard.writeText(dirty ? $("prompt").value : promptModel); $("copy").textContent = "已复制";
    clearTimeout(copiedTimer); copiedTimer = setTimeout(() => $("copy").textContent = "复制完整 Prompt", 1500); }
  catch { $("prompt-note").textContent = "复制失败，请在文本框中全选并手动复制。"; }
};
$("clear").onclick = () => { visibleAfter = cursor; rows = []; gap = false; renderLog(); };
$("cleanup").onclick = () => action("/cleanup");
$("cancel").onclick = () => action("/cancel");
$("new-session").onclick = () => action("/new-session");
$("reload").onclick = () => { renderClips(); $("identity").textContent = "已重载 Core 当前结果 · 完成结果保留"; };
$("follow").onclick = () => { follow = !follow; $("follow").textContent = follow ? "暂停追随" : "恢复追随"; if (follow) $("log").scrollTop = $("log").scrollHeight; };
$("log").addEventListener("scroll", () => {
  if ($("log").scrollTop + $("log").clientHeight < $("log").scrollHeight - 20) { follow = false; $("follow").textContent = "恢复追随"; }
});
function motionChanged() { document.body.dataset.motion = String(motionAllowed()); if (!motionAllowed()) reveal(); }
$("motion").onchange = motionChanged; reduced.addEventListener("change", motionChanged);
document.addEventListener("visibilitychange", () => { document.body.dataset.hidden = String(document.hidden); });
window.addEventListener("pagehide", stopTyping);
motionChanged(); poll();

