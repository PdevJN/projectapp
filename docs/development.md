# 開発者向けメモ

## モジュール構成

| モジュール | 役割 |
|---|---|
| `main.py` | エントリポイント(NiceGUI + pywebview。静的ファイルの登録) |
| `views.py` | メイン画面(ヘッダー〔メニュー 4 つ・プロジェクトの切り替え・ダッシュボード・テーマのメニュー。プロジェクト名はヘッダーの外の `title_box`。`header` / `header_menu`(項目は `MenuItem`: 文言・アイコン・操作・マーカー・キー。`menu_entry` が左のアイコンと右端のキーを足す)/ `theme_menu`。配色とフォントは `HEADER_CSS`〕・チャート領域・ヘルプのダイアログ・プレビューとダッシュボードの出入り・画像の保存・担当者向けファイルの書き出し) |
| `calendar.py` | 祝日の取得・キャッシュ(`holidays.json`)と日付種別の判定 |
| `timeline.py` | スケールごとの列生成、日時から位置・幅への変換、稼働日ベースの終了日時算出、完了予定の決め方(`effective_end`)、予定超過の判定、締切の位置、換算率(`conversion_rate`・`assignees_rate`・`counted_assignees`)、日工数(`effort_days`)、割り当て合計の超過(`overallocations`)(純粋関数) |
| `filtering.py` | 絞り込み条件(`TaskFilter`)とタスクの判定(`matches`)、セクションで描くタスクの決定(`visible_task_indexes`)(純粋関数) |
| `arrange.py` | タスクの移動(`move_task`)・コピー(`copy_task`)・日程のずらし(`shift_task`、左へずらせる限度 `min_shift_days`)と、画面から届く値の検証(`parse_move`・`parse_shift`)(純粋関数) |
| `gantt_drag.py` | ガントチャートのドラッグ操作用の JS と CSS(定数のみ。行は HTML5 の drag、バーと名前の欄の右端は pointer イベント) |
| `gantt.py` | ガントチャートの描画とスケール切替、検索・担当者の絞り込み、セクションの折りたたみ、行のドラッグ移動・コピー、バーの横移動(日次のみ)、イベントの帯(`event_rows`。見出しの中の段の行)とセルの色(`event_tints`。`stripes` と同じ全体を覆う 1 つの `ui.html`)、名前の欄の幅(CSS 変数 `--name-w`。位置は `from_name` で式にする)、ツールバーとチャートの表示・非表示(`set_visible`。スクロール位置を覚えて戻す) |
| `forms.py` | タスク・セクションの入力検証、プロジェクト名の入力・ファイル一覧・未保存の確認ダイアログ、稼働時間の設定ダイアログと入力検証、メンバーとパラメータのタブ付きダイアログ(`members_panel`・`parameters_panel`・`open_members_parameters_dialog`。適用してもダイアログは閉じず、適用のたびにプロジェクトから行を作り直す。パラメータの適用は、メンバーの未適用の行へ `remap_levels` で伝える。未適用の印は 0.3 秒ごとに更新)と検証(`build_members`) |
| `dateinput.py` | 日付と時刻の入力の整形。`parse_date_input`(省略形 → `YYYY-MM-DD`。`roll_forward` で、過ぎた日を翌年にする)・`parse_time_input`(→ `HH:MM`。どちらも、先に NFKC で全角を半角にする)・`shortcut_dates`(今日・明日・来週月)。純粋関数。`task_dialog.add_picker` の `normalize` が、blur で使う。テストは `task_dialog.today` を差し替えて日付を固定し、blur は `_event_listeners` のハンドラを直接呼ぶ(User のシミュレーションにフォーカスの移動がないため) |
| `effortunits.py` | 工数の単位(時間・日・週・月)の換算 `to_hours` / `from_hours` と、参考 `reference_text`。純粋関数。時間のときは丸めない(桁数は `build_task` が検証する。小数点以下 2 桁まで。古いファイルの値は、変えなければ保存できる)。`task_dialog.EffortField` が使い、時間を正本として持つ(単位の切り替えで丸めのずれを溜めない) |
| `preview.py` | エクスポートのプレビュー(`PreviewSettings`・期間の検証・`fit_scale`・`PreviewBar`) |
| `gitstate.py` | 格納先の git の状態を読む(読み取りだけ。`read_git_state`・`GitState`・`describe`・`tooltip`)。`git`は直呼びで、`status --porcelain=v2 --branch`の 1 回で、ブランチ・上流・ahead/behind・変更数を読む。NiceGUI に依存しない。`run`は差し替えられる |
| `gitops.py` | git の書き込み操作(`list_changes`・`commit`・`push`・`default_message`)。NiceGUI に依存しない。`gitstate.run_git`を共有し、`run`は差し替えられる。名前の検査(`valid_name`)と、`--literal-pathspecs`・`commit --only`で、選んだファイルだけをコミットする |
| `merge.py` | プロジェクトの 3 者マージ(`merge_projects`・`merge_files`・`Conflict`・`format_value`)。NiceGUI にも git にも依存しない。鍵は、タスク・メンバー・セクション・カテゴリ・イベントが`id`、パラメータ・URL テンプレートが名前。項目ごとに、片側だけが変えた値を採り、両側が違う値の項目だけを衝突にする(選択は`Conflict.id = (kind, key, field)`を鍵に`choices`で渡して、もう一度マージする) |
| `filemanager.py` | フォルダを OS のファイラで開く(`open_command`・`open_folder`。macOS は `open`、Windows は `explorer`、それ以外は `xdg-open`。シェルを通さない)。純粋に近い関数で、起動は差し替えられる |
| `export.py` | 画像化(html-to-image)・倍率・PNG の書き出し・保存ダイアログ(`ImageExporter`。`ask_path` はファイルの種類を引数に取り、担当者向けファイルでも使う) |
| `urls.py` | タスクのリンク(URL)の規則。`resolve`(`{ID}` の置き換えと、`http`・`https` の検証)、`validate_templates`、`validate_urls`、`count_usage`、`expand_template`(削除時にリンクを URL へ展開)、`rename_templates`、`apply_template_edit`(`TemplateEdit`)。純粋関数(NiceGUI に依存しない) |
| `events.py` | イベント(プロジェクト共通)の規則。`CSS_COLORS`(CSS の色名 → `#rrggbb`)、`normalize_color`、`validate_events`(文字列 30 文字以内・制御文字なし・`start ≤ end`・色名・id の重複)、`sort_events`、`assign_lanes`(開始の早い順に、空いた最小の段へ詰める。前の終了日の翌日に始まるなら同じ段)、`column_span`(列は `[start, end)` なので、終了日は翌日と比べる)、`cell_colors`(後ろが勝つ)。純粋関数(NiceGUI に依存しない) |
| `categories.py` | カテゴリ(プロジェクト共通)の規則。`validate_categories`(名前 30 文字以内・種別 20 文字以内・制御文字なし・PRJコードは半角英数字と `-` `_` `.` だけ 20 文字以内・色・重複・予約名「未定」)、`parse_expiry`、`migrate_legacy`(version 2 以前の `project_code` を、同じコードごとのカテゴリへ)、`next_color`、`count_usage`、`CategoryEdit`・`apply_edit`、`chip_text`、`by_id` |
| `ratios.py` | 相対比率のパラメータ。`ratio_detail`・`effective_ratio`(基本比率 + 選んだ段階の判定値の合計。10〜300% に丸める。合計は 4 桁に丸めて、境界を誤差で外さない)、`ParameterEdit`(旧い名前からの対応。削除は None)、`remap_levels`(段階の選択を新しい定義へ写す。`apply_parameter_edit` とメンバーのダイアログが使う)、`validate_parameters`、`apply_parameter_edit`(入れ替えや、削除と改名の組み合わせでも取り違えない)、`deletion_impacts`。純粋関数(NiceGUI に依存しない)。換算は `timeline.assignees_rate` が、編集ダイアログは実効比率のコピーを通して使う |
| `browser.py` | URL を既定のブラウザで開く(`open_url`)。`http`・`https` 以外と、開けなかったときは `OSError`。開く処理は差し替えられる |
| `shortcuts.py` | キーボードショートカットの割り当て表 `SHORTCUTS` と、判定 `resolve`(キー・修飾キー・ダイアログの有無・画面から操作名を返す。`always` の操作(倍率)は、ダイアログ・プレビュー・ダッシュボードでも効く。`aliases` は同じ操作の別のキー、`any_shift` は Shift を見ない)、`help_entries`、`ctrl_keys`。純粋関数(NiceGUI に依存しない)。`views.MainView.on_key` が操作名をメニューと同じメソッドへ振り分ける。`ui.keyboard` は 2 つ(文字キー用は入力欄で無効、`Ctrl/Cmd` 用は `ignore=[]`)。ブラウザ側は `key_guard_js`(`views.KEY_GUARD_JS`)で、割り当てたキーの既定の動き(`Ctrl+S`・`Ctrl+P` など)と macOS の警告音を止める。文字キーは入力欄の中では止めないが、ESC は文字でないので、入力欄でも止める(止めないと、入力欄にフォーカスがあるときの ESC で、macOS の警告音が鳴る。2026-10-11 に見つけた)。変換中の ESC は、変換の取り消しなので止めない。タスク編集ダイアログの ESC は、`persistent` の Quasar が `escapeKey` を送らない(ゆらすだけ)ので、`task_dialog.ESCAPE_KEYDOWN_JS` の keydown で受ける。このとき `stopPropagation` で、Quasar に ESC の印を付けさせない(Quasar は window の keydown で印を付け、keyup で一番上のダイアログへ伝える。印があると、keydown で開いた確認ダイアログが、同じ ESC の keyup で閉じて、一瞬だけ見える。2026-10-11 に実機で見つけた。keyup を遅らせて再現する)。ヘルプにラベルが増えるので、テストで部分一致の文字列を探すときは注意 |
| `dashboard.py` | ダッシュボードの集計(期間 `period_for`、進捗・負荷・工数・期限、`summarize`)。純粋関数(NiceGUI に依存しない)。負荷は `timeline.counted_span` を使い、割り当て超過の縞と同じ前提 |
| `dashboard_view.py` | ダッシュボードの表示(カードと横棒。`DashboardView`) |
| `handoff.py` | 担当者向けファイルの書き出し。タスクを todoapp 形式(`items`・`records`・`categories`)へ変える(`build_todos`)、書き込み(`write_json`)。純粋関数(NiceGUI に依存しない)。id は`uuid5`で決まる(同名のタスクは`名前#2`)。todoapp の形式は`file-format.md`(git 管理外) |
| `plantuml.py` | プレビューのガントチャートを PlantUML のテキストにする。`build_plantuml`(`PlantUml`: `text`・`task_count`・`skipped`)、`default_filename`、`write_text`(一時ファイル経由)。純粋関数(NiceGUI に依存しない)。状態の色は `gantt.STATUS_COLORS` の写し(テストで一致を確かめる)。表示名は、イベント・タスク・チェックポイントを通した 1 つの集合で重複を避ける(PlantUML は、別名を付けても、同じ表示名を 1 件にまとめるため)。描画のテストは、`java` と `plantuml.jar`(`PLANTUML_JAR` か `/usr/local/lib/plantuml.jar`)があるときだけ走る |
| `puml_import.py` | PlantUML のガントのテキストから、新規プロジェクトを作る。`parse_plantuml`(`PlantUmlImport`)、`summary`(通知文)、`read_plantuml`(UTF-8・BOM 除去)、`PLANTUML_OPEN_FILE_TYPES`。構成は `_Scanner`(行)→ `_Resolver`(日付)→ `_Builder`(`Project`)。純粋関数(NiceGUI に依存しない)。結果は `dumps_project` → `parse_project` で検証する。先行は循環になる連結を入れない。描画のテストは、`java` と `plantuml.jar` があるときだけ走る |
| `static/` | 同梱の html-to-image(MIT) |
| `task_dialog.py` | タスクの追加・編集ダイアログ(優先度チップ、日付・時刻の入力、閉じる確認、削除) |
| `models.py` | Project / Section / Task / Member / Actual と列挙型(Priority・Status・ActualMode)のデータモデル(`Task.planned_start` / `planned_end` / `planned_end_manual` / `deadline`) |
| `storage.py` | `~/.projectapp/<名前>.json` の走査・名前の検証・保存(一時ファイル経由)・読込・外部変更の検知(`file_digest`・`check_external_change`)・`.bak` の退避(`backup_file`) |
| `config.py` | テーマ・名前の欄の幅・倍率・レイアウト・格納先(`project_dir`)の設定(`config.json`。読んで更新して書く)。格納先の検査(`check_project_dir`)と起動時の解決(`resolve_project_dir`) |

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
| 名前の欄の幅 | `2026-10-06-name-width-design.md` |
| ダッシュボード | `2026-10-07-dashboard-design.md` |
| 担当者向けファイルの書き出し | `2026-10-07-assignee-handoff-design.md` |
| PlantUML 出力 | `2026-10-15-plantuml-export-design.md` |
| PlantUML 取り込み | `2026-10-16-plantuml-import-design.md` |
| 複数の担当者 | `2026-10-08-multi-assignee-design.md` |
| メンバーの相対比率のパラメータ化 | `2026-10-09-ratio-parameters-design.md` |
| セクションの入れ子 | `2026-10-09-nested-sections-design.md` |
| イベントカレンダー | `2026-10-15-events-design.md` |

実装計画は `docs/superpowers/plans/` に、同じ日付・名前(`-design` なし)である。

## ブランチ

git-flow に従う(`.claude/BRANCH.md`)。作業は `develop` から `feature/*` を切る。

## コマンド

```bash
uv sync
uv run pytest --cov=projectapp
uv run pytest -n auto          # 並列(pytest-xdist)。--cov とも併用できる
uv run ty check src
```

並列は、直列の約 3.5 倍速い(1,075 件: 直列 33〜40 秒、`-n 2` 17.5 秒、`-n 4` 10.8 秒、`-n auto`(論理 8 CPU)約 9.4 秒。繰り返しても失敗なし)。分散は、既定の `load` が速い(`--dist loadfile` は、大きなファイル(`test_gantt.py`・`test_views.py`)が 1 つのワーカーに偏って、`-n auto` で約 14 秒)。既定の `addopts` には入れていない(1 件だけ走らせるときも、ワーカーの起動で遅くなるため)。各ワーカーは別のプロセスなので、`conftest.py` の解放と凍結も、ワーカーごとに働く。実際のホームの `~/.projectapp` を読み書きするテストはない(`tmp_path` を使う)ので、競合しない。

全体のテストは約 1 分。`test/conftest.py` が、セッションの最初に基本のヒープを凍結し(`gc.freeze`。フル GC が基本のオブジェクトを毎回走査しないように)、各テストのあとで、前のテストのオブジェクト(クラスの `ui.refreshable` の対象、FastAPI の `lru_cache`、`weakref.finalize` の登録簿)を空にする。`User` のシミュレーションは、テストが終わっても要素を削除しないので、空にしないと、オブジェクトがテストの数だけ積まれ、`nicegui_reset_globals` のフル GC が進むほど遅くなる(対策前は約 7 分)。凍結したオブジェクトは、以後のフル GC と `gc.get_objects()` の対象から外れる。`test/test_leak_cleanup.py` が、積み上がらないことを確かめる。クラスに `@ui.refreshable_method` を足しても、自動で対象になる。

## 描画速度の設計制約

2026-10-06 に、`GanttChart.render` の速度を測った(8 セクション × 15 タスク = 120 タスクで、1 回約 400〜470ms。NiceGUI の要素が約 1,800 個。1 タスクあたり約 15 個)。時間の大半は NiceGUI の要素生成で、`timeline.py` の位置計算は約 5%。

**制約(守ること)**
- NiceGUI の内部関数の差し替え(モンキーパッチ。例: `nicegui.helpers.expects_arguments` のキャッシュ化。約 23〜31% 短縮)は、**しない**。非公開の内部に依存し、NiceGUI の更新で壊れうるため。
- ツールチップを `title` 属性へ置き換える案(Quasar の Tooltip 531 個が約 100 ms 分。キャッシュと合わせて約 42% 短縮)は、**しない**。見た目と動作が変わる。切り替えの設定(オプション化)も、手間に見合わないので**しない**。
- 名前の欄の幅の変更(要望 23)は、再描画しない。掴み場所は疑似要素で、要素数は増えない。ドラッグ中に `--name-w` を書き換えない(CSS 変数は子孫に継承されるので、約 1,800 要素のスタイルの再計算で、1 回約 11ms かかり、約 30fps にカクつく)。ドラッグ中は、名前の欄の幅だけを直接書き換え、離したときに `--name-w` を 1 回だけ更新する(60fps)。実ブラウザでの測り方: ヘッドレス Chrome を `--remote-debugging-port` で起動し、CDP の `Input.dispatchMouseEvent` で、実際のポインタ操作を送り、ページ内の `requestAnimationFrame` でフレーム間隔を測る。
- 速度の改善は、NiceGUI の公開 API の範囲で、見た目を変えない手段に限る。候補: 棒の中の、クリックに応答しない飾り(進捗の塗り・縞・印)を 1 つの HTML にまとめる(ヘッダーの日付ラベルの `header_cell_html` と同じ手法)。変わった行だけを更新する案は、スクロール位置とドラッグ用の JS との整合が要るので、設計から始める。

**測り方**: 120 タスクの `Project` を作り、`await chart.render.refresh()` を繰り返して時間を測る(`refresh` は予約されるだけなので、`await` が要る)。`cProfile` の自己時間で、要素生成(`inspect.signature`・`Element.__init__`)と自前の関数を分ける。ブラウザ側(Vue の描画・websocket の約 1MB)は未計測。

## ファイル形式の注意

- 形式のバージョンは先頭の `version`(整数。`models.FORMAT_VERSION`、現在 2)。キーのない古いファイルは 1 として読む。整数でない値(`true`・小数・文字列・`null`)と 1 未満は読込を拒否し、このアプリより新しい値は「アプリを更新してください」で拒否する(`storage._check_version`)。形式を変える(キーの意味を変える・消す)ときは `FORMAT_VERSION` を上げ、旧形式の読み替えはバージョンで分ける。
- version 2(2026-10-10): `members[].id` と `sections[].id`(`new_id()` の 8 桁の 16 進。入れ子のセクションも)を保存し、担当者は `tasks[].assignees[]` の `{"member": <メンバーid>, "allocation": …}` で指す(`name` は書かない。`_dump`)。実行時の `Assignee` は名前のまま(読込が id から名前へ戻す。`_member_assignees`)。読込は、`id` の欠落・`null`・空・文字列以外・重複(メンバー同士・セクション同士)、存在しない/文字列でない `member`、担当者の旧キー `name` を拒否する。名前が空・重複のメンバーは最初の 1 件を残して捨てるが、捨てた同名のメンバーの id を指す担当者は、残ったメンバーへ読む(名前が空のメンバーの id を指すものは拒否)。version 1(キーなしを含む)は、メンバー・セクションと id のないタスクに読込の最後に新しい id を振る(`_assign_ids`。ファイルの他の id と重ならない)。保存し直すと version 2 になる。
- 保存(`save_project`)は、タスク同士・メンバー同士・セクション同士の id の重複を `ValueError` にして、ファイルを書かない(読めないファイルを作らない)。担当者の名前がメンバーにいなければ、保存するファイルにだけメンバー(比率 100%)を補う(読込の補完と同じ。実行時のプロジェクトは変えない)。新しい id は `new_id(project.used_ids())` で振る(セクションの追加・新規タスク・行のコピー・メンバーのダイアログの新しい行)。メンバーのダイアログは `MemberRow.id` で行の id を引き継ぐ(改名・並べ替えでは変わらない。行を消して足し直すと新しくなる)。
- 画像の書き出し(`export.CAPTURE_JS`)は、`htmlToImage.toPng` に **`skipFonts: true`** を渡す。渡さないと、フォントの埋め込みが `@import` 先の CSS(Quasar の約 2,000 ルール)を画面のスタイルシートへ `insertRule` し、`@layer` の外に出て、書き出しのあと、見出しの行の高さ・日付のラベルの位置が変わったままになる(拡大とは無関係。2026-10-09)。画像は、フォントなしでも見た目が変わらない(システムフォントを使うため)。
- セクションは `Section.sections`(入れ子。`[{"name", "tasks", "sections"}]`)。キーがない・`null` は空。4 階層以上と、`sections` の型の違いは読込を拒否する(`storage._section`)。セクションの位置は `SectionPath`(番号のパス。root は `()`)で、マーカーのキーは `arrange.section_key`(`top`・`0`・`0.1`)。1 階層目は入れ子の前と同じ。ブラウザ側の JS は、`data-si` のキー(文字列)をそのまま送り、サーバーが `parse_section_key` で戻す。折りたたみは `GanttChart.collapsed`(パスの集合)で、親を閉じると子孫が隠れ、親を開いても子の状態は保たれる(`row_slots` と `apply_visibility` が同じ規則)
- パラメータは `Project.parameters`(`[{"name", "levels": [{"name", "value"}]}]`。`value` は割合で -0.9〜+2.9)、メンバーの選択は `Member.levels`(`{"パラメータ名": "段階名"}`)。キーがない・`null` は空。名前の空・重複、`value` の範囲外・非有限・型の違いは読込を拒否する。メンバーの選択が存在しないパラメータ・段階を指していても、読込は拒否せず、`ratios.ratio_detail` が判定値 0% として扱い、メンバーのダイアログの適用で捨てる。`Member.ratio` は基本比率。
- 担当者は `Task.assignees`(`[{"name", "allocation"}]`。`allocation` は 0.01〜1.0)。古いキー `assignee`・`allocation` は、`assignees` がないときだけ 1 人のリストとして読む(`storage._assignees`。担当者がなくても、不正な割り当て率は拒否する)。名前が空・重複、割り当て率が範囲外・非有限は読込を拒否する。保存は `assignees` だけ(`asdict` で書くので、空のときも `[]`)。チェックポイントは常に空。換算率は `timeline.assignees_rate`(メンバーにいる担当者の `相対比率 × 割り当て率` の合計。誰もいなければ 1.0)。
- リンクは `Task.urls`(`[{"title", "template", "values"}]`)、URL の型は `Project.url_templates`(`[{"name", "pattern"}]`)。`values` のキーは、テンプレートなしが `URL`、ありが `ID`。キーなし・`null` は空で読む(移行は要らない)。名前の空・重複、`http`・`https` でない型や URL、存在しないテンプレート名、キーの不一致、型の違いは読込を拒否する(`storage._url_templates`・`_task_urls`、読込後に `validate_urls`)。フィールド名は `urls`(先行タスクの連結 `predecessors` と区別する)。ID の置き換えは `str.replace` と `quote(safe="")` だけ。
- ヘッダーの日付・曜日の行(`label_row`)は、列ごとに要素を作らず、1 つの `ui.html`(マーカー `label-row-cells`)にまとめる(`header_cell_html`。セルは `data-col="<日付>"`、日次は日付と曜日の 2 行、週次・月次は日付の 1 行。内容は日付のみだが、念のため `html.escape` を通す)。NiceGUI の要素は、1 個ずつの生成が重く(`Element.__init__` が、監視付きのコレクションを 3 つ作り、それぞれで `inspect.signature` を呼ぶ)、列ごとの要素は、描画の約 8 割を占めていたため。格子線・縞と同じ作り方。個々のラベルのマーカー(`col-<日付>`・`weekday-<日付>`)はないので、テストは `test/header_cells.py` の `header_cells` で、`label-row-cells` の内容から読む。年・月の帯(`band_row`)は、要素が少ないので、そのまま。
- セクションの折りたたみ(`GanttChart.collapsed`。セクションの添字の集合)は保存しない。切り替え(`toggle_section`)は、再描画せず、`section_views` に持つ行の表示と矢印のアイコンだけを変える(行は、折りたたみ中も作って隠す)。絞り込み中とプレビュー(読み取り専用)は無視する。セクションの並べ替え・削除を足すときは、同時に添字をずらすこと(現状はセクションの追加が末尾への追加だけなので、ずれない)。
- `Task.kind`(`TaskKind`。`"通常"` / `"チェックポイント"`)。保存は `"kind"`(キーなし・`null` は通常。不正な値は読込を拒否)。チェックポイントは、締切が必須で、状態は未着手か終了だけ(`CHECKPOINT_STATUSES`)。読込(`storage._checkpoint`)は、締切なし・状態の不正を拒否し、開始予定・完了予定・工数・担当・割り当て率・実績が入っていても使わず空にする。保存(`forms.build_task` → `_build_checkpoint`)も、それらを空にし、隠した欄の入力は検証しない。`Schedule` は、チェックポイントの実効の開始・完了をどちらも締切にする(押し出されない。先行にすると後続を締切まで押し出す)。`is_overdue` は、チェックポイントだけ、先行の完了が締切を超える見込みでも超過とする(通常タスクは現在時刻だけ)。ガントチャートは、バー・実績・縞・進捗のチップを出さず、`checkpoint-<key>-<ti>` の大きめの ◆(状態の色。`CHECKPOINT_MARKER_PX`)を、締切の位置・行の中央に出す(`task_row` の早期 return)。矢印は ◆ の左右の端につなぐ。ダッシュボードは、状態別の件数に含め、進捗率の重みからは外す(見込みの超過の一覧の基準は締切)。人ごとの負荷・工数・担当者向けの書き出しは、担当と工数がないので対象外。編集ダイアログは、種別のトグル(`task-kind`)で、開始予定・完了予定・工数・担当・実績の欄を隠し、状態を 2 つにする(`apply_kind`)。
- `Task.id`(8 桁の 16 進。`models.new_id`)と `Task.predecessors`(先行タスクの `id` のリスト)を保存する。`id` のないファイルは、読込時に振る(移行は要らず、保存し直すと残る)。`predecessors` のキーがない・`null` は空。読込(`storage.load_project` → `linkgraph.validate_links`)は、`id` が空・文字列以外・重複、`predecessors` がリストでない・文字列以外を含む・重複、存在しない `id`、自分自身、循環を拒否する。`Task.id` は `compare=False`(乱数で、タスクの比較に使わない)。コピーは新しい `id` で `predecessors` は空。削除は、ほかのタスクの `predecessors` から外す(`linkgraph.drop_task_links`)。
- 実効の開始・完了は保存しない。`timeline.Schedule`(必要なものだけ算出してメモする)が、`max(開始予定, 先行の完了)` で押し出し、手指定の完了予定と工数なしの `planned_end` は押し出した幅だけ後ろへずらす(締切は動かさない)。先行の完了は、状態が「終了」で実績の終了があればその時刻、なければ先行の実効の完了。循環があっても無限再帰しない(押し出しなし)。`effective_start` / `effective_end` は `schedule` を渡さなければ、その場で上流だけを解く(先行がなければ従来の計算)。表示・判定で開始を読むときは `planned_start` を直接読まず、これを使う(入力・保存の `forms`・`task_dialog`・`storage` は自分の開始予定を扱う)。`is_overdue` は従来どおり現在時刻と比べるので、押し出されて完了予定が締切を過ぎても、時刻が締切を過ぎるまで超過にはならない。
- 矢印は `links.py`(行の並び `row_slots`・縦位置・折れ線の純粋関数)と、`gantt.GanttChart.links`(チャート全体で 1 つの `ui.html`。マーカー `links`、経路は `data-link="先行ID-後続ID"`)。DOM の順で、格子線・縞・見出しの後、行の前に置く(棒・名前の列より下)。行の並びは `row_slots` が決め、矢印の座標は、最初の行の直前に置いた高さ 0 の要素(`position: relative`)を基準に、行の上端から測る(実機の WKWebView では、年・月の帯が設計より高く、ヘッダーが約 30px 高かった。ヘッダーの高さを前提にすると、矢印が 1 行ずれる)。折りたたみは `update_links` で SVG の内容だけを作り直す。絞り込みで隠れた行・折りたたみで隠れた行・期間の外の棒には出さない。近い(12px 未満)ときの経路は、行の間を通る 5 区間。
- 押し出されたタスクのバーのドラッグは、見えている開始を基準にずらし(`arrange.shift_task(task, days, shown_start)`)、基準日と先行の完了の日より前へは動かさない(`arrange.min_shift_days`)。
- タスクの日付は、`planned_start`(開始予定)、`planned_end`(完了予定の手入力値)、`planned_end_manual`(手で指定)、`deadline`(締切)。完了予定は保存せず、`effective_end` で表示のたびに計算する。
- `planned_end_manual` のキーがないファイルは旧形式として読む。旧 `start` は開始予定、旧 `end` は締切になる(`end_auto` が `true` のものは自動算出だったので捨てる)。旧形式のファイルは、保存すると新形式になる。
- 読込時に `daily_hours`(有限の数値で、0より大きく24以下)と `work_start`(`HH:MM[:SS]` の文字列)を検証し、不正なファイルは「開けませんでした」と通知する。`planned_end_manual` は `true` のときだけ真として扱う。
- メンバーの `ratio`(0.1〜3.0)とタスクの `allocation`(0.01〜1.0)は、読み込み時に検証し、範囲外は「開けませんでした」と通知する。`allocation` のないファイルは 1.0 で読む。
- メンバー一覧にない担当者名は、読み込み時にメンバー(相対比率 1.0)として追加する(古いファイルの自由入力の担当者を失わないため)。担当者名の前後の空白は取り除き、空白のみは担当者なしとする。メンバー名の重複は最初の1件を残す。
- タスクの状態は `Status`(`未着手`・`実行中`・`一時停止`・`終了`)。旧名の `開始` は、読込時に `未着手` として読む(移行は要らず、保存し直すと `未着手` になる)。実績の「開始」(開始日時)とは別の語。
- 実績は `Task.actuals`(`[{"start", "end"}]`。`end` が `null` は進行中)で保存する。`actuals` のキーがない、または `null` の古いファイルは、実績なしとして読む(移行は要らない)。読込時に、開始なし・終了が開始より前・タイムゾーン付き・年の範囲外は不正として「開けませんでした」と通知する。 各区間は `progress`(区間の終わり時点の累積。0〜100 の整数か `null`)を持つ。`progress` のキーがない古いファイルは `null` として読み(移行は要らない)、整数でない値(`true`・小数・文字列)、範囲外、前の入力のある区間より小さい値は「開けませんでした」と通知する。タスクの現在の進捗度は `timeline.current_progress`(進捗度の入っている最後の区間の値)。
- ガントチャートの進捗の状態(`timeline.progress_state`)は、状態が「終了」なら完了か遅延完了(`is_overdue` で決める)、それ以外は進捗度を「進んでいるはずの割合」(`expected_progress`。開始予定〜完了予定の経過割合を暦の時間で計算し、稼働時間・祝日は見ない)と比べ、許容幅 `PROGRESS_TOLERANCE`(10pt)を超えた差で遅延・前倒しにする。進捗度か開始予定がないと判定せず(完了予定は `effective_end` が締切か開始予定の翌日で補う)、枠線・印は出ない。判定はファイルには保存しない。予定の棒は進捗度の幅だけ塗り(`fill_percent`。終了で進捗度が空なら100%)、状態は枠線と右の印で示す(色は CSS 変数 `--pstate` で、ダークテーマでは明るい色に替わる。`PROGRESS_STATE_COLORS` と `PROGRESS_STATE_DARK_COLORS`)(印は、予定の棒より右へ伸びる実績の棒と、締切の ◆ に重ならない位置に置く)。状態が「終了」(完了・遅延完了)のタスクは、タスク名に取り消し線を引く。
- ガントチャートの棒(予定・進捗の塗り・実績)の色は、タスクの状態で決める(未着手=灰青、実行中=青、一時停止=橙、終了=灰。`STATUS_COLORS`)。色は棒の `status-*` クラスが持つ CSS 変数 `--scolor` で、ダークテーマでは明るい色に替わる(`STATUS_DARK_COLORS`)。`task.color` はファイルに残すが、棒には使わない。
- カテゴリ(version 3。`Project.categories: list[Category]`、`Task.category_id: str | None`)。保存は `categories`(`id`・`name`・`kind`・`expiry_date`(`YYYY-MM-DD` か `null`)・`color`・`prj_code`)と `tasks[].category_id`(`null`=未定。存在しない id は読込を拒否)。「未定」は保存しない擬似カテゴリで、名前に使えない。version 2 以前の `project_code` は、読込の最後に `migrate_legacy` でカテゴリへ移す(同じコードごとに 1 つ、出現順、色は 10 色を巡回。名前はコード、PRJコードは規則に合うときだけ入れる。空と「未定」は未定。制御文字は空白に替える)。保存は `project_code` を書かず、`Task` にもフィールドはない。名前の欄のチップは `chip_text`(PRJコード、空なら名前)で、`GanttChart.category_lookup`(描画のたびに作る)から引く。書き出し(`handoff.build_todos`)は `project.categories` を登録順にすべて書き、`id` は `Category.id`(以前の `uuid5` による自動生成は廃止)。タスクダイアログのカテゴリの選択肢は、`categories.category_label`(名前が 12 文字を超えたときだけ `…` で省略し、種別と PRJコードは `(種別・PRJコード)` で必ず添える)で作り、全文(`category_full_label`)は `option`・`selected-item` スロットの `:title` に入れる。NiceGUI の `select` は選択肢の `value` に番号を渡すので、番号 → 全文の配列(JSON。属性の中なので `&quot;` に escape)で引く。省略していないものは空。設定ダイアログのカテゴリは、1 件を 2 段のブロックにする(1 段目: 名前(`grow`)・色・削除。2 段目: 種別(`grow`)・有効期限・PRJコード(`w-48`))。1 行に並べると、全角 30 文字の名前と 20 文字の PRJコードが切れて見えなかった。幅は、ヘッドレス Chrome で `input.scrollWidth <= clientWidth` を測って確かめた。設定ダイアログの色の選択は、`ui.select` の `option`・`selected-item` スロット(`forms.COLOR_OPTION_TEMPLATE`・`COLOR_SELECTED_TEMPLATE`。色付きの丸 + 色の名前。ラベル(色の名前)→色コードの対応を Vue の式に埋め込む)で描く。**NiceGUI の `select` は、Quasar の選択肢の `value` に色名ではなく番号(0〜9)を渡す**ので(`choice_element.py`)、色はラベルで引く(色名で引くと丸が黒くなる。2026-10-11 に実機で見つけた)。シミュレーションのテストでは丸の描画までは確かめられないので、描画を見るときは、ヘッドレス Chrome を `--remote-debugging-port` で起動し、CDP の `Runtime.evaluate` で `getComputedStyle(i).color` を読み、`Page.captureScreenshot` で撮る。設定ダイアログの有効期限は `type=date` の入力で、`parse_expiry` が検証する。
- タスク名(`MAX_TASK_NAME_LENGTH` = 50、制御文字なし)。入力は `build_task` が拒否する。読込は拒否せず `models.tidy_task_name` で整える(使えない文字(`FORBIDDEN_CATEGORIES` = Cc・Cf・Zl・Zp。todoapp の `has_control_chars` と同じ)は空白に替え、前後の空白を除き、50 文字に切り詰める。名前が文字列でないときだけ拒否)。`arrange.copy_task` は「(コピー)」を足して 50 文字を超えないよう、元の名前を切り詰める。名前の入力欄は `ui.textarea`(`autogrow rows=1`、`w-full`)で、長い名前は折り返す。Enter は `keydown.enter.prevent` で無効にし、貼り付けた使えない文字は値の変更時に空白へ替える(`build_task` の拒否には届かない)。**上限は `maxlength` ではなく、値の変更時に文字数で切り詰める**(ブラウザの `maxlength` は UTF-16 単位で、絵文字は 2 単位になり、早く止まる)。設定ダイアログのカテゴリの名前・種別・PRJコードは `forms.limit_length` で同じく切り詰める。
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

- 格納先(要望 8): 設定(`config.json`・`holidays.json`)の置き場所 `MainView.base_dir`(固定の `~/.projectapp`)と、プロジェクトファイルの格納先 `MainView.project_dir` は別。`project_dir` は `config.json` の `project_dir`(絶対パス。相対・空・不正は未設定)で、起動時に `resolve_project_dir` が決める(使えなければ通知して `base_dir`。設定は書き換えない)。コンストラクタの `base_dir` は設定側のまま、`project_dir` 引数で上書きできる(テスト用)。ファイルメニューの「格納先を変更」(`file-change-dir`)は、`ImageExporter.ask_directory`(ネイティブのみ)で選び、`change_project_dir` が検査 → 保存 → 一覧の読み直し → 新規プロジェクトの順に行う。確認ダイアログは閉じると消えるので、フォルダ選択の `ui.timer` は `self.client` の直下に置く。`storage.py` の関数は、引数のディレクトリを格納先として扱う(設定側のことは知らない)。
- 外部変更の検知(要望 10 の 2 番目の子): `MainView.digest` は、`open_project` が**読み込みの前**に取る(間にファイルが変わっても、保存時に `CHANGED` になる厳しい側へ倒れる)。保存の成功後は、書いたファイルを読み直して取り直す。検査は `write(overwrite=True)` の入口だけ。`write` と `save_then` は続きの処理 `after` を引き継ぐ形で、`CHANGED` のときは `open_conflict_dialog` を出して `False` を返し、`上書き`(`overwrite_external` → `commit`)と`名前をつけて保存`(`save_as_then` → `save_as_new`)の保存の成功後に `after` を呼ぶ。`.bak` は上書きのときだけで、`*.json` に一致しないので一覧に出ない。テストでは、閉じたダイアログの要素が(`hide` イベントが来ないため)残るので、`should_not_see` ではなく状態で確かめる。
- 画面の倍率(要望 27): `config.py` の `parse_zoom`・`step_zoom`・`load_zoom`・`save_zoom`(70〜200%、10% 刻み、`config.json` の `zoom`)。`views.MainView.zoom` / `change_zoom` が、`zoom_js` で `document.body.style.zoom` をかける(`run_js` はテストで差し替える)。**CSS の `zoom` なので、クライアントの座標(`clientX`)と CSS の px がずれる**: `gantt_drag.py` の `cssScale`(`document.body.style.zoom`。**WebKit は zoom 中も `getBoundingClientRect` と `offsetWidth` を拡大前の値で返すので、要素の幅の比では求めない**)で、バーの移動と名前の欄の幅の調整の移動量を割り戻す。名前の欄の右端の判定も、位置の計算ではなく、`elementFromPoint` で右へ掴み場所の幅(×倍率)進んだ点が欄の外かで決める(2026-10-09。110% 以上で、幅の調整もバーの移動量も、WebKit で外れていた)。画像の書き出し(`save_image`)の間は 100% に戻し、終わったら戻す。
- タスクのダイアログのレイアウト: `config.py` の `load_task_layout`・`save_task_layout`(`config.json` の `task_layout`。`"all"`(既定。不正な値も)か `"schedule"`)。`MainView.task_layout`・`set_task_layout`(保存できなくても画面には反映し、通知だけ出す)が、`link_args` 経由で `open_task_dialog(layout=, on_layout_change=)` へ渡す。ダイアログは、同じ部品の表示・非表示で切り替える(`refresh_visibility` が、種別とレイアウトから、欄の出し入れを 1 か所で決める。`kind`・レイアウトのどちらの変更でも走るので、登録順に依存しない。換算の説明は、完了予定の算出値を動かすので、レイアウトに関わらず出す)。`current()`(変更の判定)・保存は、レイアウトを含めず、隠した値も今までどおり扱う。割り当て率(`AssigneeFields._sync`)は、メンバーを選んだ行だけ表示する(`enabled` ではなく `visible`。テストは `should_not_see`)
- git の状態(`gitstate.py`)は、`status --porcelain=v2 --branch`を 1 回だけ呼んで解く(ブランチ・ahead/behind・変更行が 1 回で取れ、`git`を何度も起動しない)。変更の対象は、固定のパス指定(`:(glob)*.json`と、予約名の`:(exclude)`)で絞るので、ファイル名は`git`に渡さない(`*`や`:`を含む名前でも安全。削除済みのファイルも数えられる)。`fetch`しない(ネットワークに触れない・遅くならない)ので、ahead/behind は取得済みの追跡ブランチとの比較。`GIT_OPTIONAL_LOCKS=0`で他の`git`のロックを取らず、`LC_ALL=C`で「not a git repository」の判定を言語に依存させない。画面は`MainView.read_git`を`run.io_bound`で待ち(アプリの終了中は`None`が返るので捨てる)、`git_generation`で、遅れて返った古い結果を捨てる。ツールチップは、チップの子ではなく`target`で指す兄弟の要素(テストはその兄弟を探す)。画面のテストは`read_git`を差し替え、`conftest.py`の autouse が`views.read_git_state`を`NOT_REPO`にして、本物の`git`を呼ばない。出力の形(上流が消えたときは`# branch.upstream`だけで`# branch.ab`なし、空のリポジトリは`# branch.oid (initial)`)は、実機の`git 2.54`で確かめた(2026-10-13)。
- git のコミットとプッシュ(`gitops.py`)は、`add -A -- <名前>`のあと`commit --only -m <メッセージ> -- <名前>`で、選んだファイルだけをコミットする(別に stage したファイルは入らず、その stage も残る。実機で確認、2026-10-13)。名前は`valid_name`(プロジェクト名の規則〔`storage.INVALID_NAME_CHARS`と制御文字を含まない〕に合う、予約名でない`*.json`。`[`は許す)で検査し、さらに`--literal-pathspecs`を付けるので、`a[1].json`のような名前を別のファイルへのパターンと取り違えない。`status --porcelain=v2 -z`の出力のパスは、作業フォルダ基準でなくリポジトリのルート基準(`sub/甲.json`)なので、直下の`*.json`だけに絞るパス指定を使って、最後の`/`以降を名前にする。改名(`2 `の記録)は、新しい名前の追加と、次の記録の元の名前の削除の 2 件にする(`git show`は、同じ内容の削除と追加を改名として 1 行にまとめるので、テストは`--no-renames`で見る)。変更のない名前を含むときは`git commit`を呼ばない(空のコミットを避ける)。プッシュは`GIT_TERMINAL_PROMPT=0`で認証の入力待ちを失敗にし、拒否(`rejected`・`non-fast-forward`・`fetch first`)には「先にプルが必要」を添える。画面は、`MainView.git_reason`(メニューの押せる・押せない、理由の通知、ダイアログの「コミットしてプッシュ」の可否)と、`git_busy`(二重実行の防止。`finally`で下ろす)で組む。ショートカットは同期の入口(`open_git_commit`・`start_git_push`)から、`later`(画面の直下のタイマー)で非同期の処理を始める。ダイアログのメッセージの案は、前回の案と同じときだけ、選択の変更で更新する(空にした欄に案を戻さない)。

- git のプル(`gitops.py`の`pull_*`)は、`rev-parse @{u}`で上流を引き、プロジェクトファイルに未コミットの変更があれば拒否してから`fetch`し、`rev-list --left-right --count HEAD...@{u}`で最新・早送り・マージを決める。マージは`merge --no-commit --no-ff @{u}`で始め、両側が変えたプロジェクトファイルを、`merge-base`との`diff --name-only --relative --no-renames -z`の共通部分として求める。`--relative`で、格納先がリポジトリのサブフォルダでも名前だけが返る。衝突中のファイルのパスはルート基準なので、`rev-parse --show-prefix`を付けて比べ、両側が変えたファイル以外に衝突(`diff --diff-filter=U`)があれば、中止する。3 版は`git show <rev>:./<名前>`で取り出す(`./`で、作業フォルダ基準にする)。どれかが取り出せなければ(片側の削除・両側の新規作成)、ファイル単位の衝突として中止する。確定は、結果を一時ファイル経由で書き、`add`して`commit -m "マージ: <上流>"`。どこで失敗しても`merge --abort`で戻す。テストは、`tmp_path`の bare リモートと 2 つのクローンで、実際の git を使う(コミットの失敗は、`commit-msg`フックと`core.hooksPath`で起こす。環境の identity に左右されないため)。
- `merge.py`は、担当者を各プロジェクトのメンバーの`id`に直して比べ、結果のメンバーの名前に戻す(片側がメンバーを改名しても、もう片側のタスクの担当者がそろう)。並びは`_order`: 自分の並びが土台で、相手だけが並べ替えたときは相手の並びが土台。土台にないもの(相手の追加・移動)は、相手の並びでの直前の兄弟(結果にすでにあるもの)のあとに入れる。既知の制限: パラメータ・段階・URL テンプレートは`id`を持たないので、名前の変更は削除と追加に見える。
- プルの画面(`MainView.run_pull`・`pull_merge`)は、`pull_ops`(`PullOps`。テストで差し替える)の各段階を`run.io_bound`で呼ぶ。衝突は、ファイルごとに`open_merge_conflict_dialog`で選ばせる(`open_conflict_dialog`は、外部変更の検知のダイアログで別物)。実機(ネイティブウィンドウ)で、別のタスクの取り込み・同じ項目の衝突の選択・ESC での中止・メニューの押せない理由・取り込み後の読み直しを確認済み(2026-10-14)。
- ダイアログの`hide`リスナーは、`disposable`(`hide`で`dialog.delete`)より前に登録する。NiceGUI はリスナーごとに別のイベントを送り、削除済みの要素へのイベントは捨てるので、後から登録した中止の処理が呼ばれず、プルが固まる(`open_merge_conflict_dialog`。回帰テストは`test_hide_cancels_even_though_disposable_deletes_the_dialog`)。`merge --abort`の前には、アプリが書き換えたファイルを`checkout --`で index の内容に戻す(未 stage のままだと「not uptodate」で通らない)。
- イベント(version 4)は `Project.events`(`Event`)。保存は `"events"`: `id`・`start`・`end`(`YYYY-MM-DD`)・`text`・`color`。version 3 以下の `events` キーは読まない。読込(`storage._events`)は、日付の形式・色名の小文字化・`validate_events` を通し、不正は拒否する。
- タスクの進捗度(version 5)は `Task.progress: int | None`(0〜100)。保存は `"progress"`。version 4 以下の同名のキーは読まない(`events` と同じ)。読込(`storage._progress`)は、整数でない・範囲外・bool を拒否し、チェックポイントは `None` にする。現在の値は `timeline.current_progress`(最後に進捗度の入っている区間 → なければ `Task.progress`)だけを通す。編集ダイアログは `TaskProgressField`(区間に進捗度があるときは読み取り専用で、`own`〔タスクの値〕は変えない)。`IntervalFields.bind` は最後のコールバックを保持するので、変更時の処理は `on_actual_change` に 1 つにまとめる。`merge.py` は `fields(Task)` で項目をほどくので、`TASK_LABELS` に表示名を足すだけ
- イベントの色の層は `opacity` で薄め、ライトとダークで値を変える(`EVENT_CSS`)。`ui.html` に入れるのは検証済みの色と数値だけで、利用者の文字列は `ui.label` と `title` 属性で出す。帯の `overflow: clip` は `sticky` の文字を保つため(`hidden` だと、帯がスクロールの枠になって `sticky` が効かない)。日次の列は最低 42 列あるので、表示期間が短くても列は 42 に満たない分が足される。

## 既知の見送り事項

最終レビューで見つかり、直さずに見送った軽微な指摘。該当箇所を触るときに見直す。

### イベントカレンダー(PR #18)

- 並びが開始日順でない古いファイルは、変更しなくても「編集中」になる(保存時に開始日順へ並べ替えるため)
- git マージで開始日と終了日を別々に変えると `start > end` になり、取り込みを拒否する(安全側の挙動)
- セルの色が、ラベル行とイベントの帯の背後にも広がる
- `color_hex` は、検証を通っていない色名だと `KeyError` になる

### PlantUML の出力(PR #19)

- 空白だけのプロジェクト名では `title` の行が構文エラーになる(アプリは空白だけの名前を許さないので実害はない)
- `write_text` が作る `.puml` の権限が 0600 になる(`write_png` と同じ作り)
- テストにない入力: 別名と同じ名前のタスク(`T2` など)、平日の祝日と同じ日に始まるタスク、構文を壊す文字を `render` に通すケース
- プレビューの保存ボタンを有効にする経路が 3 つある(`on_preview_change`・`apply_preview`・`save_*` の `finally`)。`saving` 中に `on_preview_change` を許すと壊れうる

### PlantUML の取り込み(`feature/plantuml-import`)

- `then`・`separator` などの構文は対象外。公式文法の全面的な網羅はしない
