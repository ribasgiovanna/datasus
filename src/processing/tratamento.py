"""
Módulo de tratamento e transformação dos dados extraídos do DATASUS.
"""

import pandas as pd
import os
from config.config import PROCESSED_DIR


def ler_dados_brutos(caminho: str) -> pd.DataFrame:
    """Lê um arquivo CSV/TXT bruto e retorna um DataFrame."""
    if caminho.endswith(".csv") or caminho.endswith(".txt"):
        df = pd.read_csv(caminho, sep=";", encoding="latin1", skiprows=3)
    else:
        raise ValueError(f"Formato não suportado: {caminho}")
    return df


def limpar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas de totais e colunas vazias, normaliza nomes."""
    # Remove linhas e colunas totalmente nulas
    df = df.dropna(how="all").dropna(axis=1, how="all")

    # Remove rodapé (linhas de total do DATASUS costumam ter "Total" na primeira coluna)
    primeira_coluna = df.columns[0]
    df = df[~df[primeira_coluna].astype(str).str.lower().str.startswith("total")]

    # Normaliza nomes de colunas
    df.columns = [
        col.strip().lower().replace(" ", "_").replace("/", "_")
        for col in df.columns
    ]

    return df.reset_index(drop=True)


def salvar_processado(df: pd.DataFrame, nome_arquivo: str) -> str:
    """Salva o DataFrame processado em CSV e retorna o caminho."""
    caminho_saida = os.path.join(PROCESSED_DIR, nome_arquivo)
    df.to_csv(caminho_saida, index=False, encoding="utf-8-sig", sep=";")
    print(f"[INFO] Arquivo salvo: {caminho_saida}")
    return caminho_saida
