"""テストをまたいで、前のテストのオブジェクトが残らないこと(`test/conftest.py` の解放の確認)。

`User` のシミュレーションは、テストが終わっても、クライアントとその要素を削除しない。何もしないと、
次のものが、前のテストのオブジェクトを保持し続け、フル GC(`nicegui_reset_globals` が、各テストの前後に行う)が
テストの数だけ遅くなる(全体のテストが遅くなる原因だった)。
- クラスの `ui.refreshable`(`GanttChart.render` など)の `targets`
- FastAPI の `lru_cache`(ページ関数をキーにする。ページ関数のクロージャが、インスタンスを持つ)
- `weakref.finalize` の登録簿(`ui.dialog` が、自分自身を捕まえるラムダを登録する)
積み上がっていないことを、同じテストを繰り返して、生きているインスタンスの数で確かめる。
"""

import gc

from pathlib import Path

import httpx
import pytest
from nicegui import context, ui
from nicegui.testing import User

from projectapp.calendar import save_cache
from projectapp.forms import open_section_dialog
from projectapp.gantt import GanttActions, GanttChart
from projectapp.models import Project
from projectapp.views import MainView

NOOP = GanttActions(*([lambda *args, **kwargs: None] * 7))


# 同じテストを 2 回走らせる。2 回目に、1 回目のインスタンスが残っていれば、件数が 2 になる
@pytest.mark.parametrize("round_", [1, 2])
async def test_a_gantt_chart_does_not_outlive_its_test(user: User, round_: int) -> None:
    @ui.page("/")
    def index() -> None:
        GanttChart(Project("demo"), {}, NOOP).build()

    await user.open("/")
    assert len(GanttChart.render.targets) == 1


@pytest.mark.parametrize("round_", [1, 2])
async def test_a_main_view_does_not_outlive_its_test(user: User, tmp_path: Path, round_: int) -> None:
    save_cache({}, tmp_path)  # 祝日の取得を起こさない

    @ui.page("/")
    def index() -> None:
        MainView(tmp_path, httpx.MockTransport(lambda request: httpx.Response(200))).build()

    await user.open("/")
    assert len(MainView.title.targets) == 1
    assert len(MainView.theme_buttons.targets) == 1


ROUNDS = 6
# 直前のテストの分は、pytest の fixture の後始末が、次のテストの始まりまで持つので、残ってよい
MAX_LIVE_VIEWS = 2


def live_main_views() -> int:
    gc.collect()
    return sum(type(o) is MainView for o in gc.get_objects())


# ページ関数のクロージャ(FastAPI のキャッシュ)と、開いたままのダイアログ(`weakref.finalize` の登録簿。
# ボタンが `MainView` のメソッドを持つ)の 2 つの経路は、片方だけ断っても、もう片方が同じ `MainView` を保持する。
# どちらかが残ると、`MainView` がテストの数だけ積まれる。
@pytest.mark.parametrize("round_", range(ROUNDS))
async def test_main_views_do_not_pile_up_across_tests(user: User, tmp_path: Path, round_: int) -> None:
    assert live_main_views() <= MAX_LIVE_VIEWS, f"前のテストの MainView が残っている(round {round_})"
    save_cache({}, tmp_path)  # 祝日の取得を起こさない
    captured: list[MainView] = []  # ページ関数のクロージャが持つ

    @ui.page("/")
    def index() -> None:
        captured.append(MainView(tmp_path, httpx.MockTransport(lambda request: httpx.Response(200))))
        captured[0].build()

    await user.open("/")
    user.find(marker="add-section").click()
    await user.should_see(marker="section-name")  # ダイアログを開いたまま、テストが終わる


def test_the_baseline_heap_is_frozen_out_of_the_full_gc() -> None:
    # nicegui_reset_globals は、各テストの前後にフル GC を行う。import 済みの基本のオブジェクトを走査し続けると、
    # 1 回あたり約 50ms かかるので、conftest がセッションの最初に凍結する
    assert gc.get_freeze_count() > 50_000
