# gemini-slurp

Ah... Google Gemini. Nails the fancy stuff (esp. AI), but forgets the
basics, like allowing you to organize your zillion Gemini chats. Sigh.

This tool exports your Gemini chats (prompts + responses) into
Obsidian-friendly Markdown files in your vault, via Takeout.

Benefits:
- mostly works<sup>1</sup>
- no extra dependencies
- Obsidian has better search anyways
- even better, can run `black-oracle` on this content

1. weak point: there are no Chat IDs in the takeout, you need to use
   heuristics to thread them back together into discrete chats.

## Getting a Takeout export

1. Go to [takeout.google.com](https://takeout.google.com)
2. Click **Deselect All**
3. Check the **My Activity** checkbox
4. Click the **All Activity Data Included** button that appears under it
5. In the dialog, click **Deselect All**, then check **Gemini Apps**
   only, and confirm
6. Proceed through the export wizard

Google will email you when the archive is ready. You can also set up a
**periodic export** (every 2 months for up to a year) so fresh archives
land in your inbox automatically.

Once downloaded, the archive may auto-unpack to `~/Downloads/Takeout`
(macOS default), or you can point the script at the ZIP directly.

## Usage

```bash
python gemini-slurp.py [takeout_path] [--obsidian-chat-path PATH] \
                       [--gap-minutes N] [--force]
```

| Argument | Default | Description |
|---|---|---|
| `takeout_path` | `~/Downloads/Takeout` | Takeout ZIP or unpacked dir |
| `--obsidian-chat-path` | `~/Documents/Personal/chats/Gemini` | Output dir |
| `--gap-minutes` | `60` | Silence gap that starts a new conversation |
| `--force` | off | Overwrite files even if manually edited |

**Examples:**

```bash
# Use all defaults
python gemini-slurp.py

# Explicit ZIP
python gemini-slurp.py ~/Downloads/takeout-20260401.zip

# Tighter grouping — 30 min gap instead of 60
python gemini-slurp.py --gap-minutes 30
```

## Output format

Each conversation becomes a Markdown file named
`<YYYYMMDD_HHMM>_<prompt_slug>.md`:

```markdown
---
first_turn: 2026-03-27T12:00:00
last_turn: 2026-03-27T12:45:00
turn_count: 3
sync_hash: a1b2c3d4e5f6g7h8
---
# What might be some interesting coding projects for 3D printing

**You** (2026-03-27 12:00:00):
What might be some interesting coding projects for 3D printing?

---

**Gemini:**
Congrats on the Bambu Lab P2S! Here are a few ideas...

---
```

## Conversation grouping

The Takeout export contains individual prompt-response turns with no
explicit conversation boundaries. The script groups turns into
conversations by time proximity: a gap larger than `--gap-minutes`
(default 60) starts a new file.

This works well for the common case. If you occasionally return to an
old chat hours or days later, that follow-up will appear as a separate
conversation rather than appending to the original — an inherent
limitation of the Takeout format.

## Manual edit protection

Each file contains a `sync_hash` in its frontmatter — a hash of the
file content. On subsequent runs, if the hash doesn't match (i.e. you've
edited the file), the script skips it and prints `SKIP (manually
edited)`. Use `--force` to override.

## Approaches considered

Three approaches were evaluated before settling on the current one:

### 1. Google Takeout — JSON (rejected)

Early Takeout exports included a `MyActivity.json` file. This was the
original approach in this repo. Google has since switched to HTML-only
exports, so this no longer works.

### 2. `gemini-webapi` reverse-engineered API (rejected)

[HanaokaYuzu/Gemini-API](https://github.com/HanaokaYuzu/Gemini-API)
reverse-engineers the Gemini web app's internal RPC endpoints. It can
call `read_chat(cid)` to fetch full conversation content given a chat ID.

**Pros:** Full content, proper conversation boundaries (no grouping
heuristics needed), no Takeout step.

**Cons:** The `LIST_CHATS` RPC (`MaZiqc`) consistently returned null
during testing — making it impossible to enumerate conversations without
knowing their IDs in advance. Even if it worked, reverse-engineered APIs
are fragile and can break silently when Google changes their internals.
Also adds an external async dependency (`gemini-webapi`, `orjson`,
`curl_cffi`).

### 3. Google Takeout — HTML (current approach)

The current `MyActivity.html` format contains full prompt and response
text inside each activity card. Parsing is done with regex (rather than
an HTML parser) because the file contains unclosed tags that confuse
depth-tracking parsers.

**Pros:** Full content, no external dependencies, official Google export,
works offline.

**Cons:** No explicit conversation boundaries — grouping is heuristic
(time-gap based). Turns from revisited old chats may not group correctly.
Requires periodic manual Takeout downloads (though Google's periodic
export feature mitigates this).
