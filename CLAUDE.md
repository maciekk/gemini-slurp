# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A single-file Python utility (`gemini-slurp.py`) that reads a Google Takeout ZIP archive and exports Gemini conversation history as Markdown files into an Obsidian vault.

## Running

Configure the two constants at the top of the script before running:

```python
TAKEOUT_ZIP = "./Downloads/takeout-xxxxxxxx.zip"   # path to your Takeout ZIP
OBSIDIAN_INBOX = "/path/to/your/Obsidian/Vault/Gemini_Sync"  # output directory
```

Then run:

```bash
python gemini-slurp.py
```

No external dependencies — uses only Python standard library (`json`, `os`, `re`, `zipfile`).

## Architecture

Everything lives in `extract_and_parse(zip_path, output_dir)`:

1. **Extract** — opens the Takeout ZIP, finds the file matching `*Gemini*/MyActivity.json`
2. **Group** — iterates JSON entries, extracts chat IDs from `titleUrl` via regex (`/app/<id>`), groups messages by chat ID into a `conversations` dict
3. **Write** — for each conversation, writes a `.md` file with YAML frontmatter (`gemini_id`, `last_updated`, `status`) and messages in chronological order (Takeout is newest-first, so messages are reversed before writing); files are overwritten on each run

Output filename format: `<safe_title>_<chat_id>.md` where `safe_title` strips non-alphanumeric characters and truncates to 50 chars.

## Known Limitations

- Message content falls back to `description` then `title` from the activity entry — actual prompt/response pairs are not always present in Takeout exports; the comment on line 54 notes this may need adjustment depending on the specific Takeout payload format.
