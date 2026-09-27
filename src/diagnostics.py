"""Geração de diagnósticos para resultados de validação.

Este módulo recebe exclusivamente registros produzidos pelo validator. Não lê
arquivos, não escreve planilhas e não contém lógica de comparação ou interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import List


_DIAGNOSTICOS = (
    (
        "Ausente na Fonte A",
        "O documento existe na Fonte B, mas não foi localizado na Fonte A.",
    ),
    (
        "Ausente na Fonte B",
        "O documento existe na Fonte A, mas não foi localizado na Fonte B.",
    ),
    (
        "Divergencia de Valor",
        "Os valores encontrados nas duas fontes não coincidem dentro da "
        "tolerância configurada.",
    ),
    (
        "Divergencia de Responsavel",
        "O responsável informado nas fontes é diferente.",
    ),
    (
        "Duplicidade na Fonte A",
        "O documento aparece mais de uma vez na Fonte A.",
    ),
    (
        "Duplicidade na Fonte B",
        "O documento aparece mais de uma vez na Fonte B.",
    ),
)


def _required_value(resultado: Mapping[str, object], chave: str) -> object:
    """Obtém um campo obrigatório do resultado ou informa o formato inválido."""

    if chave not in resultado:
        raise ValueError(
            f"Resultado de validação sem o campo obrigatório {chave!r}."
        )
    return resultado[chave]


def _classificacao(resultado: Mapping[str, object]) -> str:
    """Retorna a classificação textual de um resultado."""

    classificacao = _required_value(resultado, "Classificacao")
    if not isinstance(classificacao, str):
        raise TypeError(
            "O campo 'Classificacao' do resultado deve ser texto."
        )
    return classificacao


def gerar_diagnostico(resultado: Mapping[str, object]) -> str:
    """Explica os problemas presentes em um resultado do validator.

    O diagnóstico é derivado somente dos campos ``Problematico`` e
    ``Classificacao`` produzidos por :func:`validator.comparar_fontes`.
    Quando não há problemas, retorna a mensagem de registro validado. Quando
    há mais de um problema, as explicações são combinadas na mesma ordem das
    classificações oficiais.

    Args:
        resultado: mapeamento de uma linha do DataFrame de validação. Um
            ``pandas.Series`` também pode ser utilizado.

    Raises:
        ValueError: se ``Problematico`` ou ``Classificacao`` não existir.
        TypeError: se ``Classificacao`` não for texto.
    """

    problematico = _required_value(resultado, "Problematico")
    classificacao = _classificacao(resultado)

    if not bool(problematico):
        return "Registro validado sem inconsistências."

    partes: List[str] = [
        explicacao
        for marcador, explicacao in _DIAGNOSTICOS
        if marcador in classificacao
    ]

    if not partes:
        raise ValueError(
            "Resultado marcado como problemático sem uma classificação "
            "reconhecida."
        )

    return " ".join(partes)
