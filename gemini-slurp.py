#!/usr/bin/env python3
import json
import os
import re
import zipfile

# --- Configuration ---
TAKEOUT_ZIP = "./Downloads/takeout-xxxxxxxx.zip" 
OBSIDIAN_INBOX = "/path/to/your/Obsidian/Vault/Gemini_Sync"

def extract_and_parse(zip_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. Extract the specific JSON from the Takeout Zip
    json_data = None
    with zipfile.ZipFile(zip_path, 'r') as z:
        for filename in z.namelist():
            if filename.endswith("MyActivity.json") and "Gemini" in filename:
                with z.open(filename) as f:
                    json_data = json.load(f)
                break

    if not json_data:
        print("Could not find Gemini JSON in the provided Takeout zip.")
        return

    # 2. Group scattered activity items into full conversations
    conversations = {}

    for entry in json_data:
        url = entry.get("titleUrl", "")

        # Extract the unique Gemini ID (e.g., /app/1a2b3c)
        match = re.search(r'/app/([a-zA-Z0-9_-]+)', url)
        if not match:
            continue

        chat_id = match.group(1)
        timestamp = entry.get("time", "Unknown Time")

        if chat_id not in conversations:
            # Clean the title for file naming
            raw_title = entry.get("title", f"Gemini Chat {chat_id}")
            safe_title = re.sub(r'[^a-zA-Z0-9 _-]', '', raw_title)[:50]

            conversations[chat_id] = {
                "file_name": f"{safe_title}_{chat_id}.md",
                "last_updated": timestamp,
                "messages": []
            }

        # Extract the actual prompt/response text
        # (You may need to adjust these keys based on your specific Takeout payload)
        content = entry.get("description") or entry.get("title")
        conversations[chat_id]["messages"].append(f"**[{timestamp}]**\n{content}\n")

    # 3. Write to Obsidian with Frontmatter (Overwrite Method)
    for chat_id, chat_data in conversations.items():
        filepath = os.path.join(output_dir, chat_data["file_name"])

        # Construct Markdown with YAML
        markdown_content = f"""---
gemini_id: {chat_id}
last_updated: {chat_data["last_updated"]}
status: active
---
# {chat_data["file_name"].replace('.md', '')}

"""
        # Takeout logs are newest-first. Reverse them for standard reading.
        for msg in reversed(chat_data["messages"]):
            markdown_content += msg + "\n---\n"

        # Because we overwrite the file, any updates made in the Gemini Web UI 
        # since the last export will seamlessly append to the bottom of the note.
        with open(filepath, 'w', encoding='utf-8') as out_file:
            out_file.write(markdown_content)

    print(f"Sync complete. Processed {len(conversations)} conversations into Obsidian.")

if __name__ == "__main__":
    extract_and_parse(TAKEOUT_ZIP, OBSIDIAN_INBOX)
