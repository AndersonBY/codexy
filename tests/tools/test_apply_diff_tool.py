import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from codexy.tools.apply_diff_tool import apply_diff_tool, parse_diff_blocks

# --- Test Fixtures ---


@pytest.fixture
def test_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Creates a temporary directory for the test and sets PROJECT_ROOT within the tool module."""
    monkeypatch.chdir(tmp_path)
    # Explicitly get the module from sys.modules to avoid ambiguity
    module_to_patch = sys.modules["codexy.tools.apply_diff_tool"]
    monkeypatch.setattr(module_to_patch, "PROJECT_ROOT", tmp_path)
    print(f"PROJECT_ROOT set to: {tmp_path}")
    return tmp_path


# --- parse_diff_blocks Tests ---


def test_parse_diff_blocks_single_block():
    """Test parsing a diff string with a single block."""
    diff_text = """<<<<<<< SEARCH
:start_line:10
-------
original line
=======
modified line
>>>>>>> REPLACE"""

    blocks = parse_diff_blocks(diff_text)

    assert len(blocks) == 1
    assert blocks[0][0] == 10
    assert blocks[0][1].rstrip("\n") == "original line"
    assert blocks[0][2].rstrip("\n") == "modified line"


def test_parse_diff_blocks_multiple_blocks():
    """Test parsing a diff string with multiple blocks."""
    diff_text = """<<<<<<< SEARCH
:start_line:5
-------
first block original
=======
first block modified
>>>>>>> REPLACE
<<<<<<< SEARCH
:start_line:10
-------
second block original
=======
second block modified
>>>>>>> REPLACE"""

    blocks = parse_diff_blocks(diff_text)

    # Blocks should be sorted by line number in descending order
    assert len(blocks) == 2
    assert blocks[0][0] == 10  # Higher line number first
    assert blocks[0][1].rstrip("\n") == "second block original"
    assert blocks[0][2].rstrip("\n") == "second block modified"
    assert blocks[1][0] == 5
    assert blocks[1][1].rstrip("\n") == "first block original"
    assert blocks[1][2].rstrip("\n") == "first block modified"


def test_parse_diff_blocks_multiline():
    """Test parsing a diff string with multi-line blocks."""
    diff_text = """<<<<<<< SEARCH
:start_line:3
-------
line 1
line 2
line 3
=======
new line 1
new line 2
>>>>>>> REPLACE"""

    blocks = parse_diff_blocks(diff_text)

    assert len(blocks) == 1
    assert blocks[0][0] == 3
    assert blocks[0][1].rstrip("\n").split("\n") == ["line 1", "line 2", "line 3"]
    assert blocks[0][2].rstrip("\n").split("\n") == ["new line 1", "new line 2"]


def test_parse_diff_blocks_empty_search():
    """Test parsing a diff with empty search content."""
    diff_text = """<<<<<<< SEARCH
:start_line:8
-------
=======
added content
>>>>>>> REPLACE"""

    blocks = parse_diff_blocks(diff_text)

    assert len(blocks) == 1
    assert blocks[0][0] == 8
    assert blocks[0][1].rstrip("\n") == ""
    assert blocks[0][2].rstrip("\n") == "added content"


def test_parse_diff_blocks_empty_replace():
    """Test parsing a diff with empty replace content."""
    diff_text = """<<<<<<< SEARCH
:start_line:8
-------
content to delete
=======
>>>>>>> REPLACE"""

    blocks = parse_diff_blocks(diff_text)

    assert len(blocks) == 1
    assert blocks[0][0] == 8
    assert blocks[0][1].rstrip("\n") == "content to delete"
    assert blocks[0][2].rstrip("\n") == ""


def test_parse_diff_blocks_whitespace_variations():
    """Test parsing a diff with whitespace variations in markers."""
    diff_text = """  <<<<<<<   SEARCH
:start_line:15
-------
text
=======
new text
>>>>>>>  REPLACE  """

    blocks = parse_diff_blocks(diff_text)

    assert len(blocks) == 1
    assert blocks[0][0] == 15
    assert blocks[0][1].rstrip("\n") == "text"
    assert blocks[0][2].rstrip("\n") == "new text"


def test_parse_diff_blocks_crlf_normalization():
    """Test normalization of CRLF line endings."""
    diff_text = """<<<<<<< SEARCH
:start_line:20
-------
line 1\r\nline 2
=======
new line 1\r\nnew line 2
>>>>>>> REPLACE"""

    blocks = parse_diff_blocks(diff_text)

    assert len(blocks) == 1
    assert blocks[0][0] == 20
    # The \r\n sequence is escaped but should be normalized to \n in the output
    assert blocks[0][1].rstrip("\n") == "line 1\nline 2"
    assert blocks[0][2].rstrip("\n") == "new line 1\nnew line 2"


def test_parse_diff_blocks_empty_diff():
    """Test parsing an empty diff string."""
    diff_text = ""

    blocks = parse_diff_blocks(diff_text)

    assert len(blocks) == 0


def test_parse_diff_blocks_invalid_diff():
    """Test parsing an invalid diff string raises ValueError."""
    diff_text = "This is not a valid diff format"

    with pytest.raises(ValueError):
        parse_diff_blocks(diff_text)


# --- apply_diff_tool Tests ---


def test_apply_diff_tool_single_line(test_dir: Path):
    """Test applying a single-line diff."""
    file_path = test_dir / "test_file.txt"
    file_path.write_text("Line 1\nLine 2\nLine 3\n", encoding="utf-8")

    diff = """<<<<<<< SEARCH
:start_line:2
-------
Line 2
=======
Modified Line 2
>>>>>>> REPLACE"""

    result = apply_diff_tool("test_file.txt", diff)

    assert "Successfully" in result
    assert "1 diff block(s)" in result
    assert file_path.read_text(encoding="utf-8") == "Line 1\nModified Line 2\nLine 3\n"


def test_apply_diff_tool_multiple_blocks(test_dir: Path):
    """Test applying multiple diff blocks to a file."""
    file_path = test_dir / "multi_block.txt"
    file_path.write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n", encoding="utf-8")

    diff = """<<<<<<< SEARCH
:start_line:2
-------
Line 2
=======
Modified Line 2
>>>>>>> REPLACE
<<<<<<< SEARCH
:start_line:4
-------
Line 4
=======
Modified Line 4
>>>>>>> REPLACE"""

    result = apply_diff_tool("multi_block.txt", diff)

    assert "Successfully" in result
    assert "2 diff block(s)" in result
    assert file_path.read_text(encoding="utf-8") == "Line 1\nModified Line 2\nLine 3\nModified Line 4\nLine 5\n"


def test_apply_diff_tool_multiline_block(test_dir: Path):
    """Test applying a multi-line diff block."""
    file_path = test_dir / "multiline.txt"
    file_path.write_text("Title\nParagraph 1\nParagraph 2\nParagraph 3\nFooter\n", encoding="utf-8")

    diff = """<<<<<<< SEARCH
:start_line:2
-------
Paragraph 1
Paragraph 2
Paragraph 3
=======
New Paragraph A
New Paragraph B
>>>>>>> REPLACE"""

    result = apply_diff_tool("multiline.txt", diff)

    assert "Successfully" in result
    assert file_path.read_text(encoding="utf-8") == "Title\nNew Paragraph A\nNew Paragraph B\nFooter\n"


def test_apply_diff_tool_no_match(test_dir: Path):
    """Test applying a diff that doesn't match the file content."""
    file_path = test_dir / "no_match.txt"
    file_path.write_text("Line 1\nLine X\nLine 3\n", encoding="utf-8")

    diff = """<<<<<<< SEARCH
:start_line:2
-------
Line 2
=======
Modified Line 2
>>>>>>> REPLACE"""

    result = apply_diff_tool("no_match.txt", diff)

    assert "Failed" in result
    assert "SEARCH content does not exactly match" in result
    # File should remain unchanged
    assert file_path.read_text(encoding="utf-8") == "Line 1\nLine X\nLine 3\n"


def test_apply_diff_tool_out_of_bounds(test_dir: Path):
    """Test applying a diff with out-of-bounds line number."""
    file_path = test_dir / "short.txt"
    file_path.write_text("Line 1\nLine 2\n", encoding="utf-8")

    diff = """<<<<<<< SEARCH
:start_line:10
-------
Non-existent line
=======
New line
>>>>>>> REPLACE"""

    result = apply_diff_tool("short.txt", diff)

    assert "Failed" in result
    assert "out of bounds" in result
    # File should remain unchanged
    assert file_path.read_text(encoding="utf-8") == "Line 1\nLine 2\n"


def test_apply_diff_tool_nonexistent_file(test_dir: Path):
    """Test applying a diff to a non-existent file."""
    diff = """<<<<<<< SEARCH
:start_line:1
-------
Some content
=======
New content
>>>>>>> REPLACE"""

    result = apply_diff_tool("nonexistent.txt", diff)

    assert "Error" in result
    assert "File not found" in result


def test_apply_diff_tool_file_outside_project(test_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Test applying a diff to a file outside the project root."""
    # Create a file in the parent directory
    outside_file = test_dir.parent / "outside.txt"
    outside_file.write_text("Content", encoding="utf-8")

    diff = """<<<<<<< SEARCH
:start_line:1
-------
Content
=======
New content
>>>>>>> REPLACE"""

    # Use '../outside.txt' to attempt to access file outside project
    result = apply_diff_tool("../outside.txt", diff)

    assert "Error" in result
    assert "outside of project root" in result


def test_apply_diff_tool_empty_path():
    """Test applying a diff with an empty path."""
    diff = """<<<<<<< SEARCH
:start_line:1
-------
Content
=======
New content
>>>>>>> REPLACE"""

    result = apply_diff_tool("", diff)

    assert "Error" in result
    assert "'path' argument is required" in result


def test_apply_diff_tool_empty_diff(test_dir: Path):
    """Test applying an empty diff."""
    file_path = test_dir / "empty_diff.txt"
    file_path.write_text("Content", encoding="utf-8")

    result = apply_diff_tool("empty_diff.txt", "")

    assert "Error" in result
    assert "'diff' argument is required" in result


def test_apply_diff_tool_partial_success(test_dir: Path):
    """Test applying a diff with one successful block and one failed block."""
    file_path = test_dir / "partial.txt"
    file_path.write_text("Line 1\nLine 2\nLine 3\n", encoding="utf-8")

    diff = """<<<<<<< SEARCH
:start_line:1
-------
Line 1
=======
Modified Line 1
>>>>>>> REPLACE
<<<<<<< SEARCH
:start_line:3
-------
Wrong Line 3
=======
Modified Line 3
>>>>>>> REPLACE"""

    result = apply_diff_tool("partial.txt", diff)

    # Should report failures but still apply good changes
    assert "Failed" in result
    assert "SEARCH content does not exactly match" in result
    # File should remain unchanged since we have errors
    assert file_path.read_text(encoding="utf-8") == "Line 1\nLine 2\nLine 3\n"
