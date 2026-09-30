import datetime
import json
import urllib.parse
import uuid

import gspread
import pandas as pd
import streamlit as st


# =========================================================
# CONFIGURAÇÃO
# =========================================================
st.set_page_config(
    page_title="Controle de Despesas",
    page_icon="💰",
    layout="wide",
)

st.title("💡 Gestão de Despesas e Solicitações")
st.markdown("---")

# Colunas suportadas pela versão atual.
# "Criado Em" é nova e permite ordenar registros sem depender do ID.
COLUNAS = [
    "ID",
    "Data",
    "Filha",
    "Valor Solicitado",
    "Objetivo",
    "Status",
    "Valor Pago",
    "Observacao",
    "Descricao Pedido",
    "Criado Em",
]

STATUS_OPCOES = ["Pendente", "Aprovado", "Alterado", "Negado"]
FILHAS = ["Lorena", "Estela"]
OBJETIVOS = [
    "Lanche da Escola",
    "Transporte/Uber",
    "Material Escolar",
    "Passeio/Lazer",
    "Vestuário",
    "Outros",
]


# =========================================================
# ACESSO PÚBLICO
# =========================================================
# A aplicação é intencionalmente pública.
# Qualquer pessoa que possua o link pode usar as três áreas.
st.sidebar.header("👤 Quem está acessando?")

perfil = st.sidebar.radio(
    "Selecione o seu perfil:",
    [
        "Filha (Fazer Pedido)",
        "Responsável (Painel & Aprovação)",
        "Visualizar Painel / Gráficos",
    ],
)

# =========================================================
# CONEXÃO COM GOOGLE SHEETS
# =========================================================
@st.cache_resource
def conectar_google_sheets():
    try:
        cred_dict = json.loads(st.secrets["google_credentials"])
        gc = gspread.service_account_from_dict(cred_dict)
        sh = gc.open("Controle Despesas Filhas")
        return sh, sh.sheet1
    except KeyError:
        st.error("A configuração 'google_credentials' não está no Streamlit Secrets.")
        st.stop()
    except Exception:
        st.error(
            "Não foi possível conectar ao Google Sheets. "
            "Verifique as credenciais, o nome da planilha e as permissões."
        )
        st.stop()


sh, planilha = conectar_google_sheets()


# =========================================================
# FUNÇÕES DE DADOS
# =========================================================
def limpar_moeda(valor):
    """Converte valores monetários brasileiros para float."""
    if pd.isna(valor) or valor == "":
        return 0.0

    if isinstance(valor, (int, float)):
        return float(valor)

    valor_str = (
        str(valor)
        .replace("R$", "")
        .replace(" ", "")
        .replace("\xa0", "")
        .strip()
    )

    if "," in valor_str:
        valor_str = valor_str.replace(".", "").replace(",", ".")

    try:
        return float(valor_str)
    except (ValueError, TypeError):
        return 0.0


def normalizar_id(valor):
    """Mantém IDs antigos numéricos e novos IDs alfanuméricos como texto."""
    if pd.isna(valor):
        return ""

    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))

    return str(valor).strip()


def carregar_dados():
    """
    Lê a planilha e normaliza os dados.
    Se o Google Sheets falhar, interrompe a execução para evitar
    operações sobre uma cópia potencialmente desatualizada.
    """
    try:
        registros = planilha.get_all_records()
    except Exception:
        st.error(
            "⚠️ Falha de comunicação com o Google Sheets. "
            "Recarregue a página em alguns instantes."
        )
        st.stop()

    if not registros:
        return pd.DataFrame(columns=COLUNAS)

    df = pd.DataFrame(registros)

    # Retrocompatibilidade com a planilha antiga.
    for coluna in COLUNAS:
        if coluna not in df.columns:
            df[coluna] = ""

    df["ID"] = df["ID"].apply(normalizar_id)

    df["Data"] = pd.to_datetime(
        df["Data"],
        dayfirst=True,
        errors="coerce",
    ).dt.date

    df["Valor Solicitado"] = df["Valor Solicitado"].apply(limpar_moeda)
    df["Valor Pago"] = df["Valor Pago"].apply(limpar_moeda)

    # Registros antigos não têm Criado Em.
    df["Criado Em"] = pd.to_datetime(
        df["Criado Em"],
        errors="coerce",
    )

    # Fallback para registros antigos: usa a posição da linha.
    if df["Criado Em"].isna().any():
        agora = pd.Timestamp.now()
        df.loc[df["Criado Em"].isna(), "Criado Em"] = agora

    return df[COLUNAS]


def gerar_id():
    """
    Gera um identificador praticamente impossível de colidir
    sem precisar consultar o maior ID existente.

    Formato: PED-XXXXXXXX
    """
    return f"PED-{uuid.uuid4().hex[:8].upper()}"


def localizar_linha_por_id(id_registro):
    """Localiza a linha física do registro na planilha."""
    try:
        celula = planilha.find(str(id_registro), in_column=1)
        return celula.row if celula else None
    except Exception:
        st.error("Não foi possível localizar o registro no Google Sheets.")
        return None


def inserir_pedido(
    nome_filha,
    valor_solicitado,
    data_pedido,
    objetivo,
    descricao_pedido,
):
    novo_id = gerar_id()
    criado_em = datetime.datetime.now().isoformat(timespec="seconds")

    planilha.append_row(
        [
            novo_id,
            data_pedido.strftime("%d/%m/%Y"),
            nome_filha,
            float(valor_solicitado),
            objetivo,
            "Pendente",
            0.0,
            "",
            descricao_pedido.strip(),
            criado_em,
        ],
        value_input_option="USER_ENTERED",
    )

    return novo_id


def atualizar_pedido_seguro(
    id_registro,
    novo_valor_solicitado,
    novo_status,
    valor_pago,
    observacao,
):
    """
    Versão correta da atualização: D:G são os campos editáveis.
    """
    linha = localizar_linha_por_id(id_registro)

    if not linha:
        return False

    # D:H = Valor Solicitado, Objetivo, Status, Valor Pago, Observacao.
    # O Objetivo existente é preservado; a Descricao Pedido (I) não é alterada.
    objetivo_atual = planilha.cell(linha, 5).value or ""

    planilha.update(
        f"D{linha}:H{linha}",
        [
            [
                float(novo_valor_solicitado),
                objetivo_atual,
                novo_status,
                float(valor_pago),
                observacao.strip(),
            ]
        ],
        value_input_option="USER_ENTERED",
    )
    return True


def excluir_pedido(id_registro):
    linha = localizar_linha_por_id(id_registro)

    if not linha:
        return False

    planilha.delete_rows(linha)
    return True


df = carregar_dados()


# =========================================================
# PERFIL: FILHA
# =========================================================
if perfil == "Filha (Fazer Pedido)":
    st.subheader("📝 Nova Solicitação de Valor")

    with st.form("form_pedido", clear_on_submit=True):
        nome_filha = st.selectbox("Quem está pedindo?", FILHAS)

        valor_solicitado = st.number_input(
            "Valor solicitado (R$)",
            min_value=0.01,
            format="%.2f",
            step=1.00,
        )

        data_pedido = st.date_input(
            "Data necessária",
            value=datetime.date.today(),
            format="DD/MM/YYYY",
        )

        objetivo = st.selectbox(
            "Objetivo / Destinação",
            OBJETIVOS,
        )

        descricao_pedido = st.text_input(
            "Descrição do pedido (Opcional)",
            placeholder="Ex.: Livro de Biologia, lanche na padaria",
        )

        botao_enviar = st.form_submit_button(
            "Enviar Solicitação",
            use_container_width=True,
        )

    if botao_enviar:
        if valor_solicitado <= 0:
            st.error("Preencha o valor corretamente.")
        else:
            try:
                novo_id = inserir_pedido(
                    nome_filha,
                    valor_solicitado,
                    data_pedido,
                    objetivo,
                    descricao_pedido,
                )

                st.success(
                    f"Pedido {novo_id} gravado na planilha. "
                    "Use o botão abaixo para avisar o responsável."
                )

                numero_responsavel = st.secrets.get("numero_responsavel")
                url_do_app = st.secrets.get(
                    "url_do_app",
                    "https://controle-gastos-piolhos.streamlit.app/",
                )

                if not numero_responsavel:
                    st.warning(
                        "O pedido foi salvo, mas o número do WhatsApp "
                        "não está configurado no Streamlit Secrets."
                    )
                else:
                    detalhe_msg = (
                        f" ({descricao_pedido.strip()})"
                        if descricao_pedido.strip()
                        else ""
                    )

                    mensagem = (
                        f"Olá! A {nome_filha} solicitou "
                        f"R$ {valor_solicitado:.2f} para "
                        f"'{objetivo}'{detalhe_msg} em "
                        f"{data_pedido.strftime('%d/%m/%Y')}.\n\n"
                        f"Pedido: {novo_id}\n"
                        f"👉 Acesse o painel: {url_do_app}"
                    )

                    link_zap = (
                        f"https://wa.me/{numero_responsavel}"
                        f"?text={urllib.parse.quote(mensagem)}"
                    )

                    st.markdown(
                        f"""
                        <a href="{link_zap}" target="_blank">
                            <button style="
                                background-color:#25D366;
                                color:white;
                                padding:12px 24px;
                                border:none;
                                border-radius:6px;
                                font-size:16px;
                                font-weight:bold;
                                cursor:pointer;
                            ">
                                📲 Avisar Responsável no WhatsApp
                            </button>
                        </a>
                        """,
                        unsafe_allow_html=True,
                    )

            except Exception:
                st.error(
                    "Não foi possível gravar o pedido. "
                    "Verifique a conexão com o Google Sheets."
                )


# =========================================================
# PERFIL: RESPONSÁVEL
# =========================================================
elif perfil == "Responsável (Painel & Aprovação)":
    st.subheader("⚙️ Painel de Gestão e Aprovação")

    if df.empty:
        st.info("Nenhuma solicitação registrada.")
    else:
        df_reverso = df.sort_values(
            by=["Criado Em", "ID"],
            ascending=[False, False],
        )

        st.dataframe(
            df_reverso.drop(columns=["Criado Em"]),
            height=250,
            use_container_width=True,
            column_config={
                "Data": st.column_config.DateColumn(
                    "Data",
                    format="DD/MM/YYYY",
                ),
                "Valor Solicitado": st.column_config.NumberColumn(
                    "Valor Solicitado",
                    format="R$ %.2f",
                ),
                "Valor Pago": st.column_config.NumberColumn(
                    "Valor Pago",
                    format="R$ %.2f",
                ),
            },
        )

        st.markdown("---")
        st.write("### 📝 Atualizar Status ou Valor")

        opcoes_dropdown = []

        for _, row in df_reverso.iterrows():
            desc_extra = (
                f" - {row['Descricao Pedido']}"
                if pd.notna(row["Descricao Pedido"])
                and row["Descricao Pedido"] != ""
                else ""
            )

            texto = (
                f"ID {row['ID']} | {row['Status']} | {row['Filha']} | "
                f"R$ {row['Valor Solicitado']:.2f} "
                f"({row['Objetivo']}{desc_extra})"
            )

            opcoes_dropdown.append(texto)

        col_selecao, col_botao_apagar = st.columns([4, 1])

        with col_selecao:
            escolha_texto = st.selectbox(
                "ID",
                opcoes_dropdown,
                label_visibility="collapsed",
            )

            id_escolhido = escolha_texto.split("|")[0].replace("ID", "").strip()

            registros_id = df[df["ID"] == id_escolhido]

            if registros_id.empty:
                st.error("O registro selecionado não está mais disponível.")
                st.stop()

            linha_selecionada = registros_id.iloc[0]

        with col_botao_apagar:
            with st.expander("🗑️ Apagar"):
                st.warning("A exclusão é permanente.")

                if st.button("Confirmar exclusão", key="btn_apagar"):
                    try:
                        if excluir_pedido(id_escolhido):
                            st.success("Apagado com sucesso.")
                            st.rerun()
                        else:
                            st.error("Registro não encontrado.")
                    except Exception:
                        st.error("Não foi possível apagar o registro.")

        if (
            pd.notna(linha_selecionada["Descricao Pedido"])
            and linha_selecionada["Descricao Pedido"] != ""
        ):
            st.info(
                f"📌 **Detalhes informados pela filha:** "
                f"{linha_selecionada['Descricao Pedido']}"
            )

        status_atual = (
            linha_selecionada["Status"]
            if linha_selecionada["Status"] in STATUS_OPCOES
            else "Pendente"
        )

        with st.form("form_atualizacao"):
            novo_status = st.selectbox(
                "Novo Status",
                STATUS_OPCOES,
                index=STATUS_OPCOES.index(status_atual),
            )

            col1, col2 = st.columns(2)

            novo_valor_solicitado = col1.number_input(
                "Corrigir Valor Solicitado (R$)",
                min_value=0.0,
                value=float(linha_selecionada["Valor Solicitado"]),
                format="%.2f",
            )

            valor_pago_atual = float(linha_selecionada["Valor Pago"])

            valor_pago = col2.number_input(
                "Valor Pago/Liberado (R$)",
                min_value=0.0,
                value=(
                    valor_pago_atual
                    if valor_pago_atual > 0
                    else float(linha_selecionada["Valor Solicitado"])
                ),
                format="%.2f",
            )

            observacao = st.text_input(
                "Observação",
                value=str(linha_selecionada["Observacao"]),
                placeholder="Motivo da alteração, negação ou dados do PIX",
            )

            salvar = st.form_submit_button(
                "Salvar Alteração na Planilha",
                use_container_width=True,
            )

        if salvar:
            if novo_status == "Negado":
                valor_pago = 0.0

            if valor_pago > novo_valor_solicitado and novo_status != "Alterado":
                st.warning(
                    "O valor pago está acima do valor solicitado. "
                    "Confirme se isso é realmente desejado."
                )

            try:
                if atualizar_pedido_seguro(
                    id_escolhido,
                    novo_valor_solicitado,
                    novo_status,
                    valor_pago,
                    observacao,
                ):
                    st.success("Atualizado com sucesso.")
                    st.rerun()
                else:
                    st.error("Registro não encontrado.")
            except Exception:
                st.error(
                    "Não foi possível atualizar o registro. "
                    "Nenhuma alteração parcial foi feita pelo aplicativo."
                )


# =========================================================
# PERFIL: DASHBOARD
# =========================================================
else:
    st.subheader("📊 Dashboard de Gastos e Destinação dos Recursos")

    if df.empty:
        st.info("Ainda não há dados suficientes para gerar o dashboard.")
    else:
        df_aprovados = df[
            df["Status"].isin(["Aprovado", "Alterado"])
        ].copy()

        total_solicitado = df["Valor Solicitado"].sum()

        total_pago = (
            df_aprovados["Valor Pago"].sum()
            if not df_aprovados.empty
            else 0.0
        )

        total_pedidos = len(df)
        total_pendentes = int((df["Status"] == "Pendente").sum())
        total_negados = int((df["Status"] == "Negado").sum())

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Total solicitado",
            f"R$ {total_solicitado:,.2f}",
        )

        col2.metric(
            "Total pago",
            f"R$ {total_pago:,.2f}",
        )

        col3.metric(
            "Pedidos",
            total_pedidos,
        )

        col4.metric(
            "Pendentes",
            total_pendentes,
        )

        st.markdown("---")

        if not df_aprovados.empty:
            st.write("### 👧 Gastos por filha")

            gastos_filhos = (
                df_aprovados.groupby("Filha")["Valor Pago"]
                .sum()
                .sort_values(ascending=False)
            )

            st.bar_chart(gastos_filhos)

            st.write("### 🎯 Gastos por objetivo")

            gastos_objetivo = (
                df_aprovados.groupby("Objetivo")["Valor Pago"]
                .sum()
                .sort_values(ascending=False)
            )

            st.bar_chart(gastos_objetivo)

        else:
            st.info(
                "Nenhum gasto aprovado registrado ainda "
                "para exibir os gráficos."
            )

        st.markdown("---")

        st.write("### 📋 Histórico Consolidado")

        st.dataframe(
            df.sort_values(
                by=["Criado Em", "ID"],
                ascending=[False, False],
            ).drop(columns=["Criado Em"]),
            use_container_width=True,
            column_config={
                "Data": st.column_config.DateColumn(
                    "Data",
                    format="DD/MM/YYYY",
                ),
                "Valor Solicitado": st.column_config.NumberColumn(
                    "Valor Solicitado",
                    format="R$ %.2f",
                ),
                "Valor Pago": st.column_config.NumberColumn(
                    "Valor Pago",
                    format="R$ %.2f",
                ),
            },
        )
