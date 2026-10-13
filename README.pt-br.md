# Bloody Mary - dados de hemoterapia do DATASUS, extração e análise

[English](README.md) · Português

Projeto que automatiza a extração dos dados de hemoterapia do Paraná no TabNet do DATASUS
(Produção Ambulatorial do SUS), trata os dados e os apresenta em um dashboard.

> **Resumo**
> - **O que é:** um pipeline de RPA que extrai dados públicos de hemoterapia do DATASUS, trata e apresenta em gráficos.
> - **Problema:** o TabNet só responde a uma consulta manual por vez, por um formulário lento.
> - **Minha parte:** a ideia do projeto e os módulos de extração e de tratamento.
> - **Destaques:** extração paralela com checkpoint, alternativas em cascata e isolamento de falhas por período (veja [Confiabilidade](#confiabilidade)).

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

## Confiabilidade

O TabNet é um sistema governamental antigo e lento, então o pipeline foi feito para seguir
em frente quando uma etapa falha, em vez de perder a execução inteira.

| Situação | Como é tratada |
|---|---|
| Um período falha (tempo esgotado, erro do navegador) | Cada período roda em um processo próprio; o erro é capturado, o período aparece na lista de falhas no fim e os demais continuam |
| Um período não retorna linhas | Conta como falha e é informado, em vez de ser salvo vazio sem aviso |
| A execução é interrompida | Checkpoint: cada período é salvo em um Excel próprio, e uma nova execução pula os períodos que já têm arquivo |
| Páginas lentas | Esperas explícitas em toda interação (20 s) e limite de 60 s para carregar a página, em vez de pausas fixas |
| Filtro oculto ou opção não encontrada pelo nome | O filtro é expandido antes; a opção é escolhida pelo texto, depois pelo valor e, por último, via JavaScript |
| O resultado não abre em nova aba | Verificação periódica de `window_handles` com tempo limite e, se não abrir, segue na aba atual |
| A tabela não pode ser lida de um jeito | Três estratégias em cascata: download direto do CSV, depois a tabela `tabdados` via BeautifulSoup e, por fim, `pandas.read_html` |
| Carga no servidor | Só 3 workers, iniciados com 10 s de intervalo |
| Um arquivo não pode ser lido na consolidação | É ignorado com aviso, e os demais períodos são consolidados |
| Linhas de "Total" do DATASUS e linhas/colunas vazias | Removidas no tratamento, para não distorcer somas e médias |

**Limitações conhecidas:** períodos com falha não são tentados de novo automaticamente na
mesma execução (rodar o script outra vez refaz só o que falta); o checkpoint confia que um
arquivo existente está completo; e uma mudança na estrutura da página do TabNet só é
percebida quando um seletor falha, porque as colunas de saída ainda não são validadas
contra um esquema.

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
