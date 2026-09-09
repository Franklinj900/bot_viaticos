import streamlit as st
import pandas as pd
import datetime
import random
import extra_streamlit_components as stx
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from database import SessionLocal

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Dashboard Viáticos", page_icon="📊", layout="wide")

# Inicializar el cliente de Slack usando los Secretos de Streamlit
try:
    SLACK_TOKEN = st.secrets["SLACK_BOT_TOKEN"]
    cliente_slack = WebClient(token=SLACK_TOKEN)
except Exception as e:
    st.error("⚠️ Error: No se encontró el SLACK_BOT_TOKEN en los Secrets de Streamlit.")
    cliente_slack = None

# --- 2. GESTIÓN DE COOKIES (MANTENER SESIÓN ABIERTA) ---
@st.cache_resource
def obtener_gestor_cookies():
    return stx.CookieManager()

gestor_cookies = obtener_gestor_cookies()

# Intentar leer la cookie al cargar la página
usuario_guardado = gestor_cookies.get(cookie="usuario_viaticos")

# Inicializar el estado de la sesión
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "esperando_codigo" not in st.session_state:
    st.session_state["esperando_codigo"] = False

# Si la cookie existe, forzar autenticación silenciosa
if usuario_guardado:
    st.session_state["autenticado"] = True
    st.session_state["usuario"] = usuario_guardado


# --- 3. FUNCIONES DE BASE DE DATOS Y SLACK ---
def cargar_datos_viaticos():
    """Descarga los datos de Neon.tech con protección anti-bloqueos."""
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
            v.tasa_bcv_dia AS "Tasa_BCV" 
        FROM viaticos v 
        LEFT JOIN servicios s ON v.id_servicio = s.id_servicio
        ORDER BY v.fecha_gasto DESC
        """
        df = pd.read_sql(query, db.bind)
        # Asegurarnos de que las fechas sean formato datetime en Pandas
        if not df.empty:
            df["fecha_gasto"] = pd.to_datetime(df["fecha_gasto"])
        return df
    except Exception as e:
        db.rollback() # <- EL ESCUDO CONTRA EL ERROR "Invalid Transaction"
        st.error(f"Error al conectar con la base de datos: {e}")
        return pd.DataFrame()
    finally:
        db.close()

def enviar_codigo_slack(correo):
    """Busca al usuario por correo en Slack y le envía un DM con un código de 4 dígitos."""
    try:
        # Buscar el ID del usuario en Slack usando su correo
        respuesta_usuario = cliente_slack.users_lookupByEmail(email=correo)
        user_id = respuesta_usuario["user"]["id"]
        
        # Generar código aleatorio de 4 dígitos
        codigo_generado = str(random.randint(1000, 9999))
        
        # Enviar mensaje directo
        mensaje = f"🔐 Tu código de acceso al Dashboard de Viáticos es: *{codigo_generado}*\n_No compartas este código con nadie._"
        cliente_slack.chat_postMessage(channel=user_id, text=mensaje)
        
        return codigo_generado
    except SlackApiError as e:
        st.error("No se pudo encontrar un usuario de Slack con ese correo o el bot no tiene permisos.")
        return None


# --- 4. INTERFAZ DE LOGIN ---
if not st.session_state["autenticado"]:
    st.title("🔐 Acceso Seguro - Dashboard de Viáticos")
    st.markdown("Por favor, verifica tu identidad usando tu correo corporativo conectado a Slack.")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        # Paso 1: Pedir el correo
        if not st.session_state["esperando_codigo"]:
            correo_input = st.text_input("Correo Electrónico (Slack)")
            if st.button("Enviar código de verificación", type="primary"):
                if correo_input and cliente_slack:
                    with st.spinner("Buscando en Slack y enviando código..."):
                        codigo = enviar_codigo_slack(correo_input.strip())
                        if codigo:
                            st.session_state["codigo_real"] = codigo
                            st.session_state["email_temporal"] = correo_input.strip()
                            st.session_state["esperando_codigo"] = True
                            st.rerun()
                else:
                    st.warning("Ingresa un correo válido.")
                    
        # Paso 2: Pedir el código
        else:
            st.info(f"Se ha enviado un código por mensaje directo de Slack a: **{st.session_state['email_temporal']}**")
            codigo_input = st.text_input("Ingresa el código de 4 dígitos", max_chars=4)
            
            if st.button("Verificar y Entrar", type="primary"):
                if codigo_input == st.session_state["codigo_real"]:
                    # Login exitoso
                    st.session_state["autenticado"] = True
                    st.session_state["usuario"] = st.session_state["email_temporal"]
                    
                    # Crear cookie para que dure 7 días
                    vencimiento = datetime.datetime.now() + datetime.timedelta(days=7)
                    gestor_cookies.set("usuario_viaticos", st.session_state["usuario"], expires_at=vencimiento)
                    
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("Código incorrecto. Intenta de nuevo.")
            
            if st.button("Cancelar y volver"):
                st.session_state["esperando_codigo"] = False
                st.rerun()


# --- 5. INTERFAZ DEL DASHBOARD (SOLO SI ESTÁ AUTENTICADO) ---
else:
    # Sidebar
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
    st.sidebar.write(f"👤 **Usuario:**\n{st.session_state['usuario']}")
    
    if st.sidebar.button("Cerrar Sesión"):
        gestor_cookies.delete("usuario_viaticos")
        for key in ["autenticado", "usuario", "esperando_codigo", "codigo_real", "email_temporal"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
        
    st.sidebar.divider()
    st.sidebar.header("Filtros")

    # Cargar Datos
    df = cargar_datos_viaticos()

    if df.empty:
        st.title("📊 Dashboard de Viáticos")
        st.warning("No hay datos de viáticos registrados todavía o hubo un error de conexión.")
    else:
        # Filtros Dinámicos
        clientes_unicos = ["Todos"] + list(df["Cliente"].dropna().unique())
        cliente_sel = st.sidebar.selectbox("Filtrar por Cliente", clientes_unicos)
        
        categorias_unicas = ["Todas"] + list(df["Categoria"].dropna().unique())
        categoria_sel = st.sidebar.selectbox("Filtrar por Categoría", categorias_unicas)

        # Aplicar Filtros
        df_filtrado = df.copy()
        if cliente_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Cliente"] == cliente_sel]
        if categoria_sel != "Todas":
            df_filtrado = df_filtrado[df_filtrado["Categoria"] == categoria_sel]

        # Interfaz Principal
        st.title("📊 Dashboard de Viáticos")
        st.markdown("---")

        # Tarjetas de KPI
        total_usd = df_filtrado["Total_USD"].sum()
        conteo_tickets = df_filtrado["Ticket_Num"].nunique()
        gasto_promedio = df_filtrado["Total_USD"].mean() if not df_filtrado.empty else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("Gasto Total (USD)", f"${total_usd:,.2f}")
        col2.metric("Tickets Atendidos", f"{conteo_tickets}")
        col3.metric("Gasto Promedio por Registro", f"${gasto_promedio:,.2f}")
        
        st.markdown("---")
        
        # Gráficas y Tablas
        col_grafica, col_tabla = st.columns([1, 1])
        
        with col_grafica:
            st.subheader("Gastos por Categoría (USD)")
            if not df_filtrado.empty:
                gastos_por_cat = df_filtrado.groupby("Categoria")["Total_USD"].sum().reset_index()
                st.bar_chart(gastos_por_cat, x="Categoria", y="Total_USD", use_container_width=True)
            else:
                st.info("No hay datos para graficar con los filtros actuales.")

        with col_tabla:
            st.subheader("Gastos por Cliente (USD)")
            if not df_filtrado.empty:
                gastos_por_cliente = df_filtrado.groupby("Cliente")["Total_USD"].sum().sort_values(ascending=False)
                st.dataframe(gastos_por_cliente, use_container_width=True)

        st.markdown("---")
        st.subheader("📋 Detalle General de Viáticos")
        # Mostrar la tabla formateada para que los números se vean limpios
        st.dataframe(
            df_filtrado.style.format({"Total_USD": "${:.2f}", "Tasa_BCV": "Bs. {:.2f}"}),
            use_container_width=True, 
            hide_index=True
        )
