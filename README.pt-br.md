# DATASUS Hemoterapia PR - extração e análise

[English](README.md) · Português

Projeto que automatiza a extração dos dados de hemoterapia do Paraná no TabNet do DATASUS
(Produção Ambulatorial do SUS), trata os dados e os apresenta em um dashboard. No
portfólio, aparece com o nome **Bloody Mary**.

Projeto em equipe. Projeto final do curso de Programação em Python da Harve (escola de
tecnologia), abril de 2026.

![Dashboard](docs/dashboard.png)

## Equipe e responsabilidades

| Pessoa | Contribuição |
|---|---|
| Giovanna Ribas dos Reis ([@ribasgiovanna](https://github.com/ribasgiovanna)) | Ideia do projeto (usar dados de banco de sangue / hemoterapia) e trabalho nos módulos de extração (`src/rpa/extrator_datasus.py`) e de tratamento (`src/processing/tratamento.py`) |
| Jackson Beggi ([@JacksonBeggi](https://github.com/JacksonBeggi)) | Orquestração do RPA, extração paralela e integração |
| wingCODING ([@WingCODING](https://github.com/WingCODING)) | Orquestração do RPA e dashboard |

Este repositório é uma cópia mantida na conta da Giovanna. O histórico de commits está
concentrado nas contas dos colegas por causa do fluxo de trabalho da época (uma pessoa
fazia o merge das branches). Repositórios de origem:
[JacksonBeggi/Projeto_Harve](https://github.com/JacksonBeggi) e
[WingCODING/datasus](https://github.com/WingCODING/datasus).

## O que o projeto faz

1. **Extração (RPA)** - abre o TabNet do DATASUS no navegador (Selenium), seleciona
   linha, coluna, conteúdo, período, estado e subgrupo de procedimento, e lê a tabela de
   resultado (`pandas.read_html`, com BeautifulSoup como alternativa).
   - Seletores por `id`, para contornar caracteres especiais nos atributos `name`
     (`SRegião`, `SMunicípio`)
   - Esperas explícitas em toda interação
   - Troca de aba por verificação periódica de `window_handles`, com tempo limite
2. **Extração em lote** (`extrair_todos.py`) - roda vários períodos em paralelo
   (3 workers), com intervalo entre o início de cada um, checkpoint (pula o que já foi
   baixado) e consolidação dos arquivos Excel individuais em um único arquivo.
3. **Tratamento** (`src/processing/tratamento.py`) - remove os rodapés de "Total" do
   DATASUS e as linhas e colunas vazias, padroniza os nomes das colunas e salva o
   resultado em CSV.
4. **Dashboard** (`frontMain.py`) - uma visualização em Streamlit para comparar o volume
   entre meses e anos.

## Dados

Dados reais extraídos do TabNet do DATASUS - Produção Ambulatorial do SUS, subgrupo de
procedimento 0306 (Hemoterapia), métrica "quantidade aprovada", filtrados para o estado do
Paraná. Eles refletem os procedimentos de hemoterapia aprovados e registrados no SUS, um
indicador relacionado às doações de sangue, mas não idêntico a elas.

## Tecnologias

- Python 3
- Selenium (automação do navegador)
- pandas, openpyxl, lxml, BeautifulSoup
- Streamlit (dashboard)

## Estrutura

```
.
├── main.py                       # extração de um período (ponto de entrada)
├── extrair_todos.py              # extração paralela de todos os períodos + consolidação
├── frontMain.py                  # dashboard em Streamlit
├── config/
│   └── config.py                 # URL do TabNet, pastas e tempos limite
└── src/
    ├── rpa/
    │   └── extrator_datasus.py   # navegação no DATASUS e extração da tabela
    └── processing/
        └── tratamento.py         # limpeza e padronização dos dados
```

## Como executar

```bash
pip install -r requirements.txt

python main.py            # extrai um período
python extrair_todos.py   # extrai todos os períodos em paralelo
streamlit run frontMain.py
```

A extração usa o Selenium e abre um navegador; o WebDriver correspondente precisa estar
disponível.
