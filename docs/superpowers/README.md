# 設計書と実装計画

機能ごとに、設計 → 設計書 → 実装計画の順で進めた記録。**当時の判断の記録で、後の変更は本文に反映していない**(各ファイルの先頭の「状態」と「後の変更」で示す)。現在の仕様は [`CLAUDE.md`](../../CLAUDE.md)、実装の注意は [`docs/development.md`](../development.md) を正とする。

範囲が小さい要望(26 ショートカット、27 画面の拡大・縮小、34 完了予定の参考値など)は、チャットで設計を承認して実装したので、設計書はない。要望の一覧と実績は [`docs/request-history.md`](../request-history.md)。

| 日付 | 内容 | 設計書 | 計画 | 要望 | マージ | 後の変更 |
|---|---|---|---|---|---|---|
| 2026-10-02 | ガントチャートの基本表示 | [設計](specs/2026-10-02-gantt-basic-design.md) | [計画](plans/2026-10-03-gantt-basic.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | — |
| 2026-10-03 | 開始予定・完了予定・締切 | [設計](specs/2026-10-03-planned-dates-design.md) | [計画](plans/2026-10-03-planned-dates.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | — |
| 2026-10-03 | プロジェクトの保存・読込 | [設計](specs/2026-10-03-project-save-design.md) | [計画](plans/2026-10-03-project-save.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | ファイル形式は`version`付き(5。`docs/development.md`)。格納先は要望 8 で変更可能 |
| 2026-10-03 | メンバーと割り当て | [設計](specs/2026-10-03-resources-design.md) | [計画](plans/2026-10-03-resources.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | 相対比率はパラメータ化(ratio-parameters)、複数担当(multi-assignee) |
| 2026-10-03 | 日程計算 | [設計](specs/2026-10-03-schedule-calc-design.md) | [計画](plans/2026-10-03-schedule-calc.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | 完了予定の参考値を、手で指定でも出す(要望 34。PR #31) |
| 2026-10-03 | タスク編集ダイアログ | [設計](specs/2026-10-03-task-edit-dialog-design.md) | [計画](plans/2026-10-03-task-edit-dialog.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | 入力の見直し(task-dialog-input)、進捗度の入力は 1 つに(PR #35) |
| 2026-10-03 | 稼働時間の設定 | [設計](specs/2026-10-03-work-hours-design.md) | [計画](plans/2026-10-03-work-hours.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | — |
| 2026-10-04 | 実績の入力 | [設計](specs/2026-10-04-actuals-design.md) | [計画](plans/2026-10-04-actuals.md) | — | 9b2294b(2026-10-04) | 実績の進捗度は廃止(PR #35)。進捗度はタスクの欄の 1 つ |
| 2026-10-04 | 行の移動・コピー、バーの横移動 | [設計](specs/2026-10-04-drag-and-drop-design.md) | [計画](plans/2026-10-04-drag-and-drop.md) | — | 0623167(2026-10-04) | — |
| 2026-10-04 | 検索・担当者の絞り込み | [設計](specs/2026-10-04-filtering-design.md) | [計画](plans/2026-10-04-filtering.md) | — | 最初の機能群(36e46a1・5a45807・6dc7972・4a6a774・0623167・9b2294b。2026-10-03〜04) | — |
| 2026-10-04 | 進捗率に応じたバーの表現 | [設計](specs/2026-10-04-progress-bar-design.md) | [計画](plans/2026-10-04-progress-bar.md) | 要望 14 | 803dfff(2026-10-04) | 進捗はタスクの進捗度だけを見る(PR #35)。実績のバー上の進捗の文字は廃止 |
| 2026-10-04 | 進捗度(実績の区間ごと) | [設計](specs/2026-10-04-progress-design.md) | [計画](plans/2026-10-04-progress.md) | 要望 1 | 7fdfb2c(2026-10-04) | 実績の区間の進捗度は廃止し、`Task.progress` の 1 つにした(PR #35。古いファイルは読込でタスクの進捗度へ寄せる) |
| 2026-10-05 | 実績の複数区間と記録方式 | [設計](specs/2026-10-05-actual-intervals-design.md) | [計画](plans/2026-10-05-actual-intervals.md) | 要望 15 | ec64cba(2026-10-05) | 区間ごとの進捗度の入力は廃止(PR #35) |
| 2026-10-05 | エクスポートとプレビュー | [設計](specs/2026-10-05-export-preview-design.md) | [計画](plans/2026-10-05-export-preview.md) | 要望 2 | e7fbf52(2026-10-06) | PlantUML としても保存できる(plantuml-export) |
| 2026-10-05 | タスク表示のチップ | [設計](specs/2026-10-05-task-chips-design.md) | [計画](plans/2026-10-05-task-chips.md) | 要望 3・9 | 0278f64(2026-10-05) | ProjectCode はカテゴリ(category)に置き換わった |
| 2026-10-06 | ヘッダーの整理 | [設計](specs/2026-10-06-header-labels-design.md) | — | — | 9118de3・fec31e0・37ab27e・8eca5c3(2026-10-07) | メニューは 5 つになった(project-menu、Git メニュー〔PR #15〕)。カスタムテーマ(PR #26) |
| 2026-10-06 | 名前の欄の幅 | [設計](specs/2026-10-06-name-width-design.md) | [計画](plans/2026-10-06-name-width.md) | 要望 23 | 5d5cc4c(2026-10-07) | — |
| 2026-10-06 | セクションの折りたたみ | [設計](specs/2026-10-06-section-collapse-design.md) | [計画](plans/2026-10-06-section-collapse.md) | 要望 19 | 45d8063(2026-10-06) | セクションの入れ子(nested-sections) |
| 2026-10-07 | 担当者向けファイルの書き出し | [設計](specs/2026-10-07-assignee-handoff-design.md) | [計画](plans/2026-10-07-assignee-handoff.md) | 要望 4 | baa0656(2026-10-07) | 複数の担当者に対応(multi-assignee) |
| 2026-10-07 | ダッシュボード | [設計](specs/2026-10-07-dashboard-design.md) | [計画](plans/2026-10-07-dashboard.md) | 要望 6 | 5d4018c(2026-10-07) | 複数の担当者・進捗度の見直しを反映 |
| 2026-10-07 | 先行タスクの連結(矢印) | [設計](specs/2026-10-07-task-links-design.md) | [計画](plans/2026-10-07-task-links.md) | — | PR #1(3947822。2026-10-07) | — |
| 2026-10-08 | チェックポイント | [設計](specs/2026-10-08-checkpoint-design.md) | [計画](plans/2026-10-08-checkpoint.md) | 要望 21 | PR #2(8d735a6。2026-10-08) | — |
| 2026-10-08 | タスクへの複数アサイン | [設計](specs/2026-10-08-multi-assignee-design.md) | [計画](plans/2026-10-08-multi-assignee.md) | 要望 22 | 1fdd77d(2026-10-09) | — |
| 2026-10-08 | タスクのリンク(URL) | [設計](specs/2026-10-08-url-links-design.md) | [計画](plans/2026-10-08-url-links.md) | 要望 25 | PR #3(4ed4219。2026-10-08) | — |
| 2026-10-09 | セクションの入れ子(3 階層) | [設計](specs/2026-10-09-nested-sections-design.md) | [計画](plans/2026-10-09-nested-sections.md) | 要望 7 | 200d882(2026-10-09) | — |
| 2026-10-09 | 相対比率のパラメータ化 | [設計](specs/2026-10-09-ratio-parameters-design.md) | [計画](plans/2026-10-09-ratio-parameters.md) | 要望 20 | b164632(2026-10-09) | — |
| 2026-10-10 | メンバー・セクションの安定 id | [設計](specs/2026-10-10-stable-ids-design.md) | [計画](plans/2026-10-10-stable-ids.md) | — | 3dfb667(2026-10-10) | — |
| 2026-10-11 | カテゴリ機能 | [設計](specs/2026-10-11-category-design.md) | [計画](plans/2026-10-11-category.md) | 要望 29 | PR #4(75126f7。2026-10-11) | — |
| 2026-10-11 | 格納先の指定 | [設計](specs/2026-10-11-project-dir-design.md) | [計画](plans/2026-10-11-project-dir.md) | 要望 8 | PR #11(210766f。2026-10-12) | — |
| 2026-10-11 | プロジェクトメニューの見直し | [設計](specs/2026-10-11-project-menu-design.md) | [計画](plans/2026-10-11-project-menu.md) | — | PR #5(0cce975。2026-10-11) | Git メニューを足した(PR #15) |
| 2026-10-11 | タスクのダイアログの入力の見直し | [設計](specs/2026-10-11-task-dialog-input-design.md) | [計画](plans/2026-10-11-task-dialog-input.md) | — | PR #6(786097f。2026-10-11) | 完了予定の参考値(要望 34。PR #31)、進捗度の入力は 1 つに(PR #35) |
| 2026-10-12 | 外部変更の検知 | [設計](specs/2026-10-12-external-change-design.md) | [計画](plans/2026-10-12-external-change.md) | 要望 10 の 2 | PR #12(2026-10-13) | — |
| 2026-10-12 | git の状態表示 | [設計](specs/2026-10-12-git-status-design.md) | [計画](plans/2026-10-13-git-status.md) | 要望 10 の 3 | PR #13(2026-10-13) | — |
| 2026-10-13 | git のコミットとプッシュ | [設計](specs/2026-10-13-git-commit-push-design.md) | [計画](plans/2026-10-13-git-commit-push.md) | 要望 10 の 4 | PR #15(2026-10-13) | — |
| 2026-10-14 | git のプルとマージ | [設計](specs/2026-10-14-git-pull-merge-design.md) | [計画](plans/2026-10-14-git-pull-merge.md) | 要望 10 の 5 | PR #16(2026-10-14) | — |
| 2026-10-15 | イベント | [設計](specs/2026-10-15-events-design.md) | [計画](plans/2026-10-15-events.md) | — | PR #18(9b86779。2026-10-15) | — |
| 2026-10-15 | PlantUML 出力 | [設計](specs/2026-10-15-plantuml-export-design.md) | [計画](plans/2026-10-15-plantuml-export.md) | — | PR #19(05c601a。2026-10-15) | 担当者名は、表示名の末尾の括弧書きをやめ、担当構文`on {名前:60%}`で出す(割り当て率つき。人数の上限なし) |
| 2026-10-16 | PlantUML の取り込み | [設計](specs/2026-10-16-plantuml-import-design.md) | [計画](plans/2026-10-16-plantuml-import.md) | 要望 37 | PR #21(1a081c2。2026-10-16) | 日付がまったくないガントは取り込み日を開始にする(PR #33)、`requires`・`is N% complete`・`<style>` を読む(PR #34) |
| 2026-10-16 | 進捗度の持ち方の見直し(`Task.progress`) | [設計](specs/2026-10-16-task-progress-design.md) | [計画](plans/2026-10-16-task-progress.md) | 要望 38 | PR #22(3fe89a3。2026-10-16) | 区間の進捗度の優先と、欄の読み取り専用の仕様は廃止(PR #35) |
| 2026-10-17 | カスタムテーマ | [設計](specs/2026-10-17-custom-theme-design.md) | [計画](plans/2026-10-17-custom-theme.md) | 要望 28 | PR #26(ef8ade3。2026-10-18) | — |
| 2026-10-17 | 元に戻す・やり直し | [設計](specs/2026-10-17-undo-redo-design.md) | [計画](plans/2026-10-17-undo-redo.md) | 要望 36 | PR #24(89b058d。2026-10-17) | — |
| 2026-10-18 | タスクの分解(まとめ) | [設計](specs/2026-10-18-task-decompose-design.md) | [計画](plans/2026-10-18-task-decompose.md) | 要望 33 | PR #42(ee724a6。2026-10-18) | — |
| 2026-10-18 | ダッシュボードのメンバー絞り込みと内訳 | [設計](specs/2026-10-18-dashboard-member-filter-design.md) | [計画](plans/2026-10-18-dashboard-member-filter.md) | 要望 43 | PR #53(3a2cabf。2026-10-18) | — |
| 2026-10-22 | 稼働日の上書き | [設計](specs/2026-10-22-work-days-design.md) | [計画](plans/2026-10-22-work-days.md) | 要望 30 | 未マージ(`feature/work-days`) | — |
| 2026-10-22 | セクションの並べ替え(ドラッグ) | [設計](specs/2026-10-22-section-move-design.md) | [計画](plans/2026-10-22-section-move.md) | — | PR #68(806e31a。2026-10-22) | — |
