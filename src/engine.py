"""Orquestração do pipeline de validação do UniversalDataValidator.

O engine coordena os módulos especializados, mas não implementa regras de
leitura, normalização, validação, diagnóstico ou persistência.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

import numpy as np
import pandas as pd

from .config import AppConfig
from .normalizer import converter_numero, normalizar_chave
from .reader import (
    ExcelReader,
    ReadFile,
    ReaderResult,
    locate_column,
)
from .report import (
    carregar_historico,
    criar_relatorio,
)
from .validator import comparar_fontes


ProgressCallback = Callable[[str], None]


@dataclass
class EngineResult:
    """Resultado estruturado de uma execução completa do pipeline."""

    report: Mapping[str, object]
    source_a_reader: ReaderResult
    source_b_reader: ReaderResult
    source_a: pd.DataFrame
    source_b: pd.DataFrame
    validation: pd.DataFrame

    def __getitem__(self, key: str) -> object:
        """Permite acessar as chaves do resultado de ``criar_relatorio``."""

        return self.report[key]

    def get(self, key: str, default: object = None) -> object:
        """Retorna um item do relatório sem expor detalhes do pipeline."""

        return self.report.get(key, default)

    @property
    def summary(self) -> Optional[pd.DataFrame]:
        """Retorna o resumo gerado pelo módulo de relatório."""

        value = self.report.get("resumo")
        return value if isinstance(value, pd.DataFrame) else None


class ValidationEngine:
    """Coordena leitura, preparação, validação e geração do relatório."""

    def __init__(self, reader: Optional[ExcelReader] = None) -> None:
        """Inicializa o engine com um leitor substituível para testes."""

        self.reader = reader

    def run(
        self,
        config: AppConfig,
        progress: Optional[ProgressCallback] = None,
    ) -> EngineResult:
        """Executa o pipeline completo para a configuração informada.

        Erros são propagados com contexto da etapa e da fonte. Arquivos
        rejeitados pelo reader permanecem disponíveis no resultado; a execução
        falha somente quando uma fonte não possui nenhum arquivo processável.
        """

        self._validate_config(config)
        notify = progress or (lambda _message: None)
        reader = self.reader or ExcelReader(config.accepted_extensions)

        notify("Lendo a Fonte A...")
        reader_a = self._read_source(
            config.source_a_path,
            config,
            config.source_a_name,
            reader,
        )
        source_a = self._prepare_source(
            reader_a,
            config,
            config.source_a_name,
        )
        notify(f"Registros preparados na {config.source_a_name}: {len(source_a)}")

        notify("Lendo a Fonte B...")
        reader_b = self._read_source(
            config.source_b_path,
            config,
            config.source_b_name,
            reader,
        )
        source_b = self._prepare_source(
            reader_b,
            config,
            config.source_b_name,
        )
        notify(f"Registros preparados na {config.source_b_name}: {len(source_b)}")

        notify("Comparando fontes...")
        try:
            validation = comparar_fontes(
                source_a,
                source_b,
                config.tolerance,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"Falha na validação das fontes: {error}") from error

        notify("Carregando histórico...")
        history_path = config.output_path / "historico_ultima_validacao.csv"
        history = carregar_historico(str(history_path))

        notify("Gerando relatório...")
        try:
            report = criar_relatorio(
                validation,
                source_a,
                source_b,
                str(config.output_path),
                config.source_a_name,
                config.source_b_name,
                history,
            )
        except (OSError, TypeError, ValueError) as error:
            raise OSError(f"Falha na geração do relatório: {error}") from error

        notify("Pipeline concluído.")
        return EngineResult(
            report=report,
            source_a_reader=reader_a,
            source_b_reader=reader_b,
            source_a=source_a,
            source_b=source_b,
            validation=validation,
        )

    def _read_source(
        self,
        path: Path,
        config: AppConfig,
        source_name: str,
        reader: ExcelReader,
    ) -> ReaderResult:
        """Lê uma fonte e preserva rejeições registradas pelo reader."""

        if not path.is_dir():
            raise ValueError(
                f"O diretório da {source_name} não existe: {path}"
            )

        try:
            result = reader.process(
                str(path),
                required_columns={
                    "documento": list(config.document_columns),
                },
            )
        except (OSError, TypeError, ValueError) as error:
            raise OSError(
                f"Falha ao ler a {source_name}: {error}"
            ) from error

        if not result.data:
            rejected = len(result.rejected)
            raise ValueError(
                f"Nenhum arquivo processável encontrado na {source_name}. "
                f"Arquivos encontrados: {len(result.files_found)}; "
                f"rejeitados: {rejected}."
            )

        return result

    def _prepare_source(
        self,
        reader_result: ReaderResult,
        config: AppConfig,
        source_name: str,
    ) -> pd.DataFrame:
        """Consolida arquivos lidos em colunas padronizadas para o validator."""

        parts = [
            self._prepare_file(
                read_file,
                config,
                source_name,
            )
            for read_file in reader_result.data
        ]

        if not parts:
            raise ValueError(
                f"A {source_name} não possui dados preparados para validar."
            )

        return pd.concat(parts, ignore_index=True)

    def _prepare_file(
        self,
        read_file: ReadFile,
        config: AppConfig,
        source_name: str,
    ) -> pd.DataFrame:
        """Mapeia e normaliza um arquivo lido sem executar comparação."""

        document_column = locate_column(
            read_file.df,
            list(config.document_columns),
        )
        if document_column is None:
            raise ValueError(
                f"A {source_name} não possui coluna de documento: "
                f"{read_file.path}"
            )

        value_column = locate_column(
            read_file.df,
            list(config.value_columns),
        )
        responsible_column = locate_column(
            read_file.df,
            list(config.responsible_columns),
        )

        result = pd.DataFrame(index=read_file.df.index)
        result["Documento"] = read_file.df[document_column].map(normalizar_chave)
        result["Valor"] = self._convert_values(
            read_file.df[value_column]
            if value_column is not None
            else pd.Series(np.nan, index=read_file.df.index),
            read_file,
            source_name,
        )
        result["Responsavel"] = (
            read_file.df[responsible_column]
            if responsible_column is not None
            else ""
        )
        result["Fonte"] = source_name
        result["Arquivo_Origem"] = Path(read_file.path).name
        result["Caminho_Origem"] = read_file.path
        result["Linha_Origem"] = range(
            read_file.header_row + 2,
            read_file.header_row + 2 + len(read_file.df),
        )
        return result.reset_index(drop=True)

    def _convert_values(
        self,
        values: pd.Series,
        read_file: ReadFile,
        source_name: str,
    ) -> pd.Series:
        """Converte valores usando normalizer e mantém ausentes como NaN."""

        converted = []
        for row_index, value in values.items():
            conversion = converter_numero(value)
            if conversion.is_invalid:
                raise ValueError(
                    f"Valor inválido na {source_name}, arquivo "
                    f"{read_file.path}, linha {row_index}: "
                    f"{conversion.reason}"
                )
            converted.append(
                np.nan
                if conversion.is_missing
                else conversion.value
            )
        return pd.Series(converted, index=values.index, dtype="float64")

    @staticmethod
    def _validate_config(config: AppConfig) -> None:
        """Valida o tipo e os invariantes básicos da configuração."""

        if not isinstance(config, AppConfig):
            raise TypeError("O engine requer uma instância de AppConfig.")

        if not config.accepted_extensions:
            raise ValueError("A configuração não possui extensões aceitas.")


def run_validation(
    config: AppConfig,
    progress: Optional[ProgressCallback] = None,
) -> EngineResult:
    """Atalho para executar o pipeline com um ``ValidationEngine`` padrão."""

    return ValidationEngine().run(config, progress)
