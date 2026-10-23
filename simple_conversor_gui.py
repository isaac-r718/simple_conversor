"""Interfaz gráfica para convertir carpetas de documentos a Markdown."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from simple_conversor import ROOT, convert_path


class SimpleConversorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("simple_conversor")
        self.root.minsize(620, 390)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        self.input_folder = tk.StringVar(value=str(ROOT / "not_md"))
        self.output_folder = tk.StringVar(value=str(ROOT / "md"))
        self.overwrite = tk.BooleanVar(value=False)
        self.messages: queue.Queue[tuple[str, bool] | None] = queue.Queue()

        self._build_widgets()
        self.root.after(100, self._read_messages)

    def _build_widgets(self) -> None:
        folders = ttk.LabelFrame(self.root, text="Carpetas")
        folders.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        folders.columnconfigure(1, weight=1)

        ttk.Label(folders, text="Archivos de origen:").grid(
            row=0, column=0, padx=(10, 6), pady=8, sticky="w"
        )
        ttk.Entry(folders, textvariable=self.input_folder).grid(
            row=0, column=1, padx=6, pady=8, sticky="ew"
        )
        ttk.Button(
            folders, text="Cambiar...", command=self._choose_input
        ).grid(row=0, column=2, padx=(6, 10), pady=8)

        ttk.Label(folders, text="Carpeta de destino:").grid(
            row=1, column=0, padx=(10, 6), pady=8, sticky="w"
        )
        ttk.Entry(folders, textvariable=self.output_folder).grid(
            row=1, column=1, padx=6, pady=8, sticky="ew"
        )
        ttk.Button(
            folders, text="Cambiar...", command=self._choose_output
        ).grid(row=1, column=2, padx=(6, 10), pady=8)

        options = ttk.Frame(self.root)
        options.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        ttk.Checkbutton(
            options,
            text="Reemplazar archivos Markdown existentes",
            variable=self.overwrite,
        ).pack(side="left")
        self.convert_button = ttk.Button(
            options, text="Convertir", command=self._start_conversion
        )
        self.convert_button.pack(side="right")

        log_frame = ttk.LabelFrame(self.root, text="Progreso")
        log_frame.grid(row=3, column=0, padx=12, pady=6, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.log.configure(yscrollcommand=scrollbar.set)

        ttk.Label(
            self.root,
            text="El contenido se procesa localmente. Los PDF escaneados requieren OCR.",
        ).grid(row=4, column=0, padx=12, pady=(0, 10), sticky="w")

    def _choose_input(self) -> None:
        folder = filedialog.askdirectory(
            title="Selecciona la carpeta con los documentos",
            initialdir=self.input_folder.get() or str(ROOT),
        )
        if folder:
            self.input_folder.set(folder)

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(
            title="Selecciona la carpeta de destino",
            initialdir=self.output_folder.get() or str(ROOT),
        )
        if folder:
            self.output_folder.set(folder)

    def _append_log(self, message: str, is_error: bool = False) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{'Error: ' if is_error else ''}{message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start_conversion(self) -> None:
        source = Path(self.input_folder.get().strip()).expanduser()
        destination = Path(self.output_folder.get().strip()).expanduser()
        if not self.input_folder.get().strip() or not source.is_dir():
            messagebox.showerror(
                "Carpeta de origen inválida",
                "Selecciona una carpeta de origen existente.",
                parent=self.root,
            )
            return
        if not self.output_folder.get().strip():
            messagebox.showerror(
                "Destino inválido",
                "Selecciona una carpeta de destino.",
                parent=self.root,
            )
            return

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.convert_button.configure(state="disabled")
        self._append_log("Iniciando conversión...")
        worker = threading.Thread(
            target=self._convert,
            args=(source, destination, self.overwrite.get()),
            daemon=True,
        )
        worker.start()

    def _convert(self, source: Path, destination: Path, overwrite: bool) -> None:
        try:
            convert_path(
                source,
                destination,
                overwrite=overwrite,
                on_message=lambda message, is_error: self.messages.put(
                    (message, is_error)
                ),
            )
        except (OSError, ValueError) as error:
            self.messages.put((f"No se pudo completar la conversión: {error}", True))
        finally:
            self.messages.put(None)

    def _read_messages(self) -> None:
        while True:
            try:
                item = self.messages.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self.convert_button.configure(state="normal")
            else:
                self._append_log(*item)
        self.root.after(100, self._read_messages)


def main() -> None:
    root = tk.Tk()
    SimpleConversorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
