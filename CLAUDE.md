# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A single-file Python utility (`gemini-slurp.py`) that exports Gemini conversation history from a Google Takeout archive into Obsidian-friendly Markdown files. No external dependencies — uses only the Python standard library.

## Running

```bash
python gemini-slurp.py [~/Downloads/Takeout] [--obsidian-chat-path PATH] [--gap-minutes N] [--force]
```

## Architecture

- `find_activity_html(takeout_path)` — locates `MyActivity.html` inside a Takeout ZIP or unpacked directory
- `parse_activity_cards(html)` — regex-based parser that splits the HTML into outer-cell blocks and extracts `prompt`, `response_html`, and `timestamp` from each "Prompted" card; skips Canvas/Used/other card types
- `html_to_markdown(html)` — best-effort conversion of response HTML to Markdown (headings, bold, italic, code, lists)
- `group_into_conversations(cards, gap_minutes)` — sorts cards chronologically and splits into conversations on gaps > `gap_minutes`
- `write_conversation(output_dir, turns, force)` — writes a `.md` file with YAML frontmatter; protects manually edited files via `sync_hash`

Output filename format: `<YYYYMMDD_HHMM>_<prompt_slug>.md`

## Key implementation notes

- **Regex parser, not HTMLParser:** The Takeout HTML has unclosed tags causing final depth ~1688 in testing. Depth-based tracking in `HTMLParser` fails; regex splitting on `outer-cell` div boundaries is reliable.
- **sync_hash:** SHA-256 of file content excluding the `sync_hash:` line itself (first 16 hex chars). Written into frontmatter. On re-run, if file content doesn't match its stored hash, the file is skipped (user has edited it). `--force` overrides.
- **Timestamp format:** `Mar 27, 2026, 12:09:53\u202fPM EDT` — note the narrow no-break space (`\u202f`) between time and AM/PM.
- **Footer stripping:** Each card ends with a standard `Gemini Apps / Why is this here?` footer; stripped via regex split before writing.

## Tests

```bash
pip install pytest
python -m pytest test_gemini_slurp.py -v
```

49 tests covering: timestamp parsing, HTML card parsing, HTML-to-Markdown conversion, conversation grouping, file writing, idempotency, manual-edit protection, sync_hash, Takeout file discovery (ZIP and directory), and end-to-end round-trips.

## Approaches considered and rejected

See README.md for the full rationale. In brief:

1. **Takeout JSON** — Google no longer exports this format.
2. **`gemini-webapi` reverse-engineered API** — `LIST_CHATS` RPC returned null in testing; no way to enumerate conversations. Fragile external dependency.
3. **Takeout HTML (current)** — Full content available; pure stdlib; grouping is heuristic but acceptable.
