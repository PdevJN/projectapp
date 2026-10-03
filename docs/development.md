# 開発者向けメモ

## モジュール構成

| モジュール | 役割 |
|---|---|
| `main.py` | エントリポイント(NiceGUI + pywebview) |
| `views.py` | メイン画面(ヘッダー・チャート領域・テーマFAB・ヘルプ) |
| `calendar.py` | 祝日の取得・キャッシュ(`holidays.json`)と日付種別の判定 |
| `timeline.py` | スケールごとの列生成、日時から位置・幅への変換、稼働日ベースの終了日時算出、完了予定の決め方(`effective_end`)、予定超過の判定、締切の位置(純粋関数) |
| `gantt.py` | ガントチャートの描画とスケール切替 |
| `forms.py` | タスク・セクションの入力検証、プロジェクト名の入力・ファイル一覧・未保存の確認ダイアログ、稼働時間の設定ダイアログと入力検証 |
| `task_dialog.py` | タスクの追加・編集ダイアログ(優先度チップ、日付・時刻の入力、閉じる確認、削除) |
| `models.py` | Project / Section / Task / Member のデータモデル(`Task.planned_start` / `planned_end` / `planned_end_manual` / `deadline`) |
| `storage.py` | `~/.projectapp/<名前>.json` の走査・名前の検証・保存(一時ファイル経由)・読込 |
| `config.py` | テーマ設定(`config.json`) |

## コマンド

```bash
uv sync
uv run pytest --cov=projectapp
uvx ty check src
```

## ファイル形式の注意

- タスクの日付は、`planned_start`(開始予定)、`planned_end`(完了予定の手入力値)、`planned_end_manual`(手で指定)、`deadline`(締切)。完了予定は保存せず、`effective_end` で表示のたびに計算する。
- `planned_end_manual` のキーがないファイルは旧形式として読む。旧 `start` は開始予定、旧 `end` は締切になる(`end_auto` が `true` のものは自動算出だったので捨てる)。旧形式のファイルは、保存すると新形式になる。
- 読込時に `daily_hours`(有限の数値で、0より大きく24以下)と `work_start`(`HH:MM[:SS]` の文字列)を検証し、不正なファイルは「開けませんでした」と通知する。`planned_end_manual` は `true` のときだけ真として扱う。
