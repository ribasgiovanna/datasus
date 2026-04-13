"""
Extração paralela de TODOS os períodos do DATASUS.

Configuração:
- 3 workers headless em paralelo
- Stagger de 10s entre os 3 primeiros workers (evita pico de carga no servidor)
- Checkpoint automático: períodos já baixados são ignorados
- Ao final, consolida todos os Excel individuais em um arquivo único

Uso:
    .\.venv\Scripts\python extrair_todos.py
"""

import sys
import os
import time
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.rpa.extrator_datasus import executar_consulta, listar_periodos
from config.config import DOWNLOADS_DIR

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
MAX_WORKERS = 3
STAGGER_SEGUNDOS = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parâmetros fixos de extração (ajuste conforme necessidade)
# ---------------------------------------------------------------------------
PARAMS_EXTRACAO = {
    "linha": "Município",
    "coluna": "Região",
    "conteudo": ["Qtd.aprovada"],
    "uf": ["16"],               # 16 = Paraná
    "subgrupo_proced": ["22"],  # 22 = 0306 Hemoterapia
}


# ---------------------------------------------------------------------------
# Worker function (nível de módulo — obrigatório para ser picklável no Windows)
# ---------------------------------------------------------------------------
def _worker_periodo(args: tuple) -> tuple:
    """
    Processa UM período e salva o Excel individual em downloads/.
    Executado em processo separado pelo ProcessPoolExecutor.

    Args:
        args: (periodo_value, periodo_label, stagger_segundos)

    Returns:
        (periodo_value, periodo_label, qtd_registros, erro_ou_None)
    """
    periodo_value, periodo_label, stagger = args

    # Stagger inicial para não sobrecarregar o servidor ao arrancar
    if stagger > 0:
        time.sleep(stagger)

    try:
        # "Jan/2026" → "Jan_2026"
        periodo_nome = periodo_label.replace("/", "_")
        registros = executar_consulta(
            linha=PARAMS_EXTRACAO["linha"],
            coluna=PARAMS_EXTRACAO["coluna"],
            conteudo=PARAMS_EXTRACAO["conteudo"],
            periodos=[periodo_value],
            uf=PARAMS_EXTRACAO.get("uf"),
            subgrupo_proced=PARAMS_EXTRACAO.get("subgrupo_proced"),
            headless=True,
            manter_navegador=False,
            prefixo=f"Hemoterapia_Parana_{periodo_nome}",
        )
        return (periodo_value, periodo_label, len(registros), None)
    except Exception as exc:
        return (periodo_value, periodo_label, 0, str(exc))


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------
def _periodo_ja_baixado(periodo_label: str) -> bool:
    """Retorna True se já existe Excel para este período em downloads/."""
    nome = periodo_label.replace("/", "_")  # "Jan/2026" → "Jan_2026"
    return Path(DOWNLOADS_DIR).joinpath(f"Hemoterapia_Parana_{nome}.xlsx").exists()


# ---------------------------------------------------------------------------
# Consolidação
# ---------------------------------------------------------------------------
def consolidar_excels() -> str:
    """
    Lê todos os Excel individuais (resultado_qabr*.xlsx) em downloads/
    e gera um único arquivo consolidado_datasus_{timestamp}.xlsx.
    Retorna o caminho do arquivo consolidado.
    """
    arquivos = sorted(Path(DOWNLOADS_DIR).glob("Hemoterapia_Parana_*.xlsx"))
    if not arquivos:
        log.error("Nenhum arquivo Excel encontrado para consolidar.")
        return ""

    dfs = []
    for arq in arquivos:
        try:
            df = pd.read_excel(arq, engine="openpyxl")
            # Extrai período do nome: Hemoterapia_Parana_Jan_2026.xlsx → Jan/2026
            partes = arq.stem.split("_")
            # índices: [0]=Hemoterapia [1]=Parana [2]=Jan [3]=2026
            periodo = f"{partes[2]}/{partes[3]}" if len(partes) > 3 else arq.stem
            df.insert(0, "Periodo", periodo)
            dfs.append(df)
        except Exception as exc:
            log.warning("Falha ao ler %s: %s", arq.name, exc)

    if not dfs:
        log.error("Nenhum DataFrame válido para consolidar.")
        return ""

    consolidado = pd.concat(dfs, ignore_index=True)
    caminho = os.path.join(DOWNLOADS_DIR, "Hemoterapia_Parana_CONSOLIDADO.xlsx")
    consolidado.to_excel(caminho, index=False, engine="openpyxl")
    log.info("Consolidado salvo: %s (%d linhas)", caminho, len(consolidado))
    return caminho


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print(" DATASUS — Extração completa de todos os períodos")
    print(f" Workers: {MAX_WORKERS} | Headless: True | Stagger: {STAGGER_SEGUNDOS}s/worker")
    print("=" * 65)

    # 1. Descobrir períodos
    print("\n[1/4] Descobrindo períodos disponíveis no DATASUS...")
    periodos = listar_periodos(headless=True)
    print(f"       {len(periodos)} períodos encontrados.")

    # 2. Checkpoint — ignora os já baixados
    pendentes = [p for p in periodos if not _periodo_ja_baixado(p["label"])]
    ja_baixados = len(periodos) - len(pendentes)
    print(f"[2/4] Já baixados: {ja_baixados} | Pendentes: {len(pendentes)}")

    if not pendentes:
        print("       Todos os períodos já foram baixados.")
    else:
        # Primeiros MAX_WORKERS tarefas recebem stagger escalonado (0s, 10s, 20s).
        # As demais recebem 0s — workers já estarão em ritmo cadenciado.
        tarefas = [
            (p["value"], p["label"], i * STAGGER_SEGUNDOS if i < MAX_WORKERS else 0)
            for i, p in enumerate(pendentes)
        ]

        print(f"\n[3/4] Extraindo {len(pendentes)} períodos com {MAX_WORKERS} workers...")
        inicio = datetime.now()
        sucesso = 0
        falhas = []

        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futuros = {pool.submit(_worker_periodo, t): t for t in tarefas}
            for i, futuro in enumerate(as_completed(futuros), 1):
                periodo_value, periodo_label, qtd, erro = futuro.result()
                status = f"{qtd} registros" if not erro else f"ERRO: {erro[:70]}"
                print(f"  [{i:>3}/{len(tarefas)}] {periodo_label:<12} ({periodo_value}) → {status}")
                if not erro and qtd > 0:
                    sucesso += 1
                else:
                    falhas.append((periodo_value, periodo_label, erro or "0 registros"))

        duracao = (datetime.now() - inicio).total_seconds()
        print(f"\n  Sucesso: {sucesso} | Falhas: {len(falhas)} | Duração: {duracao / 60:.1f} min")

        if falhas:
            print("  Períodos com falha:")
            for v, l, e in falhas:
                print(f"    {l} ({v}): {e[:80]}")

    # 4. Consolidar todos os Excel em um único arquivo
    print("\n[4/4] Consolidando todos os períodos em um único arquivo...")
    caminho = consolidar_excels()
    if caminho:
        print(f"  → {caminho}")

    print("\n[FIM] Extração completa concluída.")


if __name__ == "__main__":
    main()
