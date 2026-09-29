import datetime
import urllib.parse
import pandas as pd
import streamlit as st
import json
import gspread

st.set_page_config(page_title="Controle de Despesas", page_icon="💰", layout="wide")
st.title("💡 Gestão de Despesas e Solicitações")
st.markdown("---")

# ---------------------------------------------------------
# CONEXÃO COM O GOOGLE SHEETS
# ---------------------------------------------------------
@st.cache_resource
def conectar_planilha():
    # Lê a chave secreta guardada no cofre do Streamlit
    cred_dict = json.loads(st.secrets["google_credentials"])
    gc = gspread.service_account_from_dict(cred_dict)
    # Abre a planilha pelo nome exato (deve estar idêntico ao do Google Drive)
    sh = gc.open("Controle Despesas Filhas")
    return sh.sheet1

# Conecta e carrega os dados
planilha = conectar_planilha()

def carregar_dados():
    registros = planilha.get_all_records()
    if not registros:
        return pd.DataFrame(columns=["ID", "Data", "Filha", "Valor Solicitado", "Objetivo", "Status", "Valor Pago", "Observacao"])
    
    df_temp = pd.DataFrame(registros)
    # Formata datas e números para o sistema entender
    df_temp["Data"] = pd.to_datetime(df_temp["Data"], format="%d/%m/%Y", errors="coerce").dt.date
    df_temp["Valor Solicitado"] = pd.to_numeric(df_temp["Valor Solicitado"].replace({',': '.'}, regex=True), errors='coerce')
    df_temp["Valor Pago"] = pd.to_numeric(df_temp["Valor Pago"].replace({',': '.'}, regex=True), errors='coerce')
    return df_temp

df = carregar_dados()

# ---------------------------------------------------------
# MENU DE PERFIL
# ---------------------------------------------------------
st.sidebar.header("👤 Quem está acessando?")
perfil = st.sidebar.radio("Selecione o seu perfil:", ["Filha (Fazer Pedido)", "Regina / Gestora (Painel & Aprovação)", "Visualizar Painel / Gráficos"])

# ---------------------------------------------------------
# TELA 1: FILHA
# ---------------------------------------------------------
if perfil == "Filha (Fazer Pedido)":
  st.subheader("📝 Nova Solicitação de Valor")
  with st.form("form_pedido", clear_on_submit=True):
    nome_filha = st.selectbox("Quem está pedindo?", ["Lorena", "Estela"])
    valor_solicitado = st.number_input("Valor solicitado (R$)", min_value=0.01, format="%.2f", step=1.00)
    data_pedido = st.date_input("Data necessária", value=datetime.date.today(), format="DD/MM/YYYY")
    objetivo = st.selectbox(
    "Objetivo / Destinação", 
    ["Lanche da Escola", "Transporte/Uber", "Roupas", "Passeio/Lazer", "Outros"]
)
    botao_enviar = st.form_submit_button("Enviar Solicitação")

    if botao_enviar:
      if valor_solicitado > 0 and objetivo.strip() != "":
        novo_id = int(df["ID"].max() + 1) if not df.empty and pd.notna(df["ID"].max()) else 1
        
        # Salva NA PLANILHA DO GOOGLE
        planilha.append_row([
            novo_id, 
            data_pedido.strftime("%d/%m/%Y"), 
            nome_filha, 
            float(valor_solicitado), 
            objetivo.strip(), 
            "Pendente", 
            0.0, 
            ""
        ])
        
        st.success("✅ Pedido gravado na planilha! Clique no botão abaixo para avisar a Regina:")
        numero_regina = "5511992506787"
        mensagem = f"Olá Regina! A {nome_filha} solicitou R$ {valor_solicitado:.2f} para '{objetivo.strip()}' em {data_pedido.strftime('%d/%m/%Y')}."
        link_zap = f"https://wa.me/{numero_regina}?text={urllib.parse.quote(mensagem)}"
        st.markdown(f'<a href="{link_zap}" target="_blank"><button style="background-color:#25D366; color:white; padding:12px 24px; border:none; border-radius:6px; font-size:16px; font-weight: bold; cursor: pointer; text-decoration: none;">📲 Avisar Regina no WhatsApp</button></a>', unsafe_allow_html=True)
      else:
        st.error("⚠️ Preencha o valor e o objetivo corretamente.")

# ---------------------------------------------------------
# TELA 2: REGINA
# ---------------------------------------------------------
elif perfil == "Regina / Gestora (Painel & Aprovação)":
  st.subheader("⚙️ Painel de Gestão e Aprovação (Regina)")
  if df.empty:
    st.info("Nenhuma solicitação registrada.")
  else:
    st.dataframe(df, use_container_width=True, column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "Valor Solicitado": st.column_config.NumberColumn("Valor Solicitado", format="R$ %.2f"),
        "Valor Pago": st.column_config.NumberColumn("Valor Pago", format="R$ %.2f")
    })

    st.write("### Atualizar Status")
    id_escolhido = st.selectbox("Selecione o ID da solicitação:", df["ID"].tolist())
    linha_selecionada = df[df["ID"] == id_escolhido].iloc[0]

    st.info(f"**Detalhes:** {linha_selecionada['Filha']} pediu R$ {linha_selecionada['Valor Solicitado']:.2f} para *{linha_selecionada['Objetivo']}*")
    
    status_opcoes = ["Pendente", "Aprovado", "Alterado", "Negado"]
    status_atual = linha_selecionada["Status"] if linha_selecionada["Status"] in status_opcoes else "Pendente"
    
    with st.form("form_atualizacao"):
      novo_status = st.selectbox("Novo Status", status_opcoes, index=status_opcoes.index(status_atual))
      valor_pago = st.number_input("Valor Pago/Liberado (R$)", value=float(linha_selecionada["Valor Pago"]) if linha_selecionada["Valor Pago"] > 0 else float(linha_selecionada["Valor Solicitado"]), format="%.2f")
      observacao = st.text_input("Observação", value=str(linha_selecionada["Observacao"]))
      if st.form_submit_button("Salvar Alteração na Planilha"):
        # Encontra a linha exata na planilha pelo ID
        celula = planilha.find(str(id_escolhido), in_column=1)
        if celula:
          planilha.update_cell(celula.row, 6, novo_status)
          planilha.update_cell(celula.row, 7, float(valor_pago))
          planilha.update_cell(celula.row, 8, observacao.strip())
          st.success("✅ Atualizado com sucesso!")
          # Atualiza a página
          st.rerun()

# ---------------------------------------------------------
# TELA 3: GRÁFICOS
# ---------------------------------------------------------
else:
  st.subheader("📊 Dashboard de Gastos")
  if df.empty:
    st.info("Ainda não há dados.")
  else:
    total_solicitado = df["Valor Solicitado"].sum()
    df_aprovados = df[df["Status"].isin(["Aprovado", "Alterado"])]
    total_pago = df_aprovados["Valor Pago"].sum() if not df_aprovados.empty else 0.0

    col1, col2 = st.columns(2)
    col1.metric("Total Solicitado Geral", f"R$ {total_solicitado:.2f}")
    col2.metric("Total Efetivamente Pago", f"R$ {total_pago:.2f}")

    if not df_aprovados.empty:
      st.write("### 👧 Gastos Totais por Filha (Aprovados/Alterados)")
      st.bar_chart(df_aprovados.groupby("Filha")["Valor Pago"].sum())
