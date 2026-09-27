"""Validação e comparação entre duas fontes preparadas.

Este módulo trabalha exclusivamente sobre DataFrames. Não lê arquivos, não
gera planilhas e não contém código de interface.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Dict, Iterable, List, Set

import numpy as np
import pandas as pd

from .normalizer import converter_numero, normalizar_texto


REQUIRED_COLUMNS = {"Documento", "Valor", "Responsavel"}
TOTAL_MARKERS = ("total", "subtotal", "soma")


def _validate_tolerance(tolerancia: object) -> float:
    """Valida e retorna a tolerância como float."""

    if isinstance(tolerancia, bool) or not isinstance(tolerancia, Real):
        raise ValueError("A tolerância deve ser um número real não negativo.")

    tolerancia_float = float(tolerancia)
    if not math.isfinite(tolerancia_float):
        raise ValueError("A tolerância deve ser finita; NaN e infinito não são permitidos.")
    if tolerancia_float < 0:
        raise ValueError("A tolerância não pode ser negativa.")

    return tolerancia_float


def _validate_columns(frame: pd.DataFrame, fonte: str) -> None:
    """Garante que as colunas necessárias estejam disponíveis."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"A {fonte} deve ser um pandas.DataFrame.")

    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        nomes = ", ".join(sorted(missing))
        raise ValueError(
            f"A {fonte} não possui as colunas obrigatórias: {nomes}. "
            "A validação foi interrompida para evitar resultado falso."
        )


def _without_total_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove documentos vazios e linhas de total/subtotal/soma."""

    result = frame.copy()
    documentos = result["Documento"].astype("string").str.strip()
    valid_document = documentos.notna() & documentos.ne("")
    is_total = documentos.str.lower().str.contains(
        "|".join(TOTAL_MARKERS),
        regex=True,
        na=False,
    )

    result = result.loc[valid_document & ~is_total].copy()
    result["Documento"] = documentos.loc[result.index]
    return result


def _validate_values(frame: pd.DataFrame, fonte: str) -> pd.DataFrame:
    """Converte valores monetários e rejeita valores não interpretáveis."""

    result = frame.copy()
    converted: List[object] = []
    invalid: List[str] = []

    for index, value in result["Valor"].items():
        conversion = converter_numero(value)
        if conversion.is_invalid:
            documento = result.at[index, "Documento"]
            invalid.append(
                f"documento {documento!r}, linha {index}: {conversion.reason}"
            )
            converted.append(np.nan)
        elif conversion.is_missing:
            converted.append(np.nan)
        else:
            converted.append(conversion.value)

    if invalid:
        details = "; ".join(invalid[:3])
        suffix = " ..." if len(invalid) > 3 else ""
        raise ValueError(
            f"A {fonte} contém valor(es) inválido(s) ou não interpretável(is): "
            f"{details}{suffix}"
        )

    result["Valor"] = converted
    return result


def _group_counts(frame: pd.DataFrame) -> pd.Series:
    """Calcula a quantidade de ocorrências por documento."""

    return frame.groupby("Documento").size()


def _group_values(frame: pd.DataFrame) -> pd.Series:
    """Calcula o valor agregado por documento, preservando ausência como NaN."""

    return frame.groupby("Documento")["Valor"].sum(min_count=1)


def _group_responsibles(frame: pd.DataFrame) -> pd.Series:
    """Obtém o primeiro responsável informado para cada documento."""

    return frame.groupby("Documento")["Responsavel"].first()


def _difference(value_a: object, value_b: object) -> float:
    """Calcula diferença quando os dois valores estão disponíveis."""

    if pd.notna(value_a) and pd.notna(value_b):
        return float(value_a - value_b)
    return np.nan


def _append_value_problem(
    problems: List[str],
    value_a: object,
    value_b: object,
    difference: float,
    tolerance: float,
) -> None:
    """Adiciona divergência de valor quando excede a tolerância."""

    if pd.notna(value_a) and pd.notna(value_b) and abs(difference) > tolerance:
        problems.append("Divergencia de Valor")


def _priority(problems: Iterable[str]) -> str:
    """Classifica a prioridade usando a precedência validada no V13."""

    problems = list(problems)
    if any("Ausente" in problem for problem in problems):
        return "ALTA"
    if "Divergencia de Valor" in problems:
        return "ALTA"
    if any("Duplicidade" in problem for problem in problems):
        return "MEDIA"
    return "BAIXA"


def _build_record(
    documento: object,
    counts_a: pd.Series,
    counts_b: pd.Series,
    values_a: pd.Series,
    values_b: pd.Series,
    responsible_a: pd.Series,
    responsible_b: pd.Series,
    tolerance: float,
) -> Dict[str, object]:
    """Monta o resultado de validação de um documento."""

    exists_a = documento in counts_a.index
    exists_b = documento in counts_b.index
    value_a = values_a.get(documento, np.nan)
    value_b = values_b.get(documento, np.nan)
    resp_a = responsible_a.get(documento, "")
    resp_b = responsible_b.get(documento, "")
    difference = _difference(value_a, value_b)
    problems: List[str] = []

    if not exists_a:
        problems.append("Ausente na Fonte A")
    if not exists_b:
        problems.append("Ausente na Fonte B")

    if exists_a and exists_b:
        _append_value_problem(
            problems,
            value_a,
            value_b,
            difference,
            tolerance,
        )

        if (
            normalizar_texto(resp_a) != normalizar_texto(resp_b)
            and (resp_a != "" or resp_b != "")
        ):
            problems.append("Divergencia de Responsavel")

    if counts_a.get(documento, 0) > 1:
        problems.append("Duplicidade na Fonte A")
    if counts_b.get(documento, 0) > 1:
        problems.append("Duplicidade na Fonte B")

    classification = "OK" if not problems else " | ".join(problems)

    return {
        "Documento": documento,
        "Valor_Fonte_A": value_a,
        "Valor_Fonte_B": value_b,
        "Diferenca_Valor": difference,
        "Responsavel_Fonte_A": resp_a,
        "Responsavel_Fonte_B": resp_b,
        "Qtd_Fonte_A": int(counts_a.get(documento, 0)),
        "Qtd_Fonte_B": int(counts_b.get(documento, 0)),
        "Classificacao": classification,
        "Prioridade": "Sem problema" if not problems else _priority(problems),
        "Problematico": bool(problems),
    }


def comparar_fontes(
    fonte_a: pd.DataFrame,
    fonte_b: pd.DataFrame,
    tolerancia: float = 0.01,
) -> pd.DataFrame:
    """Compara duas fontes preparadas e retorna um DataFrame de validação.

    As fontes devem conter ``Documento``, ``Valor`` e ``Responsavel``. Linhas
    sem documento e linhas de total/subtotal/soma são desconsideradas. Cada
    documento é agregado por fonte: duplicidade é determinada pela quantidade
    de ocorrências, enquanto divergência de valor compara os totais agregados.

    Erros de esquema, tolerância ou valores monetários inválidos interrompem a
    operação com ``ValueError`` explícito; nunca são convertidos em um resultado
    aparentemente correto.
    """

    tolerance = _validate_tolerance(tolerancia)
    _validate_columns(fonte_a, "Fonte A")
    _validate_columns(fonte_b, "Fonte B")

    a = _validate_values(_without_total_rows(fonte_a), "Fonte A")
    b = _validate_values(_without_total_rows(fonte_b), "Fonte B")

    counts_a = _group_counts(a)
    counts_b = _group_counts(b)
    values_a = _group_values(a)
    values_b = _group_values(b)
    responsible_a = _group_responsibles(a)
    responsible_b = _group_responsibles(b)

    documents: Set[object] = set(counts_a.index) | set(counts_b.index)
    records = [
        _build_record(
            documento,
            counts_a,
            counts_b,
            values_a,
            values_b,
            responsible_a,
            responsible_b,
            tolerance,
        )
        for documento in sorted(documents, key=lambda item: str(item))
    ]

    return pd.DataFrame(records)
