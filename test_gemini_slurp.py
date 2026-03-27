"""Tests for gemini-slurp.py"""
import os
import tempfile
import zipfile
from datetime import datetime

import pytest

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

# Import gemini-slurp.py despite the hyphen in the filename
_loader = SourceFileLoader("gemini_slurp", os.path.join(os.path.dirname(__file__), "gemini-slurp.py"))
_spec = spec_from_loader("gemini_slurp", _loader)
gs = module_from_spec(_spec)
_loader.exec_module(gs)


# ---------------------------------------------------------------------------
# Fixtures: minimal Takeout HTML fragments
# ---------------------------------------------------------------------------

def _make_card_html(prompt, timestamp, response_html="<p>Response.</p>"):
    """Build one outer-cell div matching the Google Takeout format."""
    return (
        f'<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
        f'<div class="mdl-grid">'
        f'<div class="header-cell mdl-cell mdl-cell--12-col">'
        f'<p class="mdl-typography--title">Gemini Apps<br></p></div>'
        f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">'
        f'Prompted\xa0{prompt}<br>{timestamp}<br>'
        f'{response_html}'
        f'<b>Products:</b><br>&emsp;Gemini Apps<br><b>Why is this here?</b><br>'
        f'&emsp;This activity was saved to your Google Account.</div>'
        f'</div></div>'
    )


def _make_non_prompted_card(action, timestamp):
    """Build a non-Prompted card (e.g. Canvas creation)."""
    return (
        f'<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
        f'<div class="mdl-grid">'
        f'<div class="header-cell mdl-cell mdl-cell--12-col">'
        f'<p class="mdl-typography--title">Gemini Apps<br></p></div>'
        f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">'
        f'{action}<br>{timestamp}<br>'
        f'<b>Products:</b><br>&emsp;Gemini Apps<br><b>Why is this here?</b></div>'
        f'</div></div>'
    )


SINGLE_CARD_HTML = (
    "<html><body>"
    + _make_card_html(
        "What is Python?",
        "Mar 27, 2026, 12:09:53\u202fPM EDT",
        "<p>Python is a programming language.</p>",
    )
    + "</body></html>"
)

TWO_CARDS_SAME_CONV = (
    "<html><body>"
    + _make_card_html("First question", "Mar 27, 2026, 12:00:00\u202fPM EDT", "<p>Answer one.</p>")
    + _make_card_html("Follow up", "Mar 27, 2026, 12:30:00\u202fPM EDT", "<p>Answer two.</p>")
    + "</body></html>"
)

TWO_CARDS_DIFF_CONV = (
    "<html><body>"
    + _make_card_html("Morning question", "Mar 27, 2026, 8:00:00\u202fAM EDT", "<p>Morning answer.</p>")
    + _make_card_html("Evening question", "Mar 27, 2026, 10:00:00\u202fPM EDT", "<p>Evening answer.</p>")
    + "</body></html>"
)

MIXED_CARDS = (
    "<html><body>"
    + _make_card_html("Real prompt", "Mar 27, 2026, 12:00:00\u202fPM EDT", "<p>Real answer.</p>")
    + _make_non_prompted_card(
        "Created Gemini Canvas titled\xa0My Canvas",
        "Mar 27, 2026, 12:05:00\u202fPM EDT",
    )
    + "</body></html>"
)


# ---------------------------------------------------------------------------
# Tests: timestamp parsing
# ---------------------------------------------------------------------------

class TestParseTimestamp:
    def test_standard_format(self):
        dt = gs._parse_timestamp("Mar 27, 2026, 12:09:53 PM EDT")
        assert dt == datetime(2026, 3, 27, 12, 9, 53)

    def test_narrow_no_break_space(self):
        dt = gs._parse_timestamp("Mar 27, 2026, 12:09:53\u202fPM EDT")
        assert dt == datetime(2026, 3, 27, 12, 9, 53)

    def test_am_time(self):
        dt = gs._parse_timestamp("Jun 21, 2025, 2:13:17 AM EST")
        assert dt == datetime(2025, 6, 21, 2, 13, 17)

    def test_invalid_returns_none(self):
        assert gs._parse_timestamp("not a timestamp") is None
        assert gs._parse_timestamp("") is None


# ---------------------------------------------------------------------------
# Tests: HTML parsing
# ---------------------------------------------------------------------------

class TestParseActivityCards:
    def test_single_card(self):
        cards = gs.parse_activity_cards(SINGLE_CARD_HTML)
        assert len(cards) == 1
        assert cards[0]["prompt"] == "What is Python?"
        assert cards[0]["timestamp"] == datetime(2026, 3, 27, 12, 9, 53)
        assert "programming language" in cards[0]["response_html"]

    def test_strips_footer(self):
        cards = gs.parse_activity_cards(SINGLE_CARD_HTML)
        assert "Why is this here" not in cards[0]["response_html"]
        assert "Gemini Apps" not in cards[0]["response_html"]

    def test_skips_non_prompted_cards(self):
        cards = gs.parse_activity_cards(MIXED_CARDS)
        assert len(cards) == 1
        assert cards[0]["prompt"] == "Real prompt"

    def test_empty_html(self):
        assert gs.parse_activity_cards("") == []
        assert gs.parse_activity_cards("<html></html>") == []

    def test_html_entities_in_prompt(self):
        html = (
            "<html><body>"
            + _make_card_html(
                "What &amp; why is &quot;Python&quot;?",
                "Mar 1, 2026, 1:00:00\u202fPM EDT",
            )
            + "</body></html>"
        )
        cards = gs.parse_activity_cards(html)
        assert cards[0]["prompt"] == 'What & why is "Python"?'


# ---------------------------------------------------------------------------
# Tests: HTML to Markdown conversion
# ---------------------------------------------------------------------------

class TestHtmlToMarkdown:
    def test_paragraphs(self):
        md = gs.html_to_markdown("<p>First paragraph.</p><p>Second paragraph.</p>")
        assert "First paragraph." in md
        assert "Second paragraph." in md

    def test_bold(self):
        assert "**bold**" in gs.html_to_markdown("<strong>bold</strong>")
        assert "**bold**" in gs.html_to_markdown("<b>bold</b>")

    def test_italic(self):
        assert "*italic*" in gs.html_to_markdown("<em>italic</em>")

    def test_code(self):
        assert "`code`" in gs.html_to_markdown("<code>code</code>")

    def test_list_items(self):
        md = gs.html_to_markdown("<ul><li>one</li><li>two</li></ul>")
        assert "- one" in md
        assert "- two" in md

    def test_headings(self):
        md = gs.html_to_markdown("<h3>Title</h3>")
        assert "### Title" in md

    def test_entities(self):
        md = gs.html_to_markdown("&amp; &lt; &gt; &quot;")
        assert "& < > \"" == md

    def test_empty(self):
        assert gs.html_to_markdown("") == ""
        assert gs.html_to_markdown(None) == ""

    def test_strips_unknown_tags(self):
        md = gs.html_to_markdown("<span class='x'>text</span>")
        assert md == "text"


# ---------------------------------------------------------------------------
# Tests: conversation grouping
# ---------------------------------------------------------------------------

class TestGroupIntoConversations:
    def _card(self, timestamp):
        return {"prompt": "q", "response_html": "<p>a</p>", "timestamp": timestamp}

    def test_empty(self):
        assert gs.group_into_conversations([]) == []

    def test_single_card(self):
        convs = gs.group_into_conversations([self._card(datetime(2026, 1, 1, 12, 0))])
        assert len(convs) == 1
        assert len(convs[0]) == 1

    def test_close_turns_grouped(self):
        cards = [
            self._card(datetime(2026, 1, 1, 12, 0)),
            self._card(datetime(2026, 1, 1, 12, 30)),
            self._card(datetime(2026, 1, 1, 12, 55)),
        ]
        convs = gs.group_into_conversations(cards, gap_minutes=60)
        assert len(convs) == 1
        assert len(convs[0]) == 3

    def test_gap_splits_conversations(self):
        cards = [
            self._card(datetime(2026, 1, 1, 8, 0)),
            self._card(datetime(2026, 1, 1, 8, 30)),
            self._card(datetime(2026, 1, 1, 22, 0)),
        ]
        convs = gs.group_into_conversations(cards, gap_minutes=60)
        assert len(convs) == 2
        assert len(convs[0]) == 2
        assert len(convs[1]) == 1

    def test_unsorted_input(self):
        cards = [
            self._card(datetime(2026, 1, 1, 22, 0)),
            self._card(datetime(2026, 1, 1, 8, 0)),
            self._card(datetime(2026, 1, 1, 8, 30)),
        ]
        convs = gs.group_into_conversations(cards, gap_minutes=60)
        assert len(convs) == 2
        # First conversation should be chronologically first
        assert convs[0][0]["timestamp"] == datetime(2026, 1, 1, 8, 0)

    def test_custom_gap(self):
        cards = [
            self._card(datetime(2026, 1, 1, 12, 0)),
            self._card(datetime(2026, 1, 1, 12, 20)),
        ]
        assert len(gs.group_into_conversations(cards, gap_minutes=30)) == 1
        assert len(gs.group_into_conversations(cards, gap_minutes=10)) == 2

    def test_exact_gap_boundary(self):
        cards = [
            self._card(datetime(2026, 1, 1, 12, 0)),
            self._card(datetime(2026, 1, 1, 13, 0)),  # exactly 60 min
        ]
        # Exactly at the boundary should NOT split (uses >)
        assert len(gs.group_into_conversations(cards, gap_minutes=60)) == 1


# ---------------------------------------------------------------------------
# Tests: file writing, idempotency, and manual-edit protection
# ---------------------------------------------------------------------------

class TestWriteConversation:
    def _turns(self):
        return [
            {
                "prompt": "Hello world",
                "response_html": "<p>Hi there!</p>",
                "timestamp": datetime(2026, 3, 27, 12, 0, 0),
            },
        ]

    def test_creates_file(self, tmp_path):
        fn, status = gs.write_conversation(str(tmp_path), self._turns())
        assert status == "written"
        assert (tmp_path / fn).exists()

    def test_frontmatter_present(self, tmp_path):
        fn, _ = gs.write_conversation(str(tmp_path), self._turns())
        content = (tmp_path / fn).read_text()
        assert "first_turn:" in content
        assert "last_turn:" in content
        assert "turn_count: 1" in content
        assert "sync_hash:" in content

    def test_content_present(self, tmp_path):
        fn, _ = gs.write_conversation(str(tmp_path), self._turns())
        content = (tmp_path / fn).read_text()
        assert "**You**" in content
        assert "Hello world" in content
        assert "**Gemini:**" in content
        assert "Hi there!" in content

    def test_idempotent(self, tmp_path):
        turns = self._turns()
        gs.write_conversation(str(tmp_path), turns)
        _, status = gs.write_conversation(str(tmp_path), turns)
        assert status == "unchanged"

    def test_skips_manually_edited_file(self, tmp_path):
        turns = self._turns()
        fn, _ = gs.write_conversation(str(tmp_path), turns)
        # Simulate manual edit
        filepath = tmp_path / fn
        filepath.write_text(filepath.read_text() + "\nmy personal notes\n")
        _, status = gs.write_conversation(str(tmp_path), turns)
        assert status == "skipped"

    def test_force_overwrites_edited_file(self, tmp_path):
        turns = self._turns()
        fn, _ = gs.write_conversation(str(tmp_path), turns)
        filepath = tmp_path / fn
        filepath.write_text(filepath.read_text() + "\nmy personal notes\n")
        _, status = gs.write_conversation(str(tmp_path), turns, force=True)
        assert status == "written"

    def test_multi_turn(self, tmp_path):
        turns = [
            {
                "prompt": "First question",
                "response_html": "<p>First answer.</p>",
                "timestamp": datetime(2026, 3, 27, 12, 0, 0),
            },
            {
                "prompt": "Second question",
                "response_html": "<p>Second answer.</p>",
                "timestamp": datetime(2026, 3, 27, 12, 5, 0),
            },
        ]
        fn, _ = gs.write_conversation(str(tmp_path), turns)
        content = (tmp_path / fn).read_text()
        assert "turn_count: 2" in content
        assert "First question" in content
        assert "Second question" in content


# ---------------------------------------------------------------------------
# Tests: filename generation
# ---------------------------------------------------------------------------

class TestConversationFilename:
    def test_basic(self):
        turns = [{"prompt": "Hello world", "timestamp": datetime(2026, 3, 27, 12, 0)}]
        fn = gs._conversation_filename(turns)
        assert fn == "20260327_1200_Hello_world.md"

    def test_special_chars_stripped(self):
        turns = [{"prompt": "What's the deal with $$$?", "timestamp": datetime(2026, 1, 1, 8, 0)}]
        fn = gs._conversation_filename(turns)
        assert "$" not in fn
        assert "'" not in fn
        assert fn.endswith(".md")

    def test_long_prompt_truncated(self):
        turns = [{"prompt": "a" * 200, "timestamp": datetime(2026, 1, 1, 8, 0)}]
        fn = gs._conversation_filename(turns)
        # 50 chars of prompt + timestamp prefix + .md
        assert len(fn.split("_", 2)[2].replace(".md", "")) <= 50

    def test_empty_prompt(self):
        turns = [{"prompt": "!!!???", "timestamp": datetime(2026, 1, 1, 8, 0)}]
        fn = gs._conversation_filename(turns)
        assert "chat" in fn


# ---------------------------------------------------------------------------
# Tests: sync_hash internals
# ---------------------------------------------------------------------------

class TestSyncHash:
    def test_content_hash_excludes_hash_line(self):
        a = gs._content_hash("line1\nsync_hash: abc123\nline2")
        b = gs._content_hash("line1\nsync_hash: different\nline2")
        assert a == b

    def test_content_hash_sensitive_to_content(self):
        a = gs._content_hash("line1\nline2")
        b = gs._content_hash("line1\nline3")
        assert a != b

    def test_file_matches_hash_missing_file(self, tmp_path):
        assert gs._file_matches_hash(str(tmp_path / "nonexistent.md")) is True

    def test_file_matches_hash_no_hash_in_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("no frontmatter here")
        assert gs._file_matches_hash(str(f)) is True

    def test_file_matches_hash_valid(self, tmp_path):
        turns = [{"prompt": "q", "response_html": "<p>a</p>", "timestamp": datetime(2026, 1, 1, 12, 0)}]
        fn, _ = gs.write_conversation(str(tmp_path), turns)
        assert gs._file_matches_hash(str(tmp_path / fn)) is True

    def test_file_matches_hash_after_edit(self, tmp_path):
        turns = [{"prompt": "q", "response_html": "<p>a</p>", "timestamp": datetime(2026, 1, 1, 12, 0)}]
        fn, _ = gs.write_conversation(str(tmp_path), turns)
        filepath = tmp_path / fn
        filepath.write_text(filepath.read_text() + "\nedited")
        assert gs._file_matches_hash(str(filepath)) is False


# ---------------------------------------------------------------------------
# Tests: Takeout file discovery
# ---------------------------------------------------------------------------

class TestFindActivityHtml:
    def test_from_directory(self, tmp_path):
        gemini_dir = tmp_path / "My Activity" / "Gemini Apps"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "MyActivity.html").write_text("<html>test</html>")
        assert gs.find_activity_html(str(tmp_path)) == "<html>test</html>"

    def test_from_zip(self, tmp_path):
        zip_path = tmp_path / "takeout.zip"
        with zipfile.ZipFile(str(zip_path), "w") as z:
            z.writestr("Takeout/My Activity/Gemini Apps/MyActivity.html", "<html>zipped</html>")
        assert gs.find_activity_html(str(zip_path)) == "<html>zipped</html>"

    def test_missing_returns_none(self, tmp_path):
        assert gs.find_activity_html(str(tmp_path)) is None

    def test_wrong_folder_ignored(self, tmp_path):
        other_dir = tmp_path / "My Activity" / "Chrome"
        other_dir.mkdir(parents=True)
        (other_dir / "MyActivity.html").write_text("<html>wrong</html>")
        assert gs.find_activity_html(str(tmp_path)) is None


# ---------------------------------------------------------------------------
# Integration: parse → group → write round-trip
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_two_cards_same_conversation(self, tmp_path):
        cards = gs.parse_activity_cards(TWO_CARDS_SAME_CONV)
        assert len(cards) == 2
        convs = gs.group_into_conversations(cards, gap_minutes=60)
        assert len(convs) == 1
        fn, status = gs.write_conversation(str(tmp_path), convs[0])
        assert status == "written"
        content = (tmp_path / fn).read_text()
        assert "turn_count: 2" in content
        assert "First question" in content
        assert "Follow up" in content

    def test_two_cards_different_conversations(self, tmp_path):
        cards = gs.parse_activity_cards(TWO_CARDS_DIFF_CONV)
        convs = gs.group_into_conversations(cards, gap_minutes=60)
        assert len(convs) == 2
        for conv in convs:
            fn, status = gs.write_conversation(str(tmp_path), conv)
            assert status == "written"

    def test_roundtrip_from_zip(self, tmp_path):
        zip_path = tmp_path / "takeout.zip"
        with zipfile.ZipFile(str(zip_path), "w") as z:
            z.writestr("Takeout/My Activity/Gemini Apps/MyActivity.html", SINGLE_CARD_HTML)
        html_content = gs.find_activity_html(str(zip_path))
        cards = gs.parse_activity_cards(html_content)
        assert len(cards) == 1
        convs = gs.group_into_conversations(cards)
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        fn, _ = gs.write_conversation(str(out_dir), convs[0])
        content = (out_dir / fn).read_text()
        assert "What is Python?" in content
        assert "programming language" in content
