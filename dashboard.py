import streamlit as st
import pandas as pd
import datetime
import random
import extra_streamlit_components as stx
import plotly.express as px
import plotly.graph_objects as go
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from database import SessionLocal
import calendar

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Dashboard Viáticos", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

try:
    SLACK_TOKEN = st.secrets["SLACK_BOT_TOKEN"]
    cliente_slack = WebClient(token=SLACK_TOKEN)
except Exception as e:
    st.error("⚠️ Error: No se encontró el SLACK_BOT_TOKEN en los Secrets de Streamlit.")
    cliente_slack = None

# --- 2. GESTIÓN DE COOKIES ---
gestor_cookies = stx.CookieManager(key="gestor_cookies_app")
usuario_guardado = gestor_cookies.get(cookie="usuario_viaticos")

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "esperando_codigo" not in st.session_state:
    st.session_state["esperando_codigo"] = False

if usuario_guardado:
    st.session_state["autenticado"] = True
    st.session_state["usuario"] = usuario_guardado

# --- 3. FUNCIONES DE BASE DE DATOS Y SLACK ---
@st.cache_data(ttl=300) # Cache de 5 min para que sea rapidísimo
def cargar_datos_viaticos():
    db = SessionLocal()
    try:
        query = """
        SELECT 
            v.fecha_gasto, 
            s.fecha_servicio AS "Fecha_Ticket", 
            v.id_servicio AS "Ticket_Num", 
            s.cliente AS "Cliente", 
            s.estado_ve AS "Estado", 
            s.ciudad AS "Ciudad", 
            v.categoria_gasto AS "Categoria", 
            v.monto_usd_calculado AS "Total_USD", 
            (SELECT STRING_AGG(tipo_equipo, ', ') FROM equipos_asignados WHERE id_servicio = s.id_servicio) AS "Equipos",
            v.tasa_bcv_dia AS "Tasa_BCV" 
        FROM viaticos v 
        LEFT JOIN servicios s ON v.id_servicio = s.id_servicio
        ORDER BY v.fecha_gasto DESC
        """
        df = pd.read_sql(query, db.bind)
        if not df.empty:
            df["fecha_gasto"] = pd.to_datetime(df["fecha_gasto"])
            df["Mes"] = df["fecha_gasto"].dt.month
            df["Año"] = df["fecha_gasto"].dt.year
            df["Nombre_Mes"] = df["fecha_gasto"].dt.strftime('%B') # Nombre del mes
        return df
    except Exception as e:
        db.rollback() 
        st.error(f"Error al conectar con la base de datos: {e}")
        return pd.DataFrame()
    finally:
        db.close()

def enviar_codigo_slack(correo):
    try:
        respuesta_usuario = cliente_slack.users_lookupByEmail(email=correo)
        user_id = respuesta_usuario["user"]["id"]
        codigo_generado = str(random.randint(1000, 9999))
        mensaje = f"🔐 Tu código de acceso al Dashboard de Viáticos es: *{codigo_generado}*"
        cliente_slack.chat_postMessage(channel=user_id, text=mensaje)
        return codigo_generado
    except SlackApiError:
        return None

# --- 4. INTERFAZ DE LOGIN ---
if not st.session_state["autenticado"]:
    st.title("🔐 Acceso Seguro - Analítica de Viáticos")
    col1, col2 = st.columns([1, 2])
    with col1:
        if not st.session_state["esperando_codigo"]:
            correo_input = st.text_input("Correo Electrónico (Slack)")
            if st.button("Enviar código", type="primary"):
                if correo_input and cliente_slack:
                    with st.spinner("Enviando código..."):
                        codigo = enviar_codigo_slack(correo_input.strip())
                        if codigo:
                            st.session_state["codigo_real"] = codigo
                            st.session_state["email_temporal"] = correo_input.strip()
                            st.session_state["esperando_codigo"] = True
                            st.rerun()
                else:
                    st.warning("Ingresa un correo.")
        else:
            st.info(f"Código enviado por Slack a: **{st.session_state['email_temporal']}**")
            codigo_input = st.text_input("Ingresa el código", max_chars=4)
            if st.button("Verificar", type="primary"):
                if codigo_input == st.session_state["codigo_real"]:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario"] = st.session_state["email_temporal"]
                    gestor_cookies.set("usuario_viaticos", st.session_state["usuario"], expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                else:
                    st.error("Código incorrecto.")
            if st.button("Cancelar"):
                st.session_state["esperando_codigo"] = False
                st.rerun()

# --- 5. INTERFAZ AVANZADA DEL DASHBOARD ---
else:
    # --- SIDEBAR (FILTROS GLOBALES) ---
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.sidebar.write(f"👤 {st.session_state['usuario']}")
    if st.sidebar.button("Cerrar Sesión", use_container_width=True):
        gestor_cookies.delete("usuario_viaticos")
        for key in ["autenticado", "usuario", "esperando_codigo", "codigo_real", "email_temporal"]:
            if key in st.session_state: del st.session_state[key]
        st.rerun()
        
    st.sidebar.divider()
    st.sidebar.header("🎯 Filtros Globales")

    df = cargar_datos_viaticos()

    if df.empty:
        st.warning("No hay datos registrados aún.")
    else:
        # Filtro de Fechas
        min_date, max_date = df["fecha_gasto"].min().date(), df["fecha_gasto"].max().date()
        fecha_rango = st.sidebar.date_input("Rango de Fechas", [min_date, max_date], min_value=min_date, max_value=max_date)
        
        # Selectores
        cliente_sel = st.sidebar.multiselect("🏢 Clientes", sorted(df["Cliente"].dropna().unique()))
        categoria_sel = st.sidebar.multiselect("🏷️ Categorías", sorted(df["Categoria"].dropna().unique()))
        equipo_sel = st.sidebar.multiselect("⚙️ Equipos", ["Ecógrafo", "Rayos X", "Tomógrafo", "Incubadora", "Resonador", "Monitor", "Anestesia", "Otro"])

        # Aplicar Filtros Globales (Afectan a todo menos a la pestaña Mensual)
        df_filt = df.copy()
        if len(fecha_rango) == 2:
            df_filt = df_filt[(df_filt["fecha_gasto"].dt.date >= fecha_rango[0]) & (df_filt["fecha_gasto"].dt.date <= fecha_rango[1])]
        if cliente_sel: df_filt = df_filt[df_filt["Cliente"].isin(cliente_sel)]
        if categoria_sel: df_filt = df_filt[df_filt["Categoria"].isin(categoria_sel)]
        if equipo_sel:
            patron = '|'.join(equipo_sel)
            df_filt = df_filt[df_filt["Equipos"].str.contains(patron, na=False, regex=True)]

        st.title("🚀 Centro de Inteligencia de Viáticos")
        
        # --- CREACIÓN DE PESTAÑAS ---
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Visión General", 
            "📈 Análisis en el Tiempo", 
            "⚖️ Comparativas", 
            "📅 Cierre Mensual", 
            "📋 Base de Datos"
        ])

        # ==========================================
        # PESTAÑA 1: VISIÓN GENERAL
        # ==========================================
        with tab1:
            st.subheader("Resumen de Operaciones")
            col1, col2, col3, col4 = st.columns(4)
            t_usd = df_filt["Total_USD"].sum()
            t_tickets = df_filt["Ticket_Num"].nunique()
            avg_ticket = t_usd / t_tickets if t_tickets > 0 else 0
            max_gasto = df_filt["Total_USD"].max() if not df_filt.empty else 0

            col1.metric("Gasto Total", f"${t_usd:,.2f}")
            col2.metric("Tickets Atendidos", f"{t_tickets}")
            col3.metric("Costo Promedio p/Ticket", f"${avg_ticket:,.2f}")
            col4.metric("Gasto Máximo Único", f"${max_gasto:,.2f}")
            
            st.divider()
            
            c1, c2 = st.columns(2)
            with c1:
                # Gráfico de Anillo (Donut) para Categorías usando Plotly
                if not df_filt.empty:
                    fig_cat = px.pie(df_filt, values='Total_USD', names='Categoria', hole=0.4, 
                                     title="Distribución del Gasto por Categoría",
                                     color_discrete_sequence=px.colors.sequential.Teal)
                    fig_cat.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_cat, use_container_width=True)
            
            with c2:
                # Top 10 Clientes que más gastan
                if not df_filt.empty:
                    top_clientes = df_filt.groupby('Cliente')['Total_USD'].sum().nlargest(10).reset_index()
                    fig_cli = px.bar(top_clientes, x='Total_USD', y='Cliente', orientation='h', 
                                     title="Top 10 Clientes por Consumo de Viáticos",
                                     color='Total_USD', color_continuous_scale='Blues')
                    fig_cli.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_cli, use_container_width=True)

        # ==========================================
        # PESTAÑA 2: ANÁLISIS EN EL TIEMPO
        # ==========================================
        with tab2:
            st.subheader("Evolución del Gasto")
            st.markdown("Observa cómo fluctúan los gastos (afectado por los filtros del panel lateral).")
            
            if not df_filt.empty:
                # Agrupar por día
                df_tiempo = df_filt.groupby(df_filt['fecha_gasto'].dt.date)['Total_USD'].sum().reset_index()
                df_tiempo.columns = ['Fecha', 'Gasto USD']
                
                fig_line = px.area(df_tiempo, x='Fecha', y='Gasto USD', 
                                   title="Tendencia de Gastos Diarios (USD)",
                                   markers=True, color_discrete_sequence=['#1f77b4'])
                fig_line.update_layout(xaxis_title="Fecha", yaxis_title="Monto (USD)", hovermode="x unified")
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("No hay datos en el rango seleccionado.")

        # ==========================================
        # PESTAÑA 3: COMPARATIVAS
        # ==========================================
        with tab3:
            st.subheader("⚖️ Comparativa Cliente A vs Cliente B")
            st.markdown("Compara los gastos de dos clientes independientemente de los filtros globales.")
            
            clientes_disp = sorted(df["Cliente"].dropna().unique())
            c_a, c_b = st.columns(2)
            
            with c_a:
                cli_1 = st.selectbox("Selecciona el Cliente A", clientes_disp, index=0)
                df_1 = df[df["Cliente"] == cli_1]
                st.metric(f"Total Gastado {cli_1}", f"${df_1['Total_USD'].sum():,.2f}")
                if not df_1.empty:
                    fig1 = px.bar(df_1.groupby('Categoria')['Total_USD'].sum().reset_index(), 
                                  x='Categoria', y='Total_USD', title=f"Gastos de {cli_1}")
                    st.plotly_chart(fig1, use_container_width=True)

            with c_b:
                idx_b = 1 if len(clientes_disp) > 1 else 0
                cli_2 = st.selectbox("Selecciona el Cliente B", clientes_disp, index=idx_b)
                df_2 = df[df["Cliente"] == cli_2]
                st.metric(f"Total Gastado {cli_2}", f"${df_2['Total_USD'].sum():,.2f}")
                if not df_2.empty:
                    fig2 = px.bar(df_2.groupby('Categoria')['Total_USD'].sum().reset_index(), 
                                  x='Categoria', y='Total_USD', title=f"Gastos de {cli_2}",
                                  color_discrete_sequence=['#ff7f0e'])
                    st.plotly_chart(fig2, use_container_width=True)

        # ==========================================
        # PESTAÑA 4: CIERRE MENSUAL FIJO
        # ==========================================
        with tab4:
            st.subheader("📅 Reporte de Cierre Mensual")
            st.markdown("Esta sección ignora los filtros globales. Selecciona un mes y año para ver el reporte exacto.")
            
            col_m1, col_m2, _ = st.columns([1,1,2])
            with col_m1:
                lista_anios = sorted(df["Año"].dropna().unique(), reverse=True)
                anio_sel = st.selectbox("Año", lista_anios)
            with col_m2:
                # Mapear nombres de meses disponibles para el año seleccionado
                meses_del_anio = sorted(df[df["Año"] == anio_sel]["Mes"].unique())
                nombres_meses = [calendar.month_name[m] for m in meses_del_anio]
                mes_str = st.selectbox("Mes", nombres_meses)
                mes_num = list(calendar.month_name).index(mes_str)

            df_mes = df[(df["Año"] == anio_sel) & (df["Mes"] == mes_num)]
            
            if not df_mes.empty:
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Total {mes_str} {anio_sel}", f"${df_mes['Total_USD'].sum():,.2f}")
                c2.metric("Tickets del Mes", f"{df_mes['Ticket_Num'].nunique()}")
                top_cat_mes = df_mes.groupby("Categoria")["Total_USD"].sum().idxmax()
                c3.metric("Categoría de Mayor Gasto", f"{top_cat_mes}")
                
                st.plotly_chart(
                    px.histogram(df_mes, x="fecha_gasto", y="Total_USD", color="Categoria",
                                 title=f"Gastos diarios durante {mes_str} {anio_sel} (Agrupado por Categoría)",
                                 barmode="stack"), 
                    use_container_width=True
                )
            else:
                st.info("No hay gastos registrados en este mes.")

        # ==========================================
        # PESTAÑA 5: BASE DE DATOS CRUDA
        # ==========================================
        with tab5:
            st.subheader("📋 Extraer Datos")
            st.markdown("Datos filtrados según el panel lateral.")
            st.dataframe(
                df_filt.style.format({"Total_USD": "${:.2f}", "Tasa_BCV": "Bs. {:.2f}"}),
                use_container_width=True, 
                hide_index=True
            )
