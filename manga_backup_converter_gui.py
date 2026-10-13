import os
import sys
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Ensure proto and current folder are in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
proto_dir = os.path.join(current_dir, 'proto')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

from manga_converter_engine import convert_any, detect_backup_format, TARGET_FORMATS

FORMAT_OPTIONS = [
    ("Mihon (.tachibk)", "mihon", ".tachibk"),
    ("Tachimanga (.tmb)", "tachimanga", ".tmb"),
    ("Mangayomi (.backup)", "mangayomi", ".backup"),
    ("Aidoku (.aib)", "aidoku", ".aib"),
    ("Paperback (.pas4)", "paperback", ".pas4"),
    ("Tachiyomi (.proto.gz)", "tachi", ".proto.gz"),
    ("TachiyomiSY (.tachibk)", "sy", ".tachibk"),
    ("TachiyomiJ2K (.tachibk)", "j2k", ".tachibk"),
    ("Yokai (.tachibk)", "yokai", ".tachibk"),
    ("Neko (.tachibk)", "neko", ".tachibk"),
]

FORMAT_DISPLAY_NAMES = {
    'tachimanga': 'Tachimanga (.tmb)',
    'mihon': 'Mihon (.tachibk)',
    'tachiyomi': 'Tachiyomi (.proto.gz)',
    'mangayomi': 'Mangayomi (.backup)',
    'aidoku': 'Aidoku (.aib)',
    'paperback': 'Paperback (.pas4)',
    'unknown': 'Formato desconhecido'
}

class MangaConverterApp:
    def __init__(self, root, initial_file=None):
        self.root = root
        self.root.title("Manga Backup Converter - Todos os Formatos")
        self.root.geometry("740x650")
        self.root.minsize(680, 580)

        # Apply dark modern color palette
        self.bg_color = "#0f172a"        # Slate 900
        self.card_bg = "#1e293b"         # Slate 800
        self.input_bg = "#334155"        # Slate 700
        self.accent_color = "#38bdf8"     # Sky 400
        self.accent_hover = "#0284c7"     # Sky 600
        self.text_main = "#f8fafc"        # Slate 50
        self.text_dim = "#94a3b8"         # Slate 400
        self.success_color = "#22c55e"    # Green 500
        self.danger_color = "#ef4444"     # Red 500
        self.console_bg = "#090d16"

        self.root.configure(bg=self.bg_color)

        self.input_file_var = tk.StringVar()
        self.output_file_var = tk.StringVar()
        self.target_format_var = tk.StringVar(value=FORMAT_OPTIONS[0][0])
        self.status_var = tk.StringVar(value="Pronto para converter")
        self.is_converting = False
        self.last_converted_path = None

        self._setup_styles()
        self._create_widgets()

        if HAS_WINDND:
            windnd.hook_dropfiles(self.root, func=self._on_files_dropped)

        if initial_file and os.path.exists(initial_file):
            self.set_input_file(initial_file)

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.style.configure(".", background=self.bg_color, foreground=self.text_main, font=("Segoe UI", 10))
        self.style.configure("Card.TFrame", background=self.card_bg, relief="flat")
        self.style.configure("Header.TLabel", background=self.bg_color, foreground=self.text_main, font=("Segoe UI", 16, "bold"))
        self.style.configure("SubHeader.TLabel", background=self.bg_color, foreground=self.text_dim, font=("Segoe UI", 10))
        self.style.configure("CardHeader.TLabel", background=self.card_bg, foreground=self.accent_color, font=("Segoe UI", 11, "bold"))
        self.style.configure("CardLabel.TLabel", background=self.card_bg, foreground=self.text_main, font=("Segoe UI", 10))
        self.style.configure("DimLabel.TLabel", background=self.card_bg, foreground=self.text_dim, font=("Segoe UI", 9))
        self.style.configure("Status.TLabel", background=self.bg_color, foreground=self.accent_color, font=("Segoe UI", 10, "italic"))

        # Combobox style
        self.style.configure("TCombobox", fieldbackground=self.input_bg, background=self.input_bg, foreground=self.text_main, arrowcolor=self.text_main)
        self.style.map("TCombobox", fieldbackground=[('readonly', self.input_bg)], foreground=[('readonly', self.text_main)])

    def _create_widgets(self):
        # Header Container
        header_frame = tk.Frame(self.root, bg=self.bg_color, padx=20, pady=12)
        header_frame.pack(fill="x")

        title_lbl = ttk.Label(header_frame, text="Manga Backup Converter", style="Header.TLabel")
        title_lbl.pack(anchor="w")

        subtitle_lbl = ttk.Label(
            header_frame,
            text="Converta backups entre Mihon, Tachimanga, Mangayomi, Aidoku, Paperback, Tachiyomi e forks!",
            style="SubHeader.TLabel"
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Main Scrollable / Body Container
        body_frame = tk.Frame(self.root, bg=self.bg_color, padx=20)
        body_frame.pack(fill="both", expand=True)

        # 1. Step 1: Input File Card
        input_card = tk.Frame(body_frame, bg=self.card_bg, padx=16, pady=12, relief="ridge", bd=1)
        input_card.pack(fill="x", pady=5)

        step1_title = ttk.Label(input_card, text="1. Selecione o arquivo de backup", style="CardHeader.TLabel")
        step1_title.pack(anchor="w", pady=(0, 6))

        # Drop Zone Label
        self.drop_zone = tk.Label(
            input_card,
            text="📥 Arraste e solte o arquivo aqui\nou clique em 'Procurar Arquivo...'",
            bg=self.input_bg,
            fg=self.text_main,
            font=("Segoe UI", 10),
            padx=12,
            pady=10,
            relief="groove",
            cursor="hand2"
        )
        self.drop_zone.pack(fill="x", pady=(0, 6))
        self.drop_zone.bind("<Button-1>", lambda e: self.browse_input_file())

        input_row = tk.Frame(input_card, bg=self.card_bg)
        input_row.pack(fill="x")

        self.input_entry = tk.Entry(
            input_row,
            textvariable=self.input_file_var,
            bg=self.input_bg,
            fg=self.text_main,
            insertbackground="white",
            font=("Segoe UI", 10),
            relief="flat",
            bd=5
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = tk.Button(
            input_row,
            text="📁 Procurar Arquivo...",
            command=self.browse_input_file,
            bg=self.accent_hover,
            fg="white",
            activebackground=self.accent_color,
            activeforeground="black",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2"
        )
        browse_btn.pack(side="right")

        self.file_info_lbl = ttk.Label(input_card, text="Nenhum arquivo selecionado", style="DimLabel.TLabel")
        self.file_info_lbl.pack(anchor="w", pady=(4, 0))

        # 2. Step 2: Format & Output Card
        format_card = tk.Frame(body_frame, bg=self.card_bg, padx=16, pady=12, relief="ridge", bd=1)
        format_card.pack(fill="x", pady=5)

        step2_title = ttk.Label(format_card, text="2. Escolha o formato de destino", style="CardHeader.TLabel")
        step2_title.pack(anchor="w", pady=(0, 6))

        format_row = tk.Frame(format_card, bg=self.card_bg)
        format_row.pack(fill="x", pady=(0, 8))

        format_lbl = ttk.Label(format_row, text="Formato de saída:", style="CardLabel.TLabel")
        format_lbl.pack(side="left", padx=(0, 10))

        self.format_combo = ttk.Combobox(
            format_row,
            textvariable=self.target_format_var,
            values=[opt[0] for opt in FORMAT_OPTIONS],
            state="readonly",
            font=("Segoe UI", 10),
            width=36
        )
        self.format_combo.current(0)
        self.format_combo.pack(side="left")
        self.format_combo.bind("<<ComboboxSelected>>", self._on_format_changed)

        output_row = tk.Frame(format_card, bg=self.card_bg)
        output_row.pack(fill="x", pady=(4, 0))

        output_lbl = ttk.Label(output_row, text="Salvar como:", style="CardLabel.TLabel")
        output_lbl.pack(side="left", padx=(0, 24))

        self.output_entry = tk.Entry(
            output_row,
            textvariable=self.output_file_var,
            bg=self.input_bg,
            fg=self.text_main,
            insertbackground="white",
            font=("Segoe UI", 10),
            relief="flat",
            bd=5
        )
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        save_btn = tk.Button(
            output_row,
            text="Alterar...",
            command=self.browse_output_file,
            bg="#475569",
            fg="white",
            activebackground="#64748b",
            font=("Segoe UI", 9),
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2"
        )
        save_btn.pack(side="right")

        # 3. Step 3: Conversion Actions & Logs
        action_card = tk.Frame(body_frame, bg=self.card_bg, padx=16, pady=10, relief="ridge", bd=1)
        action_card.pack(fill="both", expand=True, pady=5)

        btn_row = tk.Frame(action_card, bg=self.card_bg)
        btn_row.pack(fill="x", pady=(0, 8))

        self.convert_btn = tk.Button(
            btn_row,
            text="⚡ CONVERTER ARQUIVO",
            command=self.start_conversion,
            bg=self.accent_color,
            fg="#0f172a",
            activebackground=self.accent_hover,
            activeforeground="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            padx=20,
            pady=7,
            cursor="hand2"
        )
        self.convert_btn.pack(side="left")

        self.open_folder_btn = tk.Button(
            btn_row,
            text="📂 Abrir Pasta de Destino",
            command=self.open_destination_folder,
            bg="#334155",
            fg="white",
            activebackground="#475569",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=14,
            pady=7,
            state="disabled",
            cursor="hand2"
        )
        self.open_folder_btn.pack(side="left", padx=(10, 0))

        self.status_lbl = ttk.Label(btn_row, textvariable=self.status_var, style="Status.TLabel")
        self.status_lbl.pack(side="right", padx=(10, 0))

        # Log Text Box
        log_frame = tk.Frame(action_card, bg=self.console_bg)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            bg=self.console_bg,
            fg="#cbd5e1",
            insertbackground="white",
            font=("Consolas", 9),
            relief="flat",
            bd=6,
            height=7
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview, bg=self.console_bg)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, message):
        """Append log message thread-safely."""
        def _append():
            self.log_text.insert("end", f"{message}\n")
            self.log_text.see("end")
        self.root.after(0, _append)

    def _on_files_dropped(self, files):
        if files and len(files) > 0:
            file_path = files[0]
            if isinstance(file_path, bytes):
                file_path = file_path.decode('utf-8', errors='ignore')
            self.set_input_file(file_path)

    def browse_input_file(self):
        filepath = filedialog.askopenfilename(
            title="Selecione o arquivo de backup",
            filetypes=[
                ("Todos os Backups Suportados", "*.tmb;*.tachibk;*.proto.gz;*.backup;*.aib;*.pas4"),
                ("Tachimanga (*.tmb)", "*.tmb"),
                ("Mihon / Tachiyomi (*.tachibk;*.proto.gz)", "*.tachibk;*.proto.gz"),
                ("Mangayomi (*.backup)", "*.backup"),
                ("Aidoku (*.aib)", "*.aib"),
                ("Paperback (*.pas4)", "*.pas4"),
                ("Todos os arquivos (*.*)", "*.*")
            ]
        )
        if filepath:
            self.set_input_file(filepath)

    def browse_output_file(self):
        curr_out = self.output_file_var.get()
        init_dir = os.path.dirname(curr_out) if curr_out else os.path.dirname(self.input_file_var.get() or "")
        init_file = os.path.basename(curr_out) if curr_out else ""

        selected_fmt_tuple = self._get_selected_format_tuple()
        ext = selected_fmt_tuple[2]
        desc = selected_fmt_tuple[0]

        filepath = filedialog.asksaveasfilename(
            title="Salvar arquivo convertido como",
            initialdir=init_dir or os.getcwd(),
            initialfile=init_file,
            defaultextension=ext,
            filetypes=[(desc, f"*{ext}"), ("Todos os arquivos", "*.*")]
        )
        if filepath:
            self.output_file_var.set(filepath)

    def set_input_file(self, filepath):
        if not os.path.exists(filepath):
            return
        filepath = os.path.abspath(filepath)
        self.input_file_var.set(filepath)

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        fmt = detect_backup_format(filepath)
        fmt_display = FORMAT_DISPLAY_NAMES.get(fmt, fmt.upper())

        info_str = f"Formato de entrada: {fmt_display} | Tamanho: {size_mb:.2f} MB"
        self.file_info_lbl.config(text=info_str)
        self.drop_zone.config(text=f"📄 {os.path.basename(filepath)} ({size_mb:.2f} MB)")

        # Auto select opposite format if possible
        if fmt == 'tachimanga':
            self.format_combo.current(0)  # Mihon
        elif fmt in ('mihon', 'tachiyomi'):
            self.format_combo.current(1)  # Tachimanga
        elif fmt == 'mangayomi':
            self.format_combo.current(0)  # Mihon
        elif fmt == 'aidoku':
            self.format_combo.current(0)  # Mihon
        elif fmt == 'paperback':
            self.format_combo.current(0)  # Mihon

        self._update_default_output_path()

    def _on_format_changed(self, event=None):
        self._update_default_output_path()

    def _get_selected_format_tuple(self):
        selected_text = self.target_format_var.get()
        for opt in FORMAT_OPTIONS:
            if opt[0] == selected_text:
                return opt
        return FORMAT_OPTIONS[0]

    def _update_default_output_path(self):
        inp = self.input_file_var.get()
        if not inp:
            return

        base, _ = os.path.splitext(inp)
        selected_opt = self._get_selected_format_tuple()
        ext = selected_opt[2]

        out = f"{base}_converted{ext}"
        self.output_file_var.set(out)

    def start_conversion(self):
        if self.is_converting:
            return

        input_path = self.input_file_var.get().strip()
        output_path = self.output_file_var.get().strip()
        selected_opt = self._get_selected_format_tuple()
        target_fmt_key = selected_opt[1]

        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Erro", "Por favor, selecione um arquivo de entrada válido.")
            return

        if not output_path:
            messagebox.showerror("Erro", "Por favor, selecione o caminho de saída.")
            return

        self.is_converting = True
        self.convert_btn.config(state="disabled", text="Convertendo...")
        self.open_folder_btn.config(state="disabled")
        self.status_var.set("Convertendo backup...")
        self.log_text.delete("1.0", "end")
        self.log(f"--- Iniciando Conversão ---")
        self.log(f"Origem: {input_path}")
        self.log(f"Destino: {output_path}")
        self.log(f"Formato desejado: {selected_opt[0]}")

        thread = threading.Thread(
            target=self._run_conversion,
            args=(input_path, output_path, target_fmt_key),
            daemon=True
        )
        thread.start()

    def _run_conversion(self, input_path, output_path, target_fmt_key):
        try:
            convert_any(input_path, output_path, target_fmt_key, log_cb=self.log)
            self.last_converted_path = output_path
            self.root.after(0, self._on_conversion_success)
        except Exception as e:
            self.root.after(0, lambda: self._on_conversion_error(str(e)))

    def _on_conversion_success(self):
        self.is_converting = False
        self.convert_btn.config(state="normal", text="⚡ CONVERTER ARQUIVO")
        self.open_folder_btn.config(state="normal")
        self.status_var.set("✅ Conversão concluída com sucesso!")
        self.log("\n✅ Conversão finalizada com sucesso!")
        messagebox.showinfo("Sucesso", f"Backup convertido com sucesso!\nSalvo em:\n{self.last_converted_path}")

    def _on_conversion_error(self, err_msg):
        self.is_converting = False
        self.convert_btn.config(state="normal", text="⚡ CONVERTER ARQUIVO")
        self.status_var.set("❌ Erro durante a conversão")
        self.log(f"\n❌ ERRO: {err_msg}")
        messagebox.showerror("Erro de Conversão", f"Ocorreu um erro ao converter o backup:\n\n{err_msg}")

    def open_destination_folder(self):
        path = self.last_converted_path or self.output_file_var.get()
        if path and os.path.exists(path):
            folder = os.path.dirname(os.path.abspath(path))
            if sys.platform == 'win32':
                subprocess.Popen(f'explorer /select,"{os.path.abspath(path)}"')
            else:
                subprocess.Popen(['xdg-open', folder])
        elif path:
            folder = os.path.dirname(os.path.abspath(path))
            if os.path.exists(folder):
                if sys.platform == 'win32':
                    os.startfile(folder)
                else:
                    subprocess.Popen(['xdg-open', folder])

def launch_gui(initial_file=None):
    root = tk.Tk()
    app = MangaConverterApp(root, initial_file=initial_file)
    root.mainloop()

if __name__ == '__main__':
    arg_file = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else None
    launch_gui(arg_file)
