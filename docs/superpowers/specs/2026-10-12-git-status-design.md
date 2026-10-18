# git の状態表示 設計書

> **状態**: 実装済み — 要望 10 の 3 — マージ PR #13(2026-10-13)。当時の記録で、現在の仕様は [`CLAUDE.md`](../../../CLAUDE.md) を正とする。

**状態: 確定(2026-10-13)**。確定時に、実機で`git status`の挙動を確かめ、「パス指定」「`Runner`」「`describe`の`error`」の 3 点を直した(下の該当箇所)。

要望 10(git / GitHub 連携)の 3 番目の子の作業。分割は`docs/request-history.md`の「要望 10 の分割」。

## 目的

格納先が`git clone`したフォルダのとき、プロジェクトファイルの共有状態(ブランチ・未コミットの変更・ahead/behind)を、アプリの中で読み取り専用で見られるようにする。4 番目(コミットとプッシュ)・5 番目(プルとマージ)の操作の土台になる。

## 範囲

**含む**:
- 格納先の git の状態を読む`gitstate.py`(NiceGUI に依存しない)
- ヘッダーの状態チップ(読み取り専用。押すと読み直す)
- `CLAUDE.md`と`docs/development.md`の更新

**含まない**:
- `fetch`(ネットワークに触れない。ahead/behind は、取得済みのリモート追跡ブランチとの比較)
- コミット・プッシュ・プル・ブランチの切り替え・ブランチの一覧(4・5 番目の子)
- 定期的な自動更新、ウィンドウに戻ったときの更新
- `.gitignore` の編集、複数リポジトリ、サブモジュール
- git の認証・設定(各自の環境に任せる)

## 決定事項(確認済み)

- **表示場所は、ヘッダーの小さなチップ**。プロジェクトを切り替えるコンボの近くに置く。操作のボタン(4・5 番目の子)も、あとでここに足せる。
- **更新のタイミングは、操作のあとと手動**。起動時・格納先の変更後・プロジェクトを開いたとき・保存の成功後に自動で読み、それ以外はチップのクリックで読み直す。定期実行はしない(外部変更の検知が「保存の直前だけ」調べる方針と揃える)。
- **「変更あり」は、格納先のプロジェクトファイルだけを数える**。格納先直下の`*.json`で、予約名の`config`・`holidays`を除く。`git`のパス指定(`:(glob)*.json`・`:(exclude)config.json`・`:(exclude)holidays.json`。固定の文字列で、ファイル名を渡さない)で絞る。`list_project_files`との違いは、名前の検証(先頭が`.`など)を`git`側ではしないこと。削除済み(追跡中でファイルがない)のファイルも数えられる。リポジトリにほかのファイルがあっても無関係。4 番目の子の「プロジェクトファイルだけをコミット」と範囲が揃う。
- **git の呼び出しは`git`コマンドの直呼び**(ライブラリは足さない)。認証・設定は各自の環境に任せる。

## 設計

### `gitstate.py`

- `GitKind`(列挙): `NO_GIT`(`git`コマンドがない)・`NOT_REPO`(作業ツリーの中ではない)・`OK`。
- `GitState`(`frozen` の値): `kind: GitKind`・`branch: str | None`(detached は`None`)・`head: str`(短いハッシュ。コミットがまだない場合は空)・`upstream: str | None`・`ahead: int | None`・`behind: int | None`(上流がなければ`None`)・`dirty: int`(プロジェクトファイルの未コミットの変更数)・`error: str | None`(読めなかった理由)。
- `read_git_state(project_dir: Path, run: Runner = _run, timeout: float = 5.0) -> GitState`(`git`は`-C <project_dir>`で呼ぶ):
  1. `git -C <dir> rev-parse --is-inside-work-tree`。`FileNotFoundError` なら`NO_GIT`。終了コードが 0 以外で、出力が「リポジトリではない」なら`NOT_REPO`。それ以外の失敗は`OK`の形で`error`に理由を入れる。
  2. `git -C <dir> status --porcelain=v2 --branch --untracked-files=all -- ':(glob)*.json' ':(exclude)config.json' ':(exclude)holidays.json'` の 1 回で、ブランチ(`# branch.head`)・コミット(`# branch.oid`)・上流(`# branch.upstream`)・ahead/behind(`# branch.ab`)・変更行を解析する。変更行の数が`dirty`(未追跡も数える)。プロジェクトファイルが 1 つもなくても同じ呼び出しで、`dirty`は 0 になる(パス指定が固定なので、リポジトリ全体を見ることはない)。
  3. 環境変数に`GIT_OPTIONAL_LOCKS=0`(他の`git`のロックを取らない)と、`LC_ALL=C`(出力の言語を固定)を足す。シェルは通さず、パスは引数のまま渡す。
  4. タイムアウト(既定 5 秒)は、`error`に「git が応答しません」を入れる。
- `Runner`: `(args: list[str], timeout: float) -> CompletedProcess[str]` の呼び出し可能(作業フォルダは、`args`の`-C`で渡すので、`cwd`は持たない。格納先が消えていても、`FileNotFoundError`は`git`がないときだけ起きる)。既定の`_run`は`subprocess.run`(`capture_output`・`text`・`encoding="utf-8"`・`errors="replace"`)。テストで差し替える。
- `describe(state) -> str`: チップの文言。`main`、`main ↑1`、`main ↓2`、`main ↑1 ↓2`、`main ●3`(複数は半角スペース区切り。0 は省く)。detached は`(abc1234)`、コミットがまだないブランチは`main`。`NO_GIT`・`NOT_REPO`は空文字。`error`があるときは`git`。
- `tooltip(state) -> str`: マウスオーバーの文言。ブランチ・上流・ahead/behind の意味・変更数・`error`。

### 画面(`views.py`)

- ヘッダーのプロジェクト切り替えコンボの左に、チップ 1 つ(マーカー`git-state`)。`kind` が`OK`で`error`がないときだけ、`describe`の文言を出す。`NO_GIT`・`NOT_REPO`は非表示。
- `error`があるときは、警告色で、文言は`git`だけ(`describe`が返す)、マウスオーバーに`error`を出す(通知は出さない。保存のたびにうるさいため)。
- `dirty > 0` は強調色、`behind > 0` は注意の色(プルが要ることを、4・5 番目の子の前に目立たせる)。ダークテーマでも読める色にする。
- 更新: `refresh_git()`。起動時(`build`)・`change_project_dir` のあと・`open_project` のあと・`commit`(保存の本体。git のコミットではない)の成功後・チップのクリックで呼ぶ。`read_git_state` は`nicegui.run.io_bound`で待ち、画面を止めない。連続して呼ばれたときに古い結果が新しい結果を上書きしないよう、呼び出しごとに世代番号を進め、結果が返ったときに世代が違えば捨てる。`MainView.git_state` に最後の結果を持つ。
- 画面を持たないテストのために、`refresh_git` は`self.read_git: Callable[[Path], GitState]`を通して読む(既定は`read_git_state`。テストで差し替える)。

### ドキュメント

- `CLAUDE.md`: 「ヘッダー」の節に、git の状態チップ(場所・表示・更新のタイミング・対象のファイル)を足す。
- `docs/development.md`: モジュールの表に`gitstate.py`を足し、実装メモに、`status --porcelain=v2`を 1 回で読む理由・`fetch`しない理由・世代番号を書く。

## テスト

- `read_git_state`(`tmp_path`に実際の`git init`。`user.name`・`user.email` はリポジトリ内で設定する):
  - 作業ツリーの外 → `NOT_REPO`。
  - 空のリポジトリ(コミットなし)→ `OK`、`head`は空、`dirty`は未追跡のプロジェクトファイルの数。
  - コミット済み・変更なし → `dirty == 0`、ブランチ名、短いハッシュ。
  - プロジェクトファイルの変更・追加(未追跡)・削除 → それぞれ`dirty`に数える。
  - プロジェクトファイル以外(`README.md`・`config.json`)の変更 → `dirty`に数えない。
  - 格納先がリポジトリのサブフォルダ → そのフォルダの`*.json`だけを数える。
  - detached HEAD → `branch is None`。
  - 上流あり(ローカルの bare リモートを`clone`して作る)で、ahead・behind・両方・なし。上流なし → `ahead`・`behind`・`upstream`は`None`。
  - プロジェクトファイルが 1 つもない → `dirty == 0`で、リポジトリ全体の変更を数えない。`config.json`は数えない(予約名)。
- 差し替えた`run`で: `FileNotFoundError` → `NO_GIT`、`TimeoutExpired` → `error`、想定外の出力・終了コード → `error`(例外を外へ出さない)。日本語を含むファイル名(`甲.json`)が、引用符付きの出力でも数えられること。
- `describe`・`tooltip`: 各組み合わせ。
- 画面: チップは`OK`のときだけ出る。`dirty`・ahead/behind の文言。クリックで読み直す。保存の成功後・プロジェクトを開いたあと・格納先の変更後に更新される。古い結果は捨てられる(後から返った古い結果が表示を変えない)。`error`のときは警告色で、通知は出ない。
- 既存のテストが、変更なしで通ること(`read_git`の既定は、テストの`conftest`で`NOT_REPO`相当に差し替え、本物の`git`を呼ばない)。

## 未確認・リスク

- `status --porcelain=v2`の`# branch.ab`は、上流があるときだけ出る。上流が消えた場合(`gone`)は出ないので、`ahead`・`behind`は`None`になり、`upstream`だけ残る。この場合の文言は`main`のまま(`tooltip`に「上流が見つかりません」を出す)。
- ahead/behind は、最後に`fetch`した時点のリモートとの比較なので、相手の最新のプッシュは見えない。`fetch`は 5 番目の子(プル)の最初の操作として扱う。チップの文言とマウスオーバーで、「最後に取得した時点」と分かるようにする。
- 大きなリポジトリでは`status`が遅い。パス指定でプロジェクトファイルだけに絞り、`--untracked-files=all` は格納先の範囲に限られるので、通常は問題にならない。遅い場合はタイムアウト(5 秒)で`error`になり、画面は止まらない。
- 日本語のファイル名は、`core.quotepath`の設定で`status`の出力が 8 進のエスケープになる。件数だけを数えるので、解析では名前を使わない。
- Windows での`git`の見つけ方・改行コード(`autocrlf`)による「変更あり」の誤判定は、この子では扱わない。
