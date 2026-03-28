// interceptor.js — runs in PAGE context (not extension context).
// Injected via a <script> tag by content.js so it can patch window.fetch
// before any page code runs.
//
// Gemini streams responses as chunks. Each chunk is a text/plain payload
// that looks like:
//
//   )]}'\n[[["<json-string>",1]]]
//
// The outer )]}' prefix is an XSSI guard. We strip it and parse the rest.
// The actual conversation content is buried inside a nested array; we
// forward the raw chunk to content.js for collection and later inspection.

(function () {
  const TARGET_PATH = "/_/BardChatUi/data/";
  const MSG_TYPE = "gemini-slurp-capture";

  const origFetch = window.fetch.bind(window);

  window.fetch = async function (...args) {
    const request = args[0];
    const url =
      typeof request === "string"
        ? request
        : request instanceof Request
        ? request.url
        : String(request);

    const response = await origFetch(...args);

    if (url.includes(TARGET_PATH)) {
      // Clone so we don't consume the body the page needs.
      const clone = response.clone();
      clone.text().then((body) => {
        window.postMessage(
          {
            type: MSG_TYPE,
            url,
            body,
            timestamp: Date.now(),
          },
          "*"
        );
      });
    }

    return response;
  };

  console.debug("[gemini-slurp] fetch interceptor installed");
})();
