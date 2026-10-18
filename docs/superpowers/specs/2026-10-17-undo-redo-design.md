# 元に戻す(Undo)とやり直し(Redo)の設計(要望 36)

> **状態**: 実装済み — 要望 36 — マージ PR #24(89b058d。2026-10-17)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。

## 目的

保存前の編集を、誤操作や試行錯誤のあとでも気軽に戻せるようにする。
成功の目安は次のとおり。

- `Ctrl/Cmd+Z` で 1 つ前の状態へ、`Ctrl/Cmd+Shift+Z` で元に戻す前の状態へ往復できる。
- 保存した時点の内容まで戻すと「未保存」の扱いが消え、それより前へ戻すと再び未保存になる。

## 決めたこと

| 項目 | 決定 |
| --- | --- |
| 対象範囲 | プロジェクト全体(タスク・セクション・設定・メンバー・パラメータ・カテゴリ・URL テンプレート・イベント) |
| 方式 | 変更後スナップショット(`Project` の複製を積む) |
| 履歴の深さ | 50 件(超えたら古いものから捨てる) |
| 保存 | 履歴を残す(保存をまたいで Undo できる) |
| 履歴を破棄する場面 | 別のプロジェクトを開く・新規作成・PlantUML 取り込み・プルでの読み直し・`名前をつけて保存`(保存前の新規プロジェクトの最初の保存を含む) |
| 操作面 | キーのみ(`Ctrl/Cmd+Z`・`Ctrl/Cmd+Shift+Z`)。ヘッダーにメニューは足さない |

## 方式の比較(採用理由)

- **スナップショット(採用)**: 編集の入口を 1 本に集約すれば取りこぼしがなく、将来の編集(要望 35 の一括操作)も、1 回の呼び出しなら自動で 1 ステップになる。`is_dirty` が毎回 `asdict` で複製を作っており、費用の桁は同じ。
- コマンド方式(不採用): すべての編集に逆操作を書く必要があり、漏れやすい。
- 差分方式(不採用): このデータ量ではメモリの利点が小さく、実装が複雑になる。

## 構成

### `history.py`(新規。NiceGUI に依存しない純粋なクラス)

```python
class History:
    LIMIT = 50
    def record(self, before: Project) -> None   # 変更の直前の状態を積む。Redo は空にする
    def undo(self, current: Project) -> Project | None  # current を Redo に積み、直前の状態を返す。なければ None
    def redo(self, current: Project) -> Project | None
    def clear(self) -> None
    def can_undo(self) -> bool
    def can_redo(self) -> bool
```

- 保持するのは `Project` の複製(`deepcopy`)。呼び出し側が渡した物と履歴の中身が、同じ物を指さないようにする。
- `record` は、積む直前の状態が先頭と等しければ積まない(無変更の呼び出しを 1 ステップにしない)。
- 上限を超えたら、Undo 側の最も古いものを捨てる。Redo 側は Undo の上限で自然に制限される。

### `views.py`

- 直前の状態を `self.committed`(`Project` の複製)として持つ。`mark_clean` の `snapshot`(保存済みの内容。辞書)とは別物。
- 編集の入口を `after_edit()` に集約する。現在 `self.gantt.set_project(self.project)` を直接呼んでいる編集の経路(`apply_members`・`apply_parameters`・`apply_settings`・`apply_templates`・`apply_categories`・`apply_events`・`save_section`・`save_subsection`・`delete_task`・`move_task`・`shift_task`・`save_task`)を置き換える。
  - `after_edit()`: `self.project != self.committed` なら、`history.record(self.committed)` のあと `self.committed = deepcopy(self.project)` とし、`gantt.set_project` で描き直す。等しければ描き直しだけ。
- `undo()` / `redo()`: `History` から状態を取り、`self.project` を差し替え、`self.committed` を合わせ、`gantt.set_project` で描き直し、通知する。
  - `is_dirty` は内容の比較なので変更しない。
  - 折りたたみ・絞り込み・スクロールは `Project` の外にあるので、Undo では動かない。
- 履歴の破棄(`history.clear()` と `committed` の取り直し)は、`show_project`(開く・新規作成・PlantUML 取り込み・プル後の読み直しが通る)と、`save_as_new` の成功時に行う。
- 編集のあと、`warn_overallocation` などの通知は、今までどおり編集の経路が出す。Undo・Redo では出さない。

### `shortcuts.py`

- `Shortcut("z", "undo", "元に戻す", ctrl=True)` と `Shortcut("z", "redo", "やり直す", ctrl=True, shift=True)` を足す。`ショートカットヘルプ`に自動で載る。
- ダイアログ・プレビュー・ダッシュボードの表示中は効かない(既存の `resolve` の規則のまま)。
- `SHORTCUT_METHODS` に `undo` / `redo` を足す。
- `on_modified_key` は入力欄でも受け、`key_guard_js` は `Ctrl/Cmd` 付きの割り当てキーの標準動作を入力欄でも止める。このままだと、入力欄の `Ctrl/Cmd+Z` が文字の取り消しにならず、プロジェクトの Undo が誤爆する。
  - 入力欄(`input`・`textarea`・`select`・`contenteditable`)にフォーカスがあるときは、`undo`/`redo` をサーバーへ送らず、標準動作も止めない(標準の文字の取り消しに任せる)。入力欄を抜ければ、プロジェクトの Undo が効く。
  - 実装は、NiceGUI の `ui.keyboard` が初期設定で入力欄・ボタンのイベントを送らないことを使う。`Ctrl/Cmd+Z` は専用の 3 つ目の `ui.keyboard`(`on_undo_key`。`ignore` は `input`・`select`・`textarea`。`button` は無視しない)で受け、文字キー用(`on_plain_key`)と、入力欄でも受ける側(`on_modified_key`)では受けない。文字キー用は `button` を無視するので、ダイアログを閉じてフォーカスがボタンに戻ったあとに Undo が届かなくなるため。`key_guard_js` も、入力欄の中の `Ctrl/Cmd+Z` では `preventDefault` しない。
  - 実機(macOS のネイティブウィンドウ)で、検索欄の `Cmd+Z` が文字の取り消しになることと、入力欄の外で Undo が効くことを確かめる(実装計画の独立したタスク)。

### 通知

- `元に戻しました` / `やり直しました`
- 戻せないとき: `これ以上戻せません` / `やり直す操作がありません`

## データの流れ

```
編集の入口 → Project を書き換え → after_edit()
    → 変わっていれば history.record(committed) / committed = 複製
    → gantt.set_project()

Ctrl/Cmd+Z → history.undo(project) → project = 返された状態、committed = 複製 → gantt.set_project()
```

## エラー処理・端の挙動

- 履歴が空のときは通知だけ出し、何も変えない。
- 保存の失敗は `Project` を変えないので、履歴に影響しない。
- 保存(上書き)は履歴を残す。保存より前へ Undo すると、`is_dirty` が真になり、保存・別のプロジェクトを開く前の確認ダイアログが出る。
- `名前をつけて保存` は、プロジェクトの名前が変わり別ファイルになるので、履歴を破棄する。保存前の新規プロジェクトの最初の保存も、名前を付ける保存(`save_as_new`)を通るので、同じく破棄する。2 回目以降の上書き保存は破棄しない。
- 調べて確認したこと: タスクの編集ダイアログは、保存時に新しい `Task` を返すだけで、元を直接書き換えない。保存(`write`)は `Project` を書き換えない。

## 範囲外

- 要望 35(一括操作)そのもの。1 回の編集の入口で呼べば、自動で 1 ステップになる。
- 操作名つきの履歴の表示、`編集`メニュー。
- 折りたたみ・絞り込み・スクロールの復元。
- 履歴の永続化(アプリを閉じると消える)。

## テスト

- `History` の単体テスト: 積む・戻す・やり直す・Redo の破棄・50 件の上限・同一内容は積まない・`clear`・渡した物の複製(あとから書き換えても履歴が変わらない)。
- views の結合テスト: タスクの保存・削除・移動の Undo/Redo、設定の適用の Undo、保存をまたぐ Undo と `is_dirty`、別のプロジェクトを開いたあと・`名前をつけて保存`のあとに履歴が空であること、ダイアログ表示中にキーが効かないこと。
- ショートカットの単体テスト: `resolve` が `z` を `undo` / `redo` に振り分ける。
- 手動確認: 実際のネイティブウィンドウで、ドラッグ移動の Undo と、検索欄での `Ctrl/Cmd+Z`。

## 文書の更新

- `CLAUDE.md`(projectapp)のキーボードショートカットの節と、`docs/development.md`(モジュール構成)、`docs/requests.md`(要望 36 の状態)。
