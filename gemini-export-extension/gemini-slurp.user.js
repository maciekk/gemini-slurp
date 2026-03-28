// ==UserScript==
// @name         Gemini Slurp
// @namespace    https://github.com/your-repo/gemini-slurp
// @version      0.2
// @description  Intercept and export Gemini conversations to JSON
// @match        https://gemini.google.com/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  // Broad filter — capture anything going to gemini.google.com that
  // looks like an API/RPC call. We log everything and let the export
  // reveal the real endpoint paths.
  const API_PATTERN = /\/(data|rpc|generate|stream|lamda|BardChatUi)/i;

  const captures = [];

  function record(url, body, method) {
    const parsed = parseBody(body);
    captures.push({ url, method, timestamp: Date.now(), raw: body, parsed });
    updateButton();
    console.debug(`[gemini-slurp] ${captures.length} capture(s) — ${url}`);
  }

  // ── 1. Patch fetch ────────────────────────────────────────────────────
  const origFetch = window.fetch.bind(window);
  window.fetch = async function (...args) {
    const req = args[0];
    const url =
      typeof req === "string"
        ? req
        : req instanceof Request
        ? req.url
        : String(req);
    const method = (args[1]?.method || (req instanceof Request ? req.method : "GET")).toUpperCase();

    const response = await origFetch(...args);

    if (API_PATTERN.test(url)) {
      response.clone().text().then((body) => record(url, body, method));
    }

    return response;
  };

  // ── 2. Patch XMLHttpRequest ───────────────────────────────────────────
  const OrigXHR = window.XMLHttpRequest;
  window.XMLHttpRequest = function () {
    const xhr = new OrigXHR();
    let _url = "";
    let _method = "GET";

    const origOpen = xhr.open.bind(xhr);
    xhr.open = function (method, url, ...rest) {
      _url = url;
      _method = method.toUpperCase();
      return origOpen(method, url, ...rest);
    };

    xhr.addEventListener("load", function () {
      if (API_PATTERN.test(_url)) {
        record(_url, xhr.responseText, _method);
      }
    });

    return xhr;
  };

  // ── 3. Parse helper ───────────────────────────────────────────────────
  function parseBody(raw) {
    if (!raw) return null;
    // Strip )]}' XSSI guard, try JSON parse.
    const stripped = raw.replace(/^\s*\)\]\}'\s*/, "");
    try {
      return JSON.parse(stripped);
    } catch {
      // Streaming: multiple chunks separated by the guard.
      const results = [];
      for (const chunk of stripped.split(/\)\]\}'\s*/)) {
        const t = chunk.trim();
        if (!t) continue;
        try { results.push(JSON.parse(t)); }
        catch { results.push(t); }
      }
      return results.length === 0 ? raw : results.length === 1 ? results[0] : results;
    }
  }

  // ── 4. Export button ──────────────────────────────────────────────────
  let btn = null;

  function updateButton() {
    if (btn) btn.textContent = `⬇ Export (${captures.length})`;
  }

  function injectButton() {
    if (document.getElementById("gemini-slurp-btn")) return;

    btn = document.createElement("button");
    btn.id = "gemini-slurp-btn";
    btn.textContent = `⬇ Export (0)`;
    Object.assign(btn.style, {
      position: "fixed",
      bottom: "24px",
      right: "24px",
      zIndex: "99999",
      padding: "10px 18px",
      background: "#1a73e8",
      color: "#fff",
      border: "none",
      borderRadius: "8px",
      cursor: "pointer",
      fontSize: "14px",
      fontFamily: "sans-serif",
      boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
    });

    btn.addEventListener("click", () => {
      if (captures.length === 0) {
        alert(
          "[gemini-slurp] Nothing captured yet.\n" +
            "Check the browser console for [gemini-slurp] messages.\n" +
            "If none appear, the script may not share the page JS context."
        );
        return;
      }
      const blob = new Blob([JSON.stringify(captures, null, 2)], {
        type: "application/json",
      });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `gemini-slurp-${Date.now()}.json`;
      a.click();
    });

    document.body.appendChild(btn);
  }

  if (document.body) {
    injectButton();
  } else {
    document.addEventListener("DOMContentLoaded", injectButton);
  }

  console.debug("[gemini-slurp] v0.2 loaded — patching fetch + XHR");
})();
