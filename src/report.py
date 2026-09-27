"""Geração e persistência dos relatórios do UniversalDataValidator.

Este módulo recebe DataFrames já preparados e validados. Não lê Excel, não
compara fontes, não normaliza dados e não contém código de interface.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from .diagnostics import gerar_diagnostico


OUTPUT_FILENAME = "relatorio_validacao_final.xlsx"
HISTORY_FILENAME = "historico_ultima_validacao.csv"
VALIDATION_COLUMNS = (
    "Documento",
    "Classificacao",
    "Prioridade",
    "Valor_Fonte_A",
    "Valor_Fonte_B",
)


def _require_columns(
    frame: pd.DataFrame,
    required: tuple[str, ...],
    name: str,
) -> None:
    """Valida que um DataFrame contém as colunas necessárias."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} deve ser um pandas.DataFrame.")

    missing = [column for column in required if column not in frame.columns]
    if missing:
        names = ", ".join(missing)
        raise ValueError(
            f"{name} não possui as colunas obrigatórias: {names}."
        )


def _problematic_tables(validacao: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Cria as tabelas filtradas por tipo de problema."""

    problematicos = validacao.loc[
        validacao["Problematico"].astype(bool)
    ].copy()
    if problematicos.empty:
        problematicos["Diagnostico"] = pd.Series(
            dtype="string",
            index=problematicos.index,
        )
    else:
        problematicos["Diagnostico"] = problematicos.apply(
            gerar_diagnostico,
            axis=1,
        )
    classification = problematicos["Classificacao"].astype("string")

    return {
        "problemas": problematicos,
        "divergencias_valor": problematicos.loc[
            classification.str.contains("Divergencia de Valor", na=False)
        ].copy(),
        "divergencias_resp": problematicos.loc[
            classification.str.contains(
                "Divergencia de Responsavel",
                na=False,
            )
        ].copy(),
        "ausentes_a": problematicos.loc[
            classification.str.contains("Ausente na Fonte A", na=False)
        ].copy(),
        "ausentes_b": problematicos.loc[
            classification.str.contains("Ausente na Fonte B", na=False)
        ].copy(),
        "duplicidades": problematicos.loc[
            classification.str.contains("Duplicidade", na=False)
        ].copy(),
    }


def _build_summary(
    validacao: pd.DataFrame,
    tables: Dict[str, pd.DataFrame],
    nome_a: str,
    nome_b: str,
) -> pd.DataFrame:
    """Monta o painel resumido da validação."""

    total = len(validacao)
    problematicos = len(tables["problemas"])
    resumo = pd.DataFrame(
        [
            ["Documentos analisados", total],
            ["Documentos problematicos", problematicos],
            ["Documentos OK", total - problematicos],
            ["Ausentes na Fonte A", len(tables["ausentes_a"])],
            ["Ausentes na Fonte B", len(tables["ausentes_b"])],
            ["Divergencias de Valor", len(tables["divergencias_valor"])],
            [
                "Divergencias de Responsavel",
                len(tables["divergencias_resp"]),
            ],
            ["Documentos com duplicidade", len(tables["duplicidades"])],
        ],
        columns=["Indicador", "Quantidade"],
    )
    resumo["Data_Execucao"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    resumo["Fonte_A"] = nome_a
    resumo["Fonte_B"] = nome_b
    return resumo


def _build_traceability(
    fonte_a: pd.DataFrame,
    fonte_b: pd.DataFrame,
    problematicos: pd.DataFrame,
) -> pd.DataFrame:
    """Retorna as linhas de origem dos documentos problemáticos."""

    docs = set(problematicos["Documento"])
    rastreabilidade_a = fonte_a.loc[fonte_a["Documento"].isin(docs)].copy()
    rastreabilidade_b = fonte_b.loc[fonte_b["Documento"].isin(docs)].copy()
    return pd.concat(
        [rastreabilidade_a, rastreabilidade_b],
        ignore_index=True,
    )


def _history_frame(validacao: pd.DataFrame) -> pd.DataFrame:
    """Seleciona o estado mínimo persistido entre execuções."""

    return validacao.loc[:, list(VALIDATION_COLUMNS)].copy()


def _empty_history_table() -> pd.DataFrame:
    """Cria uma tabela vazia com as colunas históricas esperadas."""

    return pd.DataFrame(columns=VALIDATION_COLUMNS)


def _build_history_changes(
    atual: pd.DataFrame,
    anterior: Optional[pd.DataFrame],
) -> Dict[str, pd.DataFrame]:
    """Identifica novos, resolvidos e alterados entre duas validações."""

    empty = _empty_history_table()
    if anterior is None or anterior.empty:
        return {
            "novos": atual.copy(),
            "resolvidos": empty,
            "alteracoes": empty,
        }

    _require_columns(anterior, VALIDATION_COLUMNS, "histórico anterior")
    previous = anterior.loc[:, list(VALIDATION_COLUMNS)].copy()
    previous_indexed = previous.set_index("Documento")
    current_indexed = atual.set_index("Documento")

    previous_docs = set(previous_indexed.index)
    current_docs = set(current_indexed.index)
    new_docs = current_docs - previous_docs
    resolved_docs = previous_docs - current_docs
    common_docs = previous_docs & current_docs

    altered_docs = []
    for document in common_docs:
        old = previous_indexed.loc[document]
        new = current_indexed.loc[document]
        if (
            str(old["Classificacao"]) != str(new["Classificacao"])
            or _number_or_zero(old["Valor_Fonte_A"])
            != _number_or_zero(new["Valor_Fonte_A"])
            or _number_or_zero(old["Valor_Fonte_B"])
            != _number_or_zero(new["Valor_Fonte_B"])
        ):
            altered_docs.append(document)

    return {
        "novos": atual.loc[atual["Documento"].isin(new_docs)].copy(),
        "resolvidos": previous.loc[
            previous["Documento"].isin(resolved_docs)
        ].copy(),
        "alteracoes": atual.loc[
            atual["Documento"].isin(altered_docs)
        ].copy(),
    }


def _number_or_zero(value: object) -> float:
    """Converte valores históricos ausentes em zero para comparação legada."""

    return 0.0 if pd.isna(value) else float(value)


def _persist_history(history: pd.DataFrame, path: str) -> None:
    """Persiste o histórico CSV e informa erros de escrita."""

    try:
        history.to_csv(path, index=False, encoding="utf-8-sig")
    except (OSError, ValueError) as error:
        raise OSError(f"Não foi possível salvar o histórico em {path}: {error}") from error


def carregar_historico(path: str) -> Optional[pd.DataFrame]:
    """Carrega o histórico anterior, retornando ``None`` quando não existe.

    Erros de leitura ou estrutura não são ocultados: um histórico presente,
    mas inválido, deve interromper a execução em vez de gerar mudanças
    incorretas.
    """

    if not os.path.exists(path):
        return None

    try:
        history = pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype={"Documento": "string"},
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise OSError(
            f"Não foi possível ler o histórico em {path}: {error}"
        ) from error

    _require_columns(history, VALIDATION_COLUMNS, "histórico")
    return history


def _persist_excel(sheets: Dict[str, pd.DataFrame], path: str) -> None:
    """Persiste todas as abas em um único arquivo Excel."""

    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet_name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=sheet_name, index=False)
    except (OSError, ValueError, ImportError) as error:
        raise OSError(f"Não foi possível salvar o relatório em {path}: {error}") from error


def criar_relatorio(
    validacao: pd.DataFrame,
    fonte_a: pd.DataFrame,
    fonte_b: pd.DataFrame,
    pasta_saida: str = "output",
    nome_a: str = "Fonte A",
    nome_b: str = "Fonte B",
    historico_anterior: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    """Gera e persiste o relatório completo da validação.

    ``validacao`` deve ser o resultado de ``validator.comparar_fontes`` e as
    fontes devem preservar ``Fonte``, ``Arquivo_Origem``, ``Caminho_Origem`` e
    ``Linha_Origem`` quando esses dados estiverem disponíveis.

    O Excel é salvo como ``output/relatorio_validacao_final.xlsx`` por padrão,
    e o estado mínimo usado para comparar execuções como
    ``output/historico_ultima_validacao.csv``.
    """

    _require_columns(
        validacao,
        (
            "Documento",
            "Classificacao",
            "Problematico",
            "Prioridade",
            "Valor_Fonte_A",
            "Valor_Fonte_B",
        ),
        "validação",
    )
    _require_columns(fonte_a, ("Documento",), "Fonte A")
    _require_columns(fonte_b, ("Documento",), "Fonte B")

    os.makedirs(pasta_saida, exist_ok=True)
    tables = _problematic_tables(validacao)
    resumo = _build_summary(validacao, tables, nome_a, nome_b)
    rastreabilidade = _build_traceability(
        fonte_a,
        fonte_b,
        tables["problemas"],
    )
    atual_hist = _history_frame(validacao)
    changes = _build_history_changes(atual_hist, historico_anterior)

    history_path = os.path.join(pasta_saida, HISTORY_FILENAME)
    excel_path = os.path.join(pasta_saida, OUTPUT_FILENAME)
    _persist_history(atual_hist, history_path)

    sheets = {
        "Painel": resumo,
        "Diagnostico": tables["problemas"],
        "Divergencias_Valor": tables["divergencias_valor"],
        "Divergencias_Responsavel": tables["divergencias_resp"],
        "Ausentes_Fonte_A": tables["ausentes_a"],
        "Ausentes_Fonte_B": tables["ausentes_b"],
        "Duplicidades": tables["duplicidades"],
        "Rastreabilidade": rastreabilidade,
        "Base_Fonte_A": fonte_a,
        "Base_Fonte_B": fonte_b,
        "Novos_Problemas": changes["novos"],
        "Resolvidos": changes["resolvidos"],
        "Alteracoes": changes["alteracoes"],
        "Validacao_Completa": validacao,
    }
    _persist_excel(sheets, excel_path)

    return {
        "resumo": resumo,
        "validacao": validacao,
        "problemas": tables["problemas"],
        "divergencias_valor": tables["divergencias_valor"],
        "divergencias_resp": tables["divergencias_resp"],
        "ausentes_a": tables["ausentes_a"],
        "ausentes_b": tables["ausentes_b"],
        "duplicidades": tables["duplicidades"],
        "rastreabilidade": rastreabilidade,
        "novos": changes["novos"],
        "resolvidos": changes["resolvidos"],
        "alteracoes": changes["alteracoes"],
        "arquivo_excel": excel_path,
        "arquivo_historico": history_path,
    }
