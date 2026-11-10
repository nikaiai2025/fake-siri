# 開発・検証

利用者向けの導入手順は[README](../README.md)、設定の意味は[設定](configuration.md)を参照してください。

## テスト

PowerShellでリポジトリ直下から実行します。自動テストではマイク・Codex・VOICEVOXを実際には起動しません。Tkの画面テストはWindowsのデスクトップ環境が必要です。

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/check_publication.py
git diff --check
```

`check_publication.py` はGit管理ファイル・未追跡の公開候補・既存履歴を対象に、個人環境のパス、代表的なトークン、秘密鍵、ローカル専用ファイルの混入を検査します。値は表示せず該当箇所を報告します。検出パターン外の情報を保証するものではないため、公開差分も確認してください。

Gitの作成者・コミット者メールアドレスも公開履歴に含まれます。公開前に `git log --format=fuller` で確認してください。匿名化する場合はGitHubのメール設定に表示されるnoreplyアドレスを使い、既存コミットは別途対応します。

## 実機での確認

初回導入ではREADMEの `--doctor` を使います。音声認識まで試す場合は、常駐アプリを終了してから次を実行してください。常駐中にもう1つ文字起こしモデルを読み込むと、メモリ使用量が増えます。

```powershell
.venv/Scripts/python.exe scripts/smoke_test.py
```

VOICEVOXの合成音声をVoskとfaster-whisperで認識します。実マイクからの距離や雑音の試験は別途必要です。`--ask` を付けると回答・音声合成まで試しますが、Codexの利用枠を消費します。生成物は `trash/smoke/` に残るため、公開物には含めません。

開始・終了の電子音は `scripts/generate_cues.py` で再生成できます。

## 依存関係の更新と公開

`setup.cmd` は `requirements.lock.txt` を使います。依存関係を更新するときは `requirements.txt` と照合し、Windows x64・Python 3.12の専用環境で解決・検証した全パッケージのバージョンを固定してください。

公開するのはソース・設定の既定値・自作素材・文書です。`config.local.json`、`trash/`、`.venv/`、ログイン情報、モデル、VOICEVOX本体を含めません。作業フォルダー全体をZIP化せず、Git管理対象から公開物を作成してください。

リポジトリを移動した場合は `setup.cmd` を再実行して仮想環境とショートカットを確認してください。既存ショートカットが別の導入先を指すときは上書きせず停止するので、使わない方のショートカットを整理してから再実行します。
