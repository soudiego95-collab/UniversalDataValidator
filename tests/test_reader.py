from pathlib import Path

import pandas as pd

from src.reader import ExcelReader, detect_header, locate_column


def write_excel(path: Path, rows, startrow=0):
    frame = pd.DataFrame(rows)
    frame.to_excel(path, index=False, startrow=startrow)


def test_leitura_excel_simples_e_deteccao_de_cabecalho(tmp_path):
    path = tmp_path / "fonte.xlsx"
    write_excel(
        path,
        [{"Documento": "1", "Valor": "10", "Responsavel": "Ana"}],
        startrow=2,
    )

    assert detect_header(str(path)) == 2
    result = ExcelReader().process(
        str(path),
        required_columns={"documento": ["Documento"]},
    )

    assert len(result.files_found) == 1
    assert len(result.processed) == 1
    assert result.data[0].df.iloc[0]["Documento"] == 1


def test_localizacao_de_colunas_por_equivalencia(tmp_path):
    frame = pd.DataFrame(columns=["Código do Documento", "Valor Total"])

    assert locate_column(frame, ["Documento", "Codigo"]) == "Código do Documento"
    assert locate_column(frame, ["Valor", "Total"]) == "Valor Total"


def test_leitura_de_multiplos_arquivos_e_consolidacao(tmp_path):
    write_excel(tmp_path / "a.xlsx", [{"Documento": "1", "Valor": 10}])
    write_excel(tmp_path / "b.xlsx", [{"Documento": "2", "Valor": 20}])
    (tmp_path / "~$temporario.xlsx").write_bytes(b"ignored")

    result = ExcelReader().process(
        str(tmp_path),
        required_columns={"documento": ["Documento"]},
    )
    consolidated = pd.concat([item.df for item in result.data], ignore_index=True)

    assert len(result.files_found) == 2
    assert len(result.processed) == 2
    assert sorted(consolidated["Documento"].tolist()) == [1, 2]


def test_arquivo_sem_coluna_obrigatoria_e_rejeitado_com_motivo(tmp_path):
    path = tmp_path / "sem_documento.xlsx"
    write_excel(path, [{"Valor": 10, "Responsavel": "Ana"}])

    result = ExcelReader().process(
        str(path),
        required_columns={"documento": ["Documento"]},
    )

    assert len(result.rejected) == 1
    assert "documento" in result.rejected[0].reason.lower()
    assert result.rejected[0].columns_found["documento"] is None


def test_metadados_de_origem_sao_preservados_no_arquivo_lido(tmp_path):
    path = tmp_path / "origem.xlsx"
    write_excel(path, [{"Documento": "10"}], startrow=1)

    result = ExcelReader().process(
        str(path),
        required_columns={"documento": ["Documento"]},
    )

    read_file = result.data[0]
    assert read_file.path == str(path.resolve())
    assert read_file.header_row == 1
