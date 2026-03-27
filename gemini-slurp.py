#!/usr/bin/env python3
"""Export Gemini conversation history from Google Takeout to Obsidian Markdown files.

Parses MyActivity.html from a Takeout archive (ZIP or unpacked directory),
groups prompt-response turns into conversations by time proximity, and writes
each conversation as a Markdown file with YAML frontmatter.

Files are protected from overwrite if manually edited (via sync_hash in
frontmatter). Use --force to override.

No external dependencies — uses only the Python standard library.
"""
import argparse
import hashlib
import html as html_mod
import os
import re
import zipfile
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Takeout file discovery
# ---------------------------------------------------------------------------

def find_activity_html(takeout_path):
    """Locate and read MyActivity.html from a Takeout ZIP or directory."""
    if os.path.isdir(takeout_path):
        for root, _, files in os.walk(takeout_path):
            for fname in files:
                if fname == "MyActivity.html" and "Gemini" in root:
                    with open(os.path.join(root, fname), encoding="utf-8") as f:
                        return f.read()
    else:
        with zipfile.ZipFile(takeout_path, "r") as z:
            for filename in z.namelist():
                if filename.endswith("MyActivity.html") and "Gemini" in filename:
                    with z.open(filename) as f:
                        return f.read().decode("utf-8")
    return None


# ---------------------------------------------------------------------------
# HTML parsing (regex-based — robust against unclosed tags in Takeout HTML)
# ---------------------------------------------------------------------------

_TS_RE = re.compile(
    r"([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}\s*[AP]M)\s+[A-Z]+"
)


def _parse_timestamp(ts_str):
    clean = re.sub(r"\s+", " ", ts_str).strip()
    m = _TS_RE.match(clean)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%b %d, %Y, %I:%M:%S %p")
    except ValueError:
        return None


def parse_activity_cards(html_content):
    """Extract prompted activity cards from the Takeout HTML.

    Returns a list of dicts with keys: prompt, response_html, timestamp.
    """
    # Split into outer-cell blocks
    cell_starts = [m.start() for m in re.finditer(r'<div class="outer-cell', html_content)]
    if not cell_starts:
        return []

    cards = []
    for i, start in enumerate(cell_starts):
        end = cell_starts[i + 1] if i + 1 < len(cell_starts) else len(html_content)
        cell = html_content[start:end]

        # Find the first content-cell with body-1
        m = re.search(r'mdl-typography--body-1">(.*)', cell, re.DOTALL)
        if not m:
            continue
        content = m.group(1)

        # Only process "Prompted" cards
        if not content.startswith("Prompted"):
            continue

        # Structure: Prompted\xa0<prompt><br><timestamp><br><response...>
        parts = re.split(r"<br\s*/?>", content, maxsplit=2)
        if len(parts) < 3:
            continue

        prompt_raw = parts[0]
        ts_raw = parts[1]
        response_raw = parts[2]

        # Extract prompt text (strip "Prompted\xa0" prefix)
        prompt = html_mod.unescape(prompt_raw)
        prompt = prompt.replace("Prompted", "", 1).strip().lstrip("\xa0").strip()

        # Parse timestamp
        timestamp = _parse_timestamp(html_mod.unescape(ts_raw))
        if not timestamp:
            continue

        # Strip the standard footer
        response_html = re.split(
            r"<br>\s*(?:&emsp;|&nbsp;|\s)*Gemini Apps\s*<br>",
            response_raw,
            maxsplit=1,
        )[0].strip()

        cards.append({
            "prompt": prompt,
            "response_html": response_html,
            "timestamp": timestamp,
        })

    return cards


def html_to_markdown(h):
    """Best-effort conversion of response HTML to readable Markdown."""
    if not h:
        return ""
    text = h
    # Headings
    text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n### \1\n", text, flags=re.DOTALL)
    # Bold / strong
    text = re.sub(r"<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>", r"**\1**", text, flags=re.DOTALL)
    # Italic / em
    text = re.sub(r"<(?:i|em)[^>]*>(.*?)</(?:i|em)>", r"*\1*", text, flags=re.DOTALL)
    # Code
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    # List items
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL)
    # Paragraphs / divs / lists → newlines
    text = re.sub(r"</?(?:p|div|ol|ul|hr)[^>]*>", "\n", text)
    # Line breaks
    text = re.sub(r"<br\s*/?>", "\n", text)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode entities
    text = html_mod.unescape(text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Conversation grouping
# ---------------------------------------------------------------------------

def group_into_conversations(cards, gap_minutes=60):
    """Group cards into conversations by time proximity.

    Cards may arrive in any order. We sort chronologically, then start a
    new conversation whenever the gap exceeds gap_minutes.

    Returns a list of conversations (each a list of card dicts),
    in chronological order.
    """
    if not cards:
        return []

    sorted_cards = sorted(cards, key=lambda c: c["timestamp"])
    conversations = []
    current = [sorted_cards[0]]

    for card in sorted_cards[1:]:
        if card["timestamp"] - current[-1]["timestamp"] > timedelta(minutes=gap_minutes):
            conversations.append(current)
            current = [card]
        else:
            current.append(card)

    conversations.append(current)
    return conversations


# ---------------------------------------------------------------------------
# Writing + sync_hash protection
# ---------------------------------------------------------------------------

def _content_hash(content):
    """SHA-256 of file content excluding the sync_hash line."""
    lines = [l for l in content.splitlines() if not l.startswith("sync_hash:")]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def _file_matches_hash(filepath):
    """Check if the file on disk still matches its sync_hash."""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return True  # no file = safe to write
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("sync_hash:"):
            stored = stripped.split(":", 1)[1].strip()
            return _content_hash(content) == stored
    return True  # no hash found = not ours or old format, safe to overwrite


def _conversation_filename(turns):
    """Generate a filename from the first turn's prompt and timestamp."""
    first = turns[0]
    ts_part = first["timestamp"].strftime("%Y%m%d_%H%M")
    prompt_words = re.sub(r"[^a-zA-Z0-9 ]", "", first["prompt"])[:50].strip()
    if not prompt_words:
        prompt_words = "chat"
    slug = re.sub(r"\s+", "_", prompt_words)
    return f"{ts_part}_{slug}.md"


def write_conversation(output_dir, turns, force=False):
    """Write a conversation file.

    Returns (filename, status) where status is one of:
      'written', 'skipped' (manually edited), 'unchanged'.
    """
    filename = _conversation_filename(turns)
    filepath = os.path.join(output_dir, filename)

    first_ts = turns[0]["timestamp"].isoformat()
    last_ts = turns[-1]["timestamp"].isoformat()

    lines = [
        "---",
        f"first_turn: {first_ts}",
        f"last_turn: {last_ts}",
        f"turn_count: {len(turns)}",
        "sync_hash: PLACEHOLDER",
        "---",
        f"# {turns[0]['prompt'][:80]}",
        "",
    ]

    for turn in turns:
        ts = turn["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"**You** ({ts}):\n{turn['prompt']}\n")
        lines.append("---\n")
        response_md = html_to_markdown(turn["response_html"])
        if response_md:
            lines.append(f"**Gemini:**\n{response_md}\n")
            lines.append("---\n")

    content = "\n".join(lines)
    actual_hash = _content_hash(content)
    content = content.replace("sync_hash: PLACEHOLDER", f"sync_hash: {actual_hash}")

    # Protect manually edited files
    if not force and os.path.exists(filepath) and not _file_matches_hash(filepath):
        return filename, "skipped"

    # Skip if content unchanged
    if os.path.exists(filepath):
        with open(filepath, encoding="utf-8") as f:
            if f.read() == content:
                return filename, "unchanged"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filename, "written"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Export Gemini conversation history from Google Takeout to Obsidian Markdown files."
    )
    ap.add_argument(
        "takeout_path",
        nargs="?",
        default=os.path.expanduser("~/Downloads/Takeout"),
        help="Path to the Takeout ZIP or unpacked directory (default: ~/Downloads/Takeout)",
    )
    ap.add_argument(
        "--obsidian-chat-path",
        default=os.path.expanduser("~/Documents/Personal/chats/Gemini"),
        help="Directory where Markdown files will be written (default: ~/Documents/Personal/chats/Gemini)",
    )
    ap.add_argument(
        "--gap-minutes",
        type=int,
        default=60,
        help="Minutes of silence before starting a new conversation (default: 60)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files even if they were manually edited",
    )
    args = ap.parse_args()

    # 1. Find and parse the HTML
    print(f"Reading Takeout from {args.takeout_path}...")
    html_content = find_activity_html(args.takeout_path)
    if not html_content:
        print("Could not find MyActivity.html in the provided Takeout path.")
        return

    cards = parse_activity_cards(html_content)
    print(f"Parsed {len(cards)} prompted turns.")

    # 2. Group into conversations
    conversations = group_into_conversations(cards, args.gap_minutes)
    print(f"Grouped into {len(conversations)} conversations "
          f"(gap threshold: {args.gap_minutes} min).\n")

    if not conversations:
        print("No conversations found.")
        return

    # 3. Write files
    os.makedirs(args.obsidian_chat_path, exist_ok=True)

    written = 0
    skipped = 0
    unchanged = 0
    for conv in conversations:
        fn, status = write_conversation(args.obsidian_chat_path, conv, args.force)
        if status == "written":
            print(f"  WRITE  {fn} ({len(conv)} turns)")
            written += 1
        elif status == "skipped":
            print(f"  SKIP   {fn} (manually edited)")
            skipped += 1
        else:
            unchanged += 1

    print(f"\nDone. {written} written, {unchanged} unchanged, {skipped} skipped (manually edited).")
    print(f"Output: {args.obsidian_chat_path}")


if __name__ == "__main__":
    main()
