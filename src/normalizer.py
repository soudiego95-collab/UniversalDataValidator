"""Normalização e conversão de valores usados pelo UniversalDataValidator.

Este módulo não lê arquivos, compara fontes, executa regras de negócio ou gera
relatórios. Conversões que podem falhar retornam ``ConversionResult`` para que
o chamador diferencie valores válidos, ausentes e inválidos sem depender de
``NaN``.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from numbers import Real
from typing import Literal, Optional

import pandas as pd


ConversionStatus = Literal["valid", "missing", "invalid"]


@dataclass(frozen=True)
class ConversionResult:
    """Resultado rastreável de uma conversão.

    ``status`` é ``valid`` quando ``value`` pode ser usado, ``missing`` para
    valores ausentes ou vazios e ``invalid`` quando o valor não é interpretável.
    ``reason`` contém uma explicação para estados diferentes de ``valid``.
    """

    status: ConversionStatus
    value: Optional[float] = None
    original: object = None
    reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Indica se o resultado contém um valor convertido válido."""

        return self.status == "valid"

    @property
    def is_missing(self) -> bool:
        """Indica se o valor original estava ausente ou vazio."""

        return self.status == "missing"

    @property
    def is_invalid(self) -> bool:
        """Indica se o valor original não pôde ser interpretado."""

        return self.status == "invalid"


def _is_missing(value: object) -> bool:
    """Retorna ``True`` para nulos escalares ou texto vazio."""

    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False

    return isinstance(result, bool) and result


def normalizar_texto(valor: object, *, remover_acentos: bool = True) -> str:
    """Normaliza texto, tratando nulos como string vazia.

    Remove espaços excedentes, converte para minúsculas e, por padrão, remove
    acentos. Use ``remover_acentos=False`` quando a apresentação original for
    relevante; para comparações, o padrão é recomendado.
    """

    if _is_missing(valor):
        return ""

    texto = str(valor).strip()
    texto = re.sub(r"\s+", " ", texto)

    if remover_acentos:
        decomposed = unicodedata.normalize("NFKD", texto)
        texto = "".join(
            caractere
            for caractere in decomposed
            if not unicodedata.combining(caractere)
        )

    return texto.lower().strip()


def normalizar_coluna(valor: object) -> str:
    """Normaliza um nome de coluna para comparação entre planilhas."""

    return normalizar_texto(valor).replace(" ", "_")


def normalizar_chave(valor: object) -> str:
    """Normaliza um documento ou identificador sem descartar informação.

    Espaços externos e internos são removidos. Números inteiros vindos do Excel
    como ``123.0`` tornam-se ``123``; zeros à esquerda em strings, como
    ``"00123"``, são preservados. Valores decimais não inteiros não são
    truncados. Nulos retornam string vazia.
    """

    if _is_missing(valor):
        return ""

    if isinstance(valor, bool):
        return str(valor).strip()

    if isinstance(valor, Real):
        numero = float(valor)
        if not math.isfinite(numero):
            return ""
        if numero.is_integer():
            return str(int(numero))
        return format(numero, "f").rstrip("0").rstrip(".")

    texto = re.sub(r"\s+", "", str(valor).strip())
    if not texto:
        return ""

    if texto.startswith("(") and texto.endswith(")"):
        texto = "-" + texto[1:-1]

    # Apenas remove o sufixo .0 de uma string numérica; não altera zeros à
    # esquerda nem outras partes do identificador.
    if re.fullmatch(r"-?\d+\.0+", texto):
        texto = texto[: texto.index(".")]

    return texto


def _invalid_number(valor: object, reason: str) -> ConversionResult:
    """Cria um resultado inválido padronizado."""

    return ConversionResult(
        status="invalid",
        original=valor,
        reason=reason,
    )


def converter_numero(valor: object) -> ConversionResult:
    """Converte números e formatos monetários brasileiros com rastreabilidade.

    Aceita números reais e textos como ``R$ 1.234,56``, ``1.234,56`` e
    ``1234,56``. Valores ausentes retornam ``missing``. Formatos não
    interpretáveis retornam ``invalid`` e nunca são convertidos silenciosamente
    para ``NaN``.
    """

    if _is_missing(valor):
        return ConversionResult(status="missing", original=valor, reason="valor ausente")

    if isinstance(valor, bool):
        return _invalid_number(valor, "booleano não é um valor monetário")

    if isinstance(valor, Real):
        numero = float(valor)
        if not math.isfinite(numero):
            return _invalid_number(valor, "número não finito")
        return ConversionResult(status="valid", value=numero, original=valor)

    texto_original = str(valor).strip()
    texto = texto_original.lower().replace(" ", "")
    negativo_parenteses = texto.startswith("(") and texto.endswith(")")
    if negativo_parenteses:
        texto = "-" + texto[1:-1]

    texto = re.sub(r"^(r\$|brl)", "", texto)
    if not texto:
        return ConversionResult(status="missing", original=valor, reason="valor vazio")

    if not re.fullmatch(r"-?\d+(?:[.,]\d+)*", texto):
        return _invalid_number(valor, f"formato monetário não reconhecido: {texto_original!r}")

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        numero = float(Decimal(texto))
    except (InvalidOperation, ValueError, OverflowError):
        return _invalid_number(valor, f"número não interpretável: {texto_original!r}")

    if not math.isfinite(numero):
        return _invalid_number(valor, "resultado não finito")

    return ConversionResult(status="valid", value=numero, original=valor)


def formatar_reais(valor: object) -> str:
    """Formata um valor válido como moeda brasileira.

    Valores ausentes resultam em string vazia. Valores inválidos geram
    ``ValueError`` explícito, evitando exibir um valor aparentemente válido ou
    mascarar uma falha de conversão. Também aceita um ``ConversionResult``.
    """

    resultado = valor if isinstance(valor, ConversionResult) else converter_numero(valor)

    if resultado.is_missing:
        return ""
    if resultado.is_invalid or resultado.value is None:
        motivo = resultado.reason or "valor monetário inválido"
        raise ValueError(motivo)

    texto = f"{resultado.value:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def exigir_numero(valor: object) -> float:
    """Retorna um número válido ou lança ``ValueError`` para uso estrito.

    Esta função é útil em pontos que não podem prosseguir com dados ausentes ou
    inválidos e evita que esses estados sejam confundidos com ``NaN``.
    """

    resultado = converter_numero(valor)
    if not resultado.is_valid or resultado.value is None:
        motivo = resultado.reason or f"valor {resultado.status}"
        raise ValueError(motivo)
    return resultado.value
