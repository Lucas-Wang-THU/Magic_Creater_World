/** Shared utility functions used across the application. */

import { state } from "./state.js";

/** Shorthand for document.getElementById */
export const $ = (id) => document.getElementById(id);

/** Shorthand for document.querySelectorAll */
export const $$ = (sel, root) => (root || document).querySelectorAll(sel);

/** Show a toast notification (auto-hides after 2.8s). */
export function toast(msg) {
  const t = $("toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2800);
}

/** Escape HTML special characters. */
export function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Escape a value for use in an HTML attribute. */
export function escapeAttr(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Format an ISO date string to a readable locale string. */
export function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/** Simple debounce helper. */
export function debounce(fn, ms = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/** Mark or clear the global dirty flag. */
export function setDirty(v) {
  state.dirty = v;
  const el = $("saveStatus");
  if (!el) return;
  const icon = v ? "edit_note" : "cloud_done";
  const label = v ? "有未保存更改" : "已同步";
  el.innerHTML = `<span class="ms status-ic" aria-hidden="true">${icon}</span>${label}`;
  el.classList.toggle("dirty", v);
}

/** Check if there are unsaved changes. */
export function isDirty() {
  return state.dirty;
}

/** Clear the dirty flag. */
export function clearDirty() {
  setDirty(false);
}

/** Generic fetch wrapper for the backend API. */
export async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { _raw: text };
  }
  if (!r.ok) {
    const detail = data.detail ?? data._raw ?? r.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}
