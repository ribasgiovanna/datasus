"""
Configurações globais do projeto.
"""

import os

# URL principal do TabNet DATASUS
URL_DATASUS = "https://tabnet.datasus.gov.br/cgi/deftohtm.exe?sia/cnv/qabr.def"

# Diretórios
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")  # Excel de extração e download CSV

# Selenium
WAIT_TIMEOUT = 20  # segundos

# Garantir que os diretórios existam
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
