import streamlit as st
import pandas as pd
import numpy as np

# Nomes dos meses em português para facilitar a visualização
MESES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}
MESES_ABREVIADOS = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
    7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
}

# Configuração inicial da página
st.set_page_config(
    page_title="Dashboard Banco de Sangue DATASUS", 
    page_icon="🩸",
    layout="wide"
)

# Título do Dashboard
st.title("🩸 Dashboard do Banco de Sangue (DATASUS)")
st.markdown("Analise as tendências de doações de sangue. Compare o volume de doações entre diferentes meses e anos.")

# ==========================================
# 1. FUNÇÃO PARA CARREGAR DADOS (DATASUS)
# ==========================================
CONSOLIDADO = "Hemoterapia_Parana_CONSOLIDADO.xlsx"


def _caminho_consolidado():
    """Usa o consolidado gerado pela extração (downloads/) e cai para a cópia
    versionada na raiz do projeto quando ele ainda não existe."""
    from pathlib import Path
    try:
        from config.config import DOWNLOADS_DIR
        gerado = Path(DOWNLOADS_DIR) / CONSOLIDADO
        if gerado.exists():
            return gerado
    except Exception:
        pass
    return Path(__file__).resolve().parent / CONSOLIDADO


@st.cache_data
def load_data():
    # Lendo o dataset real extraído do DATASUS.
    df = pd.read_excel(_caminho_consolidado(), engine="openpyxl")
    
    # Tratamento de dados
    # Total pode conter strings ou caracteres como '-'
    df['Total'] = pd.to_numeric(df['Total'], errors='coerce').fillna(0)
    
    # O período vem no formato 'Abr/2008'
    df[['Mes_str', 'Ano']] = df['Periodo'].str.split('/', expand=True)
    df['Ano'] = df['Ano'].astype(int)
    
    # Mapeamento reverso dos meses
    MAPA_MESES_REVERSO = {
        v: k for k, v in MESES_ABREVIADOS.items()
    }
    df['Mês'] = df['Mes_str'].map(MAPA_MESES_REVERSO)
    
    # Agrupando para somar todas as doações (ignorando o detalhe de município para o dashboard principal)
    df_agrupado = df.groupby(['Ano', 'Mês'], as_index=False)['Total'].sum()
    df_agrupado.rename(columns={'Total': 'Qtd_Doacoes'}, inplace=True)
    
    # Adiciona colunas auxiliares com o nome do mês
    df_agrupado['Nome do Mês'] = df_agrupado['Mês'].map(MESES_PT)
    return df_agrupado

df = load_data()

# ==========================================
# 2. BARRA LATERAL (FILTROS)
# ==========================================
st.sidebar.header("Filtros de Análise 📊")

anos_disponiveis = sorted(df['Ano'].unique())
meses_disponiveis = sorted(df['Mês'].unique())

# Filtro de Ano (Comparação)
st.sidebar.subheader("Comparação de Anos")
anos_selecionados = st.sidebar.multiselect(
    "Selecione os anos:",
    options=anos_disponiveis,
    default=anos_disponiveis[-2:] # Pega os 2 últimos anos por padrão
)

# Filtro de Mês
st.sidebar.subheader("Filtrar por Mês")
meses_selecionados = st.sidebar.multiselect(
    "Selecione os meses:",
    options=meses_disponiveis,
    format_func=lambda x: MESES_PT[x],
    default=meses_disponiveis
)

st.sidebar.markdown("---")
st.sidebar.info("💡 **Dica:** Utilize os filtros acima para comparar o desempenho das doações de sangue no tempo. Você pode comparar vários anos usando o filtro de Anos.")


# ==========================================
# 3. PROCESSAMENTO DOS DADOS FILTRADOS
# ==========================================
df_filtrado = df[
    (df['Ano'].isin(anos_selecionados)) & 
    (df['Mês'].isin(meses_selecionados))
]

# Parar a execução se o filtro ficar vazio
if df_filtrado.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados. Por favor, ajuste as opções na barra lateral.")
    st.stop()


# ==========================================
# 4. ATUALIZAÇÃO DE DADOS (EXTRAÇÃO)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Atualização de Dados")
with st.sidebar.expander("Atualizar base do DATASUS"):
    st.warning("A extração de dados pode levar vários minutos e executará o bot em segundo plano.")
    confirmacao = st.checkbox("Confirmo que desejo buscar novos dados")
    
    if st.button("Iniciar Extração", disabled=not confirmacao):
        with st.spinner("Extraindo e consolidando dados... Aguarde."):
            import subprocess
            import sys
            try:
                # Chama o script extrair_todos em um subprocesso para evitar block total da UI e problemas com multiprocessamento do Streamlit
                result = subprocess.run(
                    [sys.executable, "extrair_todos.py"], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                if result.returncode == 0:
                    st.success("Extração finalizada com sucesso! A página será atualizada.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Ocorreu um erro durante a extração.")
                    st.code(result.stderr[-1000:] if result.stderr else "Erro desconhecido")
            except Exception as e:
                st.error(f"Erro ao tentar rodar a extração: {e}")

# ==========================================
# 5. MÉTRICAS PRINCIPAIS (KPIs)
# ==========================================
st.subheader("Resumo das Doações")
col1, col2, col3 = st.columns(3)

# Calculando métricas
total_doacoes = df_filtrado['Qtd_Doacoes'].sum()
mes_campeao = df_filtrado.loc[df_filtrado['Qtd_Doacoes'].idxmax()]

col1.metric("Total de Doações (Período Filtrado)", f"{total_doacoes:,.0f}".replace(',', '.'))
col2.metric(
    "Mês com Mais Doações (Recorde)", 
    f"{mes_campeao['Nome do Mês']} ({mes_campeao['Ano']})", 
    f"{mes_campeao['Qtd_Doacoes']:,.0f}".replace(',', '.')
)

# Lógica para comparar o último ano da seleção com o ano anterior da seleção
if len(anos_selecionados) >= 2:
    ano_recente = sorted(anos_selecionados)[-1]
    ano_anterior = sorted(anos_selecionados)[-2]
    
    total_recente = df_filtrado[df_filtrado['Ano'] == ano_recente]['Qtd_Doacoes'].sum()
    total_anterior = df_filtrado[df_filtrado['Ano'] == ano_anterior]['Qtd_Doacoes'].sum()
    
    if total_anterior > 0:
        variacao_pct = ((total_recente - total_anterior) / total_anterior) * 100
        col3.metric(
            f"Variação: {ano_recente} vs {ano_anterior}", 
            f"{total_recente:,.0f}".replace(',', '.'), 
            f"{variacao_pct:.1f}%"
        )
else:
    col3.metric("Média Mensal de Doações", f"{df_filtrado['Qtd_Doacoes'].mean():,.0f}".replace(',', '.'))

st.markdown("---")


# ==========================================
# 5. GRÁFICOS E VISUALIZAÇÕES
# ==========================================

tab1, tab2 = st.tabs(["Comparativo Anual por Mês", "Acumulado por Mês"])

with tab1:
    # Gráfico 1: Comparação de Linhas entre os Anos (Eixo X = Meses, Linhas = Anos)
    st.subheader("Comparativo Mensal (Ano a Ano)")
    st.text("Compare o desempenho de cada ano ao longo dos meses.")

    # Tabela dinâmica para colocar Meses nas Linhas e Anos nas Colunas
    df_pivot = df_filtrado.pivot_table(
        index='Mês', 
        columns='Ano', 
        values='Qtd_Doacoes', 
        aggfunc='sum'
    )
    # Alterar o formato do índice (Eixo X) para mostrar os nomes abreviados
    df_pivot.index = df_pivot.index.map(MESES_ABREVIADOS)

    st.line_chart(df_pivot)

with tab2:
    # Gráfico 2: Total acumulado (somando todos os anos selecionados) por mês
    st.subheader("Meses com Maior Volume de Doação (Agregado)")
    st.text("Somatório total das doações por mês nos anos selecionados.")

    df_agrupado_mes = df_filtrado.groupby('Mês')['Qtd_Doacoes'].sum().reset_index()
    df_agrupado_mes['Mês_Abrev'] = df_agrupado_mes['Mês'].map(MESES_ABREVIADOS)
    df_agrupado_mes = df_agrupado_mes.set_index('Mês_Abrev')

    st.bar_chart(df_agrupado_mes['Qtd_Doacoes'], color="#cf142b") # Vermelho do Sangue

st.caption("Nota: dados reais extraídos do TabNet do DATASUS (Produção Ambulatorial SUS, subgrupo 0306 - Hemoterapia, quantidade aprovada), filtrados para o Paraná. O arquivo consolidado é atualizado ao rodar `extrair_todos.py`.")