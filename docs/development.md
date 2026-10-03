# 開発者向けメモ

## モジュール構成

| モジュール | 役割 |
|---|---|
| `main.py` | エントリポイント(NiceGUI + pywebview) |
| `views.py` | メイン画面(ヘッダー・チャート領域・テーマFAB・ヘルプ) |
| `calendar.py` | 祝日の取得・キャッシュ(`holidays.json`)と日付種別の判定 |
| `timeline.py` | スケールごとの列生成、日時から位置・幅への変換、稼働日ベースの終了日時算出、自動算出された終了の再計算、予定超過の判定(純粋関数) |
| `gantt.py` | ガントチャートの描画とスケール切替 |
| `forms.py` | タスク・セクションの追加・編集ダイアログ、プロジェクト名の入力・ファイル一覧・未保存の確認ダイアログ、稼働時間の設定ダイアログと入力検証 |
| `models.py` | Project / Section / Task / Member のデータモデル(`Task.end_auto` は自動算出された終了の印) |
| `storage.py` | `~/.projectapp/<名前>.json` の走査・名前の検証・保存(一時ファイル経由)・読込 |
| `config.py` | テーマ設定(`config.json`) |

## コマンド

```bash
uv sync
uv run pytest --cov=projectapp
uvx ty check src
```
