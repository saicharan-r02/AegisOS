import ast
import os
from typing import List,Optional
from pydantic import BaseModel,Field
from aegis_os.tools.base import BaseAegisTool,ToolResult

class ASTGrepArgs(BaseModel):
    symbol_name: str=Field(
        description="Name of the function, class, or method to search for."
    )
    search_path: str=Field(
        description="Directory or file to search. Searches recursively for directories."
    )
    symbol_type: Optional[str]=Field(
        default=None,
        description="Type of symbol: 'function','class',or None for both.",
    )

class _ASTMatch:
    def __init__(self,file: str,line: int,kind: str,name: str,qualified: str):
        self.file=file
        self.line=line
        self.kind=kind
        self.name=name
        self.qualified=qualified #e.g., ClassName.method_name

    def __str__(self) -> str:
        return f"{self.file}:{self.line} [{self.kind}] {self.qualified}"


def _grep_file(filepath: str,symbol_name: str,symbol_type: Optional[str]) -> List[_ASTMatch]:
    matches: List[_ASTMatch]=[]
    try:
        with open(filepath,"r",encoding="utf-8",errors="ignore") as f:
            source=f.read()
        tree=ast.parse(source,filename=filepath)
    except (SyntaxError,OSError):
        return matches

    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            if symbol_type and symbol_type != "function":
                continue
            if node.name.lower()==symbol_name.lower() or symbol_name.lower() in node.name.lower():
                parent=_find_parent_class(tree,node)
                qualified=f"{parent}.{node.name}" if parent else node.name
                matches.append(
                    _ASTMatch(filepath,node.lineno,"function",node.name,qualified)
                )
        elif isinstance(node,ast.ClassDef):
            if symbol_type and symbol_type != "class":
                continue
            if node.name.lower()==symbol_name.lower() or symbol_name.lower() in node.name.lower():
                matches.append(
                    _ASTMatch(filepath,node.lineno,"class",node.name,node.name)
                )
    return matches


def _find_parent_class(tree: ast.AST, target_node: ast.AST) -> Optional[str]:
    """Walk the tree and find the immediate parent ClassDef of the target node."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in ast.walk(node):
                if child is target_node:
                    return node.name
    return None


class ASTGrepTool(BaseAegisTool):
    """
    Search Python source files for function/class definitions by name using AST parsing.
    Returns file path, line number, and qualified symbol name. Does not read file
    contents into context — safe for large codebases.
    """
    name="ast_grep"
    description=(
        "Search Python source files for function or class definitions by name using "
        "AST parsing. Returns file path and line number without reading file contents. "
        "Use symbol_type='function' or 'class' to narrow results."
    )
    args_schema=ASTGrepArgs

    def _execute(self, args: ASTGrepArgs) -> ToolResult:
        search_path=args.search_path
        all_matches: List[_ASTMatch]=[]

        if os.path.isfile(search_path):
            python_files=[search_path]
        elif os.path.isdir(search_path):
            python_files=[]
            for root,_dirs,files in os.walk(search_path):
                for fname in files:
                    if fname.endswith(".py"):
                        python_files.append(os.path.join(root,fname))
        else:
            return ToolResult.fail(error=f"Path does not exist: {search_path}")

        for fpath in python_files:
            all_matches.extend(_grep_file(fpath,args.symbol_name,args.symbol_type))

        if not all_matches:
            return ToolResult(
                success=True,
                output=f"No symbols matching '{args.symbol_name}' found in {search_path}.",
                error=None,
                metadata={"match_count": 0},
            )

        lines = [str(m) for m in all_matches]
        return ToolResult(
            success=True,
            output="\n".join(lines),
            error=None,
            metadata={"match_count": len(all_matches)},
        )