"""Interface Tkinter do UniversalDataValidator V14.

Este módulo controla somente a interação com o usuário. O processamento é
delegado ao engine e executado em uma thread de trabalho.
"""

from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from .config import AppConfig, default_config
from .engine import EngineResult, run_validation


ValidationRunner = Callable[
    [AppConfig, Callable[[str], None]],
    EngineResult,
]


class ValidatorApp:
    """Janela principal para configurar e iniciar uma validação."""

    def __init__(
        self,
        root: tk.Tk,
        runner: ValidationRunner = run_validation,
        config: Optional[AppConfig] = None,
    ) -> None:
        self.root = root
        self.runner = runner
        self.config = config or default_config()
        self.result: Optional[EngineResult] = None
        self._worker: Optional[threading.Thread] = None
        self._build_window()

    def _build_window(self) -> None:
        """Cria a janela, campos, controles e área de status."""

        self.root.title("Universal Data Validator V14")
        self.root.geometry("980x760")
        self.root.minsize(820, 620)

        ttk.Label(
            self.root,
            text="UNIVERSAL DATA VALIDATOR",
            font=("Arial", 20, "bold"),
        ).pack(pady=(15, 2))
        ttk.Label(
            self.root,
            text="Validação profissional de fontes de dados",
        ).pack(pady=(0, 12))

        fields = ttk.Frame(self.root, padding=(24, 8))
        fields.pack(fill="x")

        self.project_var = self._add_path_field(
            fields, 0, "Pasta do projeto:", self.config.project_dir
        )
        self.source_a_var = self._add_path_field(
            fields, 1, "Pasta da Fonte A:", self.config.source_a_path
        )
        self.source_b_var = self._add_path_field(
            fields, 2, "Pasta da Fonte B:", self.config.source_b_path
        )
        self.source_a_name_var = self._add_text_field(
            fields, 3, "Nome da Fonte A:", self.config.source_a_name
        )
        self.source_b_name_var = self._add_text_field(
            fields, 4, "Nome da Fonte B:", self.config.source_b_name
        )

        ttk.Label(fields, text="Tolerância:").grid(
            row=5, column=0, sticky="w", pady=5
        )
        self.tolerance_var = tk.StringVar(value=str(self.config.tolerance))
        ttk.Entry(fields, textvariable=self.tolerance_var, width=18).grid(
            row=5, column=1, sticky="w", padx=10, pady=5
        )

        controls = ttk.Frame(self.root)
        controls.pack(pady=10)
        self.run_button = ttk.Button(
            controls,
            text="EXECUTAR VALIDAÇÃO",
            command=self.start_validation,
        )
        self.run_button.pack(side="left", padx=5)
        self.view_button = ttk.Button(
            controls,
            text="VISUALIZAR RESULTADO",
            command=self.show_result,
            state="disabled",
        )
        self.view_button.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(
            self.root, mode="indeterminate", length=520
        )
        self.progress.pack(pady=(0, 8))

        ttk.Label(
            self.root,
            text="Status da execução:",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", padx=24)
        self.log = tk.Text(
            self.root, height=18, width=110, state="disabled"
        )
        self.log.pack(padx=24, pady=8, fill="both", expand=True)

    def _add_path_field(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        value: Path,
    ) -> tk.StringVar:
        """Adiciona um campo de diretório com seletor."""

        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", pady=5
        )
        variable = tk.StringVar(value=str(value))
        ttk.Entry(parent, textvariable=variable, width=78).grid(
            row=row, column=1, padx=10, pady=5, sticky="ew"
        )
        parent.columnconfigure(1, weight=1)
        ttk.Button(
            parent,
            text="Selecionar",
            command=lambda: self._choose_directory(variable, label),
        ).grid(row=row, column=2, pady=5)
        return variable

    def _add_text_field(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        value: str,
    ) -> tk.StringVar:
        """Adiciona um campo textual de configuração."""

        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", pady=5
        )
        variable = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=variable, width=42).grid(
            row=row, column=1, padx=10, pady=5, sticky="w"
        )
        return variable

    def _choose_directory(
        self,
        variable: tk.StringVar,
        label: str,
    ) -> None:
        """Abre o seletor de diretórios e atualiza o campo."""

        selected = filedialog.askdirectory(
            title=f"Selecione {label}"
        )
        if selected:
            variable.set(selected)

    def _write_log(self, message: str) -> None:
        """Atualiza o log; deve ser chamado somente pela thread Tk."""

        self.log.configure(state="normal")
        self.log.insert(tk.END, f"{message}\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def _schedule_log(self, message: str) -> None:
        """Agenda uma atualização de log segura para a thread Tk."""

        self.root.after(0, self._write_log, message)

    def _clear_log(self) -> None:
        """Limpa o log atual."""

        self.log.configure(state="normal")
        self.log.delete("1.0", tk.END)
        self.log.configure(state="disabled")

    def _read_config(self) -> AppConfig:
        """Converte os campos da tela em um AppConfig validado."""

        try:
            tolerance = float(
                self.tolerance_var.get().strip().replace(",", ".")
            )
        except ValueError as error:
            raise ValueError(
                "A tolerância deve ser um número válido."
            ) from error

        project = Path(self.project_var.get().strip())
        source_a = Path(self.source_a_var.get().strip())
        source_b = Path(self.source_b_var.get().strip())
        name_a = self.source_a_name_var.get().strip()
        name_b = self.source_b_name_var.get().strip()

        if not project.is_dir():
            raise ValueError("A pasta do projeto não existe.")
        if not source_a.is_dir():
            raise ValueError("A pasta da Fonte A não existe.")
        if not source_b.is_dir():
            raise ValueError("A pasta da Fonte B não existe.")
        if not name_a or not name_b:
            raise ValueError("Os nomes das fontes não podem ser vazios.")

        return replace(
            self.config,
            project_dir=project,
            source_a_dir=source_a,
            source_b_dir=source_b,
            source_a_name=name_a,
            source_b_name=name_b,
            tolerance=tolerance,
        )

    def start_validation(self) -> None:
        """Valida os campos e inicia o engine sem bloquear a janela."""

        if self._worker is not None and self._worker.is_alive():
            return

        try:
            config = self._read_config()
        except (TypeError, ValueError) as error:
            self._write_log(f"ERRO DE CONFIGURAÇÃO: {error}")
            messagebox.showerror("Configuração inválida", str(error))
            return

        self._clear_log()
        self.result = None
        self.view_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self.progress.start(10)
        self._write_log("Iniciando validação...")
        self._worker = threading.Thread(
            target=self._run_engine,
            args=(config,),
            daemon=True,
        )
        self._worker.start()

    def _run_engine(self, config: AppConfig) -> None:
        """Executa o engine na thread de trabalho."""

        try:
            result = self.runner(config, self._schedule_log)
        except Exception as error:
            self.root.after(0, self._finish_with_error, error)
        else:
            self.root.after(0, self._finish_success, result)

    def _finish_success(self, result: EngineResult) -> None:
        """Atualiza a interface após uma execução bem-sucedida."""

        self.result = result
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.view_button.configure(state="normal")
        self._write_log("Validação concluída.")
        report_path = result.get("arquivo_excel")
        if report_path:
            self._write_log(f"Relatório: {report_path}")

        summary = result.summary
        if summary is not None:
            self._write_summary_log(summary)

        messagebox.showinfo(
            "Validação concluída",
            "A validação foi concluída com sucesso.",
        )

    def _finish_with_error(self, error: Exception) -> None:
        """Atualiza a interface e informa uma falha do engine."""

        self.progress.stop()
        self.run_button.configure(state="normal")
        self._write_log(f"ERRO: {error}")
        messagebox.showerror("Erro na validação", str(error))

    def _write_summary_log(self, summary: object) -> None:
        """Exibe no log as métricas retornadas pelo report."""

        self._write_log("Resumo da validação:")
        if not hasattr(summary, "itertuples"):
            return
        for row in summary.itertuples(index=False):
            self._write_log(f"{row[0]}: {row[1]}")

    def show_result(self) -> None:
        """Abre o resumo e os DataFrames retornados pelo engine."""

        if self.result is None:
            messagebox.showwarning(
                "Resultado indisponível",
                "Execute uma validação antes de visualizar o resultado.",
            )
            return

        window = tk.Toplevel(self.root)
        window.title("Resultado da validação")
        window.geometry("1100x650")
        notebook = ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._add_dataframe_tab(notebook, "Resumo", self.result.summary)
        for key, title in (
            ("problemas", "Diagnostico"),
            ("divergencias_valor", "Divergencias_Valor"),
            ("divergencias_resp", "Divergencias_Responsavel"),
            ("ausentes_a", "Ausentes_Fonte_A"),
            ("ausentes_b", "Ausentes_Fonte_B"),
            ("duplicidades", "Duplicidades"),
            ("rastreabilidade", "Rastreabilidade"),
            ("novos", "Novos_Problemas"),
            ("resolvidos", "Resolvidos"),
            ("alteracoes", "Alteracoes"),
        ):
            self._add_dataframe_tab(
                notebook,
                title,
                self.result.get(key),
            )

    def _add_dataframe_tab(
        self,
        notebook: ttk.Notebook,
        title: str,
        frame: object,
    ) -> None:
        """Exibe um DataFrame retornado sem recriá-lo na GUI."""

        tab = ttk.Frame(notebook)
        notebook.add(tab, text=title)
        if frame is None or not hasattr(frame, "columns"):
            ttk.Label(tab, text="Nenhum dado disponível.").pack(pady=20)
            return

        columns = [str(column) for column in frame.columns]
        tree = ttk.Treeview(tab, columns=columns, show="headings")
        vertical = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(
            tab, orient="horizontal", command=tree.xview
        )
        tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)

        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=145, anchor="w")
        for row in frame.itertuples(index=False, name=None):
            tree.insert("", tk.END, values=tuple(str(value) for value in row))


def create_app(
    runner: ValidationRunner = run_validation,
    config: Optional[AppConfig] = None,
) -> ValidatorApp:
    """Cria a aplicação sem iniciar o event loop."""

    root = tk.Tk()
    return ValidatorApp(root, runner, config)


def launch(
    runner: ValidationRunner = run_validation,
    config: Optional[AppConfig] = None,
) -> None:
    """Cria a janela e inicia o event loop Tkinter."""

    app = create_app(runner, config)
    app.root.mainloop()
