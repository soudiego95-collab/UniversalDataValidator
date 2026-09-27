import math

from src.normalizer import (
    converter_numero,
    formatar_reais,
    normalizar_chave,
    normalizar_coluna,
    normalizar_texto,
)


def test_normalizar_texto_remove_acentos_espacos_e_normaliza_caixa():
    assert normalizar_texto("  João   da  Silva ") == "joao da silva"
    assert normalizar_texto("  São Paulo  ", remover_acentos=False) == "são paulo"


def test_normalizar_coluna_substitui_espacos():
    assert normalizar_coluna(" Valor Total ") == "valor_total"


def test_normalizar_chave_preserva_zeros_e_trata_numero_excel():
    assert normalizar_chave(" 00123 ") == "00123"
    assert normalizar_chave(123.0) == "123"
    assert normalizar_chave("(123)") == "-123"
    assert normalizar_chave(None) == ""


def test_converter_numero_aceita_formatos_brasileiros():
    assert converter_numero("R$ 1.234,56").value == 1234.56
    assert converter_numero("1.234,56").value == 1234.56
    assert converter_numero("1234,56").value == 1234.56
    assert converter_numero(1234.56).value == 1234.56


def test_converter_numero_diferencia_ausente_de_invalido():
    missing = converter_numero("")
    invalid = converter_numero("não é número")

    assert missing.status == "missing"
    assert invalid.status == "invalid"
    assert invalid.reason
    assert math.isnan(float("nan"))


def test_formatar_reais_formata_valor_valido():
    assert formatar_reais("R$ 1.234,56") == "R$ 1.234,56"


def test_formatar_reais_rejeita_valor_invalido():
    try:
        formatar_reais("invalido")
    except ValueError as error:
        assert "formato" in str(error)
    else:
        raise AssertionError("Valor inválido deveria gerar ValueError")
