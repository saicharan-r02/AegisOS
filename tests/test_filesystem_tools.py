import os
import pytest
from pathlib import Path
from Aegis_OS.tools.filesystem_tools import (ReadFileTool,WriteFileTool,ListDirTool,SearchCodeTool,_resolve_safe_path)

def test_write_and_read_file(tmp_path):
    # Change cwd context to tmp_path for test isolation
    orig_cwd=os.getcwd()
    try:
        os.chdir(tmp_path)
        write_tool=WriteFileTool()
        read_tool=ReadFileTool()
        # 1. Write file
        content="line one\nline two\nline three\nline four"
        w_res=write_tool.execute(file_path="src/main.py",content=content)
        assert w_res.success is True
        # 2. Read whole file
        r_res=read_tool.execute(file_path="src/main.py")
        assert r_res.success is True
        assert "1 | line one" in r_res.output
        assert "4 | line four" in r_res.output
        # 3. Read slice (lines 2 to 3)
        slice_res = read_tool.execute(file_path="src/main.py",start_line=2,end_line=3)
        assert slice_res.success is True
        assert "2 | line two" in slice_res.output
        assert "3 | line three" in slice_res.output
        assert "line one" not in slice_res.output
    finally:
        os.chdir(orig_cwd)

def test_path_traversal_protection(tmp_path):
    orig_cwd=os.getcwd()
    try:
        os.chdir(tmp_path)
        read_tool=ReadFileTool()

        # Attempting to read outside workspace should fail safely
        res=read_tool.execute(file_path="../../some_secret.txt")
        assert res.success is False
        assert "access denied" in res.error.lower()
    finally:
        os.chdir(orig_cwd)

def test_search_code_tool(tmp_path):
    orig_cwd=os.getcwd()
    try:
        os.chdir(tmp_path)
        write_tool=WriteFileTool()
        search_tool=SearchCodeTool()

        write_tool.execute(file_path="app.py",content="def calculate_total(price):\n    return price * 1.2\n")
        write_tool.execute(file_path="utils.py",content="TAX_RATE = 1.2\n")

        # Search for 'calculate_total'
        res=search_tool.execute(pattern="calculate_total")
        assert res.success is True
        assert "app.py:1" in res.output
        assert "calculate_total" in res.output
    finally:
        os.chdir(orig_cwd)