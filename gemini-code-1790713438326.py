import datetime
import urllib.parse
import pandas as pd
import streamlit as st

# Configuração inicial da página
st.set_page_config(
    page_title="Controle de Despesas - Família", page_icon="💰", layout="wide"
)

st.title("💡 Gestão de Despesas e Solicitações")
st.markdown("---")

# ---------------------------------------------------------
# INICIALIZAÇÃO SEGURA DO "BANCO DE DADOS" (Session State)
# ---------------------------------------------------------
if "dados" not in st.session_state:
  st.session_state["dados"] = pd.DataFrame({
      "ID": [1, 2],
      "Data": [
          datetime.date(2026, 9, 10),
          datetime.date(2026, 9, 25),
      ],
      "Filha": ["Filha A", "Filha B"],
      "Valor Solicitado": [45.00, 120.00],
      "Objetivo": ["Lanche da escola", "Material escolar"],
      "Status": ["Aprovado", "Pendente"],
      "Valor Pago": [45.00, 0.00],
      "Observacao": ["Pix efetuado", "Aguardando confirmação"],
  })

# Garantir que a coluna de data seja sempre do tipo data correta
st.session_state["dados"]["Data"] = pd.to_datetime(
    st.session_state["dados"]["Data"]
).dt.date
df = st.session_state["dados"]

# ---------------------------------------------------------
# MENU DE SELEÇÃO DE PERFIL
# ---------------------------------------------------------
st.sidebar.header("👤 Quem está acessando?")
perfil = st.sidebar.radio(
    "Selecione o seu perfil:",
    [
        "Filha (Fazer Pedido)",
        "Regina / Gestora (Painel & Aprovação)",
        "Visualizar Painel / Gráficos",
    ],
)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Dica:** O sistema registra os pedidos e gera um atalho rápido para "
    "aviso via WhatsApp."
)

# ---------------------------------------------------------
# TELA 1: FILHA - FAZER SOLICITAÇÃO
# ---------------------------------------------------------
if perfil == "Filha (Fazer Pedido)":
  st.subheader("📝 Nova Solicitação de Valor")

  with st.form("form_pedido", clear_on_submit=True):
    nome_filha = st.selectbox("Quem está pedindo?", ["Filha A", "Filha B"])
    valor_solicitado = st.number_input(
        "Valor solicitado (R$)", min_value=0.01, format="%.2f", step=1.00
    )
    data_pedido = st.date_input(
        "Data necessária", value=datetime.date.today()
    )
    objetivo = st.text_input(
        "Objetivo / Destinação (ex: Lanche, Xerox, Livro, Transporte)"
    )

    botao_enviar = st.form_submit_button("Enviar Solicitação")

    if botao_enviar:
      if valor_solicitado > 0 and objetivo.strip() != "":
        # Gerar ID sequencial seguro
        novo_id = int(df["ID"].max() + 1) if not df.empty else 1

        novo_registro = pd.DataFrame({
            "ID": [novo_id],
            "Data": [data_pedido],
            "Filha": [nome_filha],
            "Valor Solicitado": [float(valor_solicitado)],
            "Objetivo": [objetivo.strip()],
            "Status": ["Pendente"],
            "Valor Pago": [0.0],
            "Observacao": [""],
        })

        # Atualizar o DataFrame na sessão
        st.session_state["dados"] = pd.concat(
            [df, novo_registro], ignore_index=True
        )

        st.success(
            "✅ Solicitação registrada com sucesso! Clique no botão abaixo para"
            " avisar a Regina no WhatsApp:"
        )

        # CONFIGURAÇÃO DO WHATSAPP
        # ⚠️ Insira o número da Regina com DDI e DDD (Ex: 5511999999999)
        numero_regina = "5511999999999"
        mensagem = (
            f"Olá Regina! A {nome_filha} solicitou R$ {valor_solicitado:.2f} para"
            f" '{objetivo.strip()}' em"
            f" {data_pedido.strftime('%d/%m/%Y')}."
        )
        link_zap = f"https://wa.me/{numero_regina}?text={urllib.parse.quote(mensagem)}"

        st.markdown(
            f'<a href="{link_zap}" target="_blank"><button'
            ' style="background-color:#25D366; color:white; padding:12px'
            ' 24px; border:none; border-radius:6px; font-size:16px; font-weight:'
            ' bold; cursor: pointer; text-decoration: none;">📲 Enviar Mensagem'
            ' no WhatsApp da Regina</button></a>',
            unsafe_allow_html=True,
        )
      else:
        st.error(
            "⚠️ Por favor, informe um valor válido e descreva o objetivo do"
            " gasto."
        )

# ---------------------------------------------------------
# TELA 2: REGINA - PAINEL DE APROVAÇÃO
# ---------------------------------------------------------
elif perfil == "Regina / Gestora (Painel & Aprovação)":
  st.subheader("⚙️ Painel de Gestão e Aprovação (Regina)")

  if df.empty:
    st.info("Nenhuma solicitação registrada no momento.")
  else:
    st.write("### Solicitações Registradas")
    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.write("### Atualizar Status de um Pedido")

    ids_disponiveis = df["ID"].tolist()
    id_escolhido = st.selectbox(
        "Selecione o ID da solicitação que deseja gerenciar:", ids_disponiveis
    )

    # Buscar dados da linha com segurança
    linha_filtrada = df[df["ID"] == id_escolhido]
    if not linha_filtrada.empty:
      linha_selecionada = linha_filtrada.iloc[0]

      st.info(
          f"**Detalhes do Pedido #{id_escolhido}:**"
          f" **{linha_selecionada['Filha']}** pediu R$"
          f" {linha_selecionada['Valor Solicitado']:.2f} para"
          f" *{linha_selecionada['Objetivo']}*"
      )

      # Mapear status atual para o selectbox
      status_opcoes = ["Pendente", "Aprovado", "Alterado", "Negado"]
      status_atual = (
          linha_selecionada["Status"]
          if linha_selecionada["Status"] in status_opcoes
          else "Pendente"
      )
      index_status = status_opcoes.index(status_atual)

      with st.form("form_atualizacao"):
        novo_status = st.selectbox(
            "Novo Status", status_opcoes, index=index_status
        )
        valor_pago = st.number_input(
            "Valor Efetivamente Pago/Liberado (R$)",
            value=float(linha_selecionada["Valor Pago"])
            if linha_selecionada["Valor Pago"] > 0
            else float(linha_selecionada["Valor Solicitado"]),
            format="%.2f",
            step=1.00,
        )
        observacao = st.text_input(
            "Observação (Motivo de alteração/negação ou dados do PIX)",
            value=str(linha_selecionada["Observacao"]),
        )

        salvar_alteracao = st.form_submit_button("Salvar Alteração")

        if salvar_alteracao:
          # Atualizar o DataFrame na sessão de forma segura
          df.loc[df["ID"] == id_escolhido, "Status"] = novo_status
          df.loc[df["ID"] == id_escolhido, "Valor Pago"] = float(valor_pago)
          df.loc[df["ID"] == id_escolhido, "Observacao"] = observacao.strip()
          st.session_state["dados"] = df

          st.success("✅ Status atualizado com sucesso!")
          st.rerun()

# ---------------------------------------------------------
# TELA 3: DASHBOARD E GRÁFICOS
# ---------------------------------------------------------
else:
  st.subheader("📊 Dashboard de Gastos e Destinação dos Recursos")

  if df.empty:
    st.info("Ainda não há dados suficientes para gerar gráficos.")
  else:
    total_solicitado = df["Valor Solicitado"].sum()
    # Considera valores pagos apenas de status Aprovado ou Alterado
    df_aprovados = df[df["Status"].isin(["Aprovado", "Alterado"])]
    total_pago = df_aprovados["Valor Pago"].sum() if not df_aprovados.empty else 0.0

    col1, col2 = st.columns(2)
    col1.metric("Total Solicitado Geral", f"R$ {total_solicitado:.2f}")
    col2.metric("Total Efetivamente Pago", f"R$ {total_pago:.2f}")

    st.markdown("---")

    st.write("### 👧 Gastos Totais por Filha (Aprovados/Alterados)")
    if not df_aprovados.empty:
      gastos_filha = df_aprovados.groupby("Filha")["Valor Pago"].sum()
      st.bar_chart(gastos_filha)
    else:
      st.info("Nenhum gasto aprovado registrado ainda para exibir no gráfico.")

    st.write("### 📋 Histórico Consolidado Completo")
    st.dataframe(df, use_container_width=True)