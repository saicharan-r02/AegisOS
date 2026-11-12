"""Project profiler that auto-detects languages, package managers,

commands, and convention rules from repository manifests and documentation.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class ProjectProfile(BaseModel):
    """Normalized structured profile of a codebase."""

    primary_language: str = Field(
        default="python", description="Primary detected programming language"
    )
    languages: list[str] = Field(default_factory=list, description="All detected languages")
    package_manager: str | None = Field(
        default=None, description="Detected package manager e.g. pip, npm, cargo"
    )
    test_command: str = Field(default="pytest", description="Default command to run test suite")
    lint_command: str = Field(default="ruff check .", description="Default command to run linter")
    build_command: str | None = Field(
        default=None, description="Default command to build or type-check"
    )
    rules: dict[str, str] = Field(
        default_factory=dict, description="Rules extracted from markdown docs"
    )
    frameworks: list[str] = Field(
        default_factory=list, description="Detected frameworks e.g. fastapi, react, django"
    )

    def to_context_prompt(self) -> str:
        """Render a concise summary suitable for injection into agent context."""
        parts = [
            "### Project Profile:",
            f"- Primary Language: {self.primary_language}",
            f"- All Languages: {', '.join(self.languages) if self.languages else self.primary_language}",
            f"- Package Manager: {self.package_manager or 'standard'}",
            f"- Test Command: {self.test_command}",
            f"- Lint Command: {self.lint_command}",
        ]
        if self.build_command:
            parts.append(f"- Build Command: {self.build_command}")
        if self.frameworks:
            parts.append(f"- Frameworks: {', '.join(self.frameworks)}")
        if self.rules:
            parts.append("### Project Rules & Conventions:")
            for source, content in self.rules.items():
                snippet = content.strip()[:600]
                parts.append(f"[{source}]:\n{snippet}")
        return "\n".join(parts)


class ProjectProfiler:
    """Inspects workspace directory to discover languages, commands, and rules."""

    _RULE_FILENAMES = (
        "AEGIS.md",
        "AGENTS.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "README.md",
        ".cursorrules",
    )

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def profile(self, use_cache: bool = True) -> ProjectProfile:
        """Analyze repository and return ProjectProfile, caching to .aegis/project.json."""
        cache_file = self.workspace_root / ".aegis" / "project.json"
        if use_cache and cache_file.is_file():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return ProjectProfile.model_validate(data)
            except Exception:
                pass

        languages: set[str] = set()
        frameworks: set[str] = set()
        package_manager: str | None = None
        test_command = "pytest"
        lint_command = "ruff check ."
        build_command: str | None = None

        # Check Python
        pyproject = self.workspace_root / "pyproject.toml"
        reqs = self.workspace_root / "requirements.txt"
        setup_py = self.workspace_root / "setup.py"
        if (
            pyproject.is_file()
            or reqs.is_file()
            or setup_py.is_file()
            or any(self.workspace_root.glob("*.py"))
        ):
            languages.add("python")
            package_manager = "pip"
            test_command = "pytest"
            lint_command = "ruff check ."
            if pyproject.is_file():
                try:
                    text = pyproject.read_text(encoding="utf-8")
                    if "poetry" in text:
                        package_manager = "poetry"
                        test_command = "poetry run pytest"
                    elif "flit" in text:
                        package_manager = "flit"
                    if "fastapi" in text.lower():
                        frameworks.add("fastapi")
                    if "django" in text.lower():
                        frameworks.add("django")
                except Exception:
                    pass

        # Check JavaScript / TypeScript
        pkg_json = self.workspace_root / "package.json"
        if pkg_json.is_file():
            languages.add("javascript")
            package_manager = "npm"
            if (self.workspace_root / "pnpm-lock.yaml").is_file():
                package_manager = "pnpm"
            elif (self.workspace_root / "yarn.lock").is_file():
                package_manager = "yarn"

            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "typescript" in deps or (self.workspace_root / "tsconfig.json").is_file():
                    languages.add("typescript")
                if "react" in deps:
                    frameworks.add("react")
                if "next" in deps:
                    frameworks.add("next.js")
                if "vue" in deps:
                    frameworks.add("vue")

                scripts = data.get("scripts", {})
                if "test" in scripts:
                    test_command = f"{package_manager} test"
                if "lint" in scripts:
                    lint_command = f"{package_manager} run lint"
                if "build" in scripts:
                    build_command = f"{package_manager} run build"
            except Exception:
                pass

        # Check Go
        if (self.workspace_root / "go.mod").is_file() or any(self.workspace_root.glob("*.go")):
            languages.add("go")
            package_manager = "go"
            test_command = "go test ./..."
            lint_command = "golangci-lint run"

        # Check Rust
        if (self.workspace_root / "Cargo.toml").is_file():
            languages.add("rust")
            package_manager = "cargo"
            test_command = "cargo test"
            lint_command = "cargo clippy"
            build_command = "cargo build"

        # Check Java
        if (self.workspace_root / "pom.xml").is_file():
            languages.add("java")
            package_manager = "maven"
            test_command = "mvn test"
            build_command = "mvn compile"
        elif (self.workspace_root / "build.gradle").is_file() or (
            self.workspace_root / "build.gradle.kts"
        ).is_file():
            languages.add("java")
            package_manager = "gradle"
            test_command = "gradle test"
            build_command = "gradle build"

        # Determine primary language
        ordered_langs = ["python", "typescript", "javascript", "rust", "go", "java"]
        primary = "python"
        for candidate in ordered_langs:
            if candidate in languages:
                primary = candidate
                break
        if not languages:
            languages.add("python")

        # Discover project rules from documentation files
        rules: dict[str, str] = {}
        for fname in self._RULE_FILENAMES:
            rpath = self.workspace_root / fname
            if rpath.is_file():
                try:
                    rules[fname] = rpath.read_text(encoding="utf-8")[:4000]
                except Exception:
                    pass

        profile = ProjectProfile(
            primary_language=primary,
            languages=sorted(languages),
            package_manager=package_manager,
            test_command=test_command,
            lint_command=lint_command,
            build_command=build_command,
            rules=rules,
            frameworks=sorted(frameworks),
        )

        # Cache profile
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        except Exception:
            pass

        return profile
