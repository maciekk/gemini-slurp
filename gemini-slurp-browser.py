#!/usr/bin/env python3
"""Export Gemini conversations from a browser-extension capture to Markdown.

Reads the JSON file produced by the gemini-slurp userscript/extension,
extracts conversation structure from the intercepted API calls, and
writes each conversation as an Obsidian-friendly Markdown file.

Advantages over the Takeout approach:
  - Real conversation IDs and titles (no time-gap heuristics needed)
  - Conversations have their actual Gemini title, not a derived slug
  - Works with whatever conversations you visited during the capture

Limitations:
  - Only captures conversations you actually open in the browser
  - Must re-run the export each session to pick up new conversations

Usage:
  python gemini-slurp-browser.py [capture.json] [--obsidian-chat-path PATH]
                                  [--force]

No external dependencies.
"""

import argparse
import hashlib
import json
import os
import re
from datetime import datetime


# ---------------------------------------------------------------------------
# batchexecute parser
# ---------------------------------------------------------------------------

def _parse_batchexecute(raw):
    """Parse Google's batchexecute streaming wire format.

    Format after the XSSI guard:

        <decimal-byte-count>\\n
        <json-array>\\n
        <decimal-byte-count>\\n
        <json-array>\\n
        ...

    The declared byte count is occasionally off by a byte or two, so we
    use json.JSONDecoder.raw_decode() to consume exactly one JSON object
    per chunk rather than trusting the count precisely.
    """
    body = re.sub(r"^\)\]\}'\n+", "", raw)
    decoder = json.JSONDecoder()
    results = []
    pos = 0
    while pos < len(body):
        nl = body.find("\n", pos)
        if nl == -1:
            break
        line = body[pos:nl].strip()
        if not re.match(r"^\d+$", line):
            pos = nl + 1
            continue
        start = nl + 1
        try:
            obj, consumed = decoder.raw_decode(body, start)
            results.append(obj)
            pos = start + consumed
        except Exception:
            pos = nl + 1
    return results


def _find_wrb(chunks, rpcid):
    """Return the decoded inner payload for a given RPC id."""
    for chunk in chunks:
        if not isinstance(chunk, list):
            continue
        for item in chunk:
            if (isinstance(item, list) and len(item) >= 3
                    and item[0] == "wrb.fr" and item[1] == rpcid):
                try:
                    return json.loads(item[2])
                except Exception:
                    return None
    return None


# ---------------------------------------------------------------------------
# MaZiqc — conversation list
# ---------------------------------------------------------------------------

def parse_conv_list(captures):
    """Extract conversation metadata from MaZiqc RPC captures.

    MaZiqc is the LIST_CHATS RPC.  Inner payload structure:

        [request_token_or_null, pagination_token, [
            [conv_id, title, ..., ..., ..., [unix_sec, nanos], ...],
            ...
        ]]

    Returns dict: conv_id -> {"title": str, "timestamp": datetime|None}
    """
    convs = {}
    for cap in captures:
        if not cap.get("raw") or "MaZiqc" not in cap.get("url", ""):
            continue
        inner = _find_wrb(_parse_batchexecute(cap["raw"]), "MaZiqc")
        if not inner:
            continue
        conv_list = inner[2] if len(inner) > 2 else []
        for conv in (conv_list or []):
            conv_id = conv[0] if conv else None
            if not conv_id:
                continue
            title = conv[1] if len(conv) > 1 else ""
            ts_pair = conv[5] if len(conv) > 5 else None
            ts = (datetime.fromtimestamp(ts_pair[0]) if ts_pair else None)
            if conv_id not in convs:
                convs[conv_id] = {"title": title or "", "timestamp": ts}
    return convs


# ---------------------------------------------------------------------------
# hNvQHb — conversation content
# ---------------------------------------------------------------------------

def _turn_timestamp(turn):
    """Scan a turn array for a [unix_seconds, nanos] pair."""
    for v in turn:
        if (isinstance(v, list) and len(v) == 2
                and isinstance(v[0], int) and v[0] > 1_700_000_000):
            return datetime.fromtimestamp(v[0])
    return None


def parse_conv_turns(captures):
    """Extract conversation turns from hNvQHb RPC captures.

    hNvQHb is the LOAD_CONVERSATION RPC, fired when you open a chat.

    Turn structure (positional array, not keyed):
        turn[0]  [conv_id, prev_response_id]   — back-reference
        turn[1]  [conv_id, response_id, ...]   — this turn's IDs
        turn[2]  [[user_text, ...], ...]        — user prompt parts
        turn[3]  [[[cand_id, [resp_text], ...]]]  — model candidates
        ...      [unix_sec, nanos]              — timestamp (position varies)

    Long conversations are paginated: Gemini fires a new hNvQHb each
    time the user scrolls up to load older turns. All pages for the
    same conv_id are merged and deduplicated by response_id (turn[1][1]).

    Returns dict: conv_id -> [{"timestamp", "user", "response"}, ...]
    """
    # conv_id -> {response_id -> turn_dict}  (dedup by response_id)
    convs: dict[str, dict] = {}

    for cap in captures:
        if not cap.get("raw") or "hNvQHb" not in cap.get("url", ""):
            continue
        inner = _find_wrb(_parse_batchexecute(cap["raw"]), "hNvQHb")
        if not inner:
            continue
        raw_turns = inner[0] if inner else []
        if not raw_turns:
            continue

        for turn in raw_turns:
            # Conversation ID at turn[0][0], response ID at turn[1][1]
            try:
                conv_id = turn[0][0]
            except (IndexError, TypeError):
                continue
            try:
                response_id = turn[1][1]
            except (IndexError, TypeError):
                response_id = None

            # User text: turn[2][0] is a list of strings (usually one)
            try:
                user_parts = turn[2][0] or []
                user_text = "\n".join(user_parts) if isinstance(user_parts, list) \
                    else str(user_parts)
            except (IndexError, TypeError):
                user_text = ""

            # Primary model response: turn[3][0][0][1][0]
            try:
                resp_text = turn[3][0][0][1][0]
            except (IndexError, TypeError):
                resp_text = ""

            turn_dict = {
                "timestamp": _turn_timestamp(turn),
                "user": user_text,
                "response": resp_text,
            }

            page = convs.setdefault(conv_id, {})
            # response_id is the dedup key; last write wins (idempotent)
            page[response_id] = turn_dict

    # Flatten, sort chronologically
    return {
        conv_id: sorted(page.values(), key=lambda t: t["timestamp"] or datetime.min)
        for conv_id, page in convs.items()
    }


# ---------------------------------------------------------------------------
# Markdown output — same conventions as gemini-slurp.py
# ---------------------------------------------------------------------------

def _content_hash(content):
    """SHA-256 of content excluding the sync_hash line (first 16 hex chars)."""
    lines = [l for l in content.splitlines() if not l.startswith("sync_hash:")]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]


def _file_matches_hash(filepath):
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return True
    for line in content.splitlines():
        if line.strip().startswith("sync_hash:"):
            stored = line.split(":", 1)[1].strip()
            return _content_hash(content) == stored
    return True


def _slug(text, maxlen=50):
    words = re.sub(r"[^a-zA-Z0-9 ]", "", text[:maxlen]).strip()
    return re.sub(r"\s+", "_", words) or "chat"


def write_conversation(output_dir, conv_id, meta, turns, force=False):
    """Write one conversation to a Markdown file.

    Returns (filename, status) where status is 'written', 'skipped',
    or 'unchanged'.
    """
    first_ts = turns[0]["timestamp"]
    last_ts = turns[-1]["timestamp"]
    title = (meta or {}).get("title", "")

    ts_part = first_ts.strftime("%Y%m%d_%H%M") if first_ts else "00000000_0000"
    slug_src = title or (turns[0]["user"] or "chat")
    filename = f"{ts_part}_{_slug(slug_src)}.md"
    filepath = os.path.join(output_dir, filename)

    lines = [
        "---",
        f"conversation_id: {conv_id}",
        f"title: {json.dumps(title)}",
        f"first_turn: {first_ts.isoformat() if first_ts else ''}",
        f"last_turn: {last_ts.isoformat() if last_ts else ''}",
        f"turn_count: {len(turns)}",
        "sync_hash: PLACEHOLDER",
        "---",
        f"# {title or turns[0]['user'][:80]}",
        "",
    ]

    for turn in turns:
        ts_str = turn["timestamp"].strftime("%Y-%m-%d %H:%M:%S") \
            if turn["timestamp"] else ""
        lines.append(f"**You** ({ts_str}):\n{turn['user']}\n")
        lines.append("---\n")
        if turn["response"]:
            lines.append(f"**Gemini:**\n{turn['response']}\n")
            lines.append("---\n")

    content = "\n".join(lines)
    actual_hash = _content_hash(content)
    content = content.replace("sync_hash: PLACEHOLDER", f"sync_hash: {actual_hash}")

    if not force and os.path.exists(filepath) and not _file_matches_hash(filepath):
        return filename, "skipped"

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
        description=(
            "Export Gemini conversations from a browser-extension capture "
            "to Obsidian Markdown files."
        )
    )
    ap.add_argument(
        "capture_json",
        nargs="?",
        default=os.path.expanduser("~/Downloads/gemini-slurp-latest.json"),
        help="JSON file exported by the gemini-slurp userscript (default: "
             "~/Downloads/gemini-slurp-latest.json)",
    )
    ap.add_argument(
        "--obsidian-chat-path",
        default=os.path.expanduser("~/Documents/Personal/chats/Gemini"),
        help="Output directory for Markdown files",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files even if manually edited",
    )
    args = ap.parse_args()

    if not os.path.exists(args.capture_json):
        print(f"Error: file not found: {args.capture_json}")
        return 1

    with open(args.capture_json, encoding="utf-8") as f:
        captures = json.load(f)
    print(f"Loaded {len(captures)} capture(s) from {args.capture_json}")

    conv_meta = parse_conv_list(captures)
    print(f"Conversations in list (MaZiqc): {len(conv_meta)}")

    conv_turns = parse_conv_turns(captures)
    print(f"Conversations with content (hNvQHb): {len(conv_turns)}")

    if not conv_turns:
        print(
            "\nNo conversation content found.\n"
            "Open one or more chats in Gemini before clicking Export."
        )
        return 0

    os.makedirs(args.obsidian_chat_path, exist_ok=True)

    counts = {"written": 0, "unchanged": 0, "skipped": 0}
    for conv_id, turns in conv_turns.items():
        meta = conv_meta.get(conv_id)
        filename, status = write_conversation(
            args.obsidian_chat_path, conv_id, meta, turns, force=args.force
        )
        counts[status] += 1
        label = {
            "written": "WRITE",
            "unchanged": "OK   ",
            "skipped": "SKIP  (manually edited)",
        }[status]
        print(f"  {label}  {filename}")

    print(
        f"\nDone: {counts['written']} written, "
        f"{counts['unchanged']} unchanged, "
        f"{counts['skipped']} skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
