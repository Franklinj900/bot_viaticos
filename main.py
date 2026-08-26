import ssl, os, aiohttp
from datetime import datetime
from fastapi import FastAPI, Request
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_sdk.web.async_client import AsyncWebClient
from database import init_db, SessionLocal
from models import Viatico, Usuario, Servicio, Cliente, EquipoAsignado

contexto_ssl = ssl.create_default_context()
contexto_ssl.check_hostname = False
contexto_ssl.verify_mode = ssl.CERT_NONE

# Extraemos los secretos de la caja fuerte de Render
SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

cliente_slack = AsyncWebClient(token=SLACK_TOKEN, ssl=contexto_ssl)
slack_app = AsyncApp(client=cliente_slack, signing_secret=SIGNING_SECRET)

ESTADOS_VENEZUELA = ["Amazonas", "Anzoátegui", "Apure", "Aragua", "Barinas", "Bolívar", "Carabobo", "Cojedes", "Delta Amacuro", "Falcón", "Guárico", "Lara", "Mérida", "Miranda", "Monagas", "Nueva Esparta", "Portuguesa", "Sucre", "Táchira", "Trujillo", "La Guaira", "Yaracuy", "Zulia", "Distrito Capital"]
TIPOS_EQUIPO = [{"text": {"type": "plain_text", "text": t}, "value": t} for t in ["Ecógrafo", "Rayos X", "Tomógrafo", "Incubadora", "Resonador", "Monitor", "Anestesia", "Otro"]]

async def obtener_tasa_bcv():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://ve.dolarapi.com/v1/dolares/oficial", timeout=5) as r:
                if r.status == 200: return float((await r.json())["promedio"])
    except: pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pydolarvenezuela-api.vercel.app/api/v1/dollar?page=bcv", timeout=5) as r:
                if r.status == 200: return float((await r.json())["monitors"]["bcv"]["price"])
    except: pass
    return None

# --- MÓDULO: CLIENTE ---
@slack_app.command("/nuevo-cliente")
async def abrir_cliente(ack, body, client):
    await ack()
    await client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "modal_crear_cliente", "title": {"type": "plain_text", "text": "Registrar Cliente"}, "submit": {"type": "plain_text", "text": "Guardar"},
        "blocks": [{"type": "input", "block_id": "b_nombre_cli", "element": {"type": "plain_text_input", "action_id": "i_nombre_cli"}, "label": {"type": "plain_text", "text": "Nombre de Clínica/Empresa"}}]
    })

@slack_app.view("modal_crear_cliente")
async def procesar_cliente(ack, body, client, view):
    await ack()
    nombre_cliente = view["state"]["values"]["b_nombre_cli"]["i_nombre_cli"]["value"].strip().upper()
    db = SessionLocal()
    try:
        if db.query(Cliente).filter(Cliente.nombre == nombre_cliente).first():
            await client.chat_postMessage(channel=body["user"]["id"], text=f"⚠️ El cliente *{nombre_cliente}* ya existe.")
        else:
            db.add(Cliente(nombre=nombre_cliente))
            db.commit()
            await client.chat_postMessage(channel=body["user"]["id"], text=f"🏢 *Cliente registrado:* {nombre_cliente}.")
    finally: db.close()

# --- MÓDULO: CREAR SERVICIO ---
@slack_app.command("/crear-servicio")
async def abrir_servicio(ack, body, client):
    await ack()
    db = SessionLocal()
    clientes_db = db.query(Cliente).order_by(Cliente.nombre).limit(100).all()
    db.close()
    if not clientes_db:
        await client.chat_postMessage(channel=body["user_id"], text="❌ Usa `/nuevo-cliente` primero.")
        return

    hoy = datetime.now().strftime("%Y-%m-%d")
    await client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "modal_crear_servicio", "title": {"type": "plain_text", "text": "Nuevo Servicio"}, "submit": {"type": "plain_text", "text": "Crear Ticket"},
        "blocks": [
            {"type": "input", "block_id": "b_fecha", "element": {"type": "datepicker", "initial_date": hoy, "action_id": "i_fecha"}, "label": {"type": "plain_text", "text": "Fecha del Servicio"}},
            {"type": "input", "block_id": "b_cli", "element": {"type": "static_select", "action_id": "i_cli", "options": [{"text": {"type": "plain_text", "text": c.nombre[:75]}, "value": c.nombre} for c in clientes_db]}, "label": {"type": "plain_text", "text": "Cliente"}},
            {"type": "input", "block_id": "b_estado", "element": {"type": "static_select", "action_id": "i_estado", "options": [{"text": {"type": "plain_text", "text": e}, "value": e} for e in ESTADOS_VENEZUELA]}, "label": {"type": "plain_text", "text": "Estado"}},
            {"type": "input", "block_id": "b_ciudad", "element": {"type": "plain_text_input", "action_id": "i_ciudad"}, "label": {"type": "plain_text", "text": "Ciudad (Ej. Socopó)"}},
            {"type": "header", "text": {"type": "plain_text", "text": "Primer Equipo a Revisar"}},
            {"type": "input", "block_id": "b_equi", "element": {"type": "static_select", "action_id": "i_equi", "options": TIPOS_EQUIPO}, "label": {"type": "plain_text", "text": "Tipo de Equipo"}},
            {"type": "input", "block_id": "b_marca", "optional": True, "element": {"type": "plain_text_input", "action_id": "i_marca"}, "label": {"type": "plain_text", "text": "Marca (Opcional)"}},
            {"type": "input", "block_id": "b_modelo", "optional": True, "element": {"type": "plain_text_input", "action_id": "i_modelo"}, "label": {"type": "plain_text", "text": "Modelo (Opcional)"}},
            {"type": "input", "block_id": "b_colab", "optional": True, "element": {"type": "multi_users_select", "action_id": "s_colab"}, "label": {"type": "plain_text", "text": "Ingenieros Asignados"}}
        ]
    })

@slack_app.view("modal_crear_servicio")
async def procesar_servicio(ack, body, client, view):
    await ack()
    val, user_id = view["state"]["values"], body["user"]["id"]
    fecha_str = val["b_fecha"]["i_fecha"]["selected_date"]
    fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    db = SessionLocal()
    try:
        creador = db.query(Usuario).filter(Usuario.slack_user_id == user_id).first()
        if not creador:
            creador = Usuario(slack_user_id=user_id)
            db.add(creador)
            
        nuevo_servicio = Servicio(
            creador_id=user_id, cliente=val["b_cli"]["i_cli"]["selected_option"]["value"],
            estado_ve=val["b_estado"]["i_estado"]["selected_option"]["value"],
            ciudad=val["b_ciudad"]["i_ciudad"]["value"].title(), fecha_servicio=fecha_obj
        )
        db.add(nuevo_servicio)

        primer_equipo = EquipoAsignado(
            tipo_equipo=val["b_equi"]["i_equi"]["selected_option"]["value"],
            marca=val["b_marca"]["i_marca"]["value"] if "value" in val["b_marca"]["i_marca"] else None,
            modelo=val["b_modelo"]["i_modelo"]["value"] if "value" in val["b_modelo"]["i_modelo"] else None,
            servicio=nuevo_servicio
        )
        db.add(primer_equipo)

        for c_id in val["b_colab"]["s_colab"].get("selected_users", []):
            colab = db.query(Usuario).filter(Usuario.slack_user_id == c_id).first()
            if not colab:
                colab = Usuario(slack_user_id=c_id)
                db.add(colab)
            nuevo_servicio.colaboradores.append(colab)

        db.commit()
        db.refresh(nuevo_servicio)
        await client.chat_postMessage(channel=user_id, text=f"✅ *Servicio creado!*\nTicket: `TCK-{nuevo_servicio.id_servicio}` | Fecha: {fecha_str}")
    finally: db.close()

# --- NUEVO MÓDULO: AGREGAR EQUIPO EXTRA A UN TICKET ---
@slack_app.command("/agregar-equipo")
async def abrir_equipo(ack, body, client):
    await ack()
    db = SessionLocal()
    servicios = db.query(Servicio).order_by(Servicio.id_servicio.desc()).limit(20).all()
    db.close()
    if not servicios:
        await client.chat_postMessage(channel=body["user_id"], text="❌ No hay tickets creados.")
        return
        
    opciones_tck = [{"text": {"type": "plain_text", "text": f"TCK-{s.id_servicio} | {s.cliente} ({s.fecha_servicio})"}, "value": str(s.id_servicio)} for s in servicios]

    await client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "modal_agregar_equipo", "title": {"type": "plain_text", "text": "Agregar Equipo Extra"}, "submit": {"type": "plain_text", "text": "Añadir a Ticket"},
        "blocks": [
            {"type": "input", "block_id": "b_tck", "element": {"type": "static_select", "action_id": "i_tck", "options": opciones_tck}, "label": {"type": "plain_text", "text": "Selecciona el Ticket"}},
            {"type": "input", "block_id": "b_equi", "element": {"type": "static_select", "action_id": "i_equi", "options": TIPOS_EQUIPO}, "label": {"type": "plain_text", "text": "Tipo de Equipo"}},
            {"type": "input", "block_id": "b_marca", "optional": True, "element": {"type": "plain_text_input", "action_id": "i_marca"}, "label": {"type": "plain_text", "text": "Marca"}},
            {"type": "input", "block_id": "b_modelo", "optional": True, "element": {"type": "plain_text_input", "action_id": "i_modelo"}, "label": {"type": "plain_text", "text": "Modelo"}}
        ]
    })

@slack_app.view("modal_agregar_equipo")
async def procesar_equipo(ack, body, client, view):
    await ack()
    val = view["state"]["values"]
    db = SessionLocal()
    try:
        tck_id = int(val["b_tck"]["i_tck"]["selected_option"]["value"])
        nuevo_eq = EquipoAsignado(
            id_servicio=tck_id, tipo_equipo=val["b_equi"]["i_equi"]["selected_option"]["value"],
            marca=val["b_marca"]["i_marca"]["value"] if "value" in val["b_marca"]["i_marca"] else None,
            modelo=val["b_modelo"]["i_modelo"]["value"] if "value" in val["b_modelo"]["i_modelo"] else None
        )
        db.add(nuevo_eq)
        db.commit()
        await client.chat_postMessage(channel=body["user"]["id"], text=f"🔧 *Equipo extra añadido* al TCK-{tck_id}.")
    finally: db.close()

# --- MÓDULO: VIÁTICOS Y EL RESTO IGUAL... ---
@slack_app.command("/viaticos")
async def abrir_viaticos(ack, body, client):
    await ack()
    db = SessionLocal()
    servicios = db.query(Servicio).order_by(Servicio.id_servicio.desc()).limit(20).all()
    db.close()
    if not servicios: return
    opc = [{"text": {"type": "plain_text", "text": f"TCK-{s.id_servicio} | {s.cliente}"[:75]}, "value": str(s.id_servicio)} for s in servicios]
    
    cats = [
        {"text": {"type": "plain_text", "text": "🍽️ Comida"}, "value": "Alimentación"},
        {"text": {"type": "plain_text", "text": "🚗 Gasolina / Peajes"}, "value": "Combustible/Peaje"},
        {"text": {"type": "plain_text", "text": "🚕 Taxis / Pasajes"}, "value": "Transporte"},
        {"text": {"type": "plain_text", "text": "🏨 Hospedaje"}, "value": "Hospedaje"},
        {"text": {"type": "plain_text", "text": "🧼 Insumos Limpieza"}, "value": "Limpieza"},
        {"text": {"type": "plain_text", "text": "🔌 Cables / Adaptadores"}, "value": "Cables"},
        {"text": {"type": "plain_text", "text": "⚙️ Repuestos"}, "value": "Repuestos"},
        {"text": {"type": "plain_text", "text": "💸 Gastos Extra"}, "value": "Gastos Extraordinarios"}
    ]
    await client.views_open(trigger_id=body["trigger_id"], view={
        "type": "modal", "callback_id": "modal_registro_viatico", "title": {"type": "plain_text", "text": "Viáticos"}, "submit": {"type": "plain_text", "text": "Registrar"},
        "blocks": [
            {"type": "input", "block_id": "b_srv", "element": {"type": "static_select", "action_id": "i_srv", "options": opc}, "label": {"type": "plain_text", "text": "Ticket"}},
            {"type": "input", "block_id": "b_cat", "element": {"type": "static_select", "action_id": "i_cat", "options": cats}, "label": {"type": "plain_text", "text": "Categoría"}},
            {"type": "input", "block_id": "b_mon", "element": {"type": "static_select", "action_id": "i_mon", "options": [{"text": {"type": "plain_text", "text": "USD"}, "value": "USD"}, {"text": {"type": "plain_text", "text": "Bs"}, "value": "VES"}]}, "label": {"type": "plain_text", "text": "Moneda"}},
            {"type": "input", "block_id": "b_mon_val", "element": {"type": "plain_text_input", "action_id": "i_mon_val"}, "label": {"type": "plain_text", "text": "Monto"}}
        ]
    })

@slack_app.view("modal_registro_viatico")
async def procesar_viaticos(ack, body, client, view):
    await ack()
    val, user_id = view["state"]["values"], body["user"]["id"]
    try: monto_ingresado = float(val["b_mon_val"]["i_mon_val"]["value"])
    except: return
    tasa_bcv = await obtener_tasa_bcv() or 1.0
    moneda = val["b_mon"]["i_mon"]["selected_option"]["value"]
    m_usd = monto_ingresado if moneda == "USD" else monto_ingresado / tasa_bcv
    m_bs = monto_ingresado * tasa_bcv if moneda == "USD" else monto_ingresado
    
    db = SessionLocal()
    db.add(Viatico(slack_user_id=user_id, id_servicio=int(val["b_srv"]["i_srv"]["selected_option"]["value"]), categoria_gasto=val["b_cat"]["i_cat"]["selected_option"]["value"], moneda_ingreso=moneda, monto_ingresado=monto_ingresado, tasa_bcv_dia=tasa_bcv, monto_usd_calculado=m_usd, monto_bs_calculado=m_bs))
    db.commit()
    db.close()
    await client.chat_postMessage(channel=user_id, text=f"✅ *Gasto guardado:* ${m_usd:.2f} USD")

app_fastapi = FastAPI()
slack_handler = AsyncSlackRequestHandler(slack_app)
@app_fastapi.on_event("startup")
async def startup_event(): init_db()
@app_fastapi.post("/slack/events")
async def slack_events(req: Request): return await slack_handler.handle(req)
