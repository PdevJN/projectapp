# 開発者向けメモ

## モジュール構成

| モジュール | 役割 |
|---|---|
| `main.py` | エントリポイント(NiceGUI + pywebview。静的ファイルの登録) |
| `views.py` | メイン画面(ヘッダー・チャート領域・テーマFAB・ヘルプ・プレビューの出入りと画像の保存) |
| `calendar.py` | 祝日の取得・キャッシュ(`holidays.json`)と日付種別の判定 |
| `timeline.py` | スケールごとの列生成、日時から位置・幅への変換、稼働日ベースの終了日時算出、完了予定の決め方(`effective_end`)、予定超過の判定、締切の位置、換算率(`conversion_rate`)、日工数(`effort_days`)、割り当て合計の超過(`overallocations`)(純粋関数) |
| `filtering.py` | 絞り込み条件(`TaskFilter`)とタスクの判定(`matches`)、セクションで描くタスクの決定(`visible_task_indexes`)(純粋関数) |
| `arrange.py` | タスクの移動(`move_task`)・コピー(`copy_task`)・日程のずらし(`shift_task`、左へずらせる限度 `min_shift_days`)と、画面から届く値の検証(`parse_move`・`parse_shift`)(純粋関数) |
| `gantt_drag.py` | ガントチャートのドラッグ操作用の JS と CSS(定数のみ。行は HTML5 の drag、バーは pointer イベント) |
| `gantt.py` | ガントチャートの描画とスケール切替、検索・担当者の絞り込み、セクションの折りたたみ、行のドラッグ移動・コピー、バーの横移動(日次のみ) |
| `forms.py` | タスク・セクションの入力検証、プロジェクト名の入力・ファイル一覧・未保存の確認ダイアログ、稼働時間の設定ダイアログと入力検証、メンバーのダイアログと検証(`build_members`) |
| `preview.py` | エクスポートのプレビュー(`PreviewSettings`・期間の検証・`fit_scale`・`PreviewBar`) |
| `export.py` | 画像化(html-to-image)・倍率・PNG の書き出し・保存ダイアログ(`ImageExporter`) |
| `static/` | 同梱の html-to-image(MIT) |
| `task_dialog.py` | タスクの追加・編集ダイアログ(優先度チップ、日付・時刻の入力、閉じる確認、削除) |
| `models.py` | Project / Section / Task / Member / Actual と列挙型(Priority・Status・ActualMode)のデータモデル(`Task.planned_start` / `planned_end` / `planned_end_manual` / `deadline`) |
| `storage.py` | `~/.projectapp/<名前>.json` の走査・名前の検証・保存(一時ファイル経由)・読込 |
| `config.py` | テーマ設定(`config.json`) |

## 設計書と実装計画

機能ごとに、設計 → 設計書 → 実装計画の順で進めた。設計書と実装計画は、その時点の記録で、後の変更は反映していない。現在の仕様は `CLAUDE.md`、実装の注意は下の「ファイル形式の注意」を正とする。

| 機能 | 設計書(`docs/superpowers/specs/`) |
|---|---|
| ガントチャートの基本表示 | `2026-10-02-gantt-basic-design.md` |
| 日程計算・保存・稼働時間・開始予定と完了予定 | `2026-10-03-schedule-calc-design.md`、`project-save`、`work-hours`、`planned-dates` |
| タスク編集ダイアログ | `2026-10-03-task-edit-dialog-design.md` |
| メンバーと割り当て | `2026-10-03-resources-design.md` |
| 絞り込み・ドラッグ操作 | `2026-10-04-filtering-design.md`、`drag-and-drop` |
| 実績・進捗・進捗の棒 | `2026-10-04-actuals-design.md`、`progress`、`progress-bar` |
| 実績の複数区間 | `2026-10-05-actual-intervals-design.md` |
| タスク表示のチップ | `2026-10-05-task-chips-design.md` |
| エクスポートとプレビュー | `2026-10-05-export-preview-design.md` |
| セクションの折りたたみ | `2026-10-06-section-collapse-design.md` |

実装計画は `docs/superpowers/plans/` に、同じ日付・名前(`-design` なし)である。

## ブランチ

git-flow に従う(`.claude/BRANCH.md`)。作業は `develop` から `feature/*` を切る。

## コマンド

```bash
uv sync
uv run pytest --cov=projectapp
uvx ty check src
```

全体のテストは約 1.5 分。`test/conftest.py` が、各テストのあとで、前のテストのオブジェクト(クラスの `ui.refreshable` の対象、FastAPI の `lru_cache`、`weakref.finalize` の登録簿)を空にする。`User` のシミュレーションは、テストが終わっても要素を削除しないので、空にしないと、オブジェクトがテストの数だけ積まれ、`nicegui_reset_globals` のフル GC が進むほど遅くなる(対策前は約 7 分)。`test/test_leak_cleanup.py` が、積み上がらないことを確かめる。クラスに `@ui.refreshable_method` を足しても、自動で対象になる。

## ファイル形式の注意

- セクションの折りたたみ(`GanttChart.collapsed`。セクションの添字の集合)は保存しない。切り替え(`toggle_section`)は、再描画せず、`section_views` に持つ行の表示と矢印のアイコンだけを変える(行は、折りたたみ中も作って隠す)。絞り込み中とプレビュー(読み取り専用)は無視する。セクションの並べ替え・削除を足すときは、同時に添字をずらすこと(現状はセクションの追加が末尾への追加だけなので、ずれない)。
- タスクの日付は、`planned_start`(開始予定)、`planned_end`(完了予定の手入力値)、`planned_end_manual`(手で指定)、`deadline`(締切)。完了予定は保存せず、`effective_end` で表示のたびに計算する。
- `planned_end_manual` のキーがないファイルは旧形式として読む。旧 `start` は開始予定、旧 `end` は締切になる(`end_auto` が `true` のものは自動算出だったので捨てる)。旧形式のファイルは、保存すると新形式になる。
- 読込時に `daily_hours`(有限の数値で、0より大きく24以下)と `work_start`(`HH:MM[:SS]` の文字列)を検証し、不正なファイルは「開けませんでした」と通知する。`planned_end_manual` は `true` のときだけ真として扱う。
- メンバーの `ratio`(0.1〜3.0)とタスクの `allocation`(0.01〜1.0)は、読み込み時に検証し、範囲外は「開けませんでした」と通知する。`allocation` のないファイルは 1.0 で読む。
- メンバー一覧にない担当者名は、読み込み時にメンバー(相対比率 1.0)として追加する(古いファイルの自由入力の担当者を失わないため)。担当者名の前後の空白は取り除き、空白のみは担当者なしとする。メンバー名の重複は最初の1件を残す。
- タスクの状態は `Status`(`未着手`・`実行中`・`一時停止`・`終了`)。旧名の `開始` は、読込時に `未着手` として読む(移行は要らず、保存し直すと `未着手` になる)。実績の「開始」(開始日時)とは別の語。
- 実績は `Task.actuals`(`[{"start", "end"}]`。`end` が `null` は進行中)で保存する。`actuals` のキーがない、または `null` の古いファイルは、実績なしとして読む(移行は要らない)。読込時に、開始なし・終了が開始より前・タイムゾーン付き・年の範囲外は不正として「開けませんでした」と通知する。 各区間は `progress`(区間の終わり時点の累積。0〜100 の整数か `null`)を持つ。`progress` のキーがない古いファイルは `null` として読み(移行は要らない)、整数でない値(`true`・小数・文字列)、範囲外、前の入力のある区間より小さい値は「開けませんでした」と通知する。タスクの現在の進捗度は `timeline.current_progress`(進捗度の入っている最後の区間の値)。
- ガントチャートの進捗の状態(`timeline.progress_state`)は、状態が「終了」なら完了か遅延完了(`is_overdue` で決める)、それ以外は進捗度を「進んでいるはずの割合」(`expected_progress`。開始予定〜完了予定の経過割合を暦の時間で計算し、稼働時間・祝日は見ない)と比べ、許容幅 `PROGRESS_TOLERANCE`(10pt)を超えた差で遅延・前倒しにする。進捗度か開始予定がないと判定せず(完了予定は `effective_end` が締切か開始予定の翌日で補う)、枠線・印は出ない。判定はファイルには保存しない。予定の棒は進捗度の幅だけ塗り(`fill_percent`。終了で進捗度が空なら100%)、状態は枠線と右の印で示す(色は CSS 変数 `--pstate` で、ダークテーマでは明るい色に替わる。`PROGRESS_STATE_COLORS` と `PROGRESS_STATE_DARK_COLORS`)(印は、予定の棒より右へ伸びる実績の棒と、締切の ◆ に重ならない位置に置く)。状態が「終了」(完了・遅延完了)のタスクは、タスク名に取り消し線を引く。
- ガントチャートの棒(予定・進捗の塗り・実績)の色は、タスクの状態で決める(未着手=灰青、実行中=青、一時停止=橙、終了=灰。`STATUS_COLORS`)。色は棒の `status-*` クラスが持つ CSS 変数 `--scolor` で、ダークテーマでは明るい色に替わる(`STATUS_DARK_COLORS`)。`task.color` はファイルに残すが、棒には使わない。
- `Task.project_code`(最大 `MAX_PROJECT_CODE_LENGTH` = 20 文字、前後の空白は除く)。保存は `"project_code"`(空は `""`。キーなし・`null` は空。文字列以外と超過は読込を拒否)。編集ダイアログの入力は `build_task(project_code=...)` で検証する。行のコピーは引き継ぐ。
- 名前の欄は、`task_row` の `ui.row` の枠(マーカー `task-<key>-<ti>`。固定表示・クリック・ドラッグ属性は枠が持つ)。中に、名前のラベル(`task-name-<key>-<ti>`。可変幅で省略。取り消し線は名前だけ)と、`task_chips` のチップ(`task-code-` / `task-assignee-` / `task-progress-`)を並べる。チップは縮まない。進捗は `fill_percent` の値で、棒の塗りと同じ。クリックは枠だけが処理し、名前・チップは DOM の伝播に任せる(User シミュレーションのクリックは親へ伝わらないので、テストは、枠だけがクリックの処理を持つことを確かめる)。
- 優先度の背景色は、枠の `background-color: var(--pbg)`。`prio-*` クラスが `--pbg` を持ち、ダークは `body.body--dark .prio-*` で替える(`PRIORITY_BACKGROUNDS`、`PRIORITY_DARK_BACKGROUNDS`)。予定超過の赤みは、`background-image` で重ねる。
- `gantt.ViewOptions`(`period`、`scale`、`show_chips`、`show_alerts`、`read_only`。既定値が通常の画面と同じ)。`GanttChart.options` と `view_scale`(`options.scale or scale`)で描く。ツールバーのトグルは `scale` を持ち、プレビューのスケールとは別。`set_options` は、描き直し、描画のスケールが変わるときだけ横のスクロールを先頭へ戻し、読み取り専用のときツールバーを隠す。
- 期間は `timeline.build_columns(..., period)`(開始日・終了日を含む。下限 `MIN_COLUMNS` は守る)。期間を指定したときだけ、期間と重ならない棒(予定・実績・点線・進捗の塗り・状態の印)を `bar_visible`(`timeline.in_range`)で描かない。行は残す。
- 読み取り専用: `edit_on_click` がクリックを付けず、`drag_props` とドラッグ属性を付けず、`top_add_row` とセクションの追加ボタンを出さない。
- 画像化は `export.py`: 同梱の html-to-image(`src/projectapp/static/`、MIT)で、`data-chart-content` の要素(スクロールの外へはみ出す分を含む全体)を PNG にし、base64 を Python に返す(`CAPTURE_JS`)。倍率は `export_pixel_ratio(幅) = min(2, 16384 / 幅)`(Safari 系のキャンバスの上限)。倍率 1 でも超えるとき(`exceeds_canvas`)は、警告を出して縮小して保存する。画像のデータ URL は、NiceGUI の websocket が 1 メッセージ約 1MB までなので、`window.__exportPng` に置いて、`CAPTURE_CHUNK_CHARS`(200,000 文字)ずつ取り出し、受け取ったら消す。アイコンのフォントは画像に埋め込まれないので、プレビューは、アイコン付きの編集の部品をすべて隠す。
- プレビュー(`preview.py` の `PreviewBar`、`MainView.enter_preview` / `exit_preview`): ヘッダーとツールバーを隠し、`ViewOptions(read_only=True, ...)` で同じ `GanttChart` を描き直す(別インスタンスを作らないので、絞り込みとスクロール位置が保たれる)。戻るのは「戻る」か ESC(`on_key`)。設定は保存しない。プレビューを開くとき、全期間の画像の幅が `PREVIEW_COMFORT_WIDTH_PX`(6,000px。資料に貼ると幅に合わせて縮み、文字が小さくなるため)を超えるあいだ、メイン画面のスケールから 1 段ずつ粗くして開く(`fit_scale`。細かくはしない。月次は広くても月次)。粗くしたときは、バーにお知らせを出し(`coarser_notice`)、設定を変えたら消す。開いたあとのスケールは、自動では変えない。期間は、列数の上限(`preview.MAX_COLUMNS`。日次 800・週次 400・月次 240)を超えると、描き直さずにエラーにする(初期値は検証しない)。保存中は、戻る・設定の変更を無視する(撮っている途中の画面を変えない)。期間の端で切られた棒は、進捗の塗りを、切る前の棒に対する進捗から求め直し(`clipped_fill_percent`)、描画の幅の外へはみ出す状態の印は出さない。
- 保存の流れ(`MainView.save_image`): 画像化 → 保存先の選択(pywebview のファイル保存ダイアログ) → `write_png`(一時ファイル経由。拡張子がなければ `.png`)。画像化と保存先の選択は `ImageExporter`(テストでは偽物)。ネイティブウィンドウでないときは、保存を無効にする。静的ファイルの登録(`register_static_files`)は、`main()` から一度だけ。
- 実際の画像化は、自動テストでは確かめられない(WKWebView が要る)。実機で、ライト・ダーク、日次・週次・月次、長い期間を確認する。NiceGUI の `User` は、非表示の要素を `find` で見つけず、クリックを親へ伝えず、キー入力のシミュレーションもない(テストは、`view.header_box.visible` などの属性と、`on_key` への直接の呼び出しで確かめる)。
- 実績が2件以上ある、記録方式が簡易のファイルは、ダイアログで実績の段が読み取り専用になり、保存しても実績を書き換えない(記録方式を区間にすると編集できる)。行のコピーは実績をコピーしない。バーの横移動は予定だけを動かし、実績は動かさない。
- 実績の記録方式は `Project.actual_mode`(`ActualMode`。`"simple"` / `"intervals"`)。キーのない古いファイルは `simple`、不正な値は読込を拒否する。実績の保存形式は、方式にかかわらず区間のリスト。設定ダイアログで切り替え(`apply_settings`。保存はしない)、2区間以上のタスクがあるあいだは、区間から簡易へ戻す選択を区間へ戻す(`MainView.multi_interval_count`)。
- 区間の入力の検証は `forms.build_actual_intervals`(すべて空の行は無視し、行番号は数える。開始の昇順、重ならない、終了のない区間は最後の1つだけ、進捗度は前の入力以上。エラーは「区間 N: …」)。読込(`storage`)では、重なりと並び順を検証しない(手で編集したファイルを開けなくしないため)。`suggest_status(..., intervals=True)` は、最後の区間が終わっていて進捗度が100でなければ一時停止、100なら終了を提案する。
- ダイアログは、区間のとき `IntervalFields`(行を足す)、簡易のとき `ActualFields`。どちらも `bind` / `filled` / `progress_value` / `state` の口をそろえてある(状態の提案は最後の区間で判定)。
- ガントチャートの区間の間の点線は、`gantt.actual_bars` が、隣り合う区間の隙間(前の終了 < 次の開始)にだけ引く(`ACTUAL_GAP_BACKGROUND`。マーカー `actual-gap-<key>-<ti>-<n>`)。進行中の区間の後ろ、隙間なし、重なり・逆順は引かない。
