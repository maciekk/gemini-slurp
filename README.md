# gemini-slurp

Exports your full Gemini conversation history (prompts and responses) into Obsidian-friendly Markdown files.

Uses the [gemini-webapi](https://github.com/HanaokaYuzu/Gemini-API) library to pull conversations directly from the Gemini web app via your browser cookies — no manual export step required.

## Prerequisites

1. **Be logged in** to [gemini.google.com](https://gemini.google.com) in your browser
2. Install the dependency:
   ```bash
   pip install "gemini-webapi[browser]"
   ```
   The `[browser]` extra enables automatic cookie import from your local browser session.

## Usage

```bash
python gemini-slurp.py [--obsidian-chat-path PATH] [--max-chats N] [--max-turns N]
```

| Flag | Default | Description |
|---|---|---|
| `--obsidian-chat-path` | `~/Documents/Personal/chats/Gemini` | Directory where Markdown files are written |
| `--max-chats` | `1000` | Maximum number of conversations to fetch |
| `--max-turns` | `1000` | Maximum turns per conversation |

**Examples:**

```bash
# Export everything with defaults
python gemini-slurp.py

# Custom output location
python gemini-slurp.py --obsidian-chat-path ~/Vault/chats/Gemini

# Quick test with a few chats
python gemini-slurp.py --max-chats 5
```

## Output format

Each conversation becomes a Markdown file named `<title>_<chat_id>.md` with YAML frontmatter:

```markdown
---
gemini_id: c_abc123
title: "My conversation"
last_updated: 2026-03-27T12:00:00
pinned: false
---
# My conversation

**You:**
What is the meaning of life?

---

**Gemini:**
The meaning of life is...

---
```

Files are overwritten on each run, so re-running pulls in any new messages.

## Alternative: Google Takeout

If you prefer an official Google export (metadata only — titles and timestamps, not full conversation content):

1. Go to [takeout.google.com](https://takeout.google.com)
2. Click **Deselect All**
3. Check the **My Activity** checkbox
4. Click the **All Activity Data Included** button that appears under it
5. In the dialog, click **Deselect All**, then check **Gemini Apps** only, and confirm
6. Proceed through the export wizard

Google will email you when the archive is ready. You can also set up a **periodic export** (every 2 months for up to a year) so fresh archives arrive automatically.

Note: Takeout only provides activity metadata, not full conversation content. That's why this tool uses the web API instead.
