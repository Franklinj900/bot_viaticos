import streamlit as st
import pandas as pd
import sqlite3
import random
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

st.set_page_config(page_title="Dashboard Viáticos", page_icon="💰", layout="wide")

SLACK_TOKEN = "xoxb-8347621043874-11876070517300-UmSznvLrwxbYswaa2ZT40Prb"

if "autenticado" not in st.session_state: st.session_state.autenticado = False
if "codigo_secreto" not in st.session_state: st.session_state.codigo_secreto = None

def enviar_codigo_slack(email):
    client = WebClient(token=SLACK_TOKEN)
    try:
        user_info = client.users_lookupByEmail(email=email)
        slack_user_id = user_info["user"]["id"]
        codigo = str(random.randint(1000, 9999))
        st.session_state.codigo_secreto = codigo
        client.chat_postMessage(channel=slack_user_id, text=f"🔐 Tu código de acceso: *{codigo}*")
        return True
    except SlackApiError:
        st.error("❌ No se encontró tu correo en Slack.")
        return False

if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 Acceso Seguro")
        email = st.text_input("Correo electrónico corporativo")
        if st.button("Enviar código por Slack"):
            if email and enviar_codigo_slack(email): st.success("✅ ¡Código enviado!")
        if st.session_state.codigo_secreto:
            if st.button("Entrar al Dashboard") if st.text_input("Ingresa el código", type="password") == st.session_state.codigo_secreto else False:
                st.session_state.autenticado = True
                st.rerun()

else:
    col1, col2 = st.columns([8, 1])
    with col1: st.title("📊 Análisis Financiero de Viáticos")
    with col2:
        if st.button("Cerrar Sesión"):
            st.session_state.autenticado, st.session_state.codigo_secreto = False, None
            st.rerun()
    st.markdown("---")

    conn = sqlite3.connect("./datos/viaticos.db")
    try:
        # 1. Extraer Viáticos + Datos del Servicio
        query_v = """
            SELECT v.fecha_gasto, s.fecha_servicio as Fecha_Ticket, v.id_servicio as Ticket_Num,
            s.cliente as Cliente, s.estado_ve as Estado, s.ciudad as Ciudad,
            v.categoria_gasto as Categoria, v.monto_usd_calculado as Total_USD, v.tasa_bcv_dia as Tasa_BCV
            FROM viaticos v LEFT JOIN servicios s ON v.id_servicio = s.id_servicio
        """
        df = pd.read_sql(query_v, conn)
        
        if not df.empty:
            # 2. Extraer Equipos y mapearlos a los tickets
            query_e = "SELECT id_servicio, tipo_equipo FROM equipos_asignados"
            df_eq = pd.read_sql(query_e, conn)
            equipos_dict = df_eq.groupby('id_servicio')['tipo_equipo'].apply(list).to_dict()
            
            # Asignar los equipos y asegurar que si está vacío sea una lista
            df['Equipos_Lista'] = df['Ticket_Num'].map(equipos_dict)
            df['Equipos_Lista'] = df['Equipos_Lista'].apply(lambda x: x if isinstance(x, list) else [])
            df['Equipos_Str'] = df['Equipos_Lista'].apply(lambda x: ", ".join(x))
            
            df['Fecha_Ticket'] = pd.to_datetime(df['Fecha_Ticket']).dt.date
            
            # EL ARREGLO: Convertir explícitamente TODO a string (texto) antes de sumar
            df['Ticket_Display'] = "TCK-" + df['Ticket_Num'].astype(str) + " | " + df['Cliente'].astype(str) + " | " + df['Fecha_Ticket'].astype(str)
            
    except Exception as e:
        st.error(f"Error: {e}")
        df = pd.DataFrame()
    finally: 
        conn.close()

    if df.empty:
        st.info("Aún no hay viáticos registrados en la base de datos.")
    else:
        st.sidebar.header("⚙️ Panel de Filtros")
        st.sidebar.caption("💡 Deja un filtro vacío para abarcar TODAS las opciones.")

        min_date, max_date = df['Fecha_Ticket'].min(), df['Fecha_Ticket'].max()
        fechas = st.sidebar.date_input("📅 Rango de Fechas del Ticket", [min_date, max_date], min_value=min_date, max_value=max_date)
        
        # Filtros
        tck_unicos = df['Ticket_Display'].unique().tolist()
        f_tck = st.sidebar.multiselect("🎟️ Ticket Específico", tck_unicos)

        cli_unicos = df['Cliente'].unique().tolist()
        f_cli = st.sidebar.multiselect("🏥 Cliente", cli_unicos)

        est_unicos = df['Estado'].unique().tolist()
        f_est = st.sidebar.multiselect("📍 Estado", est_unicos)
        
        cat_unicas = df['Categoria'].unique().tolist()
        f_cat = st.sidebar.multiselect("🏷️ Categoría de Gasto", cat_unicas)
        
        eq_unicos = df_eq['tipo_equipo'].unique().tolist() if not df_eq.empty else []
        f_eq = st.sidebar.multiselect("🩺 Equipo Médico (Contiene)", eq_unicos)

        # Aplicación Inteligente de Filtros (Si está vacío, asume TODOS)
        df_f = df.copy()
        if len(fechas) == 2:
            df_f = df_f[(df_f['Fecha_Ticket'] >= fechas[0]) & (df_f['Fecha_Ticket'] <= fechas[1])]
        if f_tck: df_f = df_f[df_f['Ticket_Display'].isin(f_tck)]
        if f_cli: df_f = df_f[df_f['Cliente'].isin(f_cli)]
        if f_est: df_f = df_f[df_f['Estado'].isin(f_est)]
        if f_cat: df_f = df_f[df_f['Categoria'].isin(f_cat)]
        if f_eq: 
            # Verifica si el ticket tiene AL MENOS UNO de los equipos filtrados
            df_f = df_f[df_f['Equipos_Lista'].apply(lambda eq_list: any(e in f_eq for e in eq_list))]

        # --- KPIs ---
        total_usd = df_f['Total_USD'].sum()
        total_tickets = df_f['Ticket_Num'].nunique()
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Gasto Total Acumulado (USD)", f"${total_usd:,.2f}")
        kpi2.metric("Mantenimientos Atendidos (Tickets)", total_tickets)
        kpi3.metric("Costo Promedio por Mantenimiento", f"${(total_usd/total_tickets):,.2f}" if total_tickets > 0 else "$0.00")

        st.markdown("<br>", unsafe_allow_html=True)

        # --- GRÁFICA LINEAL ---
        st.subheader("📈 Tendencia de Gastos en el Tiempo (USD)")
        if not df_f.empty:
            gasto_tiempo = df_f.groupby('Fecha_Ticket')['Total_USD'].sum()
            st.line_chart(gasto_tiempo)

        st.markdown("<br>", unsafe_allow_html=True)

        # --- GRÁFICOS INFERIORES ---
        graf1, graf2 = st.columns(2)
        with graf1:
            st.subheader("💵 Gastos por Categoría")
            if not df_f.empty:
                st.bar_chart(df_f.groupby('Categoria')['Total_USD'].sum())

        with graf2:
            st.subheader("🛠️ Porcentaje de Intervención por Equipo")
            if not df_f.empty and not df_eq.empty:
                # Obtenemos los tickets válidos tras los filtros
                tickets_validos = df_f['Ticket_Num'].unique()
                equipos_filtrados = df_eq[df_eq['id_servicio'].isin(tickets_validos)]
                
                conteo_equipos = equipos_filtrados['tipo_equipo'].value_counts()
                if not conteo_equipos.empty:
                    st.bar_chart(conteo_equipos)
                    
                    df_porcentajes = conteo_equipos.reset_index()
                    df_porcentajes.columns = ['Equipo', 'Cantidad de Mantenimientos']
                    # Total real de intervenciones de equipo
                    total_intervenciones = df_porcentajes['Cantidad de Mantenimientos'].sum()
                    df_porcentajes['Porcentaje (%)'] = (df_porcentajes['Cantidad de Mantenimientos'] / total_intervenciones * 100).apply(lambda x: f"{x:.1f}%")
                    st.dataframe(df_porcentajes, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.subheader("📋 Auditoría de Viáticos (Datos Crudos)")
        st.dataframe(df_f[['Ticket_Display', 'Ciudad', 'Equipos_Str', 'Categoria', 'Total_USD']], hide_index=True, use_container_width=True)