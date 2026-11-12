import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from aegis_os.sandbox.path_guard import PathTraversalError, validate_path


@pytest.mark.parametrize(
    "attack",
    [
        "../outside.py",
        "../../outside.py",
        "src/../../../outside.py",
        "..\\..\\Windows\\System32\\config\\SAM",
        ".ENV",
        ".env.production",
        ".git/config",
        ".GIT/objects/secret",
        ".aegis/checkpoints.db",
        ".SSH/id_rsa",
        ".aws/credentials",
        "certificates/signing.PEM",
    ],
)
def test_attack_corpus_is_blocked(tmp_workspace: Path,attack: str) -> None:
    with pytest.raises(PathTraversalError):
        validate_path(attack,tmp_workspace)


@settings(max_examples=150,deadline=None)
@given(st.lists(st.sampled_from([".","..","src","nested","file.py"]),min_size=1,max_size=8))
def test_generated_traversals_never_resolve_outside(parts: list[str]) -> None:
    workspace=Path(tempfile.gettempdir())/"aegis-hypothesis-workspace"
    attack="/".join([*parts,"target.py"])
    try:
        resolved=validate_path(attack,workspace)
    except PathTraversalError:
        return
    assert resolved.is_relative_to(workspace.resolve())


def test_symlink_to_outside_workspace_is_blocked(tmp_path: Path) -> None:
    workspace=tmp_path/"workspace"
    outside=tmp_path/"outside"
    workspace.mkdir()
    outside.mkdir()
    secret=outside/"secret.txt"
    secret.write_text("no access",encoding="utf-8")
    link=workspace/"linked"
    try:
        link.symlink_to(outside,target_is_directory=True)
    except (OSError,NotImplementedError):
        pytest.skip("Symlink creation is not available in this Windows environment.")

    with pytest.raises(PathTraversalError):
        validate_path("linked/secret.txt",workspace)
