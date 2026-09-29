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
from .analyze import MAX_ITEMS
from .stickers import names as sticker_names
from .face import DEFAULT_LEVEL, DEFAULT_SLIM, LEVELS, SLIM_LEVELS
from .paths import bgm_dir
from .project import Project

NO_BGM = "(BGM 없음)"
STYLE_LABELS = {"none": "표시 안 함", "rank": "순위형 (TOP N · 아래부터)", "ordinal": "나열형 (N가지 · 위부터)",
                "quiz": "퀴즈형 (O/X 카드)", "tier": "티어리스트 (S/A/B/C)"}
PICK_BGM = "직접 고르기..."


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.project: Project | None = None
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        root.title(f"릴스 자동 편집 v{__version__}")
        root.geometry("1040x820")
        root.minsize(900, 700)
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
        self.ng_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(prog, text="NG(다시 말한 부분) 자동 제거", variable=self.ng_var).pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(prog, maximum=1.0)
        self.progress.pack(side="left", fill="x", expand=True, padx=10)
        self.status = ttk.Label(prog, text="", width=46)
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

        fmt = ttk.Frame(left)
        fmt.pack(anchor="w")
        ttk.Label(fmt, text="목록").pack(side="left")
        self.style_var = tk.StringVar(value=STYLE_LABELS["none"])
        self.style_box = ttk.Combobox(fmt, textvariable=self.style_var, values=list(STYLE_LABELS.values()),
                                      state="readonly", width=22)
        self.style_box.pack(side="left", padx=6)
        self.style_box.bind("<<ComboboxSelected>>", lambda _e: self._layout_items())
        ttk.Label(fmt, text="개수").pack(side="left")
        self.count_var = tk.IntVar(value=5)
        self.count_spin = ttk.Spinbox(fmt, from_=2, to=MAX_ITEMS, textvariable=self.count_var, width=4,
                                      command=self._layout_items, state="readonly")
        self.count_spin.pack(side="left", padx=6)
        self.item_grid = ttk.Frame(left)
        self.item_grid.pack(anchor="w", pady=(2, 8))
        self.item_head = [ttk.Label(self.item_grid, text="순서"), ttk.Label(self.item_grid, text="목록에 들어갈 글자"),
                          ttk.Label(self.item_grid, text="나타나는 시점(초)")]
        self.item_text: dict[int, tk.StringVar] = {}
        self.item_time: dict[int, tk.StringVar] = {}
        self.item_rows: dict[int, tuple[ttk.Label, ttk.Entry, ttk.Entry]] = {}
        self.item_widgets: list[tk.Widget] = [self.style_box, self.count_spin]
        for slot in range(1, MAX_ITEMS + 1):
            self.item_text[slot] = tk.StringVar()
            self.item_time[slot] = tk.StringVar()
            row = (ttk.Label(self.item_grid, text=""),
                   ttk.Entry(self.item_grid, textvariable=self.item_text[slot], width=28),
                   ttk.Entry(self.item_grid, textvariable=self.item_time[slot], width=8))
            self.item_rows[slot] = row
            self.item_widgets += [row[1], row[2]]
        self._layout_items()

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

        ttk.Label(left, text="얼굴 자동 보정").pack(anchor="w", pady=(10, 0))
        faces = ttk.Frame(left)
        faces.pack(anchor="w")
        ttk.Label(faces, text="피부 결").grid(row=0, column=0, sticky="w")
        self.retouch_var = tk.StringVar(value=DEFAULT_LEVEL)
        ttk.Combobox(faces, textvariable=self.retouch_var, values=list(LEVELS), state="readonly", width=8).grid(row=0, column=1, padx=6, pady=2)
        ttk.Label(faces, text="얼굴형 갸름하게").grid(row=1, column=0, sticky="w")
        self.slim_var = tk.StringVar(value=DEFAULT_SLIM)
        ttk.Combobox(faces, textvariable=self.slim_var, values=list(SLIM_LEVELS), state="readonly", width=8).grid(row=1, column=1, padx=6, pady=2)
        self.face_note = ttk.Label(left, text="", foreground="#666")
        self.face_note.pack(anchor="w")

        ttk.Label(right, text="자막 (한 줄 = 화면에 한 번 나오는 자막 · 글자만 고치면 타이밍은 그대로)").pack(anchor="w")
        sub_frame = ttk.Frame(right)
        sub_frame.pack(fill="both", expand=True)
        self.sub_text = tk.Text(sub_frame, font=("Malgun Gothic", 11), wrap="none", undo=True)
        scroll = ttk.Scrollbar(sub_frame, command=self.sub_text.yview)
        self.sub_text.configure(yscrollcommand=scroll.set)
        self.sub_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")

        # 스티커 / 퀴즈 / 티어리스트는 탭 하나에 모아서 작은 화면에서도 버튼이 보이게 한다
        tabs = self.tabs = ttk.Notebook(right)
        tabs.pack(fill="x", pady=(8, 0))
        self.sticker_text = self._tab(tabs, "그림 스티커", "한 줄에 '나타나는 시점(초) 이름' · 줄을 지우면 안 나와요\n"
                                      "쓸 수 있는 이름: " + ", ".join(sticker_names()))
        self.quiz_text = self._tab(tabs, "퀴즈 카드", "한 줄에 '문제 시작(초) 정답 공개(초) O/X 그림' · 예: 1.5 4.8 O 휴대폰\n"
                                   "그림 자리에 스티커 이름이나 사진 파일 경로(예: C:/사진/카톡.png)")
        self.tier_text = self._tab(tabs, "티어리스트", "한 줄에 '나타나는 시점(초) 등급 글자' · 예: 3.2 S 욕설")

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        self.render_btn = ttk.Button(bottom, text="③ 영상 만들기", command=self.start_render)
        self.render_btn.pack(side="left")
        self.open_btn = ttk.Button(bottom, text="결과 폴더 열기", command=self.open_output, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        self.last_output: str | None = None

    def _tab(self, tabs: ttk.Notebook, title: str, hint: str) -> tk.Text:
        frame = ttk.Frame(tabs)
        tabs.add(frame, text=title)
        ttk.Label(frame, text=hint, wraplength=500, foreground="#666").pack(anchor="w")
        text = tk.Text(frame, height=4, font=("Malgun Gothic", 11), wrap="none", undo=True)
        text.pack(fill="x")
        return text

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
        for w in [self.title_text, self.sub_text, self.sticker_text, self.quiz_text, self.tier_text, self.render_btn, *self.item_widgets]:
            w.configure(state=state)

    def _style(self) -> str:
        return next((k for k, v in STYLE_LABELS.items() if v == self.style_var.get()), "none")

    def _layout_items(self) -> None:
        """목록 형식과 개수에 맞춰 입력 줄을 보여준다. 순위형은 말하는 순서(N위 → 1위)대로 나열."""
        style, count = self._style(), int(self.count_var.get())
        for w in (*self.item_head, *[x for r in self.item_rows.values() for x in r]):
            w.grid_remove()
        if style in ("none", "quiz", "tier"):
            return
        for col, w in enumerate(self.item_head):
            w.grid(row=0, column=col)
        order = range(count, 0, -1) if style == "rank" else range(1, count + 1)
        for row, slot in enumerate(order, start=1):
            label, e1, e2 = self.item_rows[slot]
            label.configure(text=f"{slot}위" if style == "rank" else f"{slot}번째")
            label.grid(row=row, column=0, padx=4)
            e1.grid(row=row, column=1, padx=4, pady=2)
            e2.grid(row=row, column=2, padx=4, pady=2)

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

        p = analyze_video(source, lambda m, f: self.events.put(("progress", m, f)), remove_ng=self.ng_var.get())
        self.events.put(("analyzed", p))

    def _fill_form(self, p: Project) -> None:
        self._set_enabled(True)
        self.title_text.delete("1.0", "end")
        self.title_text.insert("1.0", p.title)
        self.style_var.set(STYLE_LABELS.get(p.list_style, STYLE_LABELS["none"]))
        self.count_var.set(p.list_count if p.list_count >= 2 else 5)
        by_slot = {it.rank: it for it in p.items}
        for slot in range(1, MAX_ITEMS + 1):
            it = by_slot.get(slot)
            self.item_text[slot].set(it.text if it else "")
            self.item_time[slot].set(f"{it.time:.2f}" if it and it.time is not None else "")
        self._layout_items()
        self.sub_text.delete("1.0", "end")
        self.sub_text.insert("1.0", "\n".join(c.text for c in p.captions))
        name = Path(p.bgm).stem if p.bgm else NO_BGM
        if p.bgm:
            self.bgm_paths.setdefault(name, p.bgm)
        self.bgm_var.set(name)
        self.vol_var.set(p.bgm_volume)
        self.retouch_var.set(p.retouch)
        self.slim_var.set(p.slim)
        self.face_note.configure(text="얼굴을 찾았어요" if p.face_box else "얼굴을 못 찾아서 밝기·혈색만 보정해요")
        self.tier_text.delete("1.0", "end")
        self.tier_text.insert("1.0", "\n".join(f"{t.time:.2f} {t.tier} {t.text}" for t in p.tiers))
        self.quiz_text.delete("1.0", "end")
        self.quiz_text.insert("1.0", "\n".join(f"{q.start:.2f} {q.reveal:.2f} {q.answer} {q.image}" for q in p.quiz))
        self.sticker_text.delete("1.0", "end")
        self.sticker_text.insert("1.0", "\n".join(f"{x.start:.2f} {x.name}" for x in p.stickers))
        ng = f" · NG {len(p.ng_removed)}곳 제거" if p.ng_removed else ""
        self.status.configure(text=f"분석 끝: {p.duration:.1f}초 · 컷 {len(p.segments)}개{ng} · 도입부: {p.hook_type or '-'}")
        # 퀴즈·티어 영상이면 해당 편집 탭을 바로 보여준다
        self.tabs.select({"quiz": 1, "tier": 2}.get(p.list_style, 0))

    def _collect(self) -> Project:
        from .project import RankItem

        assert self.project is not None
        p = self.project
        p.title = self.title_text.get("1.0", "end").strip()
        p.list_style = self._style()
        p.list_count = int(self.count_var.get()) if p.list_style != "none" else 0
        items = []
        for slot in range(1, p.list_count + 1):
            raw = self.item_time[slot].get().strip()
            try:
                t = float(raw) if raw else None
            except ValueError:
                raise ValueError(f"목록 {slot}번 줄의 시점은 숫자로 적어주세요 (예: 12.5)")
            items.append(RankItem(slot, t, self.item_text[slot].get().strip()))
        p.items = items
        lines = self.sub_text.get("1.0", "end").split("\n")
        p.captions = retime_captions(lines, p.captions, p.duration)
        choice = self.bgm_var.get()
        p.bgm = self.bgm_paths.get(choice) if choice not in (NO_BGM, PICK_BGM) else None
        p.bgm_volume = float(self.vol_var.get())
        p.retouch = self.retouch_var.get()
        p.slim = self.slim_var.get()
        p.stickers = self._read_stickers(p)
        p.quiz = self._read_quiz(p)
        p.tiers = self._read_tiers()
        return p

    def _read_stickers(self, p: Project) -> list:
        from .project import Sticker

        known = {(round(x.start, 2), x.name): x for x in p.stickers}
        valid = set(sticker_names())
        out = []
        for n, raw in enumerate(self.sticker_text.get("1.0", "end").splitlines(), start=1):
            parts = raw.split()
            if not parts:
                continue
            try:
                start = float(parts[0])
            except ValueError:
                raise ValueError(f"스티커 {n}번째 줄: 앞에 시점(초)을 숫자로 적어주세요 (예: 3.5 달력)")
            name = " ".join(parts[1:])
            if name not in valid:
                raise ValueError(f"스티커 {n}번째 줄: '{name}' 스티커가 없어요. 아래 목록의 이름을 써주세요.")
            old = known.get((round(start, 2), name))
            out.append(old or Sticker(start, min(start + 2.5, p.duration), name))
        return out

    def _read_tiers(self) -> list:
        from .project import TierItem

        items = []
        for n, raw in enumerate(self.tier_text.get("1.0", "end").splitlines(), start=1):
            parts = raw.split(maxsplit=2)
            if not parts:
                continue
            try:
                t, grade, text = float(parts[0]), parts[1].upper(), parts[2].strip()
            except (ValueError, IndexError):
                raise ValueError(f"티어리스트 {n}번째 줄: '시점 등급 글자' 순서로 적어주세요 (예: 3.2 S 욕설)")
            if grade not in ("S", "A", "B", "C"):
                raise ValueError(f"티어리스트 {n}번째 줄: 등급은 S, A, B, C 중 하나로 적어주세요")
            items.append(TierItem(grade, t, text))
        return items

    def _read_quiz(self, p: Project) -> list:
        from .project import QuizItem

        rows = []
        for n, raw in enumerate(self.quiz_text.get("1.0", "end").splitlines(), start=1):
            parts = raw.split(maxsplit=3)
            if not parts:
                continue
            try:
                start, reveal = float(parts[0]), float(parts[1])
                answer = parts[2].upper()
                image = parts[3].strip() if len(parts) > 3 else "물음표"
            except (ValueError, IndexError):
                raise ValueError(f"퀴즈 {n}번째 줄: '문제 시작 정답 공개 O/X 그림' 순서로 적어주세요 (예: 1.5 4.8 O 휴대폰)")
            if answer not in ("O", "X"):
                raise ValueError(f"퀴즈 {n}번째 줄: 정답은 O 또는 X로 적어주세요")
            if not Path(image).suffix and image not in sticker_names():
                raise ValueError(f"퀴즈 {n}번째 줄: '{image}' 그림이 없어요. 스티커 이름이나 사진 파일 경로를 써주세요.")
            rows.append([start, reveal, answer, image])
        rows.sort(key=lambda r: r[0])
        items = []
        for i, (start, reveal, answer, image) in enumerate(rows):
            end = rows[i + 1][0] - 0.05 if i + 1 < len(rows) else p.duration
            items.append(QuizItem(start, max(reveal, start), end, answer, image))
        return items

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
