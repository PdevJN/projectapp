import json
from pathlib import Path

import pytest

from projectapp import storage
from projectapp.models import Project, Section, Task, TaskKind
from projectapp.storage import (
    referrers_of,
    rename_project_files,
    save_project,
)


def reference_to(target: str) -> Task:
    return Task("参照", id="ref", kind=TaskKind.REFERENCE, ref_project=target)


def make(base: Path, name: str, target: str | None = None, *, nested: bool = False):
    project = Project(name)
    if target is not None:
        task = reference_to(target)
        if nested:
            project.sections.append(Section("S", id="s", tasks=[task]))
        else:
            project.tasks.append(task)
    return save_project(project, base)


def refs(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(tasks: list[dict], sections: list[dict]) -> None:
        found.extend(
            t["ref_project"] for t in tasks if t["kind"] == TaskKind.REFERENCE.value
        )
        for section in sections:
            walk(section["tasks"], section["sections"])

    walk(raw["tasks"], raw["sections"])
    return found


def test_rename_moves_the_project_file(tmp_path: Path) -> None:
    old = make(tmp_path, "旧")
    before = old.read_text(encoding="utf-8")
    rename_project_files(tmp_path, "旧", "新")
    assert not old.exists()
    assert (tmp_path / "新.json").read_text(encoding="utf-8") == before


def test_rename_rewrites_references_including_those_in_sections(
    tmp_path: Path,
) -> None:
    make(tmp_path, "旧")
    top = make(tmp_path, "参照元1", "旧")
    nested = make(tmp_path, "参照元2", "旧", nested=True)
    other = make(tmp_path, "別", "別の参照先")
    other_before = other.read_text(encoding="utf-8")
    changed = rename_project_files(tmp_path, "旧", "新")
    assert sorted(changed) == ["参照元1", "参照元2"]
    assert refs(top) == ["新"]
    assert refs(nested) == ["新"]
    assert other.read_text(encoding="utf-8") == other_before


def test_rewritten_file_keeps_everything_else(tmp_path: Path) -> None:
    make(tmp_path, "旧")
    path = make(tmp_path, "参照元", "旧")
    before = json.loads(path.read_text(encoding="utf-8"))
    rename_project_files(tmp_path, "旧", "新")
    after = json.loads(path.read_text(encoding="utf-8"))
    after["tasks"][0]["ref_project"] = "旧"
    assert after == before


def test_referrers_lists_names_and_ignores_broken_files(tmp_path: Path) -> None:
    make(tmp_path, "旧")
    make(tmp_path, "参照元", "旧")
    make(tmp_path, "無関係")
    (tmp_path / "壊れ.json").write_text("{", encoding="utf-8")
    assert referrers_of(tmp_path, "旧") == ["参照元"]


def test_rename_refuses_an_existing_name_and_changes_nothing(tmp_path: Path) -> None:
    old = make(tmp_path, "旧")
    make(tmp_path, "新")
    referrer = make(tmp_path, "参照元", "旧")
    before = referrer.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        rename_project_files(tmp_path, "旧", "新")
    assert old.exists()
    assert referrer.read_text(encoding="utf-8") == before


def test_rename_rejects_an_invalid_name(tmp_path: Path) -> None:
    make(tmp_path, "旧")
    with pytest.raises(ValueError):
        rename_project_files(tmp_path, "旧", "a/b")
    assert (tmp_path / "旧.json").exists()


def test_a_failed_rewrite_restores_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = make(tmp_path, "旧")
    first = make(tmp_path, "参照元1", "旧")
    second = make(tmp_path, "参照元2", "旧")
    originals = {p: p.read_text(encoding="utf-8") for p in (old, first, second)}
    real = storage.replace_text
    calls: list[Path] = []

    def flaky(path: Path, text: str) -> None:
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(storage, "replace_text", flaky)
    with pytest.raises(OSError):
        rename_project_files(tmp_path, "旧", "新")
    monkeypatch.setattr(storage, "replace_text", real)
    assert not (tmp_path / "新.json").exists()
    for path, text in originals.items():
        assert path.read_text(encoding="utf-8") == text


def test_referrers_ignores_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    make(tmp_path, "旧")
    make(tmp_path, "参照元", "旧")
    (tmp_path / "壊れ.json").write_bytes(b"\xff\xfe\x00")
    assert referrers_of(tmp_path, "旧") == ["参照元"]
