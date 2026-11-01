# 実装上の注意(ファイル形式・構成の約束)

> `CLAUDE.md` から分けた仕様。ここが現在の仕様の正。仕様を変えたら、該当するファイルを更新する。

## 実装上の注意

- 起動は `uv run projectapp`(ネイティブウィンドウのみ。既定)・`--mode web`(ブラウザのみ)。Web は `127.0.0.1` 固定、`--port` で変更。認証はないので LAN には出さない。ブラウザからでは、ネイティブ専用の機能(ダイアログ)は使えない(`web`では通知で断る)
- 描画は NiceGUI の要素と CSS による自前描画とする(外部のガントライブラリは使わない)
- lint と整形は ruff(`uvx ruff check`・`uvx ruff format src test`。依存には入れず、設定は`pyproject.toml`の`[tool.ruff]`)。実装の完了時に、全テストと合わせて実行する(`.claude/RULE.md`)
- 日時から位置への変換や日程計算は、NiceGUI から切り離した純粋関数(`timeline.py`)にする
- プロジェクトファイルの先頭に`version`(整数。現在 20。8 でメンバーの`work_days`を、9 でタスクの`parameters`を、10 でタスクの`weekly_crew`を、11 でプロジェクトの`reference_mode`とタスクの`ref_project`・`ref_snapshot`〔種別`プロジェクト参照`〕を、12 でプロジェクトの`plantuml_overload_notice`を、13 でプロジェクトの`ratio_limit_upper`・`ratio_limit_lower`〔相対比率の上限・下限〕を、14 でメンバーの稼働日のメモ〔`work_days[].note`〕を、15 でイベントの`closed`〔稼働日を休みにする〕を、16 でメンバーの`ratio_unclamped`〔丸め対象外〕を、17 でプロジェクトの`teams`とメンバーの`teams`〔チームと所属〕を、18 でイベントの色に`#rrggbb`を許した、19 でメンバーの`warning_limit`〔警告の件数の閾値〕とスナップショットの`warned`〔警告のタスク数〕、20 でタスクの`extra_efforts`〔追加工数の履歴。`day`・`hours`・`reason`〕)を保存する。キーのない古いファイルは 1 として読み、このアプリより新しい`version`は読込を拒否する。メンバー・セクション・カテゴリ・イベントは安定した`id`を持ち、担当者はファイルではメンバーの`id`で指す
- ファイル形式を変えるときは、キーのない古いファイルを既定値で読み(移行を要らなくする)、不正な値は読込を拒否する
- 保存は一時ファイル経由とし、新規保存は同名のファイルを上書きしない
- 実装の経緯と設計判断は`docs/superpowers/specs/`、モジュール構成とファイル形式の注意は`docs/development.md`を参照すること
