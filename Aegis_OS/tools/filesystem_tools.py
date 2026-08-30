import os
import re
from pathlib import Path
from typing import Optional,List,Dict,Any
from pydantic import BaseModel,Field

from Aegis_OS.tools.base import BaseAegisTool,ToolResult

def _resolve_safe_path(target_path: str,workspace_root: Optional[str]=None) -> Path:
    """
    Ensures that target_path stays strictly inside workspace_root
    to prevent path traversal attacks (e.g. ../../etc/passwd).
    """
    root=Path(workspace_root or os.getcwd()).resolve()
    resolved=(root/target_path).resolve()
    
    if not str(resolved).startswith(str(root)):
        raise PermissionError(f"Access denied: '{target_path}' is outside the workspace sandbox '{root}'.")
    return resolved

# 1. Read File Tool
class ReadFileInput(BaseModel):
    file_path: str =Field(description="Relative path to the file within workspace.")
    start_line: Optional[int] =Field(default=1,description="1-indexed starting line number (inclusive).")
    end_line: Optional[int] =Field(default=None,description="1-indexed ending line number (inclusive).")


class ReadFileTool(BaseAegisTool):
    name="read_file"
    description="Reads a file and returns its content with 1-indexed line numbers. Supports line range slicing."
    args_schema=ReadFileInput

    def _run(self,file_path: str,start_line: Optional[int]=1,end_line: Optional[int]=None)->ToolResult:
        try:
            safe_path=_resolve_safe_path(file_path)
            if not safe_path.is_file():
                return ToolResult(success=False,error=f"File not found:'{file_path}'")

            with open(safe_path,"r",encoding="utf-8",errors="replace") as f:
                lines=f.readlines()

            total_lines=len(lines)
            start=max(1,start_line or 1)
            end=min(total_lines,end_line) if end_line else total_lines

            if start>total_lines:
                return ToolResult(success=False,error=f"start_line ({start}) exceeds total line count ({total_lines}).")

            selected_lines=lines[start-1:end]
            formatted_output=[
                f"{i+start:4d} | {line.rstrip()}"
                for i,line in enumerate(selected_lines)
            ]

            return ToolResult(
                success=True,
                output="\n".join(formatted_output),
                metadata={
                    "file_path":file_path,
                    "total_lines":total_lines,
                    "lines_returned":len(selected_lines),
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

# 2. Write File Tool
class WriteFileInput(BaseModel):
    file_path: str =Field(description="Relative path to the file to create or overwrite.")
    content: str =Field(description="The exact text content to write.")
    overwrite: bool =Field(default=True,description="Whether to overwrite existing files.")

class WriteFileTool(BaseAegisTool):
    name="write_file"
    description="Safely writes content to a file. Automatically creates any missing parent directories."
    args_schema=WriteFileInput

    def _run(self,file_path: str,content: str,overwrite: bool =True)->ToolResult:
        try:
            safe_path=_resolve_safe_path(file_path)
            if safe_path.exists() and not overwrite:
                return ToolResult(success=False,error=f"File already exists and overwrite=False: '{file_path}'")

            safe_path.parent.mkdir(parents=True,exist_ok=True)
            with open(safe_path,"w",encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} characters to '{file_path}'.",
                metadata={"file_path": file_path,"bytes_written":len(content.encode("utf-8"))}
            )
        except Exception as e:
            return ToolResult(success=False,error=str(e))

# 3. List Directory Tool
class ListDirInput(BaseModel):
    directory_path: str =Field(default=".",description="Relative path of directory to inspect.")
    max_depth: int =Field(default=2,description="Maximum directory depth to traverse.")

class ListDirTool(BaseAegisTool):
    name="list_dir"
    description="Lists files and folders within a directory up to a specific depth."
    args_schema=ListDirInput

    def _run(self,directory_path: str =".",max_depth: int =2) -> ToolResult:
        try:
            safe_root=_resolve_safe_path(directory_path)
            if not safe_root.is_dir():
                return ToolResult(success=False, error=f"Directory not found: '{directory_path}'")

            items=[]
            for root,dirs,files in os.walk(safe_root):
                rel_root=Path(root).relative_to(safe_root)
                depth=len(rel_root.parts)
                if depth>=max_depth:
                    dirs.clear()
                    continue

                indent="  "*depth
                folder_name=Path(root).name if str(rel_root)!="." else directory_path
                items.append(f"{indent}[DIR]  {folder_name}/")

                for f in files:
                    file_indent="  "*(depth+1)
                    items.append(f"{file_indent}[FILE] {f}")

            return ToolResult(
                success=True,
                output="\n".join(items) if items else "(Empty directory)",
                metadata={"directory": directory_path}
            )
        except Exception as e:
            return ToolResult(success=False,error=str(e))

# 4. Search Code Tool (Grep / Pattern Matching)
class SearchCodeInput(BaseModel):
    pattern: str =Field(description="Regex or literal pattern to search for.")
    directory_path: str =Field(default=".",description="Subdirectory to search inside.")
    file_extension: Optional[str] =Field(default=None,description="Optional extension filter like '.py' or '.js'.")

class SearchCodeTool(BaseAegisTool):
    name="search_code"
    description="Searches for regex/text patterns across files in the workspace, returning matching line numbers and snippets."
    args_schema=SearchCodeInput

    def _run(self,pattern: str,directory_path: str=".",file_extension: Optional[str] =None) -> ToolResult:
        try:
            safe_root=_resolve_safe_path(directory_path)
            regex=re.compile(pattern, re.IGNORECASE)
            matches: List[str]=[]

            for root,_,files in os.walk(safe_root):
                # Ignore hidden directories and virtualenvs
                if any(part.startswith(".") or part in ["node_modules","__pycache__","venv"] for part in Path(root).parts):
                    continue

                for file in files:
                    if file_extension and not file.endswith(file_extension):
                        continue

                    full_path=Path(root)/file
                    try:
                        with open(full_path,"r",encoding="utf-8",errors="ignore") as f:
                            for line_idx,line in enumerate(f,start=1):
                                if regex.search(line):
                                    rel_path=full_path.relative_to(Path(os.getcwd()).resolve())
                                    matches.append(f"{rel_path}:{line_idx} | {line.strip()}")
                    except Exception:
                        continue

            if not matches:
                return ToolResult(success=True,output=f"No matches found for pattern: '{pattern}'")

            return ToolResult(
                success=True,
                output="\n".join(matches[:100]),  # Limit to first 100 matches
                metadata={"pattern": pattern,"match_count": len(matches)}
            )
        except Exception as e:
            return ToolResult(success=False,error=str(e))
