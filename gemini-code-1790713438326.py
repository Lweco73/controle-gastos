
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


def formatar_reais(valor):
    """Formata um número no padrão monetário brasileiro."""
    try:
        valor = float(valor)
    except (ValueError, TypeError):
        valor = 0.0

    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(data):
    if pd.isna(data):
        return "Sem data"
    if isinstance(data, datetime.datetime):
        return data.strftime("%d/%m/%Y")
    if isinstance(data, datetime.date):
        return data.strftime("%d/%m/%Y")
    return str(data)


def carregar_dados():
    """Lê a planilha e normaliza os dados."""
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

    # Retrocompatibilidade com a planilha existente.
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

    # Registros antigos não têm "Criado Em".
    # object evita incompatibilidade com versões recentes do Pandas.
    criado_em = pd.to_datetime(
        df["Criado Em"],
        errors="coerce",
    )

    data_fallback = pd.to_datetime(
        df["Data"],
        errors="coerce",
    )

    df["Criado Em"] = criado_em.astype("object")
    faltantes = df["Criado Em"].isna()
    df.loc[faltantes, "Criado Em"] = data_fallback.loc[faltantes].astype("object")

    return df[COLUNAS]


def gerar_id():
    """
    Gera identificador interno único.
    O ID técnico não é mostrado no seletor de pedidos.
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
    linha = localizar_linha_por_id(id_registro)

    if not linha:
        return False

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


def criar_rotulo_pedido(row):
    """
    Cria um rótulo humano para o seletor.
    O ID técnico continua existindo na planilha, mas não polui a interface.
    """
    data = formatar_data(row["Data"])
    filha = str(row["Filha"]).strip()
    valor = formatar_reais(row["Valor Solicitado"])
    status = str(row["Status"]).strip() or "Pendente"
    objetivo = str(row["Objetivo"]).strip()

    descricao = str(row["Descricao Pedido"]).strip()
    # O código técnico (PED-XXXXXXXX) não é exibido.
    # A separação por "•" facilita a leitura do pedido no dropdown.
    if descricao:
        return f"{data} • {filha} • {valor} • {objetivo} • {descricao} • {status}"

    return f"{data} • {filha} • {valor} • {objetivo} • {status}"


def ordenar_por_criacao(df_input):
    if df_input.empty:
        return df_input

    return df_input.sort_values(
        by=["Criado Em", "ID"],
        ascending=[False, False],
        na_position="last",
    )


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
                    f"Pedido registrado com sucesso. "
                    f"Valor: {formatar_reais(valor_solicitado)}."
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
                        f"{formatar_reais(valor_solicitado)} para "
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
        df_reverso = ordenar_por_criacao(df)

        # -------------------------
        # Filtros
        # -------------------------
        st.write("### 🔎 Localizar pedido")

        f1, f2, f3 = st.columns(3)

        filtro_filha = f1.selectbox(
            "Filha",
            ["Todas"] + FILHAS,
            key="filtro_responsavel_filha",
        )

        filtro_status = f2.selectbox(
            "Status",
            ["Todos"] + STATUS_OPCOES,
            key="filtro_responsavel_status",
        )

        filtro_objetivo = f3.selectbox(
            "Objetivo",
            ["Todos"] + OBJETIVOS,
            key="filtro_responsavel_objetivo",
        )

        df_filtrado = df_reverso.copy()

        if filtro_filha != "Todas":
            df_filtrado = df_filtrado[df_filtrado["Filha"] == filtro_filha]

        if filtro_status != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]

        if filtro_objetivo != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Objetivo"] == filtro_objetivo]

        if df_filtrado.empty:
            st.info("Nenhum pedido corresponde aos filtros selecionados.")
        else:
            st.dataframe(
                df_filtrado.drop(columns=["Criado Em", "ID"]),
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
            st.write("### 📝 Selecionar pedido")

            # O selectbox usa o ID interno como valor real, mas mostra
            # um rótulo amigável. Assim, dois pedidos com a mesma descrição
            # continuam sendo identificados corretamente.
            mapa_rotulos = {
                row["ID"]: criar_rotulo_pedido(row)
                for _, row in df_filtrado.iterrows()
            }

            id_escolhido = st.selectbox(
                "Pedido",
                list(mapa_rotulos.keys()),
                format_func=lambda pedido_id: mapa_rotulos[pedido_id],
                help=(
                    "O código técnico do pedido não é mostrado aqui. "
                    "Use data, filha, valor, objetivo e descrição para localizar."
                ),
            )

            linha_selecionada = df_filtrado[
                df_filtrado["ID"] == id_escolhido
            ].iloc[0]

            col_info, col_apagar = st.columns([4, 1])

            with col_info:
                st.caption(
                    f"Pedido selecionado: {linha_selecionada['Filha']} — "
                    f"{formatar_reais(linha_selecionada['Valor Solicitado'])} — "
                    f"{linha_selecionada['Objetivo']}"
                )

            with col_apagar:
                with st.expander("🗑️ Apagar"):
                    st.warning("A exclusão é permanente.")

                    if st.button(
                        "Confirmar exclusão",
                        key=f"btn_apagar_{id_escolhido}",
                    ):
                        try:
                            if excluir_pedido(id_escolhido):
                                st.success("Pedido apagado com sucesso.")
                                st.rerun()
                            else:
                                st.error("Registro não encontrado.")
                        except Exception:
                            st.error("Não foi possível apagar o registro.")

            if (
                pd.notna(linha_selecionada["Descricao Pedido"])
                and str(linha_selecionada["Descricao Pedido"]).strip() != ""
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

                if (
                    valor_pago > novo_valor_solicitado
                    and novo_status != "Alterado"
                ):
                    st.error(
                        "O valor pago não pode ser maior que o valor solicitado. "
                        "Se o valor foi alterado, selecione o status 'Alterado'."
                    )
                    st.stop()

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
        # -------------------------
        # Filtros do dashboard
        # -------------------------
        st.write("### 🔎 Filtros")

        f1, f2, f3 = st.columns(3)

        filtro_dash_filha = f1.selectbox(
            "Filha",
            ["Todas"] + FILHAS,
            key="filtro_dash_filha",
        )

        filtro_dash_status = f2.multiselect(
            "Status",
            STATUS_OPCOES,
            default=["Aprovado", "Alterado"],
            key="filtro_dash_status",
        )

        datas_validas = [d for d in df["Data"] if pd.notna(d)]

        if datas_validas:
            data_min = min(datas_validas)
            data_max = max(datas_validas)

            periodo = f3.date_input(
                "Período",
                value=(data_min, data_max),
                min_value=data_min,
                max_value=data_max,
                format="DD/MM/YYYY",
                key="filtro_dash_periodo",
            )
        else:
            periodo = None

        df_dash = df.copy()

        if filtro_dash_filha != "Todas":
            df_dash = df_dash[df_dash["Filha"] == filtro_dash_filha]

        if filtro_dash_status:
            df_dash = df_dash[df_dash["Status"].isin(filtro_dash_status)]
        else:
            df_dash = df_dash.iloc[0:0]

        if periodo:
            if isinstance(periodo, tuple) and len(periodo) == 2:
                data_inicio, data_fim = periodo
                df_dash = df_dash[
                    df_dash["Data"].notna()
                    & (df_dash["Data"] >= data_inicio)
                    & (df_dash["Data"] <= data_fim)
                ]

        total_solicitado = df_dash["Valor Solicitado"].sum()
        total_pago = df_dash["Valor Pago"].sum()
        total_pedidos = len(df_dash)

        # Indicadores de pendentes/negados usam filha + período,
        # mas não o filtro de status, para que continuem informativos
        # mesmo quando o dashboard estiver mostrando apenas Aprovado/Alterado.
        df_status = df.copy()

        if filtro_dash_filha != "Todas":
            df_status = df_status[
                df_status["Filha"] == filtro_dash_filha
            ]

        if periodo:
            if isinstance(periodo, tuple) and len(periodo) == 2:
                data_inicio, data_fim = periodo
                df_status = df_status[
                    df_status["Data"].notna()
                    & (df_status["Data"] >= data_inicio)
                    & (df_status["Data"] <= data_fim)
                ]

        total_pendentes = int(
            (df_status["Status"] == "Pendente").sum()
        )
        total_negados = int(
            (df_status["Status"] == "Negado").sum()
        )

        col1, col2, col3, col4, col5 = st.columns(5)

        col1.metric("Total solicitado", formatar_reais(total_solicitado))
        col2.metric("Total pago", formatar_reais(total_pago))
        col3.metric("Pedidos", total_pedidos)
        col4.metric("Pendentes", total_pendentes)
        col5.metric("Negados", total_negados)

        st.markdown("---")

        if df_dash.empty:
            st.info("Nenhum registro corresponde aos filtros selecionados.")
        else:
            col_g1, col_g2 = st.columns(2)

            with col_g1:
                st.write("### 👧 Gastos por filha")

                gastos_filhos = (
                    df_dash.groupby("Filha")["Valor Pago"]
                    .sum()
                    .sort_values(ascending=False)
                )

                st.bar_chart(gastos_filhos)

            with col_g2:
                st.write("### 🎯 Gastos por objetivo")

                gastos_objetivo = (
                    df_dash.groupby("Objetivo")["Valor Pago"]
                    .sum()
                    .sort_values(ascending=False)
                )

                st.bar_chart(gastos_objetivo)

            st.write("### 📅 Evolução mensal")

            df_mensal = df_dash.copy()
            df_mensal["Mês"] = pd.to_datetime(
                df_mensal["Data"],
                errors="coerce",
            ).dt.to_period("M")

            mensal = (
                df_mensal.dropna(subset=["Mês"])
                .groupby("Mês")["Valor Pago"]
                .sum()
            )

            if not mensal.empty:
                mensal.index = mensal.index.astype(str)
                st.bar_chart(mensal)
            else:
                st.info("Não há datas suficientes para gerar a evolução mensal.")

            st.markdown("---")

            st.write("### 📋 Histórico Consolidado")

            st.dataframe(
                ordenar_por_criacao(df_dash).drop(columns=["Criado Em", "ID"]),
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
