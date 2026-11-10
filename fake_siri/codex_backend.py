from __future__ import annotations

import threading
from datetime import datetime

from .config import ROOT


def require_subscription(account: dict) -> None:
    # Called before any generation. Never silently switch to API billing.
    value = account.get("account") or {}
    if value.get("type") != "chatgpt":
        raise RuntimeError("ChatGPTログインが必要です。ターミナルで codex login を実行してください。APIキー認証では送信しません。")


def require_included_quota(status: dict) -> None:
    limits = status.get("rateLimitsByLimitId", {}).get("codex") or status.get("rateLimits")
    if not isinstance(limits, dict):
        raise RuntimeError("Codexのサブスク利用枠を確認できませんでした。送信を停止します。")
    exhausted = status.get("ordinaryUsageAllowed") is False or limits.get("spendControlReached")
    for name in ("primary", "secondary", "individualLimit"):
        window = limits.get(name)
        if isinstance(window, dict) and window.get("usedPercent", 0) >= 100:
            exhausted = True
    if exhausted:
        raise RuntimeError("Codexのサブスク利用枠が上限に達しています。回復後にお試しください。追加クレジットやAPIへの切り替えは行いません。")


class CodexBackend:
    def __init__(self, config: dict):
        self.config = config
        self.client = None
        self.thread = None
        self.turn = None
        self._lock = threading.Lock()

    def connect(self) -> str:
        if self.client is None:
            from openai_codex import Codex, CodexConfig

            workspace = ROOT / "trash/codex-workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            overrides = (
                'model_provider="openai"',
                'features.shell_tool=false', 'features.hooks=false',
                'features.apps=false', 'features.remote_plugin=false',
                'features.multi_agent=false', 'features.memories=false',
                'features.goals=false', 'features.shell_snapshot=false',
                f'web_search="{self.config["web_search"]}"',
                'model_reasoning_effort="low"', 'service_tier="default"',
            )
            self.client = Codex(CodexConfig(
                cwd=str(workspace), config_overrides=overrides,
                env={"OPENAI_API_KEY": "", "CODEX_API_KEY": ""},
                client_name="fake_siri", client_title="fake-siri", experimental_api=False,
            ))
        state = self.client.account().model_dump(by_alias=True, mode="json")
        require_subscription(state)
        return (state["account"].get("planType") or "ChatGPT")

    def ask(self, text: str, cancel: threading.Event) -> str:
        from openai_codex import ApprovalMode, Sandbox
        from pydantic import RootModel

        self.connect()
        if cancel.is_set():
            return ""
        # The pinned SDK has no high-level rate-limit method; use the documented
        # app-server RPC through its typed client, without handling login tokens.
        limits = self.client._client.request(
            "account/rateLimits/read", None, response_model=RootModel[dict],
        ).root
        require_included_quota(limits)
        if self.thread is None:
            instructions = (
                "あなたはPC常駐の日本語音声アシスタント、チャッピーです。利用者の質問に答えてください。"
                "返答はそのまま音声で読み上げます。Markdown、表、長いURL、作業実況は避けてください。"
                "最新情報が必要ならWeb検索を使い、確認できなければ推測で断定しないでください。"
                "このアプリは質問回答用です。PCのファイル操作、コマンド実行、外部への送信を実行しないでください。"
                "読み上げのためだけに重要な条件や数値を落とさないでください。" + self.config["style"]
            )
            self.thread = self.client.thread_start(
                model=self.config["model"] or None, sandbox=Sandbox.read_only,
                approval_mode=ApprovalMode.deny_all, ephemeral=True,
                base_instructions=instructions,
            )
        if cancel.is_set():
            return ""
        with self._lock:
            self.turn = self.thread.turn(
                f"現在のローカル日時: {datetime.now().astimezone().isoformat(timespec='minutes')}\n利用者: {text}",
                effort=self.config["effort"],
            )
        timed_out = threading.Event()

        def timeout():
            timed_out.set()
            self.interrupt()

        timer = threading.Timer(self.config["timeout_seconds"], timeout)
        timer.daemon = True
        timer.start()
        try:
            result = self.turn.run()
            if timed_out.is_set():
                raise TimeoutError("Codexの応答を待つ時間を超えました。もう一度お試しください。")
            if cancel.is_set():
                return ""
            if not result.final_response:
                raise RuntimeError("Codexから回答を取得できませんでした。利用枠と接続状態を確認してください。")
            return result.final_response
        finally:
            timer.cancel()
            self.turn = None

    def interrupt(self) -> None:
        with self._lock:
            turn = self.turn
        if turn is not None:
            try:
                turn.interrupt()
            except Exception:
                pass

    def reset(self) -> None:
        self.thread = None

    def close(self) -> None:
        self.interrupt()
        if self.client is not None:
            self.client.close()
            self.client = None
        self.thread = None
