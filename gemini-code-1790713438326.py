import datetime
import urllib.parse
import pandas as pd
import streamlit as st
import json
import gspread

# Configuração inicial da página
st.set_page_config(page_title="Controle de Despesas", page_icon="💰", layout="wide")
st.title("💡 Gestão de Despesas e Solicitações")
st.markdown("---")

# ---------------------------------------------------------
# CONEXÃO COM O GOOGLE SHEETS
# ---------------------------------------------------------
@st.cache_resource
def conectar_planilha():
    cred_dict = json.loads(st.secrets["google_credentials"])
    gc = gspread.service_account_from_dict(cred_dict)
    sh = gc.open("Controle Despesas Filhas")
    return sh, sh.sheet1

# Retorna a planilha inteira (sh) e a aba principal (sheet1)
sh, planilha = conectar_planilha()

def carregar_dados():
    registros = planilha.get_all_records()
    if not registros:
        return pd.DataFrame(columns=["ID", "Data", "Filha", "Valor Solicitado", "Objetivo", "Status", "Valor Pago", "Observacao", "Descricao Pedido"])
    
    df_temp = pd.DataFrame(registros)
    
    if "Descricao Pedido" not in df_temp.columns:
        df_temp["Descricao Pedido"] = ""

    df_temp["Data"] = pd.to_datetime(df_temp["Data"], format="%d/%m/%Y", errors="coerce").dt.date
    
    def limpar_moeda(valor):
        if pd.isna(valor) or valor == "": return 0.0
        if isinstance(valor, (int, float)): return float(valor)
        v_str = str(valor).replace("R$", "").replace(" ", "").replace("\xa0", "").strip()
        if "," in v_str:
            v_str = v_str.replace(".", "").replace(",", ".")
        try:
            return float(v_str)
        except:
            return 0.0

    df_temp["Valor Solicitado"] = df_temp["Valor Solicitado"].apply(limpar_moeda)
    df_temp["Valor Pago"] = df_temp["Valor Pago"].apply(limpar_moeda)
    return df_temp

df = carregar_dados()

# ---------------------------------------------------------
# MENU DE PERFIL
# ---------------------------------------------------------
st.sidebar.header("👤 Quem está acessando?")
perfil = st.sidebar.radio("Selecione o seu perfil:", ["Filha (Fazer Pedido)", "Responsável (Painel & Aprovação)", "Visualizar Painel / Gráficos"])

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
        ["Lanche da Escola", "Transporte/Uber", "Material Escolar", "Passeio/Lazer", "Vestuário", "Outros"]
    )
    
    descricao_pedido = st.text_input("Descrição do pedido (Opcional - ex: Livro de Biologia, Lanche na padaria)")
    
    botao_enviar = st.form_submit_button("Enviar Solicitação")

    if botao_enviar:
      if valor_solicitado > 0:
        novo_id = int(df["ID"].max() + 1) if not df.empty and pd.notna(df["ID"].max()) else 1
        
        planilha.append_row([
            novo_id, 
            data_pedido.strftime("%d/%m/%Y"), 
            nome_filha, 
            float(valor_solicitado), 
            objetivo, 
            "Pendente", 
            0.0, 
            "", 
            descricao_pedido.strip()
        ])
        
        st.success("✅ Pedido gravado na planilha! Clique no botão abaixo para avisar:")
        
        numero_responsavel = "5511992506787"
        url_do_app = "https://controle-gastos-piolhos.streamlit.app/#dashboard-de-gastos" 
        
        detalhe_msg = f" ({descricao_pedido.strip()})" if descricao_pedido.strip() else ""
        mensagem = (
            f"Olá! A {nome_filha} solicitou R$ {valor_solicitado:.2f} para"
            f" '{objetivo}'{detalhe_msg} em {data_pedido.strftime('%d/%m/%Y')}.\n\n"
            f"👉 Acesse o painel para aprovar ou alterar: {url_do_app}"
        )
        link_zap = f"https://wa.me/{numero_responsavel}?text={urllib.parse.quote(mensagem)}"
        
        st.markdown(f'<a href="{link_zap}" target="_blank"><button style="background-color:#25D366; color:white; padding:12px 24px; border:none; border-radius:6px; font-size:16px; font-weight: bold; cursor: pointer; text-decoration: none;">📲 Avisar Responsável no WhatsApp</button></a>', unsafe_allow_html=True)
      else:
        st.error("⚠ Preencha o valor corretamente.")

# ---------------------------------------------------------
# TELA 2: RESPONSÁVEL
# ---------------------------------------------------------
elif perfil == "Responsável (Painel & Aprovação)":
  st.subheader("⚙️ Painel de Gestão e Aprovação (Responsável)")
  if df.empty:
    st.info("Nenhuma solicitação registrada.")
  else:
    df_reverso = df.sort_values(by="ID", ascending=False)
    
    st.dataframe(df_reverso, height=250, use_container_width=True, column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "Valor Solicitado": st.column_config.NumberColumn("Valor Solicitado", format="R$ %.2f"),
        "Valor Pago": st.column_config.NumberColumn("Valor Pago", format="R$ %.2f")
    })

    st.markdown("---")
    st.write("### 📝 Atualizar Status ou Valor")
    
    opcoes_dropdown = []
    for index, row in df_reverso.iterrows():
        desc_extra = f" - {row['Descricao Pedido']}" if pd.notna(row['Descricao Pedido']) and row['Descricao Pedido'] != "" else ""
        texto = f"ID {row['ID']} | {row['Status']} | {row['Filha']} | R$ {row['Valor Solicitado']:.2f} ({row['Objetivo']}{desc_extra})"
        opcoes_dropdown.append(texto)
        
    st.write("**Selecione qual pedido deseja gerenciar:**")
    col_selecao, col_botao_apagar = st.columns([4, 1])
    
    with col_selecao:
        escolha_texto = st.selectbox("ID", opcoes_dropdown, label_visibility="collapsed")
        id_escolhido = int(escolha_texto.split("|")[0].replace("ID", "").strip())
        linha_selecionada = df[df["ID"] == id_escolhido].iloc[0]
        
    with col_botao_apagar:
        with st.expander("🗑️ Apagar"):
            if st.button("Confirmar", key="btn_apagar"):
                celula = planilha.find(str(id_escolhido), in_column=1)
                if celula:
                    # Correção aplicada: deleta a linha corretamente utilizando a aba referenciada
                    planilha.delete_rows(celula.row)
                    st.success("✅ Apagado!")
                    st.rerun()
    
    if pd.notna(linha_selecionada['Descricao Pedido']) and linha_selecionada['Descricao Pedido'] != "":
        st.info(f"📌 **Detalhes informados pela filha:** {linha_selecionada['Descricao Pedido']}")

    status_opcoes = ["Pendente", "Aprovado", "Alterado", "Negado"]
    status_atual = linha_selecionada["Status"] if linha_selecionada["Status"] in status_opcoes else "Pendente"
    
    with st.form("form_atualizacao"):
      novo_status = st.selectbox("Novo Status", status_opcoes, index=status_opcoes.index(status_atual))
      
      col1, col2 = st.columns(2)
      novo_valor_solicitado = col1.number_input("Corrigir Valor Solicitado (R$)", value=float(linha_selecionada["Valor Solicitado"]), format="%.2f")
      valor_pago = col2.number_input("Valor Pago/Liberado (R$)", value=float(linha_selecionada["Valor Pago"]) if linha_selecionada["Valor Pago"] > 0 else float(linha_selecionada["Valor Solicitado"]), format="%.2f")
      
      observacao = st.text_input("Observação (Motivo de alteração/negação ou dados do PIX)", value=str(linha_selecionada["Observacao"]))
      
      if st.form_submit_button("Salvar Alteração na Planilha"):
        celula = planilha.find(str(id_escolhido), in_column=1)
        if celula:
          planilha.update_cell(celula.row, 4, float(novo_valor_solicitado))
          planilha.update_cell(celula.row, 6, novo_status)
          planilha.update_cell(celula.row, 7, float(valor_pago))
          planilha.update_cell(celula.row, 8, observacao.strip())
          st.success("✅ Atualizado com sucesso!")
          st.rerun()

# ---------------------------------------------------------
# TELA 3: GRÁFICOS
# ---------------------------------------------------------
else:
  st.subheader("📊 Dashboard de Gastos e Destinação dos Recursos")
  if df.empty:
    st.info("Ainda não há dados suficientes para gerar gráficos.")
  else:
    total_solicitado = df["Valor Solicitado"].sum()
    df_aprovados = df[df["Status"].isin(["Aprovado", "Alterado"])]
    total_pago = df_aprovados["Valor Pago"].sum() if not df_aprovados.empty else 0.0

    col1, col2 = st.columns(2)
    col1.metric("Total Solicitado Geral", f"R$ {total_solicitado:.2f}")
    col2.metric("Total Efetivamente Pago", f"R$ {total_pago:.2f}")

    st.markdown("---")

    if not df_aprovados.empty:
      st.write("### 👧 Gastos Totais por Filha (Aprovados/Alterados)")
      st.bar_chart(df_aprovados.groupby("Filha")["Valor Pago"].sum())
    else:
      st.info("Nenhum gasto aprovado registrado ainda para exibir no gráfico.")

    st.write("### 📋 Histórico Consolidado Completo")
    st.dataframe(
        df.sort_values(by="ID", ascending=False), 
        use_container_width=True,
        column_config={
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "Valor Solicitado": st.column_config.NumberColumn("Valor Solicitado", format="R$ %.2f"),
            "Valor Pago": st.column_config.NumberColumn("Valor Pago", format="R$ %.2f")
        }
    )
