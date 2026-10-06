import gc
import sys
import weakref

import pytest
from nicegui import ui


def class_refreshables() -> list[ui.refreshable]:
    """`projectapp` のクラスに付いた `@ui.refreshable` / `@ui.refreshable_method`(例: `GanttChart.render`)。"""
    found = []
    for name, module in list(sys.modules.items()):
        if not name.startswith("projectapp."):
            continue
        for cls in list(vars(module).values()):
            if isinstance(cls, type) and cls.__module__ == name:
                found += [v for v in vars(cls).values() if isinstance(v, ui.refreshable)]
    return found


@pytest.fixture(autouse=True)
def release_refreshable_targets():
    """各テストのあとで、クラスの `ui.refreshable` が持つ対象を空にする。

    `ui.refreshable` は、描いた先の要素が削除されるまで、対象(`GanttChart` や `MainView` のインスタンス)を
    `targets` に持つ。`User` のシミュレーションは、テストが終わっても要素を削除しないので、空にしないと、
    テストの数だけ積まれ、`nicegui_reset_globals` のフル GC が、進むほど遅くなる。
    """
    yield
    for refreshable in class_refreshables():
        refreshable.targets.clear()
        refreshable.instance = None  # `__get__` が、最後に参照されたインスタンスを持つ


def clear_fastapi_caches() -> None:
    """FastAPI の `lru_cache` を空にする。ページ関数をキーに持ち、そのクロージャ(`MainView` など)ごと残る。"""
    for name, module in list(sys.modules.items()):
        if name.startswith("fastapi"):
            for value in list(vars(module).values()):
                if hasattr(value, "cache_clear"):
                    value.cache_clear()


@pytest.fixture(autouse=True)
def release_page_objects():
    """各テストのあとで、ページ関数と、ダイアログを、前のテストから引き継がない。

    次の 2 つの経路は、片方だけ断っても、もう片方が同じオブジェクトを保持するので、両方を断つ。
    - FastAPI の `lru_cache`(ページ関数のクロージャ → `MainView` → `GanttChart` → `Client`)
    - `weakref.finalize` の登録簿(`ui.dialog` が、自分自身を捕まえるラムダを登録する。ボタン → `MainView` のメソッド)
    """
    yield
    clear_fastapi_caches()
    weakref.finalize._registry.clear()


@pytest.fixture(scope="session", autouse=True)
def freeze_baseline_heap():
    """セッションの最初に、import 済みの基本のオブジェクトを、フル GC の対象から外す。

    `nicegui_reset_globals` は、各テストの前後にフル GC を行う。基本のヒープ(約 11 万オブジェクト)を
    毎回走査すると、1 回あたり約 50ms かかる(全体の約 3 割)。凍結すると、約 0.01 秒になる。
    凍結するのは、テストファイルの収集(`projectapp` と `nicegui` の import)が終わった、最初のテストの前。
    各テストが作るオブジェクトは、これまでどおり回収される。
    """
    gc.collect()
    gc.freeze()
    yield
    gc.unfreeze()
