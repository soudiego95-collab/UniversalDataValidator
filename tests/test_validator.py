import pandas as pd
import pytest

from src.validator import comparar_fontes


def source(rows):
    return pd.DataFrame(rows, columns=["Documento", "Valor", "Responsavel"])


def validate(rows_a, rows_b, tolerance=0.01):
    return comparar_fontes(
        source(rows_a),
        source(rows_b),
        tolerancia=tolerance,
    )


def row(result, document):
    return result.loc[result["Documento"] == document].iloc[0]


def test_documentos_e_valores_iguais_ficam_ok():
    result = validate([("1", 100, "Ana")], [("1", 100, "Ana")])
    item = row(result, "1")

    assert item["Classificacao"] == "OK"
    assert bool(item["Problematico"]) is False
    assert item["Qtd_Fonte_A"] == 1
    assert item["Qtd_Fonte_B"] == 1


def test_divergencia_de_valor():
    item = row(validate([("1", 100, "Ana")], [("1", 120, "Ana")]), "1")

    assert "Divergencia de Valor" in item["Classificacao"]
    assert item["Diferenca_Valor"] == -20
    assert item["Problematico"]


def test_documento_ausente_na_fonte_a():
    item = row(validate([], [("2", 20, "Ana")]), "2")

    assert item["Classificacao"] == "Ausente na Fonte A"
    assert item["Qtd_Fonte_A"] == 0
    assert item["Qtd_Fonte_B"] == 1


def test_documento_ausente_na_fonte_b():
    item = row(validate([("3", 30, "Ana")], []), "3")

    assert item["Classificacao"] == "Ausente na Fonte B"
    assert item["Qtd_Fonte_A"] == 1
    assert item["Qtd_Fonte_B"] == 0


def test_duplicidade_na_fonte_a():
    item = row(
        validate(
            [("4", 10, "Ana"), ("4", 10, "Ana")],
            [("4", 20, "Ana")],
        ),
        "4",
    )

    assert "Duplicidade na Fonte A" in item["Classificacao"]
    assert item["Qtd_Fonte_A"] == 2


def test_duplicidade_na_fonte_b():
    item = row(
        validate(
            [("5", 10, "Ana")],
            [("5", 10, "Ana"), ("5", 10, "Ana")],
        ),
        "5",
    )

    assert "Duplicidade na Fonte B" in item["Classificacao"]
    assert item["Qtd_Fonte_B"] == 2


def test_multiplos_problemas_e_contagem_de_documento_unica():
    result = validate(
        [("6", 10, "Ana"), ("6", 10, "Ana")],
        [("6", 30, "Bia"), ("6", 30, "Bia")],
    )
    item = row(result, "6")

    assert len(result) == 1
    assert "Divergencia de Valor" in item["Classificacao"]
    assert "Divergencia de Responsavel" in item["Classificacao"]
    assert "Duplicidade na Fonte A" in item["Classificacao"]
    assert "Duplicidade na Fonte B" in item["Classificacao"]


def test_tolerancia_permite_pequena_diferenca():
    item = row(
        validate([("7", 100, "Ana")], [("7", 100.005, "Ana")], 0.01),
        "7",
    )

    assert item["Classificacao"] == "OK"


@pytest.mark.parametrize("tolerance", [-1, float("nan"), float("inf")])
def test_tolerancia_invalida_gera_erro(tolerance):
    with pytest.raises(ValueError):
        validate([("8", 1, "Ana")], [("8", 1, "Ana")], tolerance)


def test_linhas_de_total_nao_sao_documentos():
    result = validate(
        [("Total Geral", 100, "Ana"), ("9", 9, "Ana")],
        [("9", 9, "Ana")],
    )

    assert list(result["Documento"]) == ["9"]
