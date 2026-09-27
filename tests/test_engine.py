from pathlib import Path

import pandas as pd

from src.config import AppConfig
from src.engine import EngineResult, run_validation


def write_source(directory: Path, filename: str, rows):
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(directory / filename, index=False)


def make_config(tmp_path, tolerance=0.01):
    return AppConfig(
        project_dir=tmp_path,
        source_a_dir=tmp_path / "a",
        source_b_dir=tmp_path / "b",
        output_dir=tmp_path / "output",
        source_a_name="Fonte A",
        source_b_name="Fonte B",
        tolerance=tolerance,
    )


def test_engine_completo_identifica_divergencia_e_gera_arquivos(tmp_path):
    write_source(
        tmp_path / "a",
        "a.xlsx",
        [{"Documento": "1", "Valor": "100", "Responsavel": "Ana"}],
    )
    write_source(
        tmp_path / "b",
        "b.xlsx",
        [{"Documento": "1", "Valor": "200", "Responsavel": "Ana"}],
    )

    result = run_validation(make_config(tmp_path))

    assert isinstance(result, EngineResult)
    assert isinstance(result.validation, pd.DataFrame)
    assert len(result.validation) == 1
    assert result.validation.iloc[0]["Problematico"]
    assert "Divergencia de Valor" in result.validation.iloc[0]["Classificacao"]
    assert (tmp_path / "output" / "relatorio_validacao_final.xlsx").is_file()
    assert (tmp_path / "output" / "historico_ultima_validacao.csv").is_file()


def test_engine_sem_divergencias_retorna_documento_ok(tmp_path):
    rows = [{"Documento": "2", "Valor": "50,00", "Responsavel": "Bia"}]
    write_source(tmp_path / "a", "a.xlsx", rows)
    write_source(tmp_path / "b", "b.xlsx", rows)

    result = run_validation(make_config(tmp_path))

    assert len(result.get("problemas")) == 0
    assert result.validation.iloc[0]["Classificacao"] == "OK"
    assert bool(result.validation.iloc[0]["Problematico"]) is False


def test_engine_preserva_historico_e_detecta_alteracao(tmp_path):
    write_source(
        tmp_path / "a",
        "a.xlsx",
        [{"Documento": "3", "Valor": 10, "Responsavel": "Ana"}],
    )
    write_source(
        tmp_path / "b",
        "b.xlsx",
        [{"Documento": "3", "Valor": 20, "Responsavel": "Ana"}],
    )
    config = make_config(tmp_path)
    run_validation(config)

    write_source(
        tmp_path / "b",
        "b.xlsx",
        [{"Documento": "3", "Valor": 10, "Responsavel": "Ana"}],
    )
    result = run_validation(config)

    assert len(result.get("resolvidos")) == 0
    assert len(result.get("alteracoes")) == 1
