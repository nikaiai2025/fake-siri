from __future__ import annotations

import copy
import logging
import math
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .assistant import Assistant
from .config import ROOT, save_config
from .wake_settings import WakePhraseEditor

BG, PAPER, INK, MUTED, GREEN = "#f3f2ee", "#ffffff", "#192725", "#677571", "#16735c"
STATES = {
    "preparing": ("準備しています", "接続と音声モデルを確認中", "#8a6d3b"),
    "waiting": ("呼びかけを待っています", "呼びかけをこのPCで待っています", GREEN),
    "recording": ("聞いています", "そのまま話してください。話し終えると自動で送信します", "#16735c"),
    "acknowledging": ("呼びかけを受け付けました", "合図の音が終わったら質問してください", GREEN),
    "returning": ("呼びかけ待ちに戻ります", "また呼びかけ語で話しかけてください", MUTED),
    "transcribing": ("言葉を読み取っています", "音声をこのPCで文字に変換しています", "#8a6d3b"),
    "thinking": ("考えています", "Codexが回答を作っています", "#8a6d3b"),
    "speaking": ("お答えします", "読み上げ後は続けて質問できます", "#3c6882"),
    "followup": ("続けて話せます", "「おしまい」で待機に戻ります。無言でも自動で戻ります", GREEN),
    "paused": ("待ち受けを停止しています", "再開すると呼びかけ語で話しかけられます", MUTED),
    "error": ("準備を確認してください", "下のメッセージを確認し、設定または再起動をお試しください", "#a84b3a"),
}


class App:
    def __init__(self, config):
        self.config = config
        self.events = queue.Queue()
        self.root = tk.Tk()
        self.root.title("チャッピー — 起動準備中")
        self.root.geometry("890x740")
        self.root.minsize(760, 620)
        self.root.configure(bg=BG)
        self.root.option_add("*Font", ("Yu Gothic UI", 11))
        icon = ROOT / "assets/chappy.ico"
        if icon.is_file():
            self.root.iconbitmap(default=str(icon))
        self.state, self.level, self.phase = "preparing", 0.0, 0
        self.tray = None
        self.closing = False
        (ROOT / "trash/stop.request").unlink(missing_ok=True)
        self.assistant = Assistant(config, self.emit)
        self._build()
        self._tray()
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.after(80, self._poll)
        self.root.after(80, self._animate)
        self.root.after_idle(self.show)
        self.assistant.start()

    def emit(self, kind, value):
        if kind == "state":
            logging.getLogger("fake_siri.lifecycle").info("state=%s", value)
        self.events.put((kind, value))

    def _build(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=(14, 10), font=("Yu Gothic UI", 10), background=PAPER, foreground=INK)
        style.configure("Primary.TButton", background=GREEN, foreground="white")
        style.map("Primary.TButton", background=[("active", "#115e4b"), ("disabled", "#b5c5bf")])
        style.configure("TEntry", padding=9, fieldbackground=PAPER)

        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=30, pady=24)
        heading = tk.Frame(container, bg=BG)
        heading.pack(fill="x", pady=(0, 22))
        tk.Label(heading, text="チャッピー", font=("Yu Gothic UI", 28, "bold"), bg=BG, fg=INK).pack(side="left")
        tk.Label(heading, text="  fake-siri", font=("Segoe UI", 12), bg=BG, fg=MUTED).pack(side="left", pady=(12, 0))
        ttk.Button(heading, text="設定", command=self.settings).pack(side="right", pady=6)

        status = tk.Frame(container, bg=PAPER, highlightbackground="#dce2dc", highlightthickness=1)
        status.pack(fill="x")
        self.canvas = tk.Canvas(status, width=122, height=130, bg=PAPER, highlightthickness=0)
        self.canvas.pack(side="left", padx=(12, 14), pady=10)
        texts = tk.Frame(status, bg=PAPER)
        texts.pack(side="left", fill="both", expand=True, pady=25, padx=(0, 10))
        self.status_title = tk.Label(texts, text="準備しています", anchor="w", bg=PAPER, fg=INK,
                                     font=("Yu Gothic UI", 19, "bold"))
        self.status_title.pack(fill="x", pady=(6, 8))
        self.status_detail = tk.Label(texts, text="", anchor="w", justify="left", wraplength=480,
                                      bg=PAPER, fg=MUTED, font=("Yu Gothic UI", 10))
        self.status_detail.pack(fill="x")

        buttons = tk.Frame(container, bg=BG)
        buttons.pack(fill="x", pady=16)
        self.toggle_button = ttk.Button(buttons, text="待ち受けを停止", style="Primary.TButton", command=self.toggle)
        self.toggle_button.pack(side="left")
        self.listen_button = ttk.Button(buttons, text="今すぐ話す", command=self.assistant.listen_now)
        self.listen_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(buttons, text="応答を中断", command=self.assistant.interrupt)
        self.stop_button.pack(side="left")
        self.new_button = ttk.Button(buttons, text="新しい会話", command=self.new_conversation)
        self.new_button.pack(side="right")

        history_header = tk.Frame(container, bg=BG)
        history_header.pack(fill="x", pady=(10, 8))
        tk.Label(history_header, text="会話", font=("Yu Gothic UI", 12, "bold"), bg=BG, fg=INK).pack(side="left")
        self.timing = tk.Label(history_header, text="", bg=BG, fg=MUTED, font=("Yu Gothic UI", 9))
        self.timing.pack(side="right")
        history_frame = tk.Frame(container, bg=PAPER, highlightbackground="#dce2dc", highlightthickness=1)
        self.history = tk.Text(history_frame, wrap="word", relief="flat", bg=PAPER, fg=INK,
                               padx=18, pady=14, font=("Yu Gothic UI", 12), height=9, state="disabled")
        self.history.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(history_frame, command=self.history.yview)
        scroll.pack(side="right", fill="y")
        self.history.configure(yscrollcommand=scroll.set)
        self.history.tag_configure("label", foreground=GREEN, font=("Yu Gothic UI", 9, "bold"), spacing1=10)
        self.history.tag_configure("error", foreground="#a84b3a")
        self.history.tag_configure("body", spacing1=4, spacing3=12)
        call_word = self.config["wake"]["phrases"][0]
        instruction = "合図の音が終わってから質問してください。" if self.config["audio"]["voice_cues"] else "続けて質問してください。"
        self.append("使い方", f"「{call_word}」と呼び、{instruction}\n下の入力欄からも質問できます。")

        entry_row = tk.Frame(container, bg=BG)
        self.input = ttk.Entry(entry_row, font=("Yu Gothic UI", 12))
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", lambda event: self.send())
        self.send_button = ttk.Button(entry_row, text="送信", style="Primary.TButton", command=self.send)
        self.send_button.pack(side="left", padx=(10, 0))
        footer = tk.Frame(container, bg=BG)
        footer.pack(side="bottom", fill="x")
        connection_area = tk.Frame(footer, bg=BG)
        connection_area.pack(side="left")
        self.connection = tk.Label(connection_area, text="接続を確認中", font=("Yu Gothic UI", 9), bg=BG, fg=MUTED)
        self.connection.pack(anchor="w")
        self.engine_status = tk.Label(connection_area, text="VOICEVOX：必要なときに起動", font=("Yu Gothic UI", 9), bg=BG, fg=MUTED)
        self.engine_status.pack(anchor="w")
        tk.Label(footer, text="×で通知領域に常駐  ·  終了は右クリックメニューから", font=("Yu Gothic UI", 9),
                 bg=BG, fg=MUTED).pack(side="right")
        entry_row.pack(side="bottom", fill="x", pady=(14, 12))
        history_frame.pack(fill="both", expand=True)
        self._update_controls()

    def append(self, label, text, error=False):
        self.history.configure(state="normal")
        self.history.insert("end", f"{label}  {datetime.now():%H:%M}\n", "label")
        self.history.insert("end", text.strip() + "\n", ("body", "error") if error else "body")
        # Keep the always-on UI bounded, without writing a transcript to disk.
        if int(self.history.index("end-1c").split(".")[0]) > 800:
            self.history.delete("1.0", "201.0")
        self.history.configure(state="disabled")
        self.history.see("end")

    def _poll(self):
        if self.closing:
            return
        stop_request = ROOT / "trash/stop.request"
        if stop_request.exists():
            stop_request.unlink(missing_ok=True)
            self.quit()
            return
        show_request = ROOT / "trash/show.request"
        if show_request.exists():
            show_request.unlink(missing_ok=True)
            self.show()
        for _ in range(100):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self.state = value
                title, detail, _ = STATES[value]
                if value == "waiting":
                    title = "「" + self.config["wake"]["phrases"][0] + "」と呼んでください"
                self.status_title.configure(text=title)
                self.status_detail.configure(text=detail)
                caption = "待ち受け中" if value == "waiting" else title
                self.root.title("チャッピー — " + caption)
                if self.tray:
                    self.tray.title = "チャッピー — " + caption
            elif kind == "level":
                self.level = value
            elif kind == "detail":
                self.status_detail.configure(text=value)
            elif kind == "user":
                self.append("あなた", value)
            elif kind == "answer":
                self.append("チャッピー", value)
            elif kind == "error":
                self.append("確認が必要です", value, error=True)
            elif kind == "ready":
                self.connection.configure(text="Codex サブスク接続済み  ·  音声処理はこのPC")
            elif kind == "voicevox":
                self.engine_status.configure(text="VOICEVOX：" + value)
            elif kind == "timing":
                self.timing.configure(text=value)
            elif kind == "show":
                self.show()
            elif kind == "toggle":
                self.toggle()
            elif kind == "quit":
                self.quit()
                return
            elif kind == "restart":
                self.config = value
                self.assistant = Assistant(value, self.emit)
                self.listen_button.configure(command=self.assistant.listen_now)
                self.stop_button.configure(command=self.assistant.interrupt)
                self.assistant.start()
        self._update_controls()
        self.root.after(80, self._poll)

    def _update_controls(self):
        ready = self.assistant.ready
        busy = self.assistant.busy.is_set()
        for button in (self.listen_button, self.send_button, self.new_button):
            button.configure(state="normal" if ready and not busy else "disabled")
        self.toggle_button.configure(state="normal" if ready else "disabled",
                                     text=("待ち受けを停止" if self.assistant.mic.enabled.is_set() else "待ち受けを再開")
                                     if ready else "起動準備中")
        self.stop_button.configure(state="normal" if busy or self.state == "recording" else "disabled")

    def _animate(self):
        if self.closing:
            return
        self.phase += 0.15
        self.canvas.delete("all")
        color = STATES[self.state][2]
        self.canvas.create_oval(13, 17, 109, 113, outline="#e6ebe7", width=2, fill="#f5f8f5")
        for i in range(7):
            busy = self.state in {"preparing", "thinking", "transcribing", "speaking"}
            wave = (math.sin(self.phase + i * 0.7) + 1) * 0.5 if busy else self.level
            height = 8 + wave * (32 - abs(3 - i) * 5)
            x = 34 + i * 9
            self.canvas.create_line(x, 65 - height / 2, x, 65 + height / 2, fill=color, width=5, capstyle="round")
        self.root.after(70, self._animate)

    def toggle(self):
        if self.assistant.mic.enabled.is_set():
            self.assistant.pause()
        else:
            self.assistant.resume()

    def send(self):
        value = self.input.get().strip()
        if value and self.assistant.ready and not self.assistant.busy.is_set():
            self.input.delete(0, "end")
            self.assistant.submit_text(value)

    def new_conversation(self):
        self.assistant.reset_conversation()
        self.append("会話", "新しい会話を始めます。")

    def settings(self):
        import sounddevice as sd
        dialog = tk.Toplevel(self.root)
        dialog.title("fake-siri の設定")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        content = tk.Frame(dialog, bg=BG)
        content.pack(padx=26, pady=22)
        values = {}

        def row(label, key, initial, choices=None):
            frame = tk.Frame(content, bg=BG)
            frame.pack(fill="x", pady=7)
            tk.Label(frame, text=label, width=15, anchor="w", bg=BG, fg=INK).pack(side="left")
            var = tk.StringVar(value=initial)
            widget = ttk.Combobox(frame, textvariable=var, values=choices, width=43, state="readonly") if choices else ttk.Entry(frame, textvariable=var, width=46)
            widget.pack(side="left")
            values[key] = var

        wake_editor = WakePhraseEditor(content, self.config["wake"]["phrases"],
                                       background=BG, foreground=INK, muted=MUTED)
        wake_editor.pack(fill="x", pady=(0, 10))
        cue_enabled = tk.BooleanVar(value=self.config["audio"]["voice_cues"])
        ttk.Checkbutton(content, text="開始・終了を音で知らせる", variable=cue_enabled).pack(anchor="w", pady=(0, 8))
        devices = sd.query_devices()
        inputs = {"Windowsの既定": None}
        outputs = {"Windowsの既定": None}
        for index, device in enumerate(devices):
            label = f"{index}: {device['name']}"
            if device["max_input_channels"]:
                inputs[label] = index
            if device["max_output_channels"]:
                outputs[label] = index
        for label, key, mapping in [("マイク", "input_device", inputs), ("スピーカー", "output_device", outputs)]:
            selected = next((k for k, v in mapping.items() if v == self.config["audio"][key]), "Windowsの既定")
            row(label, key, selected, list(mapping))
        row("VOICEVOXの声ID", "speaker", str(self.config["voicevox"]["speaker"]))
        row("話す速さ", "speed", str(self.config["voicevox"]["speedScale"]))
        row("続けて話せる秒数", "followup", str(self.config["audio"]["followup_seconds"]))
        row("VOICEVOX休止（分）", "idle_minutes", f'{self.config["voicevox"]["idle_timeout_seconds"] / 60:g}')
        row("Codexモデル", "model", self.config["codex"]["model"])
        tk.Label(content, text="既定の音声：VOICEVOX:ずんだもん（ノーマル、声ID 3）\n声を変える場合の利用規約・クレジットはREADMEを確認してください。", justify="left", bg=BG, fg=MUTED,
                 font=("Yu Gothic UI", 9)).pack(anchor="w", pady=14)

        def save():
            try:
                config = copy.deepcopy(self.config)
                wake_editor.add()  # Include any word still in the input field.
                config["wake"]["phrases"] = wake_editor.values()
                config["audio"]["voice_cues"] = cue_enabled.get()
                config["audio"]["input_device"] = inputs[values["input_device"].get()]
                config["audio"]["output_device"] = outputs[values["output_device"].get()]
                config["audio"]["followup_seconds"] = float(values["followup"].get())
                config["voicevox"]["idle_timeout_seconds"] = float(values["idle_minutes"].get()) * 60
                config["voicevox"]["speaker"] = int(values["speaker"].get())
                config["voicevox"]["speedScale"] = float(values["speed"].get())
                config["codex"]["model"] = values["model"].get().strip()
                save_config(config)
            except (ValueError, OSError) as error:
                messagebox.showerror("設定を確認してください", str(error), parent=dialog)
                return
            dialog.destroy()
            self.assistant.pause()
            self.assistant.ready = False
            old = self.assistant

            def restart():
                old.close()
                self.emit("restart", config)
            threading.Thread(target=restart, daemon=True).start()

        ttk.Button(content, text="保存して接続し直す", style="Primary.TButton", command=save).pack(anchor="e")

    def _tray(self):
        try:
            import pystray
            from PIL import Image
            with Image.open(ROOT / "assets/chappy.ico") as asset:
                icon = asset.convert("RGBA")
            menu = pystray.Menu(
                pystray.MenuItem("開く", lambda: self.emit("show", ""), default=True),
                pystray.MenuItem("待ち受けの停止／再開", lambda: self.emit("toggle", "")),
                pystray.MenuItem("終了", lambda: self.emit("quit", "")),
            )
            self.tray = pystray.Icon("fake-siri", icon, "チャッピー — 起動準備中", menu)
            self.tray.run_detached()
        except Exception:
            self.tray = None

    def show(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(150, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        logging.getLogger("fake_siri.lifecycle").info("window=shown")

    def hide(self):
        if self.tray:
            self.root.withdraw()
            logging.getLogger("fake_siri.lifecycle").info("window=hidden")
        else:
            self.quit()

    def quit(self):
        if self.closing:
            return
        self.closing = True
        if self.tray:
            self.tray.stop()
        self.assistant.pause()
        self.root.withdraw()

        def cleanup():
            self.assistant.close()
        worker = threading.Thread(target=cleanup)
        worker.start()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
