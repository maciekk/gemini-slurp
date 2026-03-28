// content.js — runs in the extension's isolated world.
//
// 1. Injects interceptor.js into the PAGE context (so it can patch
//    window.fetch before Gemini's own scripts run).
// 2. Listens for postMessage events from the interceptor.
// 3. Collects raw API chunks in memory.
// 4. Injects a floating "Export" button into the Gemini UI.
//    Clicking it downloads all collected chunks as a JSON file for
//    offline inspection / further parsing.
//
// The raw Gemini streaming format looks like:
//
//   )]}'\n[[["<escaped-json>",1]]]
//
// We strip the )]}' XSSI guard and JSON-parse what remains so that the
// downloaded file contains proper JSON arrays rather than escaped strings.
// Further parsing of the nested structure is left to a separate script
// once we know what the real API returns.

(function () {
  // ── 1. Inject interceptor into page context ──────────────────────────
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("interceptor.js");
  // Prepend to <html> so it runs before any page scripts.
  (document.documentElement || document.head || document.body).prepend(script);

  // ── 2. Collect captured chunks ───────────────────────────────────────
  const captures = [];

  window.addEventListener("message", (event) => {
    if (event.data?.type !== "gemini-slurp-capture") return;

    const { url, body, timestamp } = event.data;
    const parsed = parseGeminiChunk(body);
    captures.push({ url, timestamp, raw: body, parsed });

    console.debug(
      `[gemini-slurp] captured ${captures.length} chunk(s) from ${url}`
    );
  });

  // ── 3. Parse helper ──────────────────────────────────────────────────
  function parseGeminiChunk(raw) {
    // Strip the )]}' XSSI guard that Gemini prepends.
    const stripped = raw.replace(/^\s*\)\]\}'\s*/, "");
    // Streaming responses are sent as multiple chunks concatenated in a
    // single body; split on the guard boundary.
    const chunks = stripped.split(/\)\]\}'\s*/);
    const results = [];
    for (const chunk of chunks) {
      const trimmed = chunk.trim();
      if (!trimmed) continue;
      try {
        results.push(JSON.parse(trimmed));
      } catch {
        // Keep raw string if JSON parse fails — still useful for debugging.
        results.push(trimmed);
      }
    }
    return results.length === 1 ? results[0] : results;
  }

  // ── 4. Inject Export button ──────────────────────────────────────────
  function injectButton() {
    if (document.getElementById("gemini-slurp-btn")) return;

    const btn = document.createElement("button");
    btn.id = "gemini-slurp-btn";
    btn.textContent = "⬇ Export";
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
          "[gemini-slurp] No API calls captured yet.\n" +
            "Send a message to Gemini first, then click Export."
        );
        return;
      }

      const payload = JSON.stringify(captures, null, 2);
      const blob = new Blob([payload], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `gemini-slurp-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);

      console.debug(
        `[gemini-slurp] exported ${captures.length} chunk(s)`
      );
    });

    document.body.appendChild(btn);
  }

  // Gemini is a SPA — body may not exist yet at document_start.
  if (document.body) {
    injectButton();
  } else {
    document.addEventListener("DOMContentLoaded", injectButton);
  }
})();
