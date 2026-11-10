"""Native list editor for user-defined wake phrases and spelling variants."""
import re
import tkinter as tk
from tkinter import ttk

from .text import normalize


class WakePhraseEditor(tk.Frame):
    def __init__(self, parent, phrases, *, background, foreground, muted):
        super().__init__(parent, bg=background)
        tk.Label(self, text="呼びかけ語", bg=background, fg=foreground,
                 font=("Yu Gothic UI", 11, "bold")).pack(anchor="w")
        tk.Label(self, text="登録したどれか1つで反応します。漢字の表記も追加できます。",
                 bg=background, fg=muted, font=("Yu Gothic UI", 9)).pack(anchor="w", pady=(2, 6))
        list_row = tk.Frame(self, bg=background)
        list_row.pack(fill="x")
        self.words = tk.Listbox(list_row, height=3, exportselection=False, activestyle="none",
                                font=("Yu Gothic UI", 11), relief="solid", borderwidth=1)
        self.words.pack(side="left", fill="x", expand=True)
        scroll = ttk.Scrollbar(list_row, command=self.words.yview)
        scroll.pack(side="left", fill="y")
        self.words.configure(yscrollcommand=scroll.set)
        for phrase in phrases:
            self.words.insert("end", phrase)
        self.remove_button = ttk.Button(list_row, text="選択を削除", command=self.remove, state="disabled")
        self.remove_button.pack(side="left", padx=(10, 0))
        self.words.bind("<<ListboxSelect>>", self._selection_changed)
        self.words.bind("<Delete>", lambda event: self.remove())
        add_row = tk.Frame(self, bg=background)
        add_row.pack(fill="x", pady=(6, 0))
        self.entry = ttk.Entry(add_row)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self.add)
        ttk.Button(add_row, text="追加", command=self.add).pack(side="left", padx=(10, 0))
        self.message = tk.Label(self, text="かな・カナは同じ扱いです。先頭の語を画面に表示します。",
                                bg=background, fg=muted, font=("Yu Gothic UI", 9), anchor="w")
        self.message.pack(fill="x", pady=(4, 0))

    def values(self):
        return list(self.words.get(0, "end"))

    def add(self, event=None):
        raw = self.entry.get().strip()
        if not raw:
            return "break"
        candidates = [value.strip() for value in re.split(r"[、,\n]", raw) if value.strip()]
        if not candidates or any(not normalize(value) for value in candidates):
            self.message.configure(text="文字を含む呼びかけ語を入力してください。")
            return "break"
        existing = {normalize(value) for value in self.values()}
        added = 0
        for value in candidates:
            key = normalize(value)
            if key not in existing:
                self.words.insert("end", value)
                existing.add(key)
                added += 1
        self.entry.delete(0, "end")
        self.message.configure(text=f"{added}件を追加しました。" if added else "同じ表記の呼びかけ語が登録済みです。")
        return "break"

    def remove(self):
        for index in reversed(self.words.curselection()):
            self.words.delete(index)
        self._selection_changed()

    def _selection_changed(self, event=None):
        self.remove_button.configure(state="normal" if self.words.curselection() else "disabled")
