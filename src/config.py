"""Configurações centralizadas do UniversalDataValidator.

Este módulo apenas descreve caminhos, nomes e parâmetros configuráveis. Não
contém regras de comparação, leitura de Excel, geração de relatórios ou código
de interface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple


DEFAULT_EXTENSIONS: Tuple[str, ...] = (".xlsx", ".xls", ".xlsm")
DEFAULT_DOCUMENT_COLUMNS: Tuple[str, ...] = (
    "Documento",
    "Doc",
    "Codigo",
    "Código",
    "ID",
    "Document",
)
DEFAULT_VALUE_COLUMNS: Tuple[str, ...] = (
    "Valor",
    "Value",
    "Amount",
    "Total",
    "Valor Total",
)
DEFAULT_RESPONSIBLE_COLUMNS: Tuple[str, ...] = (
    "Gerente",
    "Responsavel",
    "Responsável",
    "Vendedor",
    "Consultor",
    "Manager",
)


def project_root() -> Path:
    """Retorna a raiz do projeto a partir da localização deste módulo."""

    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppConfig:
    """Configuração completa para uma execução do UniversalDataValidator.

    Os diretórios de entrada são relativos à raiz do projeto por padrão:
    ``input/fonte_a`` e ``input/fonte_b``. Os caminhos podem ser substituídos
    por valores absolutos ou relativos ao criar uma configuração personalizada.
    """

    project_dir: Path = field(default_factory=project_root)
    source_a_dir: Path = field(default_factory=lambda: Path("input") / "fonte_a")
    source_b_dir: Path = field(default_factory=lambda: Path("input") / "fonte_b")
    output_dir: Path = field(default_factory=lambda: Path("output"))
    source_a_name: str = "Fonte A"
    source_b_name: str = "Fonte B"
    tolerance: float = 0.01
    accepted_extensions: Tuple[str, ...] = DEFAULT_EXTENSIONS
    document_columns: Tuple[str, ...] = DEFAULT_DOCUMENT_COLUMNS
    value_columns: Tuple[str, ...] = DEFAULT_VALUE_COLUMNS
    responsible_columns: Tuple[str, ...] = DEFAULT_RESPONSIBLE_COLUMNS

    def __post_init__(self) -> None:
        """Valida invariantes estruturais da configuração."""

        if not math.isfinite(self.tolerance):
            raise ValueError("A tolerância deve ser finita.")

        if self.tolerance < 0:
            raise ValueError("A tolerância não pode ser negativa.")

        if not self.source_a_name.strip():
            raise ValueError("O nome da Fonte A não pode ser vazio.")

        if not self.source_b_name.strip():
            raise ValueError("O nome da Fonte B não pode ser vazio.")

        if not self.accepted_extensions:
            raise ValueError("É necessário informar ao menos uma extensão.")

        normalized_extensions = tuple(
            extension.lower()
            if extension.startswith(".")
            else f".{extension.lower()}"
            for extension in self.accepted_extensions
        )
        object.__setattr__(
            self,
            "accepted_extensions",
            normalized_extensions,
        )

    @property
    def source_a_path(self) -> Path:
        """Retorna o diretório absoluto configurado para a Fonte A."""

        return self._resolve(self.source_a_dir)

    @property
    def source_b_path(self) -> Path:
        """Retorna o diretório absoluto configurado para a Fonte B."""

        return self._resolve(self.source_b_dir)

    @property
    def output_path(self) -> Path:
        """Retorna o diretório absoluto configurado para os resultados."""

        return self._resolve(self.output_dir)

    def _resolve(self, path: Path) -> Path:
        """Resolve um caminho relativo tomando project_dir como base."""

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_dir / candidate


def default_config() -> AppConfig:
    """Cria a configuração padrão do projeto."""

    return AppConfig()
