import os
import pytest
from pathlib import Path

from codexy.tools.apply_patch_tool import apply_patch, ToolError
import codexy.tools.apply_patch_tool as patch_tool_module

# --- Test Fixtures ---


@pytest.fixture
def test_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Creates a temporary directory for the test and sets PROJECT_ROOT within the tool module."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(patch_tool_module, "PROJECT_ROOT", tmp_path)
    print(f"PROJECT_ROOT set to: {tmp_path}")

    def _resolve_and_check_path(relative_path: str, base_dir: Path = tmp_path) -> Path:
        """Resolves a relative path against the base directory and performs safety checks."""
        if not relative_path:
            raise ToolError("Path cannot be empty.")

        # Disallow absolute paths provided by the LLM
        if Path(relative_path).is_absolute():  # Use Pathlib's is_absolute
            raise ToolError(f"Absolute paths are not allowed: '{relative_path}'")

        # Join with project root and resolve symlinks etc.
        # Important: Resolve *after* joining with base_dir
        target_path = (base_dir / relative_path).resolve()

        # Check if the resolved path is still within the project root directory
        if not str(target_path).startswith(str(base_dir.resolve()) + os.sep) and target_path != base_dir.resolve():
            raise ToolError(
                f"Attempted file access outside of project root: '{relative_path}' resolved to '{target_path}'"
            )

        return target_path

    monkeypatch.setattr(patch_tool_module, "_resolve_and_check_path", _resolve_and_check_path)

    return tmp_path


# --- Test Cases ---


# --- Add File Tests ---
def test_add_file_simple(test_dir: Path):
    patch = """*** Begin Patch
*** Add File: new_file.txt
+Hello Patch!
+This is the second line.
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Created file: new_file.txt" in result
    assert "Error" not in result
    new_file = test_dir / "new_file.txt"
    assert new_file.exists()
    # Expect LF line endings after write
    assert new_file.read_text(encoding="utf-8") == "Hello Patch!\nThis is the second line."


def test_add_file_with_subdir(test_dir: Path):
    patch = """*** Begin Patch
*** Add File: subdir/another_file.py
+print("Hello from subdir")
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Created file: subdir/another_file.py" in result
    assert "Error" not in result
    new_file = test_dir / "subdir" / "another_file.py"
    assert new_file.exists()
    assert new_file.parent.is_dir()
    assert new_file.read_text(encoding="utf-8") == 'print("Hello from subdir")'


def test_add_file_already_exists(test_dir: Path):
    existing_file = test_dir / "exists.txt"
    existing_file.write_text("Original content", encoding="utf-8")
    patch = """*** Begin Patch
*** Add File: exists.txt
+New stuff
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "path already exists" in result
    assert existing_file.read_text(encoding="utf-8") == "Original content"


def test_add_file_no_content(test_dir: Path):
    patch = """*** Begin Patch
*** Add File: empty_file.txt
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Created file: empty_file.txt" in result
    assert "Error" not in result
    new_file = test_dir / "empty_file.txt"
    assert new_file.exists()
    assert new_file.read_text(encoding="utf-8") == ""


# --- Delete File Tests ---
def test_delete_file_simple(test_dir: Path):
    file_to_delete = test_dir / "delete_me.txt"
    file_to_delete.write_text("Ephemeral content", encoding="utf-8")
    assert file_to_delete.exists()
    patch = """*** Begin Patch
*** Delete File: delete_me.txt
*** End Patch"""
    result = apply_patch(patch)
    assert "Deleted file: delete_me.txt" in result
    assert "Error" not in result
    assert not file_to_delete.exists()


def test_delete_nonexistent_file(test_dir: Path):
    patch = """*** Begin Patch
*** Delete File: does_not_exist.txt
*** End Patch"""
    result = apply_patch(patch)
    assert "Info: File to delete not found" in result  # Should not be an error
    assert "Error" not in result


def test_delete_directory_error(test_dir: Path):
    dir_to_delete = test_dir / "a_directory"
    dir_to_delete.mkdir()
    assert dir_to_delete.is_dir()
    patch = """*** Begin Patch
*** Delete File: a_directory
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "Skipped delete: Path 'a_directory' is a directory" in result
    assert dir_to_delete.is_dir()  # Should still exist


# --- Update File Tests ---
def test_update_file_simple_replace(test_dir: Path):
    file_to_update = test_dir / "update_me.txt"
    original_content = "Line 1\nLine 2\nLine 3"
    file_to_update.write_text(original_content, encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: update_me.txt
@@ -1,3 +1,3 @@
 Line 1
-Line 2
+Replaced Line 2
 Line 3
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Updated file: update_me.txt" in result
    assert "Error" not in result
    # Expect LF endings
    assert file_to_update.read_text(encoding="utf-8") == "Line 1\nReplaced Line 2\nLine 3"


def test_update_file_add_line(test_dir: Path):
    file_to_update = test_dir / "add_line.txt"
    original_content = "First line\nThird line"
    file_to_update.write_text(original_content, encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: add_line.txt
@@ -1,2 +1,3 @@
 First line
+Second line added
 Third line
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Updated file: add_line.txt" in result
    assert "Error" not in result
    assert file_to_update.read_text(encoding="utf-8") == "First line\nSecond line added\nThird line"


def test_update_file_delete_line(test_dir: Path):
    file_to_update = test_dir / "delete_line.txt"
    original_content = "Line A\nLine B (to delete)\nLine C"
    file_to_update.write_text(original_content, encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: delete_line.txt
@@ -1,3 +1,2 @@
 Line A
-Line B (to delete)
 Line C
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Updated file: delete_line.txt" in result
    assert "Error" not in result
    assert file_to_update.read_text(encoding="utf-8") == "Line A\nLine C"


def test_update_file_multiple_hunks(test_dir: Path):
    file_to_update = test_dir / "multi_hunk.txt"
    original_content = "--- Start ---\nLine One\nLine Two\n--- Middle ---\nLine Three\nLine Four\n--- End ---"
    file_to_update.write_text(original_content, encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: multi_hunk.txt
@@ -1,3 +1,3 @@
 --- Start ---
-Line One
+Line 1 Updated
 Line Two
@@ -4,4 +4,4 @@
 --- Middle ---
 Line Three
-Line Four
+Line 4 Updated
 --- End ---
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Updated file: multi_hunk.txt" in result
    assert "Error" not in result
    expected_content = (
        "--- Start ---\nLine 1 Updated\nLine Two\n--- Middle ---\nLine Three\nLine 4 Updated\n--- End ---"
    )
    assert file_to_update.read_text(encoding="utf-8") == expected_content


def test_update_file_context_mismatch(test_dir: Path):
    file_to_update = test_dir / "context_err.txt"
    original_content = "Line 1\nLine X - Incorrect\nLine 3"  # Context will mismatch
    file_to_update.write_text(original_content, encoding="utf-8")
    # This patch expects ' Line 3' as context after deleting 'Line 2'
    patch = """*** Begin Patch
*** Update File: context_err.txt
@@ -1,3 +1,2 @@
 Line 1
-Line 2
 Line 3
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    # Stricter checks should now cause an error
    assert "Error" in result
    # The error should be due to the deletion mismatch now
    assert "Patch mismatch in 'context_err.txt': Deleting line 2" in result
    # Ensure file wasn't changed
    assert file_to_update.read_text(encoding="utf-8") == original_content


def test_update_file_delete_context_mismatch(test_dir: Path):
    file_to_update = test_dir / "delete_context_err.txt"
    original_content = "Line 1\nDIFFERENT LINE\nLine 3"  # Delete line mismatch
    file_to_update.write_text(original_content, encoding="utf-8")
    # This patch expects to delete 'Line 2'
    patch = """*** Begin Patch
*** Update File: delete_context_err.txt
@@ -1,3 +1,2 @@
 Line 1
-Line 2
 Line 3
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    # Now expects an error due to stricter delete check
    assert "Error" in result
    assert "Patch mismatch in 'delete_context_err.txt': Deleting line 2" in result
    # Ensure file wasn't changed
    assert file_to_update.read_text(encoding="utf-8") == original_content


def test_update_file_not_found(test_dir: Path):
    patch = """*** Begin Patch
*** Update File: non_existent_update.txt
@@ -1,1 +1,1 @@
-a
+b
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "File to update not found" in result


def test_update_with_no_trailing_newline_original(test_dir: Path):
    file_to_update = test_dir / "no_newline.txt"
    original_content = "Line 1"  # No trailing newline
    file_to_update.write_text(original_content, encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: no_newline.txt
@@ -1,1 +1,1 @@
-Line 1
+Line One Updated
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Updated file: no_newline.txt" in result
    assert "Error" not in result
    assert file_to_update.read_text(encoding="utf-8") == "Line One Updated"


def test_update_with_added_trailing_newline(test_dir: Path):
    file_to_update = test_dir / "add_newline.txt"
    original_content = "Line 1"  # No trailing newline
    file_to_update.write_text(original_content, encoding="utf-8")
    # Patch adds a newline via the '+' line itself
    patch_content_adds_newline = """*** Begin Patch
*** Update File: add_newline.txt
@@ -1,1 +1,1 @@
-Line 1
+Line One Updated\n
*** End of File
*** End Patch"""
    result = apply_patch(patch_content_adds_newline)
    assert "Updated file: add_newline.txt" in result
    assert "Error" not in result
    assert file_to_update.read_text(encoding="utf-8") == "Line One Updated\n"


def test_update_with_deleted_trailing_newline(test_dir: Path):
    file_to_update = test_dir / "del_newline.txt"
    original_content = "Line 1\n"  # Has trailing newline
    file_to_update.write_text(original_content, encoding="utf-8")
    # Patch content for deletion needs to match exactly, including newline
    patch_content_removes_newline = """*** Begin Patch
*** Update File: del_newline.txt
@@ -1,1 +1,1 @@
-Line 1\n
+Line One Updated
*** End of File
*** End Patch"""
    result = apply_patch(patch_content_removes_newline)
    assert "Updated file: del_newline.txt" in result
    assert "Error" not in result
    assert file_to_update.read_text(encoding="utf-8") == "Line One Updated"


# --- Move File Tests ---
def test_move_file(test_dir: Path):
    file_to_move = test_dir / "original_name.txt"
    original_content = "This will be moved."
    file_to_move.write_text(original_content, encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: original_name.txt
*** Move to: new_name_updated.txt
@@ -1,1 +1,1 @@
-This will be moved.
+This content was moved and updated.
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Updated and moved" in result
    assert "'original_name.txt' to 'new_name_updated.txt'" in result
    assert "Error" not in result
    assert not file_to_move.exists()
    new_file = test_dir / "new_name_updated.txt"
    assert new_file.exists()
    assert new_file.read_text(encoding="utf-8") == "This content was moved and updated."


def test_move_file_destination_exists(test_dir: Path):
    original_file = test_dir / "move_me.txt"
    destination_file = test_dir / "already_here.txt"
    original_file.write_text("Original", encoding="utf-8")
    destination_file.write_text("Destination", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: move_me.txt
*** Move to: already_here.txt
@@ -1,1 +1,1 @@
-Original
+Updated but fails
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "destination already exists" in result
    assert original_file.exists()
    assert original_file.read_text(encoding="utf-8") == "Original"
    assert destination_file.exists()
    assert destination_file.read_text(encoding="utf-8") == "Destination"


def test_move_file_to_subdir(test_dir: Path):
    file_to_move = test_dir / "move_into_subdir.txt"
    file_to_move.write_text("Content", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: move_into_subdir.txt
*** Move to: newdir/moved_file.txt
@@ -1,1 +1,1 @@
-Content
+New Content in Subdir
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Updated and moved" in result
    assert "Error" not in result
    assert not file_to_move.exists()
    new_file = test_dir / "newdir" / "moved_file.txt"
    assert new_file.exists()
    assert new_file.parent.is_dir()
    assert new_file.read_text(encoding="utf-8") == "New Content in Subdir"


# --- Combined Operation Test ---
def test_multiple_operations(test_dir: Path):
    file_update = test_dir / "update.log"
    file_delete = test_dir / "delete.tmp"
    file_update.write_text("Initial log\n", encoding="utf-8")
    file_delete.write_text("To be deleted", encoding="utf-8")
    patch = """*** Begin Patch
*** Add File: data/new_data.csv
+col1,col2
+val1,val2
*** End of File
*** Update File: update.log
@@ -1,1 +1,2 @@
 Initial log
+Added log line
*** End of File
*** Delete File: delete.tmp
*** End Patch"""
    result = apply_patch(patch)
    assert "Created file: data/new_data.csv" in result
    assert "Updated file: update.log" in result
    assert "Deleted file: delete.tmp" in result
    assert "Error" not in result  # Ensure no errors reported

    new_csv = test_dir / "data" / "new_data.csv"
    assert new_csv.exists()
    assert new_csv.read_text(encoding="utf-8") == "col1,col2\nval1,val2"
    # Expect LF endings after write
    assert file_update.read_text(encoding="utf-8") == "Initial log\nAdded log line\n"
    assert not file_delete.exists()


# --- Error Handling and Invalid Format Tests ---
def test_invalid_patch_format_no_prefix():
    patch = """*** Add File: missing_prefix.txt
+content
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "Must start with" in result


def test_invalid_patch_format_no_suffix():
    patch = """*** Begin Patch
*** Add File: missing_suffix.txt
+content"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "Must end with" in result


def test_invalid_hunk_line_prefix(test_dir: Path):
    file_update = test_dir / "bad_hunk.txt"
    file_update.write_text("Line 1\nLine 2", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: bad_hunk.txt
@@ -1,2 +1,2 @@
 Line 1
*Line 2 with bad prefix
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "Invalid line prefix" in result
    assert file_update.read_text(encoding="utf-8") == "Line 1\nLine 2"  # Unchanged


def test_unexpected_line_outside_block():
    patch = """*** Begin Patch
*** Add File: a.txt
+A content
*** End of File
This line should not be here
*** Delete File: b.txt
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "Unexpected line outside operation block" in result


# --- Path Safety Tests ---
def test_path_traversal_error_relative(test_dir: Path):
    patch = """*** Begin Patch
*** Add File: ../outside_project.txt
+Trying to escape
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "outside of project root" in result
    assert not (test_dir.parent / "outside_project.txt").exists()


def test_absolute_path_error(test_dir: Path):
    abs_path_str = "/etc/passwd" if os.name != "nt" else "C:\\Windows\\System32\\drivers\\etc\\hosts"
    abs_path_fstr = abs_path_str.replace("\\", "\\\\")
    patch = f"""*** Begin Patch
*** Add File: {abs_path_fstr}
+Malicious content
*** End of File
*** End Patch"""
    result = apply_patch(patch)
    assert "Error" in result
    assert "Absolute paths are not allowed" in result


def test_empty_patch_text():
    result = apply_patch("")
    assert "Error" in result
    assert "required" in result


def test_patch_with_no_operations():
    patch = """*** Begin Patch
*** End Patch"""
    result = apply_patch(patch)
    assert "contained no operations" in result


def test_patch_ends_abruptly_after_command(test_dir: Path):
    # Test parsing when EOF marker might be missing before suffix
    patch_missing_suffix = """*** Begin Patch
*** Add File: abrupt.txt
+Some content"""
    result = apply_patch(patch_missing_suffix)
    assert "Error" in result
    assert "Must end with" in result

    # Test case where EOF is missing but suffix is present
    patch_missing_eof = """*** Begin Patch
*** Add File: abrupt.txt
+Some content
*** End Patch"""
    result_missing_eof = apply_patch(patch_missing_eof)
    # The corrected parser should handle this
    assert "Created file: abrupt.txt" in result_missing_eof
    assert (test_dir / "abrupt.txt").read_text() == "Some content"
    # The warning is printed, not returned
    assert "Error" not in result_missing_eof
    # assert "Warning" in result_missing_eof # This assertion is removed
