# DATASUS Blood Bank - extraction and analysis

A project that automates the extraction of hemotherapy data for the state of Paraná
from the DATASUS TabNet (SUS Outpatient Production), treats the data and presents it
in a dashboard.

Team project. Final project of the Python Programming course at Harve (technology
school), April 2026.

## Team and roles

| Person | Contribution |
|---|---|
| Giovanna Ribas dos Reis ([@ribasgiovanna](https://github.com/ribasgiovanna)) | Project idea (using blood bank / hemotherapy data) and work on the extraction (`src/rpa/extrator_datasus.py`) and treatment (`src/processing/tratamento.py`) modules |
| Jackson Beggi ([@JacksonBeggi](https://github.com/JacksonBeggi)) | RPA orchestration, parallel extraction and integration |
| wingCODING ([@WingCODING](https://github.com/WingCODING)) | RPA orchestration and dashboard |

This repository is a copy kept on Giovanna's account. The commit history is concentrated
in the teammates' accounts because of the workflow at the time (one person merging the
branches). Origin repositories: [JacksonBeggi/Projeto_Harve](https://github.com/JacksonBeggi)
and [WingCODING/datasus](https://github.com/WingCODING/datasus).

## What it does

1. **Extraction (RPA)** - opens the DATASUS TabNet in the browser (Selenium), selects
   row, column, content, period, state and procedure subgroup, and reads the result
   table (`pandas.read_html` with a BeautifulSoup fallback).
   - Selectors by `id` to work around special characters in the `name` attributes
     (`SRegião`, `SMunicípio`)
   - Explicit waits on every interaction
   - Tab switching by polling `window_handles` with a timeout
2. **Batch extraction** (`extrair_todos.py`) - runs several periods in parallel
   (3 workers), with a stagger between them, checkpointing (skips what was already
   downloaded) and consolidation of the individual Excel files into a single one.
3. **Treatment** (`src/processing/tratamento.py`) - removes DATASUS "Total" footers,
   empty rows and columns, normalizes column names and saves the processed result
   as CSV.
4. **Dashboard** (`frontMain.py`) - a Streamlit view to compare volume across months
   and years.

## Data

Real data extracted from the DATASUS TabNet - SUS Outpatient Production, procedure
subgroup 0306 (Hemotherapy), "approved quantity" metric, filtered to the state of
Paraná. It reflects approved hemotherapy procedures recorded in SUS, which is an
indicator related to - but not identical to - blood donations.

## Tech

- Python 3
- Selenium (browser automation)
- pandas, openpyxl, lxml, BeautifulSoup
- Streamlit (dashboard)

## Structure

```
.
├── main.py                       # single-period extraction (entry point)
├── extrair_todos.py              # parallel extraction of all periods + consolidation
├── frontMain.py                  # Streamlit dashboard
├── config/
│   └── config.py                 # TabNet URL, directories, timeouts
└── src/
    ├── rpa/
    │   └── extrator_datasus.py   # DATASUS navigation and table extraction
    └── processing/
        └── tratamento.py         # data cleaning and normalization
```

## Running

```bash
pip install -r requirements.txt

python main.py            # extract one period
python extrair_todos.py   # extract all periods in parallel
streamlit run frontMain.py
```

Extraction uses Selenium and opens a browser; the matching WebDriver must be available.
