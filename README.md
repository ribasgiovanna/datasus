# 🩸 Banco de Sangue DATASUS — extração e análise

Projeto que **automatiza a extração** de dados de hemoterapia do Paraná no
**TabNet do DATASUS** (Produção Ambulatorial do SUS), trata os dados e os
apresenta em um **dashboard**.

> **Projeto em equipe.** Trabalho final do curso de **Programação em Python da Harve**
> (escola de tecnologia), abril de 2026.

## 👥 Equipe e papéis

| Pessoa | Contribuição |
|---|---|
| **Giovanna Ribas dos Reis** ([@ribasgiovanna](https://github.com/ribasgiovanna)) | Ideia do projeto (uso dos dados de banco de sangue / hemoterapia) e trabalho nos módulos de **extração** (`src/rpa/extrator_datasus.py`) e **tratamento** (`src/processing/tratamento.py`) |
| **Jackson Beggi** ([@JacksonBeggi](https://github.com/JacksonBeggi)) | Orquestração da RPA, extração paralela e integração |
| **wingCODING** ([@WingCODING](https://github.com/WingCODING)) | Orquestração da RPA e dashboard |

> Este repositório é uma cópia mantida na conta da Giovanna. O histórico de commits
> ficou concentrado nas contas dos colegas por causa do fluxo de trabalho da época
> (uma pessoa integrando as branches). Repositórios de origem:
> [JacksonBeggi/Projeto_Harve](https://github.com/JacksonBeggi) e
> [WingCODING/datasus](https://github.com/WingCODING/datasus).

## ⚙️ O que o projeto faz

1. **Extração (RPA)** — abre o TabNet do DATASUS no navegador (Selenium), seleciona
   linha, coluna, conteúdo, período, UF e subgrupo de procedimento, e lê a tabela
   de resultado (`pandas.read_html` com fallback em BeautifulSoup).
   - Seletores por `id` para contornar caracteres especiais nos `name`
     (`SRegião`, `SMunicípio`)
   - Waits explícitos em cada interação
   - Troca de aba por polling de `window_handles` com timeout
2. **Extração em lote** (`extrair_todos.py`) — roda vários períodos em paralelo
   (3 workers), com *stagger* entre eles, *checkpoint* (pula o que já foi baixado)
   e consolidação dos Excel individuais em um arquivo único.
3. **Tratamento** (`src/processing/tratamento.py`) — remove rodapés de "Total",
   linhas e colunas vazias, normaliza nomes de colunas e salva o resultado
   processado em CSV.
4. **Dashboard** (`frontMain.py`) — visualização em Streamlit para comparar o volume
   de doações entre meses e anos.

## 🛠️ Tecnologias

- Python 3
- Selenium (automação do navegador)
- pandas · openpyxl · lxml · BeautifulSoup
- Streamlit (dashboard)

## 📁 Estrutura

```
.
├── main.py                       # extração de um período (ponto de entrada)
├── extrair_todos.py              # extração paralela de todos os períodos + consolidação
├── frontMain.py                  # dashboard em Streamlit
├── config/
│   └── config.py                 # URL do TabNet, diretórios, timeouts
└── src/
    ├── rpa/
    │   └── extrator_datasus.py   # navegação e extração da tabela do DATASUS
    └── processing/
        └── tratamento.py         # limpeza e normalização dos dados
```

## ▶️ Como executar

```bash
pip install -r requirements.txt

python main.py            # extrai um período
python extrair_todos.py   # extrai todos os períodos em paralelo
streamlit run frontMain.py
```

A extração usa Selenium e abre um navegador; é necessário ter o WebDriver
correspondente disponível.
