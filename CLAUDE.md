# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working
with code in this repository.

## Style

- Wrap all prose (Markdown files, comments) at **80 characters per line**.

## What This Is

Two complementary Python utilities for exporting Gemini conversation
history to Obsidian-friendly Markdown files. No external dependencies —
both use only the Python standard library.

- **`gemini-slurp.py`** — parses a Google Takeout archive (ZIP or
  unpacked directory). Covers all historical activity but groups turns
  into conversations heuristically (time-gap based).
- **`gemini-slurp-browser.py`** — parses a JSON file captured by the
  `gemini-export-extension/gemini-slurp.user.js` userscript. Requires
  clicking each conversation in the browser, but produces real
  conversation IDs, titles, and boundaries with no heuristics.

## Running

```bash
# Takeout approach
python gemini-slurp.py [~/Downloads/Takeout] \
    [--obsidian-chat-path PATH] [--gap-minutes N] [--force]

# Browser capture approach
python gemini-slurp-browser.py [capture.json] \
    [--obsidian-chat-path PATH] [--force]
```

## Architecture — gemini-slurp.py (Takeout)

- `find_activity_html(takeout_path)` — locates `MyActivity.html` inside
  a Takeout ZIP or unpacked directory
- `parse_activity_cards(html)` — regex-based parser that splits the HTML
  into outer-cell blocks and extracts `prompt`, `response_html`, and
  `timestamp` from each "Prompted" card; skips Canvas/Used/other types
- `html_to_markdown(html)` — best-effort conversion of response HTML to
  Markdown (headings, bold, italic, code, lists)
- `group_into_conversations(cards, gap_minutes)` — sorts cards
  chronologically and splits into conversations on gaps > `gap_minutes`
- `write_conversation(output_dir, turns, force)` — writes a `.md` file
  with YAML frontmatter; protects manually edited files via `sync_hash`

Output filename format: `<YYYYMMDD_HHMM>_<prompt_slug>.md`

## Architecture — gemini-slurp-browser.py (browser capture)

The userscript (`gemini-slurp.user.js`) monkey-patches `window.fetch`
and `XMLHttpRequest` on gemini.google.com, intercepts API responses, and
exports them as a JSON array on demand.

Two RPC calls are captured and parsed:

- **`MaZiqc`** (LIST_CHATS) — fires on page load; returns a paginated
  list of all conversations with IDs, titles, and timestamps.
- **`hNvQHb`** (LOAD_CONVERSATION) — fires each time you click a chat;
  returns all turns for that conversation in one response.

Parser functions:

- `_parse_batchexecute(raw)` — decodes Google's batchexecute wire
  format: `)]}'\n\n<len>\n<json>\n<len>\n<json>...`. Uses
  `json.JSONDecoder.raw_decode()` rather than trusting the declared
  byte count (which is occasionally off by a byte or two).
- `_find_wrb(chunks, rpcid)` — extracts the inner payload string for a
  given RPC id from parsed chunks and JSON-decodes it.
- `parse_conv_list(captures)` — collects conversation metadata from all
  `MaZiqc` captures; returns `conv_id → {title, timestamp}`.
- `parse_conv_turns(captures)` — collects turns from all `hNvQHb`
  captures; returns `conv_id → [{timestamp, user, response}]`. Turn
  structure is a positional array: `[0]` back-ref IDs, `[2]` user
  parts, `[3]` model candidates, timestamp at a varying position.
- `write_conversation(...)` — identical sync_hash protection and output
  format as `gemini-slurp.py`; adds `conversation_id` and `title` to
  frontmatter.

Output filename format: `<YYYYMMDD_HHMM>_<title_slug>.md`

## Key implementation notes

- **Regex parser, not HTMLParser:** The Takeout HTML has unclosed tags
  causing final depth ~1688 in testing. Depth-based tracking in
  `HTMLParser` fails; regex splitting on `outer-cell` div boundaries is
  reliable.
- **sync_hash:** SHA-256 of file content excluding the `sync_hash:` line
  itself (first 16 hex chars). Written into frontmatter. On re-run, if
  file content doesn't match its stored hash, the file is skipped (user
  has edited it). `--force` overrides.
- **Timestamp format (Takeout):** `Mar 27, 2026, 12:09:53\u202fPM EDT`
  — note the narrow no-break space (`\u202f`) between time and AM/PM.
- **Footer stripping (Takeout):** Each card ends with a
  `<b>Products:</b> / Gemini Apps / Why is this here?` footer in a
  separate caption div; stripped by splitting on `<b>Products:</b>`
  before writing.
- **batchexecute byte counts:** The declared chunk length in the wire
  format is occasionally 1–2 bytes over the actual JSON length (the
  extra bytes are the leading characters of the next length line).
  `raw_decode()` handles this correctly.
- **`MaZiqc` requires a real browser session:** The LIST_CHATS RPC
  returned null when called from the reverse-engineered `gemini-webapi`
  library but works correctly when intercepted from a live browser
  session with real cookies.

## Tests

```bash
pip install pytest
python -m pytest test_gemini_slurp.py -v
```

49 tests covering: timestamp parsing, HTML card parsing,
HTML-to-Markdown conversion, conversation grouping, file writing,
idempotency, manual-edit protection, sync_hash, Takeout file discovery
(ZIP and directory), and end-to-end round-trips.

Tests for `gemini-slurp-browser.py` are not yet written.

## Approaches considered and rejected

See README.md for the full rationale. In brief:

1. **Takeout JSON** — Google no longer exports this format.
2. **`gemini-webapi` reverse-engineered API** — `LIST_CHATS` RPC
   returned null in testing; no way to enumerate conversations. Fragile
   external dependency.
3. **Takeout HTML (current)** — Full content available; pure stdlib;
   grouping is heuristic but acceptable.
4. **Browser userscript (current)** — Intercepts live API calls; real
   conversation IDs and titles; requires clicking each chat once.
