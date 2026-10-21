"""格納先の、開いているプロジェクト以外のプロジェクトを読む。NiceGUI に依存しない。"""

from pathlib import Path

from projectapp.dashboard import LoadFailure
from projectapp.models import Project
from projectapp.storage import list_project_files, load_project


def load_others(project_dir: Path, current: Path | None) -> tuple[list[Project], list[LoadFailure]]:
    """`current`(開いているファイル)を除く、格納先のプロジェクト。読めないものは理由とともに返す。"""
    if not project_dir.is_dir():
        return [], [LoadFailure(str(project_dir), "格納先を読めません")]
    try:
        paths = list_project_files(project_dir)
    except OSError as exc:
        return [], [LoadFailure(str(project_dir), str(exc))]
    projects: list[Project] = []
    failures: list[LoadFailure] = []
    for path in paths:
        if current is not None and path.resolve() == current.resolve():
            continue
        try:
            projects.append(load_project(path))
        except Exception as exc:  # noqa: BLE001 他人のファイルの形の崩れで、ダッシュボードを止めない
            failures.append(LoadFailure(path.stem, str(exc) or type(exc).__name__))
    return projects, failures
