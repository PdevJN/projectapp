"""既存のプロジェクトから、設定(とタスク)を引き継いだ新規プロジェクトを作る(要望 77)。NiceGUI に依存しない。"""

from copy import deepcopy
from dataclasses import replace
from enum import StrEnum

from projectapp.models import Project, Status


class InheritScope(StrEnum):
    """引き継ぐ範囲。ダイアログの選択肢は、この一覧から作る(範囲を足すときは、ここに足す)。"""

    SETTINGS = "設定のみ"
    SETTINGS_AND_TASKS = "設定とタスク"

    @property
    def with_tasks(self) -> bool:
        return self is InheritScope.SETTINGS_AND_TASKS


def inherit_project(
    source: Project, name: str, scope: InheritScope, reset_progress: bool = True
) -> Project:
    """source を複製して、name の新規プロジェクトにする(source は変えない。`id` と日付はそのまま)。
    変更履歴は持ち越さない。reset_progress なら、タスクの状態・実績・進捗度だけを初期に戻す(追加工数は残す)。"""
    result = deepcopy(
        replace(source, history=[], history_since=None)
    )  # 履歴は持ち越さない
    result.name = name
    if not scope.with_tasks:
        result.tasks, result.sections = [], []
    elif reset_progress:
        for task in result.all_tasks():
            task.status, task.actuals, task.progress = Status.NOT_STARTED, [], None
    return result
