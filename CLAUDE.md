# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A single-file Python utility (`gemini-slurp.py`) that exports full Gemini conversation history (prompts + responses) as Markdown files into an Obsidian vault. Uses the `gemini-webapi` library to fetch conversations directly from the Gemini web app via browser cookies.

## Running

```bash
pip install "gemini-webapi[browser]"
python gemini-slurp.py
```

Requires being logged in to gemini.google.com in your browser. Cookies are imported automatically.

## Architecture

- `GeminiClient()` — authenticates via browser cookies (auto-import via `browser-cookie3`)
- `client._fetch_recent_chats(recent=N)` — fetches the chat list (private method; `list_chats()` defaults to only 13)
- `client.read_chat(cid, limit=N)` — fetches full conversation history for a chat ID; returns turns newest-first
- `write_conversation()` — writes each conversation as a `.md` file with YAML frontmatter and chronological turn order

Output filename format: `<safe_title>_<chat_id>.md`

## Key library notes (gemini-webapi)

- Async-only — all network calls use `asyncio`
- `read_chat()` returns `None` if model is still generating or history is unparseable
- `ChatTurn` has `.role` ("user"/"model") and `.text`; model turns also have `.model_output` with thoughts, images, etc.
- Reverse-engineered API — can break if Google changes internal endpoints
