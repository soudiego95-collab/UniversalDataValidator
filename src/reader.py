"""
Módulo src.reader
Responsabilidades:
- localizar arquivos Excel (.xlsx, .xls, .xlsm), recursivamente;
- ignorar arquivos temporários iniciados por "~$";
- detectar automaticamente a linha de cabeçalho;
- ler planilhas Excel e retornar DataFrames;
- localizar colunas por nomes equivalentes;
- permitir configuração manual do nome das colunas;
- registrar arquivos encontrados, processados e rejeitados com motivos;
- NÃO executar regras de comparação, NÃO gerar relatórios, NÃO criar GUI.

API principal:
- ExcelReader.discover(caminho) -> List[str]
- ExcelReader.process(caminho, required_columns, manual_columns) -> ReaderResult

Usa dataclasses para estruturas de retorno.
"""
from __future__ import annotations

import glob
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


# -----------------------------
# Data classes para relatórios
# -----------------------------

@dataclass
class FileReport:
    """Resumo por arquivo após tentativa de leitura.

    path: caminho absoluto do arquivo
    processed: True se o arquivo foi lido e aceito
    rejected: True se foi rejeitado (não processado)
    reason: motivo da rejeição quando aplicável
    header_row: linha de cabeçalho detectada (0-based) ou None
    columns_found: mapeamento lógico -> nome da coluna no DataFrame (ou None)
    """

    path: str
    processed: bool
    rejected: bool
    reason: Optional[str] = None
    header_row: Optional[int] = None
    columns_found: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class ReadFile:
    """Representa um arquivo Excel lido com seu DataFrame e metadados."""

    path: str
    df: pd.DataFrame
    header_row: int


@dataclass
class ReaderResult:
    """Resumo agregado após processar um diretório/arquivo.

    files_found: lista de caminhos encontrados (podem ser vazios)
    processed: lista de FileReport para arquivos processados
    rejected: lista de FileReport para arquivos rejeitados
    data: lista de ReadFile — DataFrames lidos para arquivos processados
    """

    files_found: List[str] = field(default_factory=list)
    processed: List[FileReport] = field(default_factory=list)
    rejected: List[FileReport] = field(default_factory=list)
    data: List[ReadFile] = field(default_factory=list)


# -----------------------------
# Utilitários de normalização
# -----------------------------


def normalizar_texto(texto: object) -> str:
    """Normaliza um valor textual: none->"", remove acentos, espaços extras e maiúsculas.

    Retorna string em minúsculas sem acentuação e com espaços reduzidos.
    """

    if pd.isna(texto):
        return ""

    texto = str(texto)
    texto = texto.strip()

    # remover acentos
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    # normaliza espaços
    texto = re.sub(r"\s+", " ", texto)

    return texto.lower().strip()


def normalizar_coluna(valor: object) -> str:
    """Normaliza nomes de colunas para comparação: substitui espaços por underscore."""

    return normalizar_texto(valor).replace(" ", "_")


# -----------------------------
# Funções centrais
# -----------------------------


def find_files(
    caminho: str,
    extensoes: Optional[Iterable[str]] = None,
) -> List[str]:
    """Procura recursivamente arquivos Excel no caminho.

    - Aceita caminhos para um arquivo (retorna lista com 1 item) ou diretório.
    - Suporta extensões .xlsx, .xls, .xlsm
    - Ignora arquivos temporários cujo nome começa com "~$"

    Retorna lista ordenada e única de caminhos absolutos.
    """

    if not caminho:
        return []

    caminho = caminho.strip()

    if os.path.isfile(caminho):
        return [os.path.abspath(caminho)]

    if not os.path.isdir(caminho):
        return []

    if extensoes is None:
        extensoes = (".xlsx", ".xls", ".xlsm")

    patterns = [
        extensao if extensao.startswith("*") else f"*{extensao}"
        for extensao in extensoes
    ]
    arquivos: List[str] = []

    for ext in patterns:
        arquivos.extend(
            glob.glob(os.path.join(caminho, "**", ext), recursive=True)
        )

    arquivos = [a for a in arquivos if not os.path.basename(a).startswith("~$")]

    # tornar absolutos, únicos e ordenados
    arquivos = sorted({os.path.abspath(a) for a in arquivos})

    return arquivos


def detect_header(arquivo: str, max_rows: int = 15) -> int:
    """Detecta a melhor linha de cabeçalho (0-based) lendo até `max_rows` linhas
    sem forçar header.

    Heurística: procura a linha com maior contagem de cabeçalhos que são candidatos
    conhecidos (documento, doc, codigo, valor, gerente, responsavel...).

    Se ocorrer erro na leitura do trecho, retorna 0 (primeira linha).
    """

    try:
        teste = pd.read_excel(arquivo, sheet_name=0, header=None, nrows=max_rows)
    except Exception:
        return 0

    candidatos = {
        "documento",
        "doc",
        "codigo",
        "document",
        "valor",
        "value",
        "gerente",
        "responsavel",
        "responsavel_venda",
        "id",
    }

    melhor_linha = 0
    melhor_pontuacao = -1

    for i in range(len(teste)):
        valores = [normalizar_coluna(x) for x in teste.iloc[i].tolist()]
        pontuacao = sum(1 for v in valores if v in candidatos)

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_linha = i

    return melhor_linha


def locate_column(
    df: pd.DataFrame, candidatos: List[str], coluna_manual: str = ""
) -> Optional[str]:
    """Localiza coluna no DataFrame por equivalências.

    - Se coluna_manual for informada, tenta encontrar exatamente ou com normalização.
    - Caso contrário, normaliza todas as colunas e tenta casar com os candidatos
      (por igualdade ou substring).

    Retorna o nome exato da coluna no DataFrame ou None se não encontrado.
    """

    if coluna_manual:
        if coluna_manual in df.columns:
            return coluna_manual

        alvo = normalizar_coluna(coluna_manual)
        for coluna in df.columns:
            if normalizar_coluna(coluna) == alvo:
                return coluna

    mapa = {normalizar_coluna(col): col for col in df.columns}

    for candidato in candidatos:
        chave = normalizar_coluna(candidato)
        if chave in mapa:
            return mapa[chave]

    # tentativa por substring
    for coluna in df.columns:
        nome = normalizar_coluna(coluna)
        for candidato in candidatos:
            alvo = normalizar_coluna(candidato)
            if alvo in nome or nome in alvo:
                return coluna

    return None


def read_excel_file(arquivo: str, header_row: int) -> pd.DataFrame:
    """Lê uma planilha Excel usando header_row (0-based).

    Retorna DataFrame com colunas como strings limpas (strip).
    Pode lançar exceção em caso de falha de leitura.
    """

    df = pd.read_excel(arquivo, sheet_name=0, header=header_row)

    # Garantir nomes de colunas string e trimmed
    df.columns = [str(x).strip() for x in df.columns]

    return df


# -----------------------------
# Classe de alto nível: ExcelReader
# -----------------------------


class ExcelReader:
    """Encapsula descoberta e leitura de arquivos Excel.

    Exemplo de uso:
        reader = ExcelReader()
        result = reader.process(
            caminho='input/',
            required_columns={'documento': ['Documento','Doc','ID']},
            manual_columns={'valor': 'Total Value'}
        )

    O método process retorna ReaderResult contendo DataFrames lidos (data)
    e relatórios por arquivo (processed/rejected).
    """

    def __init__(self, extensions: Optional[Iterable[str]] = None) -> None:
        # candidatos padrão — podem ser sobrescritos no método process
        self.extensions = tuple(extensions) if extensions is not None else None
        self.default_candidates = {
            "documento": ["Documento", "Doc", "Codigo", "Código", "ID", "Document"],
            "valor": ["Valor", "Value", "Amount", "Total", "Valor Total"],
            "responsavel": [
                "Gerente",
                "Responsavel",
                "Responsável",
                "Vendedor",
                "Consultor",
                "Manager",
            ],
        }

    def discover(self, caminho: str) -> List[str]:
        """Retorna a lista de arquivos Excel encontrados no caminho.

        Público: usado para apenas descobrir arquivos sem processar.
        """

        return find_files(caminho, self.extensions)

    def process(
        self,
        caminho: str,
        required_columns: Optional[Dict[str, List[str]]] = None,
        manual_columns: Optional[Dict[str, str]] = None,
    ) -> ReaderResult:
        """Descobre e tenta ler arquivos Excel em `caminho`.

        - required_columns: mapeamento lógico -> lista de nomes candidatos. Ex: {'documento': [...]}.
          Se não informado, usa candidatos padrão.
        - manual_columns: mapeamento lógico -> nome exato de coluna para forçar mapeamento.

        O método NÃO lança em caso de falha de leitura de arquivo; em vez disso,
        registra o arquivo em rejected com o motivo.
        """

        result = ReaderResult()
        files = self.discover(caminho)
        result.files_found = files

        if required_columns is None:
            required_columns = self.default_candidates.copy()

        if manual_columns is None:
            manual_columns = {}

        for arquivo in files:
            report = FileReport(path=arquivo, processed=False, rejected=False)

            # detectar cabeçalho
            try:
                header_row = detect_header(arquivo)
                report.header_row = header_row
            except Exception as exc:  # pragma: no cover - operação de I/O
                report.rejected = True
                report.reason = f"Erro ao detectar cabeçalho: {exc}"
                result.rejected.append(report)
                continue

            # ler arquivo
            try:
                df = read_excel_file(arquivo, header_row)
            except Exception as exc:
                report.rejected = True
                report.reason = f"Erro ao ler arquivo: {exc}"
                result.rejected.append(report)
                continue

            # localizar colunas por lógica
            columns_found: Dict[str, Optional[str]] = {}
            missing_required: List[str] = []

            for logical, candidates in required_columns.items():
                manual = manual_columns.get(logical, "")
                found = locate_column(df, candidates, coluna_manual=manual)
                columns_found[logical] = found

                # se for coluna obrigatória (documento) e não encontrada -> marcar missing
                # Considera-se obrigatório qualquer chave presente em required_columns;
                # chamador pode omitir chaves que não sejam obrigatórias.
                if found is None:
                    missing_required.append(logical)

            report.columns_found = columns_found

            # Se estiver faltando coluna necessária, rejeitar o arquivo (registrar motivo)
            if missing_required:
                report.rejected = True
                # descrever quais colunas faltam e exemplos de candidatos
                missing_descr = ", ".join(missing_required)
                examples = []
                for m in missing_required:
                    ex = ",".join(required_columns.get(m, []))
                    examples.append(f"{m} (candidatos: {ex})")
                expected = "; ".join(examples)
                report.reason = (
                    f"Coluna(s) obrigatória(s) não encontrada(s): {missing_descr}. "
                    f"Exemplos esperados: {expected}"
                )
                result.rejected.append(report)
                continue

            # Arquivo considerado processado — registrar e anexar DataFrame
            report.processed = True
            result.processed.append(report)
            result.data.append(ReadFile(path=arquivo, df=df, header_row=report.header_row or 0))

        return result


# Função utilitária (fora da classe) para facilitar uso simples

def process_sources(
    caminho: str,
    required_columns: Optional[Dict[str, List[str]]] = None,
    manual_columns: Optional[Dict[str, str]] = None,
) -> ReaderResult:
    """Atalho: instancia ExcelReader e processa o caminho informado."""

    reader = ExcelReader()
    return reader.process(caminho, required_columns=required_columns, manual_columns=manual_columns)
