"""프로그램 창 (tkinter). ① 영상 선택 → ② 분석 → 추천값 확인·수정 → ③ 영상 만들기."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .analyze import retime_captions
from .paths import bgm_dir
from .project import Project

NO_BGM = "(BGM 없음)"
PICK_BGM = "직접 고르기..."


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.project: Project | None = None
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        root.title(f"릴스 자동 편집 v{__version__}")
        root.geometry("1040x720")
        root.minsize(900, 620)
        self._build()
        self._set_enabled(False)
        root.after(100, self._poll)

    # ---------- 화면 구성 ----------
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="① 원본 영상 고르기", command=self.pick_video).pack(side="left")
        self.src_label = ttk.Label(top, text="아직 고른 영상이 없어요")
        self.src_label.pack(side="left", padx=10)

        prog = ttk.Frame(self.root)
        prog.pack(fill="x", **pad)
        self.analyze_btn = ttk.Button(prog, text="② 자동 분석", command=self.start_analyze, state="disabled")
        self.analyze_btn.pack(side="left")
        self.progress = ttk.Progressbar(prog, maximum=1.0)
        self.progress.pack(side="left", fill="x", expand=True, padx=10)
        self.status = ttk.Label(prog, text="", width=34)
        self.status.pack(side="left")

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, **pad)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        ttk.Label(left, text="제목 (엔터로 줄바꿈)").pack(anchor="w")
        self.title_text = tk.Text(left, height=2, width=44, font=("Malgun Gothic", 12))
        self.title_text.pack(anchor="w", pady=(0, 8))

        self.top_var = tk.BooleanVar(value=False)
        self.top_check = ttk.Checkbutton(left, text="TOP 5 목록 표시", variable=self.top_var)
        self.top_check.pack(anchor="w")
        grid = ttk.Frame(left)
        grid.pack(anchor="w", pady=(2, 8))
        ttk.Label(grid, text="순위").grid(row=0, column=0)
        ttk.Label(grid, text="목록에 들어갈 글자").grid(row=0, column=1)
        ttk.Label(grid, text="나타나는 시점(초)").grid(row=0, column=2)
        self.item_text: dict[int, tk.StringVar] = {}
        self.item_time: dict[int, tk.StringVar] = {}
        self.item_widgets: list[tk.Widget] = []
        for row, rank in enumerate((5, 4, 3, 2, 1), start=1):
            ttk.Label(grid, text=f"{rank}위").grid(row=row, column=0, padx=4)
            self.item_text[rank] = tk.StringVar()
            self.item_time[rank] = tk.StringVar()
            e1 = ttk.Entry(grid, textvariable=self.item_text[rank], width=28)
            e2 = ttk.Entry(grid, textvariable=self.item_time[rank], width=8)
            e1.grid(row=row, column=1, padx=4, pady=2)
            e2.grid(row=row, column=2, padx=4, pady=2)
            self.item_widgets += [e1, e2]

        ttk.Label(left, text="배경음악").pack(anchor="w", pady=(6, 0))
        self.bgm_var = tk.StringVar(value=NO_BGM)
        self.bgm_box = ttk.Combobox(left, textvariable=self.bgm_var, state="readonly", width=40)
        self.bgm_box.pack(anchor="w")
        self.bgm_box.bind("<<ComboboxSelected>>", self._bgm_selected)
        self.bgm_paths: dict[str, str] = {}
        self._refresh_bgm_list()
        vol = ttk.Frame(left)
        vol.pack(anchor="w", pady=4)
        ttk.Label(vol, text="음악 크기").pack(side="left")
        self.vol_var = tk.DoubleVar(value=0.18)
        ttk.Scale(vol, from_=0.02, to=0.5, variable=self.vol_var, length=220).pack(side="left", padx=6)

        ttk.Label(right, text="자막 (한 줄 = 화면에 한 번 나오는 자막 · 글자만 고치면 타이밍은 그대로)").pack(anchor="w")
        sub_frame = ttk.Frame(right)
        sub_frame.pack(fill="both", expand=True)
        self.sub_text = tk.Text(sub_frame, font=("Malgun Gothic", 11), wrap="none", undo=True)
        scroll = ttk.Scrollbar(sub_frame, command=self.sub_text.yview)
        self.sub_text.configure(yscrollcommand=scroll.set)
        self.sub_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        self.render_btn = ttk.Button(bottom, text="③ 영상 만들기", command=self.start_render)
        self.render_btn.pack(side="left")
        self.open_btn = ttk.Button(bottom, text="결과 폴더 열기", command=self.open_output, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        self.last_output: str | None = None

    def _refresh_bgm_list(self) -> None:
        self.bgm_paths = {p.stem: str(p) for p in sorted(bgm_dir().glob("*.mp3"))} if bgm_dir().exists() else {}
        self.bgm_box["values"] = [NO_BGM, *self.bgm_paths.keys(), PICK_BGM]

    def _bgm_selected(self, _event=None) -> None:
        if self.bgm_var.get() != PICK_BGM:
            return
        path = filedialog.askopenfilename(title="배경음악 고르기", filetypes=[("음악", "*.mp3 *.wav *.m4a *.aac *.ogg"), ("모든 파일", "*.*")])
        if path:
            self.bgm_paths[Path(path).stem] = path
            self.bgm_box["values"] = [NO_BGM, *self.bgm_paths.keys(), PICK_BGM]
            self.bgm_var.set(Path(path).stem)
        else:
            self.bgm_var.set(NO_BGM)

    def _set_enabled(self, on: bool) -> None:
        state = "normal" if on else "disabled"
        for w in [self.title_text, self.sub_text, self.top_check, self.render_btn, *self.item_widgets]:
            w.configure(state=state)

    # ---------- 동작 ----------
    def pick_video(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(title="원본 영상 고르기", filetypes=[("영상", "*.mp4 *.mov *.m4v *.mkv *.avi"), ("모든 파일", "*.*")])
        if path:
            self.source = path
            self.src_label.configure(text=path)
            self.analyze_btn.configure(state="normal")
            self.status.configure(text="'② 자동 분석'을 눌러주세요")

    def start_analyze(self) -> None:
        self._run_bg(self._analyze_job, self.source)

    def _analyze_job(self, source: str) -> None:
        from .pipeline import analyze_video

        p = analyze_video(source, lambda m, f: self.events.put(("progress", m, f)))
        self.events.put(("analyzed", p))

    def _fill_form(self, p: Project) -> None:
        self._set_enabled(True)
        self.title_text.delete("1.0", "end")
        self.title_text.insert("1.0", p.title)
        self.top_var.set(p.top_mode)
        by_rank = {it.rank: it for it in p.items}
        for rank in (5, 4, 3, 2, 1):
            it = by_rank.get(rank)
            self.item_text[rank].set(it.text if it else "")
            self.item_time[rank].set(f"{it.time:.2f}" if it and it.time is not None else "")
        self.sub_text.delete("1.0", "end")
        self.sub_text.insert("1.0", "\n".join(c.text for c in p.captions))
        name = Path(p.bgm).stem if p.bgm else NO_BGM
        if p.bgm:
            self.bgm_paths.setdefault(name, p.bgm)
        self.bgm_var.set(name)
        self.vol_var.set(p.bgm_volume)
        self.status.configure(text=f"분석 끝: {p.duration:.1f}초 · 컷 {len(p.segments)}개")

    def _collect(self) -> Project:
        from .project import RankItem

        assert self.project is not None
        p = self.project
        p.title = self.title_text.get("1.0", "end").strip()
        p.top_mode = self.top_var.get()
        items = []
        for rank in (5, 4, 3, 2, 1):
            raw = self.item_time[rank].get().strip()
            try:
                t = float(raw) if raw else None
            except ValueError:
                raise ValueError(f"{rank}위 시점은 숫자로 적어주세요 (예: 12.5)")
            items.append(RankItem(rank, t, self.item_text[rank].get().strip()))
        p.items = items
        lines = self.sub_text.get("1.0", "end").split("\n")
        p.captions = retime_captions(lines, p.captions, p.duration)
        choice = self.bgm_var.get()
        p.bgm = self.bgm_paths.get(choice) if choice not in (NO_BGM, PICK_BGM) else None
        p.bgm_volume = float(self.vol_var.get())
        return p

    def start_render(self) -> None:
        if self.busy or self.project is None:
            return
        try:
            p = self._collect()
        except ValueError as e:
            messagebox.showwarning("확인해주세요", str(e))
            return
        default = Path(p.source).stem + "_릴스.mp4"
        out = filedialog.asksaveasfilename(title="저장할 곳", initialdir=str(Path(p.source).parent),
                                           initialfile=default, defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if out:
            self._run_bg(self._render_job, p, out)

    def _render_job(self, p: Project, out: str) -> None:
        from .render import render

        render(p, out, lambda f: self.events.put(("progress", "영상 만드는 중", f)))
        self.events.put(("rendered", out))

    def open_output(self) -> None:
        if not self.last_output:
            return
        folder = str(Path(self.last_output).parent)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.last_output)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    # ---------- 백그라운드 작업 ----------
    def _run_bg(self, fn, *args) -> None:
        self.busy = True
        self.analyze_btn.configure(state="disabled")
        self.render_btn.configure(state="disabled")

        def wrapper():
            try:
                fn(*args)
            except Exception as e:  # 사용자에게 그대로 보여준다
                self.events.put(("error", str(e)))

        threading.Thread(target=wrapper, daemon=True).start()

    def _done(self) -> None:
        self.busy = False
        self.analyze_btn.configure(state="normal")
        if self.project is not None:
            self.render_btn.configure(state="normal")

    def _poll(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "progress":
                    self.status.configure(text=ev[1])
                    self.progress["value"] = ev[2]
                elif kind == "analyzed":
                    self.project = ev[1]
                    self._fill_form(ev[1])
                    self._done()
                elif kind == "rendered":
                    self.last_output = ev[1]
                    self.open_btn.configure(state="normal")
                    self.status.configure(text="완성!")
                    self._done()
                    messagebox.showinfo("완성", f"저장했어요:\n{ev[1]}")
                elif kind == "error":
                    self._done()
                    self.status.configure(text="오류가 났어요")
                    messagebox.showerror("오류", ev[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


def run() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
