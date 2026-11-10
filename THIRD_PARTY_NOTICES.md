# 第三者コンポーネントと音声の利用条件

fake-siriのMIT Licenseは、このプロジェクトの自作部分に適用されます。以下のソフトウェア・モデル・音声の利用条件を変更するものではありません。

## VOICEVOXと音声

VOICEVOX本体・音声エンジン・キャラクターの音声ライブラリは同梱せず、利用者が公式配布元から別途導入します。

- [VOICEVOXのソフトウェア利用規約](https://voicevox.hiroshiba.jp/term/)：ソフトウェアの利用条件と、音声ライブラリの規約・クレジット表記を確認してください。
- 既定音声のクレジット：**VOICEVOX:ずんだもん**。[音源利用規約](https://zunko.jp/con_ongen_kiyaku.html)にはクレジットや用途に関する条件があります。
- 別の声を選ぶ場合は、[公式のキャラクター一覧](https://voicevox.hiroshiba.jp/)からその音声の利用規約を確認してください。生成音声を公開・配布するときも、選んだ音声の条件が適用されます。
- [VOICEVOX ENGINEのソースコードのライセンス](https://github.com/VOICEVOX/voicevox_engine/blob/master/LICENSE)と、配布されるソフトウェア・各音声の利用条件は別です。このリポジトリではエンジンを改変・再配布しません。

## 取得する音声モデル

| モデル | 配布元・ライセンス |
|---|---|
| vosk-model-small-ja-0.22 | [Vosk公式モデル一覧](https://alphacephei.com/vosk/models)：Apache-2.0 |
| Systran/faster-whisper-small | [モデルの配布ページ](https://huggingface.co/Systran/faster-whisper-small)：MIT |

モデルはセットアップ時に取得し、Git対象外の `trash/` に保存します。利用者が指定した既存モデルは再利用します。モデルを差し替える場合は差し替え先の条件を確認してください。

## Python依存関係

直接依存は `requirements.txt`、検証した間接依存を含む固定バージョンは `requirements.lock.txt` に記載しています。ソース公開物には `.venv` や依存ライブラリのバイナリを含めません。

| 主な依存 | 配布元 |
|---|---|
| Codex SDK・ランタイム | [OpenAI Codex](https://github.com/openai/codex) |
| faster-whisper・PyAV・Vosk | [faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[PyAV](https://github.com/PyAV-Org/PyAV)、[Vosk API](https://github.com/alphacep/vosk-api) |
| 音声入出力・無音判定 | [sounddevice](https://github.com/spatialaudio/python-sounddevice)、[soundfile](https://github.com/bastibe/python-soundfile)、[webrtcvad-wheels](https://github.com/daanzu/py-webrtcvad-wheels) |
| 通知領域・画像 | [pystray](https://github.com/moses-palmer/pystray)、[Pillow](https://github.com/python-pillow/Pillow) |

各パッケージに含まれるライセンス・NOTICEが適用されます。将来、依存物を含む実行ファイルやインストーラーを配布する場合は、同梱するバイナリと間接依存の通知・再配布条件を別途確認してください。
