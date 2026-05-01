"""
Qween TTS – Tkinter desktop application.
Run: python gui.py
"""
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from document_reader import READERS, read_document
from tts_engine import BACKENDS, DEFAULT_BACKEND, DEFAULT_DEVICE, LANGUAGES, SPEAKERS, TTSEngine

# ── Catppuccin Mocha palette ──────────────────────────────────────────────────
BG      = "#1e1e2e"
SURFACE = "#313244"
OVERLAY = "#45475a"
TEXT    = "#cdd6f4"
SUBTEXT = "#a6adc8"
BLUE    = "#89b4fa"
GREEN   = "#a6e3a1"
RED     = "#f38ba8"
YELLOW  = "#f9e2af"

FN = ("Sans", 10)
FM = ("Monospace", 10)
FB = ("Sans", 10, "bold")
FT = ("Sans", 12, "bold")


# ── App ───────────────────────────────────────────────────────────────────────

class QweenApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Qween TTS")
        self.geometry("1040x700")
        self.minsize(720, 480)
        self.configure(bg=BG)

        self.engine = TTSEngine.get_instance()
        self.output_path = os.path.join(os.getcwd(), "output.wav")
        self._model_ready = False

        self._setup_style()
        self._build()
        self._load_model_async()

    # ── ttk Style ─────────────────────────────────────────────────────────────

    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("TFrame",          background=BG)
        s.configure("Surface.TFrame",  background=SURFACE)
        s.configure("TLabel",          background=BG,      foreground=TEXT,    font=FN)
        s.configure("Title.TLabel",    background=BG,      foreground=BLUE,    font=FT)
        s.configure("Sub.TLabel",      background=BG,      foreground=SUBTEXT, font=FN)
        s.configure("Surf.TLabel",     background=SURFACE, foreground=TEXT,    font=FN)
        s.configure("SurfSub.TLabel",  background=SURFACE, foreground=SUBTEXT, font=FN)
        s.configure("SurfTitle.TLabel",background=SURFACE, foreground=BLUE,    font=FT)

        s.configure("TButton",
                    background=OVERLAY, foreground=TEXT, font=FN,
                    padding=6, relief="flat", borderwidth=0)
        s.map("TButton",
              background=[("active", "#585b70"), ("disabled", SURFACE)],
              foreground=[("disabled", SUBTEXT)])

        s.configure("Accent.TButton",
                    background=BLUE, foreground="#1e1e2e", font=FB,
                    padding=8, relief="flat", borderwidth=0)
        s.map("Accent.TButton",
              background=[("active", "#74c7ec"), ("disabled", OVERLAY)],
              foreground=[("disabled", SUBTEXT)])

        s.configure("TCombobox",
                    fieldbackground=OVERLAY, background=OVERLAY,
                    foreground=TEXT, selectbackground=BLUE,
                    selectforeground="#1e1e2e", padding=4)
        self.option_add("*TCombobox*Listbox.background", SURFACE)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", BLUE)

        s.configure("TProgressbar", troughcolor=SURFACE, background=BLUE, thickness=5)
        s.configure("TScrollbar",   background=OVERLAY, troughcolor=SURFACE, arrowcolor=SUBTEXT)
        s.configure("TSeparator",   background=OVERLAY)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_topbar()
        self._build_main()
        self._build_statusbar()

    def _build_topbar(self):
        bar = ttk.Frame(self, style="Surface.TFrame")
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(3, weight=1)

        ttk.Label(bar, text="⬛ Qween TTS", style="SurfTitle.TLabel").grid(
            row=0, column=0, padx=16, pady=10)

        ttk.Button(bar, text="Open Document…", command=self._open_file).grid(
            row=0, column=1, padx=8, pady=8)
        ttk.Button(bar, text="Paste Clipboard", command=self._paste).grid(
            row=0, column=2, padx=(0, 8), pady=8)

        # spacer
        ttk.Frame(bar, style="Surface.TFrame").grid(row=0, column=3, sticky="ew")

        ttk.Label(bar, text="Device:", style="SurfSub.TLabel").grid(
            row=0, column=4, padx=(8, 4))
        self.device_var = tk.StringVar(value=DEFAULT_DEVICE)
        ttk.Combobox(bar, textvariable=self.device_var,
                     values=["cuda:0", "cuda:1", "cpu"],
                     width=8, state="readonly").grid(row=0, column=5, padx=(0, 16))

    def _build_main(self):
        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

        # ── Left: editor ──────────────────────────────────────────────────────
        left = ttk.Frame(pane)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        pane.add(left, weight=3)

        self.text_area = tk.Text(
            left,
            bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            font=FM, wrap=tk.WORD, relief="flat", bd=0,
            padx=12, pady=10, undo=True,
            selectbackground=BLUE, selectforeground="#1e1e2e",
        )
        self.text_area.grid(row=0, column=0, sticky="nsew")
        self.text_area.bind("<KeyRelease>", self._update_count)

        vsb = ttk.Scrollbar(left, command=self.text_area.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.text_area.configure(yscrollcommand=vsb.set)

        self.count_var = tk.StringVar(value="0 chars · 0 words")
        ttk.Label(left, textvariable=self.count_var,
                  style="Sub.TLabel").grid(row=1, column=0, sticky="e", padx=6, pady=2)

        # ── Right: settings ───────────────────────────────────────────────────
        right = ttk.Frame(pane, style="Surface.TFrame")
        right.columnconfigure(0, weight=1)
        pane.add(right, weight=1)
        self._build_settings(right)

    def _build_settings(self, p):
        g = dict(padx=16, pady=5, sticky="ew")

        ttk.Label(p, text="Settings", style="SurfTitle.TLabel").grid(
            row=0, column=0, padx=16, pady=(16, 4), sticky="w")
        ttk.Separator(p).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        ttk.Label(p, text="Backend", style="SurfSub.TLabel").grid(row=2, column=0, **g)
        self.backend_var = tk.StringVar(value=DEFAULT_BACKEND)
        ttk.Combobox(
            p,
            textvariable=self.backend_var,
            values=list(BACKENDS.keys()),
            state="readonly",
        ).grid(row=3, column=0, **g)
        self.backend_var.trace_add("write", lambda *_: self._on_backend_change())

        ttk.Label(p, text="Speaker", style="SurfSub.TLabel").grid(row=4, column=0, **g)
        self.speaker_var = tk.StringVar(value="Ryan")
        ttk.Combobox(p, textvariable=self.speaker_var,
                     values=SPEAKERS, state="readonly").grid(row=5, column=0, **g)

        ttk.Label(p, text="Language", style="SurfSub.TLabel").grid(row=6, column=0, **g)
        self.lang_var = tk.StringVar(value="English")
        ttk.Combobox(p, textvariable=self.lang_var,
                     values=LANGUAGES, state="readonly").grid(row=7, column=0, **g)

        ttk.Separator(p).grid(row=8, column=0, sticky="ew", padx=16, pady=12)

        self.gen_btn = ttk.Button(p, text="▶  Generate Audio",
                                  style="Accent.TButton", command=self._generate)
        self.gen_btn.grid(row=9, column=0, **g)

        self.play_btn = ttk.Button(p, text="Play",
                                   command=self._play, state="disabled")
        self.play_btn.grid(row=10, column=0, **g)

        self.save_btn = ttk.Button(p, text="Save As…",
                                   command=self._save_as, state="disabled")
        self.save_btn.grid(row=11, column=0, **g)

        ttk.Separator(p).grid(row=12, column=0, sticky="ew", padx=16, pady=12)

        ttk.Button(p, text="Clear Text", command=self._clear).grid(
            row=13, column=0, **g)

        # Stretch filler
        ttk.Frame(p, style="Surface.TFrame").grid(row=14, column=0, sticky="nsew")
        p.rowconfigure(14, weight=1)

        # Model status indicator at bottom of panel
        self.model_indicator = ttk.Label(p, text="● Model loading…",
                                         style="SurfSub.TLabel")
        self.model_indicator.grid(row=15, column=0, padx=16, pady=(0, 12), sticky="w")

    def _build_statusbar(self):
        bar = ttk.Frame(self, style="Surface.TFrame")
        bar.grid(row=2, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(bar, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        self.status_var = tk.StringVar(value="Initialising…")
        ttk.Label(bar, textvariable=self.status_var,
                  style="SurfSub.TLabel").grid(row=0, column=1, padx=(0, 16))

    # ── Model ─────────────────────────────────────────────────────────────────

    def _load_model_async(self):
        self._model_ready = False
        self.model_indicator.configure(text="● Model loading…", foreground=SUBTEXT)
        self.progress.start(12)

        def _run():
            try:
                self.engine.load_model(
                    backend=self.backend_var.get(),
                    device=self.device_var.get(),
                    progress_cb=lambda m, _p=None: self.after(0, lambda m=m: self._set_status(m)),
                )
                self._model_ready = True
                self.after(0, self._on_model_ready)
            except Exception as e:
                self.after(0, lambda: self._set_status(f"Model error: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _on_model_ready(self):
        self.progress.stop()
        self._set_status("Ready")
        self.model_indicator.configure(text="● Model ready", foreground=GREEN)

    def _on_backend_change(self):
        self.gen_btn.config(state="disabled")
        self.play_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self._set_status("Loading model…")
        self._load_model_async()

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.update_idletasks()

    # ── Text helpers ──────────────────────────────────────────────────────────

    def _update_count(self, _event=None):
        raw = self.text_area.get("1.0", tk.END)
        chars = len(raw) - 1
        words = len(raw.split())
        self.count_var.set(f"{chars:,} chars · {words:,} words")

    def _clear(self):
        self.text_area.delete("1.0", tk.END)
        self._update_count()

    def _paste(self):
        try:
            self.text_area.insert(tk.INSERT, self.clipboard_get())
            self._update_count()
        except tk.TclError:
            pass

    # ── File open ─────────────────────────────────────────────────────────────

    def _open_file(self):
        exts = " ".join(f"*{e}" for e in READERS)
        path = filedialog.askopenfilename(
            filetypes=[
                ("All supported", exts),
                ("Plain text",    "*.txt"),
                ("Markdown",      "*.md *.markdown"),
                ("Word document", "*.docx"),
                ("PDF",           "*.pdf"),
                ("All files",     "*.*"),
            ]
        )
        if not path:
            return
        try:
            text = read_document(path)
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert("1.0", text)
            self._update_count()
            self._set_status(f"Loaded: {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Read error", str(exc))

    # ── Generate ──────────────────────────────────────────────────────────────

    def _generate(self):
        if not self._model_ready:
            messagebox.showwarning("Not ready", "The model is still loading. Please wait.")
            return
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Empty", "Enter or load text first.")
            return

        self.gen_btn.config(state="disabled")
        self.play_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.progress.start(10)

        def _run():
            try:
                self.engine.generate(
                    text=text,
                    language=self.lang_var.get(),
                    speaker=self.speaker_var.get(),
                    output_path=self.output_path,
                    backend=self.backend_var.get(),
                    device=self.device_var.get(),
                    progress_cb=lambda m, _p=None: self.after(0, lambda m=m: self._set_status(m)),
                )
                self.after(0, self._on_gen_done)
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Generation error", str(exc)))
            finally:
                self.after(0, self._on_gen_finished)

        threading.Thread(target=_run, daemon=True).start()

    def _on_gen_done(self):
        self._set_status(f"Saved: {self.output_path}")
        self.play_btn.config(state="normal")
        self.save_btn.config(state="normal")

    def _on_gen_finished(self):
        self.progress.stop()
        self.gen_btn.config(state="normal")

    # ── Audio playback / save ─────────────────────────────────────────────────

    def _play(self):
        if not os.path.exists(self.output_path):
            return
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", self.output_path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.output_path])
        else:
            os.startfile(self.output_path)

    def _save_as(self):
        dest = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if dest:
            shutil.copy(self.output_path, dest)
            self._set_status(f"Saved to: {dest}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QweenApp()
    app.mainloop()


if __name__ == "__main__":
    main()
