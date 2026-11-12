"""AST-diff test-integrity guard detecting test deletion, weakened assertions, and skipped tests."""

from __future__ import annotations

import ast


class TestIntegrityGuard:
    """Inspects AST diffs of test files to prevent LLMs from gaming benchmarks."""

    @staticmethod
    def _extract_test_functions(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
        """Find all top-level and class-level test functions."""
        funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_") or node.name.endswith("_test"):
                    funcs[node.name] = node
        return funcs

    @staticmethod
    def _count_asserts(node: ast.AST) -> int:
        """Count total assert statements in a sub-tree."""
        return sum(1 for n in ast.walk(node) if isinstance(n, ast.Assert))

    @staticmethod
    def _has_trivial_asserts(node: ast.AST) -> bool:
        """Check for trivial assertions like `assert True`, `assert 1`, `assert not False`."""
        for n in ast.walk(node):
            if isinstance(n, ast.Assert):
                test = n.test
                if isinstance(test, ast.Constant) and bool(test.value) is True:
                    return True
                if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
                    if isinstance(test.operand, ast.Constant) and bool(test.operand.value) is False:
                        return True
        return False

    @staticmethod
    def _has_skip_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Detect `@pytest.mark.skip`, `@pytest.mark.xfail`, or `@unittest.skip` decorators."""
        for dec in node.decorator_list:
            dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
            if "skip" in dec_str.lower() or "xfail" in dec_str.lower():
                return True
        return False

    @staticmethod
    def _has_empty_except_pass(node: ast.AST) -> bool:
        """Detect broad `except Exception: pass` or `except: pass` in test bodies."""
        for n in ast.walk(node):
            if isinstance(n, ast.ExceptHandler):
                # Check if body is just `pass`
                if len(n.body) == 1 and isinstance(n.body[0], ast.Pass):
                    return True
        return False

    @classmethod
    def audit_test_diff(
        cls,
        before_code: str,
        after_code: str,
        task_objective: str = "",
    ) -> tuple[bool, list[str]]:
        """Audit before and after source of a test file.

        Returns (passed, list_of_tampering_violations).
        """
        violations: list[str] = []

        try:
            tree_before = ast.parse(before_code)
        except SyntaxError:
            # If before_code was invalid or empty (e.g. brand new test file), no baseline to compare against
            return True, []

        try:
            tree_after = ast.parse(after_code)
        except SyntaxError as exc:
            return False, [f"Modified test file contains syntax error: {exc}"]

        before_tests = cls._extract_test_functions(tree_before)
        after_tests = cls._extract_test_functions(tree_after)

        # 1. Detect deleted test functions
        for name in before_tests:
            if name not in after_tests:
                violations.append(
                    f"TEST DELETION DETECTED: Test function '{name}' was deleted or renamed."
                )

        # 2. Check each remaining test function
        for name, func_after in after_tests.items():
            func_before = before_tests.get(name)

            # Check for skip decorators added
            if cls._has_skip_decorators(func_after):
                if func_before and not cls._has_skip_decorators(func_before):
                    violations.append(
                        f"TEST SKIPPING DETECTED: Added skip/xfail decorator to '{name}'."
                    )
                elif not func_before:
                    violations.append(
                        f"TEST SKIPPING DETECTED: New test '{name}' has skip/xfail decorator."
                    )

            # Check for broad except: pass suppression
            if cls._has_empty_except_pass(func_after):
                if not (func_before and cls._has_empty_except_pass(func_before)):
                    violations.append(
                        f"EXCEPTION SUPPRESSION DETECTED: Added broad `except: pass` in '{name}'."
                    )

            # If function existed before, check for weakened assertions
            if func_before:
                asserts_before = cls._count_asserts(func_before)
                asserts_after = cls._count_asserts(func_after)

                if asserts_after < asserts_before:
                    violations.append(
                        f"ASSERTION WEAKENING DETECTED: Assert count in '{name}' reduced from {asserts_before} to {asserts_after}."
                    )

                if cls._has_trivial_asserts(func_after) and not cls._has_trivial_asserts(
                    func_before
                ):
                    violations.append(
                        f"TRIVIAL ASSERTION DETECTED: '{name}' contains trivial dummy assertion like `assert True`."
                    )

        # Allow intentional test updates only if explicitly declared in task objective
        objective_allows_test_edits = any(
            phrase in task_objective.lower()
            for phrase in ("update test", "modify test", "refactor test", "fix test", "delete test")
        )

        if violations and not objective_allows_test_edits:
            return False, violations

        return True, violations
