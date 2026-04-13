"""
Ponto de entrada principal do projeto.
Coordena extração e processamento dos dados do DATASUS.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.rpa.extrator_datasus import executar_consulta


def main():
    print("[INICIO] Extração DATASUS - Produção Ambulatorial SUS")

    resultados = executar_consulta(
        linha="Município",
        coluna="Região",
        conteudo=["Qtd.aprovada"],
        periodos=["qabr2601.dbf"],      # Jan/2026
        uf=["16"],                       # 16 = Paraná
        subgrupo_proced=["22"],          # 22 = 0306 Hemoterapia
        headless=False,
        manter_navegador=True,
    )

    print(f"[FIM] {len(resultados)} registros obtidos.")
    for registro in resultados[:5]:
        print(registro)


if __name__ == "__main__":
    main()
