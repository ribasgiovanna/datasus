"""
Extrator de dados do DATASUS TabNet — versão completa e robusta
Fonte: Produção Ambulatorial do SUS - Brasil - Por Local de Atendimento
URL: https://tabnet.datasus.gov.br/cgi/deftohtm.exe?sia/cnv/qabr.def

Estratégia:
- Seletores por ID para evitar problemas com caracteres especiais nos atributos
  name (ex: "SRegião", "SMunicípio"). IDs mapeados: L, C, I, A, S1, S2, S3.
- Waits explícitos em todos os pontos de interação; time.sleep apenas no
  polling de window_handles, que é uma operação assíncrona fora do DOM.
- Seleção múltipla com deselect_all() + fallback por value quando texto falha.
- Troca de aba via polling de window_handles com timeout configurável e
  fallback para aba atual caso nenhuma nova janela seja detectada.
- Extração da tabela via pandas.read_html (lxml) + fallback BeautifulSoup;
  resultado retornado como list[dict] e salvo como CSV UTF-8-BOM.
"""

import base64
import io
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from config.config import DOWNLOAD_DIR, DOWNLOADS_DIR, PROCESSED_DIR, URL_DATASUS, WAIT_TIMEOUT

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapeamento de campos do formulário por ID
# Usamos IDs para evitar erros com caracteres especiais nos atributos name
# (ex: name="SRegião" e name="SMunicípio" causam problemas em By.NAME).
# ---------------------------------------------------------------------------
CAMPO_IDS = {
    "linha":          "L",   # select name="Linha"
    "coluna":         "C",   # select name="Coluna"
    "conteudo":       "I",   # select name="Incremento"     (seleção múltipla)
    "periodos":       "A",   # select name="Arquivos"       (seleção múltipla)
    "regiao":         "S1",  # select name="SRegião"        (seleção múltipla)
    "uf":             "S2",  # select name="SUF"             (seleção múltipla)
    "municipio":      "S3",  # select name="SMunicípio"     (seleção múltipla)
    "subgrupo_proced": "S18", # select name="SSubgrupo_proced." (seleção múltipla)
}


# ---------------------------------------------------------------------------
# Configuração do driver
# ---------------------------------------------------------------------------
def configurar_driver(headless: bool = False) -> webdriver.Edge:
    """Configura e retorna instância do Edge WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # Reduz sinalização de automação que pode causar bloqueios no site
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    prefs = {
        "download.default_directory": str(DOWNLOAD_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    # Selenium Manager detecta e baixa o msedgedriver correto automaticamente.
    driver = webdriver.Edge(options=options)
    driver.set_page_load_timeout(60)
    log.info("Driver Edge iniciado (headless=%s).", headless)
    return driver


# ---------------------------------------------------------------------------
# Helpers de seleção
# ---------------------------------------------------------------------------
def _aguardar_select(wait: WebDriverWait, campo_id: str):
    """Aguarda um <select> estar presente no DOM e retorna o WebElement."""
    return wait.until(
        EC.presence_of_element_located((By.ID, campo_id)),
        message=f"Elemento com id='{campo_id}' não encontrado no DOM.",
    )


def _expandir_filtro_se_oculto(driver: webdriver.Chrome, campo_id: str) -> None:
    """
    Verifica se o <select> de filtro está oculto (display:none / visibility:hidden).
    Se oculto, localiza e clica no toggle de expansão do DATASUS.

    O padrão de HTML do TabNet é:
      <img onclick="mostra_selecao('S2')" src="ico_mais_t.png"> ou
      <a href="..." onclick="...S2...">UF</a>
    seguido de um <select id="S2"> inicialmente oculto.

    Fallback: se o toggle não for encontrado, usa JavaScript para forçar
    visibilidade (não aciona eventos JS do formulário, mas permite interação).
    """
    try:
        elemento = driver.find_element(By.ID, campo_id)
        # Verifica se está visível via JS (mais confiável que is_displayed do Selenium)
        visivel = driver.execute_script(
            "var el=arguments[0]; var s=window.getComputedStyle(el);"
            "return s.display!=='none' && s.visibility!=='hidden' && el.offsetParent!==null;",
            elemento,
        )
        if visivel:
            return  # já está visível, nada a fazer

        log.info("Filtro id='%s' está oculto → expandindo seção...", campo_id)

        # Tenta localizar o toggle: <img> ou <a> com onclick referenciando o ID
        seletores_toggle = [
            f"//img[contains(@onclick,'{campo_id}')]",
            f"//a[contains(@onclick,'{campo_id}')]",
            f"//span[contains(@onclick,'{campo_id}')]",
            f"//td[contains(@onclick,'{campo_id}')]",
        ]
        toggle = None
        for xpath in seletores_toggle:
            try:
                toggle = driver.find_element(By.XPATH, xpath)
                break
            except NoSuchElementException:
                continue

        if toggle:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", toggle)
            toggle.click()
            # Aguarda o select se tornar visível (até 5s)
            deadline = time.time() + 5
            while time.time() < deadline:
                visivel = driver.execute_script(
                    "var el=arguments[0]; var s=window.getComputedStyle(el);"
                    "return s.display!=='none' && s.visibility!=='hidden';",
                    elemento,
                )
                if visivel:
                    log.info("  Filtro id='%s' expandido com sucesso.", campo_id)
                    return
                time.sleep(0.3)  # polling de visibilidade — sem alternativa nativa
            log.warning("  Toggle clicado mas filtro id='%s' ainda parece oculto.", campo_id)
        else:
            # Fallback: força exibição via JS (não aciona events, mas viabiliza Select API)
            log.warning(
                "Toggle para id='%s' não encontrado. Usando JS para forçar display.", campo_id
            )
            driver.execute_script(
                "var el=arguments[0]; el.style.display=''; el.style.visibility='visible';",
                elemento,
            )

    except Exception as exc:
        log.warning("Erro ao tentar expandir filtro id='%s': %s", campo_id, exc)


def _selecionar_por_js(driver: webdriver.Chrome, campo_id: str, valores: list) -> None:
    """
    Seleciona opções via JavaScript puro.
    Usado como último fallback quando o elemento não é interagível pelo Selenium.
    Suporta seleção por value e por texto visível.
    """
    log.info("  Usando seleção JS para id='%s', valores=%s", campo_id, valores)
    script = """
        var select = document.getElementById(arguments[0]);
        var valores = arguments[1];
        var encontrados = [];
        for (var i = 0; i < select.options.length; i++) {
            var opt = select.options[i];
            if (valores.includes(opt.value) || valores.includes(opt.text.trim())) {
                opt.selected = true;
                encontrados.push(opt.value || opt.text);
            } else {
                opt.selected = false;
            }
        }
        return encontrados;
    """
    selecionados = driver.execute_script(script, campo_id, valores)
    log.info("  JS selecionou: %s", selecionados)


def selecionar_simples(
    driver: webdriver.Chrome, wait: WebDriverWait, campo_id: str, valor: str
) -> None:
    """Seleciona uma única opção em um <select> pelo texto visível."""
    log.info("Campo id='%s' → selecionando: '%s'", campo_id, valor)
    _expandir_filtro_se_oculto(driver, campo_id)
    sel = Select(_aguardar_select(wait, campo_id))
    try:
        sel.select_by_visible_text(valor)
    except NoSuchElementException:
        log.warning("Texto '%s' não encontrado; tentando por value.", valor)
        try:
            sel.select_by_value(valor)
        except (NoSuchElementException, Exception):
            # Último fallback: JS
            _selecionar_por_js(driver, campo_id, [valor])


def selecionar_multiplo(
    driver: webdriver.Chrome, wait: WebDriverWait, campo_id: str, valores: list
) -> None:
    """
    Seleciona múltiplas opções em um <select multiple>.
    - Expande o filtro caso esteja colapsado.
    - Desseleciona tudo antes para garantir estado limpo.
    - Para cada valor: tenta por texto → fallback por value → fallback JS.
    """
    log.info("Campo id='%s' → selecionando múltiplos: %s", campo_id, valores)
    _expandir_filtro_se_oculto(driver, campo_id)
    elemento = _aguardar_select(wait, campo_id)

    try:
        sel = Select(elemento)
        try:
            sel.deselect_all()
        except Exception:
            pass

        falhas = []
        for valor in valores:
            try:
                sel.select_by_visible_text(valor)
                log.info("  ✓ Selecionado por texto: '%s'", valor)
            except NoSuchElementException:
                try:
                    sel.select_by_value(valor)
                    log.info("  ✓ Selecionado por value: '%s'", valor)
                except NoSuchElementException:
                    log.warning("  ✗ '%s' não encontrado via Selenium. Agendando fallback JS.", valor)
                    falhas.append(valor)

        # Para os valores que falharam, usa JS
        if falhas:
            _selecionar_por_js(driver, campo_id, falhas)

    except Exception as exc:
        # Se o Select API falhar completamente (ex: ainda não interagível), usa JS puro
        log.warning("Select API falhou para id='%s': %s. Usando JS.", campo_id, exc)
        _selecionar_por_js(driver, campo_id, valores)


# ---------------------------------------------------------------------------
# Troca de aba / janela
# ---------------------------------------------------------------------------
def trocar_para_nova_aba(
    driver: webdriver.Chrome, handle_original: str, timeout: int = 30
) -> bool:
    """
    Aguarda uma nova aba/janela abrir e troca para ela.
    Usa polling com sleep mínimo (0,5s) — necessário pois window_handles
    não tem wait nativo no Selenium.

    Retorna True se a troca foi bem-sucedida, False caso contrário.
    """
    log.info("Aguardando nova aba abrir (timeout=%ds)...", timeout)
    deadline = time.time() + timeout

    while time.time() < deadline:
        handles = driver.window_handles
        novas = [h for h in handles if h != handle_original]
        if novas:
            driver.switch_to.window(novas[-1])
            log.info("Trocou para nova aba: '%s'", driver.title)
            return True
        # sleep mínimo para polling — sem alternativa nativa no Selenium
        time.sleep(0.5)

    log.warning(
        "Nenhuma nova aba detectada em %ds. Resultado pode estar na aba atual.",
        timeout,
    )
    return False


# ---------------------------------------------------------------------------
# Extração da tabela de resultado
# ---------------------------------------------------------------------------
def _baixar_csv_direto(driver: webdriver.Chrome, base_url: str = "https://tabnet.datasus.gov.br") -> Optional[pd.DataFrame]:
    """
    Estratégia principal de extração: a página de resultado do DATASUS sempre
    expõe um link 'Copia como .CSV'. Este método localiza esse link e navega
    até ele dentro do próprio Chrome (mesma sessão), evitando bloqueios TCP
    que ocorrem com requests direto ao servidor do DATASUS.

    O CSV do DATASUS tem o formato:
        linha 1-N  → metadados (título, filtros, período)  [ignoradas]
        linha X    → cabeçalho real da tabela ("UF";"Qtd.aprovada")
        linha X+1+ → dados
        rodapé     → Fonte, Notas                          [ignoradas]

    Retorna DataFrame ou None se o link não for encontrado ou falhar.
    """
    handle_resultado = driver.current_window_handle
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        link_tag = soup.find("a", string=lambda t: t and ".CSV" in t.upper())
        if not link_tag:
            link_tag = soup.find("a", href=lambda h: h and h.lower().endswith(".csv"))

        if not link_tag:
            log.warning("Link de download .CSV não encontrado na página de resultado.")
            return None

        href = link_tag.get("href", "")
        url_csv = href if href.startswith("http") else base_url + href
        # Usa fetch() dentro do browser (mesma sessão/cookies) em vez de
        # requests que é bloqueado pelo servidor do DATASUS.
        # Os bytes são transferidos como base64 para preservar o encoding latin-1
        # original do arquivo (evita mangling de caracteres especiais quando
        # o browser interpreta erroneamente como UTF-8).
        b64 = driver.execute_async_script(
            """
            const callback = arguments[arguments.length - 1];
            fetch(arguments[0])
                .then(r => r.arrayBuffer())
                .then(buf => {
                    const bytes = new Uint8Array(buf);
                    let binary = '';
                    const chunk = 8192;
                    for (let i = 0; i < bytes.length; i += chunk) {
                        binary += String.fromCharCode(...bytes.slice(i, Math.min(i + chunk, bytes.length)));
                    }
                    callback(btoa(binary));
                })
                .catch(e => callback('__FETCH_ERROR__: ' + e.message));
            """,
            url_csv,
        )

        if not b64 or b64.startswith("__FETCH_ERROR__"):
            log.warning("fetch() falhou: %s", b64)
            return None

        # Decodifica base64 → bytes → string latin-1
        conteudo = base64.b64decode(b64).decode("latin-1", errors="replace")
        linhas = conteudo.splitlines()

        # ------------------------------------------------------------------
        # Detectar a linha do cabeçalho real da tabela:
        # Primeira linha com ";" cujos tokens são todos textuais E a linha
        # seguinte tem ao menos um token numérico (dados reais).
        # ------------------------------------------------------------------
        idx_header = None
        for i, linha in enumerate(linhas):
            if ";" not in linha:
                continue
            tokens = [t.strip().strip('"') for t in linha.split(";")]
            tokens_limpos = [t for t in tokens if t]
            if not tokens_limpos:
                continue
            todos_textuais = all(
                not t.replace(".", "").replace(",", "").replace(" ", "").isdigit()
                for t in tokens_limpos
            )
            if not todos_textuais:
                continue
            for j in range(i + 1, min(i + 5, len(linhas))):
                proxima = linhas[j].strip()
                if not proxima:
                    continue
                tokens_prox = [t.strip().strip('"') for t in proxima.split(";")]
                tem_numero = any(
                    t.replace(".", "").replace(",", "").replace(" ", "").isdigit()
                    for t in tokens_prox if t
                )
                if tem_numero:
                    idx_header = i
                break
            if idx_header is not None:
                break

        if idx_header is None:
            log.warning("Não foi possível detectar o cabeçalho da tabela no CSV.")
            return None

        log.info("Cabeçalho detectado na linha %d: %s", idx_header, linhas[idx_header])

        colunas_esperadas = linhas[idx_header].count(";") + 1
        linhas_tabela = []
        for linha in linhas[idx_header:]:
            if linha.count(";") + 1 == colunas_esperadas:
                linhas_tabela.append(linha)
            elif linhas_tabela:
                break

        csv_limpo = "\n".join(linhas_tabela)
        df = pd.read_csv(
            io.StringIO(csv_limpo),
            sep=";",
            quotechar='"',
            encoding="utf-8",
            on_bad_lines="skip",
        )
        df = df[~df.iloc[:, 0].astype(str).str.strip().str.upper().isin(["TOTAL", ""])]
        df = df.dropna(how="all").reset_index(drop=True)

        log.info("CSV direto carregado: %d linhas, %d colunas.", len(df), len(df.columns))
        return df

    except Exception as exc:
        log.warning("Falha no download direto do CSV: %s", exc)
        # Garante retorno à aba de resultado em caso de erro
        try:
            driver.switch_to.window(handle_resultado)
        except Exception:
            pass
        return None


def _html_para_dataframe(html: str) -> Optional[pd.DataFrame]:
    """
    Extrai a tabela principal de uma página HTML legada do DATASUS.
    Fallback usado quando o link de CSV direto não está disponível.

    Estratégia em cascata:
    1. BeautifulSoup com seleção por class="tabdados" — tabela principal do TabNet.
       O <thead> do DATASUS tem 2 rows: título (colspan) + cabeçalhos reais (th).
       Usamos apenas os <th> para montar o cabeçalho.
    2. pandas.read_html com io.StringIO — fallback genérico.
    """
    # Estratégia 1: BeautifulSoup com class="tabdados"
    try:
        soup = BeautifulSoup(html, "html.parser")
        tabela = soup.find("table", class_="tabdados")

        if tabela:
            # Pega apenas os <th> do thead (ignora a row de título colspan)
            cabecalho = [th.get_text(strip=True) for th in tabela.find_all("th")]

            # Lê apenas as rows do <tbody>
            tbody = tabela.find("tbody") or tabela
            linhas = []
            for tr in tbody.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cols:
                    linhas.append(cols)

            if linhas and cabecalho:
                # Alinha o número de colunas (cabeçalho pode ter mais/menos que os dados)
                n_cols = len(cabecalho)
                linhas_alinhadas = [
                    row[:n_cols] + [""] * max(0, n_cols - len(row)) for row in linhas
                ]
                df = pd.DataFrame(linhas_alinhadas, columns=cabecalho)
                # Remove rodapé "Total" e linhas de Fonte/Notas
                df = df[~df.iloc[:, 0].astype(str).str.strip().str.upper().str.startswith(("TOTAL", "FONTE"))]
                df = df.dropna(how="all").reset_index(drop=True)
                log.info("Tabela extraída via BeautifulSoup/tabdados (%d linhas).", len(df))
                return df

    except Exception as exc:
        log.warning("BeautifulSoup/tabdados falhou (%s). Tentando pandas.read_html...", exc)

    # Estratégia 2: pandas.read_html com io.StringIO (necessário no pandas 3.x)
    try:
        # Tenta com seletor de classe primeiro
        try:
            tabelas = pd.read_html(
                io.StringIO(html),
                attrs={"class": "tabdados"},
                flavor="lxml",
            )
        except Exception:
            tabelas = pd.read_html(io.StringIO(html), flavor="lxml")
            tabelas = [t for t in tabelas if len(t.columns) > 1] or tabelas

        df = max(tabelas, key=lambda t: t.size)
        # Normaliza multi-index de cabeçalho
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                " ".join(str(c) for c in col if "Unnamed" not in str(c)).strip()
                for col in df.columns
            ]
        # A tabela do DATASUS tem a primeira linha como título (colspan) — descarta
        # verificando se a linha 0 tem todos os valores iguais (célula colspan repetida)
        if len(df) > 1:
            primeira = df.iloc[0]
            if primeira.nunique() == 1:
                df = df.iloc[1:].reset_index(drop=True)
        df = df[~df.iloc[:, 0].astype(str).str.strip().str.upper().str.startswith(("TOTAL", "FONTE"))]
        df = df.dropna(how="all").reset_index(drop=True)
        log.info("Tabela extraída via pandas.read_html (%d linhas).", len(df))
        return df

    except Exception as exc:
        log.error("Falha ao extrair tabela: %s", exc)
        return None


def extrair_resultado(
    driver: webdriver.Chrome, wait: WebDriverWait
) -> Optional[pd.DataFrame]:
    """
    Aguarda o resultado carregar e extrai os dados.

    Estratégia em cascata:
    1. Download direto do arquivo .CSV exposto na página de resultado.
    2. Parsing do HTML via pandas.read_html + BeautifulSoup como fallback.
    """
    try:
        wait.until(
            EC.presence_of_element_located((By.TAG_NAME, "table")),
            message="Tabela de resultado não encontrada na página de resultado.",
        )
    except TimeoutException:
        log.warning("Timeout aguardando <table>. Tentará extrair mesmo assim.")

    # Estratégia 1: CSV direto (mais confiável e sem parsing de HTML)
    df = _baixar_csv_direto(driver)
    if df is not None and not df.empty:
        return df

    # Estratégia 2: Parsing do HTML da página
    log.info("Usando fallback: parsing do HTML da página de resultado.")
    return _html_para_dataframe(driver.page_source)


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------
def salvar_excel(df: pd.DataFrame, prefixo: str = "resultado_datasus") -> str:
    """
    Salva o DataFrame como Excel (.xlsx) na pasta downloads/.
    Usa openpyxl como engine.
    Retorna o caminho absoluto do arquivo salvo.
    """
    Path(DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    caminho = os.path.join(DOWNLOADS_DIR, f"{prefixo}.xlsx")
    df.to_excel(caminho, index=False, engine="openpyxl")
    log.info("Excel salvo em: %s", caminho)
    return caminho


def salvar_csv(df: pd.DataFrame, prefixo: str = "resultado_datasus") -> str:
    """
    Salva o DataFrame como CSV na pasta downloads/.
    Usa encoding UTF-8-BOM (utf-8-sig) para compatibilidade com Excel.
    Retorna o caminho absoluto do arquivo salvo.
    """
    Path(DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = os.path.join(DOWNLOADS_DIR, f"{prefixo}_{timestamp}.csv")
    df.to_csv(caminho, index=False, encoding="utf-8-sig", sep=";")
    log.info("CSV salvo em: %s", caminho)
    return caminho


# ---------------------------------------------------------------------------
# Descoberta de períodos disponíveis
# ---------------------------------------------------------------------------
def listar_periodos(headless: bool = True) -> list:
    """
    Abre o DATASUS, lê todas as opções do select id='A' (Arquivos/Períodos)
    e retorna lista de dicts com {"value": "qabr2601.dbf", "label": "Jan/2026"}.
    """
    driver = configurar_driver(headless=headless)
    try:
        log.info("Listando períodos disponíveis no DATASUS...")
        driver.get(URL_DATASUS)
        wait = WebDriverWait(driver, WAIT_TIMEOUT, poll_frequency=0.5)
        wait.until(
            EC.presence_of_element_located((By.ID, CAMPO_IDS["linha"])),
            message="Formulário não carregou ao listar períodos.",
        )
        _expandir_filtro_se_oculto(driver, CAMPO_IDS["periodos"])
        sel = Select(driver.find_element(By.ID, CAMPO_IDS["periodos"]))
        periodos = [
            {"value": opt.get_attribute("value"), "label": opt.text.strip()}
            for opt in sel.options
            if opt.get_attribute("value")
        ]
        log.info("%d períodos encontrados.", len(periodos))
        return periodos
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def executar_consulta(
    linha: str,
    coluna: str,
    conteudo: list,
    periodos: list,
    regiao: Optional[list] = None,
    uf: Optional[list] = None,
    municipio: Optional[list] = None,
    subgrupo_proced: Optional[list] = None,
    headless: bool = False,
    manter_navegador: bool = False,
    prefixo: Optional[str] = None,
) -> list:
    """
    Executa consulta completa no DATASUS TabNet.

    Args:
        linha:           Valor para o campo Linha (ex: "UF").
        coluna:          Valor para o campo Coluna (ex: "--Não-Ativa--").
        conteudo:        Lista de conteúdos selecionáveis (ex: ["Qtd.aprovada"]).
        periodos:        Lista de períodos disponíveis (ex: ["qabr2601.dbf"]).
        regiao:          Lista de regiões para filtro (opcional).
        uf:              Lista de códigos de UF para filtro (ex: ["16"] = Paraná).
        municipio:       Lista de municípios para filtro (opcional).
        subgrupo_proced: Lista de subgrupos de procedimento (ex: ["22"] = 0306 Hemoterapia).
        headless:        Se True, executa Edge sem interface gráfica.
        manter_navegador: Se True, não fecha o Edge ao final (útil para inspeção manual).

    Returns:
        Lista de dicionários com os dados extraídos.
        Também salva automaticamente um arquivo CSV em data/processed/.
    """
    driver = configurar_driver(headless=headless)
    wait = WebDriverWait(driver, WAIT_TIMEOUT, poll_frequency=0.5)

    try:
        # ------------------------------------------------------------------
        # 1. Abrir página
        # ------------------------------------------------------------------
        log.info("Acessando: %s", URL_DATASUS)
        driver.get(URL_DATASUS)

        # Aguarda o campo Linha estar presente — confirma que o formulário carregou
        wait.until(
            EC.presence_of_element_located((By.ID, CAMPO_IDS["linha"])),
            message="Formulário principal não carregou (campo Linha ausente).",
        )
        log.info("Página carregada: '%s'", driver.title)

        # ------------------------------------------------------------------
        # 2. Selecionar Linha
        # ------------------------------------------------------------------
        selecionar_simples(driver, wait, CAMPO_IDS["linha"], linha)

        # ------------------------------------------------------------------
        # 3. Selecionar Coluna
        # ------------------------------------------------------------------
        selecionar_simples(driver, wait, CAMPO_IDS["coluna"], coluna)

        # ------------------------------------------------------------------
        # 4. Selecionar Conteúdo (múltiplo)
        # ------------------------------------------------------------------
        selecionar_multiplo(driver, wait, CAMPO_IDS["conteudo"], conteudo)

        # ------------------------------------------------------------------
        # 5. Selecionar Períodos (múltiplo)
        # ------------------------------------------------------------------
        selecionar_multiplo(driver, wait, CAMPO_IDS["periodos"], periodos)

        # ------------------------------------------------------------------
        # 6. Filtros opcionais
        # ------------------------------------------------------------------
        if regiao:
            selecionar_multiplo(driver, wait, CAMPO_IDS["regiao"], regiao)

        if uf:
            selecionar_multiplo(driver, wait, CAMPO_IDS["uf"], uf)

        if municipio:
            selecionar_multiplo(driver, wait, CAMPO_IDS["municipio"], municipio)

        if subgrupo_proced:
            selecionar_multiplo(driver, wait, CAMPO_IDS["subgrupo_proced"], subgrupo_proced)

        # ------------------------------------------------------------------
        # 7. Registrar handle atual antes de submeter (para detectar nova aba)
        # ------------------------------------------------------------------
        handle_original = driver.current_window_handle

        # ------------------------------------------------------------------
        # 8. Clicar no botão "Mostra" para executar a consulta
        # ------------------------------------------------------------------
        log.info("Clicando no botão 'Mostra'...")
        botao = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@type='submit' and contains(@value,'Mostra')]")
            ),
            message="Botão 'Mostra' não encontrado ou não está clicável.",
        )
        botao.click()

        # ------------------------------------------------------------------
        # 9. Trocar para nova aba (resultado abre em target="_blank")
        # ------------------------------------------------------------------
        trocou = trocar_para_nova_aba(driver, handle_original, timeout=WAIT_TIMEOUT)
        if not trocou:
            log.warning("Prosseguindo na aba atual como fallback.")

        # ------------------------------------------------------------------
        # 10. Extrair tabela de resultado
        # ------------------------------------------------------------------
        log.info("Extraindo tabela de resultado...")
        df = extrair_resultado(driver, wait)

        if df is None or df.empty:
            log.error("Nenhum dado encontrado na página de resultado.")
            return []

        # ------------------------------------------------------------------
        # 11. Salvar Excel na pasta downloads/
        # ------------------------------------------------------------------
        if prefixo is None:
            prefixo = (
                f"resultado_{periodos[0].replace('.dbf', '')}"
                if len(periodos) == 1
                else "resultado_datasus"
            )
        salvar_excel(df, prefixo=prefixo)

        # ------------------------------------------------------------------
        # 12. Retornar como lista de dicionários
        # ------------------------------------------------------------------
        registros = df.to_dict(orient="records")
        log.info("Consulta concluída com sucesso. %d registros obtidos.", len(registros))
        return registros

    except TimeoutException as exc:
        log.error("Timeout durante execução da consulta: %s", exc)
        raise

    except WebDriverException as exc:
        log.error("Erro do WebDriver: %s", exc)
        raise

    except Exception as exc:
        log.error("Erro inesperado: %s", exc)
        raise

    finally:
        if manter_navegador:
            log.info("Navegador mantido aberto (manter_navegador=True).")
        else:
            driver.quit()
            log.info("Driver encerrado.")


# ---------------------------------------------------------------------------
# Exemplo de uso direto
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    resultados = executar_consulta(
        linha="UF",
        coluna="--Não-Ativa--",
        conteudo=["Qtd.aprovada"],
        periodos=["qabr2601.dbf"],
        uf=["16"],                  # 16 = Paraná
        subgrupo_proced=["22"],     # 22 = 0306 Hemoterapia
        headless=False,
        manter_navegador=True,
    )

    print(f"\n{len(resultados)} registros retornados.")
    for registro in resultados[:5]:
        print(registro)
