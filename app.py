import os, json, uuid, requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from datetime import datetime
from openai import OpenAI
from urllib.parse import quote

load_dotenv()
app = Flask(__name__)

# WHATSAPP_TOKEN = "EAAK3KV6raVkBPimgb49XjOX1DCr9kJcX7dZBHUCh9KY8VQcOuGT9RRVKL8RXuZAJuHqrMMj7ZCyMXsuVV396kEfGaeqB39wxIaiA0rD6sq1vZAqMRnOiQAr5JvKFYZAwhD9fpfnAX5o3zyLZCiVoOXFufLwRG5XKsP2M9T50ZClQQ2SX7zAsfxH2fik1btBMr8IiBHivIyyXQvrroEx2YjmkpCsgDW3wCuZAJ8jZC9mpSLZCgZD" #os.getenv("WHATSAPP_TOKEN")
# PHONE_NUMBER_ID = "796239056896115" #os.getenv("WHATSAPP_PHONE_NUMBER_ID")
# VERIFY_TOKEN = "TWSCodeJG#75" #os.getenv("WHATSAPP_VERIFY_TOKEN")
# DB_API_BASE = "https://appsintranet.esculapiosis.com/ApiCampbell/api" #os.getenv("DB_API_BASE")
# DB_API_KEY = "EAAK3KV6raVkBPimgb49XjOX1DCr9kJcX7dZBHUCh9KY8VQcOuGT9RRVKL8RXuZAJuHqrMMj7ZCyMXsuVV396kEfGaeqB39wxIaiA0rD6sq1vZAqMRnOiQAr5JvKFYZAwhD9fpfnAX5o3zyLZCiVoOXFufLwRG5XKsP2M9T50ZClQQ2SX7zAsfxH2fik1btBMr8IiBHivIyyXQvrroEx2YjmkpCsgDW3wCuZAJ8jZC9mpSLZCgZD" #os.getenv("DB_API_KEY")
# VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "https://meet.jit.si")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # opcional si usas OpenAI
# ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # opcional si usas Claude

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
DB_API_BASE = os.getenv("DB_API_BASE")
DB_API_KEY = os.getenv("DB_API_KEY")
VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "https://meet.jit.si")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # opcional si usas OpenAI
#ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # opcional si usas Claude

# ---- Estado simple en memoria (demo); en prod usa Redis/DB ----
SESSION = {}  # dict: { user_wa_id: {"step": "...", "dni": "....", ...} }

# ---------- Utilidades de WhatsApp ----------
def wa_url(path):
    return f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/{path}"

def wa_headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

def wa_send_text(to, text):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text}
    }
    r = requests.post(wa_url("messages"), headers=wa_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def wa_send_list_menu(to):
    # Menú principal (Lista interactiva)
    payload = {
      "messaging_product": "whatsapp",
      "to": to,
      "type": "interactive",
      "interactive": {
        "type": "list",
        "body": {"text": "Seleccione una opción del menú:"},
        "footer": {"text": "Agente Ortopedia"},
        "action": {
          "button": "Abrir menú",
          "sections": [{
            "title": "Opciones",
            "rows": [
              {"id": "op_consultas", "title": "1) Manejo de Consultas"},
              {"id": "op_agendar",   "title": "2) Consultar Citas"},
              {"id": "op_telefonos", "title": "3) Contactanos"}
            ]
          }]
        }
      }
    }
    r = requests.post(wa_url("messages"), headers=wa_headers(), json=payload, timeout=30)
    if not r.ok:
        # Log del cuerpo exacto del error de Meta
        raise requests.HTTPError(f"{r.status_code} {r.reason} | body={r.text}")
    return r.json()

def wa_post(path, payload):
    url = wa_url(path)
    r = requests.post(url, headers=wa_headers(), json=payload, timeout=30)
    if not r.ok:
        # 👇 verás el JSON exacto de error de Meta en los logs
        raise requests.HTTPError(f"{r.status_code} {r.reason} | body={r.text}")
    return r.json()

def wa_send_buttons(to, text, buttons):
    # buttons = [{"id":"...", "title":"..."}]  # máx 3, title ≤ ~20 chars
    payload = {
      "messaging_product": "whatsapp",
      "to": to,
      "type": "interactive",
      "interactive": {
        "type": "button",
        "body": {"text": text},  # ≤ 1024
        "action": {
          "buttons": [
            {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
            for b in buttons
          ]
        }
      }
    }
    return wa_post("messages", payload)

def wa_send_cta_url(to, text, url, label="Abrir enlace"):
    payload = {
      "messaging_product":"whatsapp",
      "to": to,
      "type":"interactive",
      "interactive":{
        "type":"cta_url",
        "body":{"text": text},                      # <= 1024 chars
        "action":{"name":"cta_url","parameters":{
          "display_text": label,                    # <= ~20 chars
          "url": url
        }}
      }
    }
    try:
        return wa_post("messages", payload)
    except requests.HTTPError as e:
        # Si tu versión de Graph / app no soporta cta_url, cae aquí.
        app.logger.error("CTA_URL no soportado o inválido: %s", e)
        # Fallback robusto: texto con el link clickeable
        return wa_send_text(to, f"{text}\n\n🔗 {url}")

# def wa_send_cta_url(to, text, url, label="Abrir enlace"):
#     # Botón CTA URL para videollamada/portal orden
#     payload = {
#       "messaging_product":"whatsapp",
#       "to":to,
#       "type":"interactive",
#       "interactive":{
#         "type":"cta_url",
#         "body":{"text": text},
#         "action":{"name":"cta_url","parameters":{"display_text":label,"url":url}}
#       }
#     }
#     r = requests.post(wa_url("messages"), headers=wa_headers(), json=payload, timeout=30)
#     r.raise_for_status()
#     return r.json()

# ---------- Tu API (BD) ----------
def api_headers():
    return {"Authorization": f"Bearer {DB_API_KEY}"} if DB_API_KEY else {}

def api_get_paciente_by_dni(CodigoEmp,dni):
    try:
        #url = f"{DB_API_BASE}/Pacientes/{CodigoEmp}/{dni}"
        #r = requests.get(url, headers=api_headers(), timeout=20)
        
        api_url = "https://appsintranet.esculapiosis.com/ApiCampbell/api/Pacientes" #f"{DB_API_BASE}/Pacientes" 
        params = {"CodigoEmp": "C30", "criterio": dni}
        r = requests.get(api_url, params=params)

        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()

        # Normaliza: si viene lista, toma el primero
        if isinstance(data, list):
            return data[0] if data else None
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None

def _extraer_nombre(p):
    if not p: 
        return "(sin nombre)"
    # Intenta campos comunes
    for k in ("Paciente", "nombre", "NombreCompleto", "fullName"):
        if k in p and p[k]:
            return str(p[k]).strip()
    # Si tu API separa nombres y apellidos:
    nombres = str(p.get("Nombres", "")).strip()
    apellidos = str(p.get("Apellidos", "")).strip()
    combo = (nombres + " " + apellidos).strip()
    return combo or "(sin nombre)"

def api_create_paciente(payload):
    r = requests.post(f"{DB_API_BASE}/Pacientes", headers=api_headers(), json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def api_get_agenda(CodigoEmp, dni):
    try:
        api_url = "https://appsintranet.esculapiosis.com/ApiCampbell/api/CitasProgramadas" #f"{DB_API_BASE}/CitasProgramadas"
        params = {"CodigoEmp": CodigoEmp, "criterio": dni}
        r = requests.get(api_url, params=params) #

        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()

        # Asegura lista
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    except Exception as e:
        app.logger.error("Error en api_get_agenda: %s", e)
        return []

def api_get_telefonos():
    r = requests.get(f"{DB_API_BASE}/telefonos", headers=api_headers(), timeout=20)
    r.raise_for_status()
    return r.json()

# ---------- IA ----------
def ai_answer(prompt, context=None):
    # Unifica: si configuras OPENAI usa GPT; si configuras ANTHROPIC usa Claude.
    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        sys_prompt = (
            "Eres un asistente clínico de ortopedia. Responde claro y breve, "
            "con enfoque informativo; no reemplazas un diagnóstico médico. "
            "Incluye banderas rojas y sugerencias de exámenes de imagen cuando corresponda."
        )
        messages = [{"role":"system","content":sys_prompt}]
        if context:
            messages.append({"role":"system","content":f"Contexto paciente: {context}"})
        messages.append({"role":"user","content":prompt})

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()

    return "⚠️ No hay proveedor de IA configurado."

# ---------- Flujo de conversación ----------
def ensure_session(user):
    if user not in SESSION:
        SESSION[user] = {"step":"init", "dni":None, "paciente":None}
    return SESSION[user]

def handle_init(user):
    SESSION[user]["step"] = "ask_dni"
    return "👋 Soy tu asistente virtual de Ortopedia.\nPor favor escribe tu *cédula* para continuar."

def handle_dni(user, text):
    CodigoEmp = "C30"

    dni = "".join(c for c in text if c.isdigit())
    if not dni:
        return "❗ Debes enviar solo números de cédula. Intenta de nuevo."

    SESSION[user]["dni"] = dni
    paciente = api_get_paciente_by_dni(CodigoEmp, dni)
    app.logger.info("Paciente API resp: %s", json.dumps(paciente, ensure_ascii=False))
 
    if paciente:
        nombre = _extraer_nombre(paciente)
        SESSION[user]["paciente"] = paciente      # guarda el dict completo
        SESSION[user]["step"] = "main_menu"
        wa_send_text(user, f"✅ Paciente Registrado: {nombre} (CC {dni})")
        try:
           wa_send_list_menu(user)
        except requests.HTTPError as e:
            app.logger.error("LIST ERROR: %s", e)  # mostrará body=... con la causa exacta
        #wa_send_list_menu(user)
        return None
    else:
        SESSION[user]["step"] = "register_wait_name"
        return ("No encontré tu registro.\n"
                "Por favor envía en *un solo mensaje*:\n"
                "`Nombre Apellidos`")

def handle_register_name(user, text):
    nombre = " ".join(text.strip().split())
    if len(nombre) < 3:
        return "❗ Nombre muy corto. Envía: `Nombre Apellidos`."
    payload = {"dni": SESSION[user]["dni"], "nombre": nombre}
    try:
        paciente = api_create_paciente(payload)
        SESSION[user]["paciente"] = paciente
        SESSION[user]["step"] = "main_menu"
        wa_send_text(user, f"✅ Registrado {nombre} (CC {payload['dni']})")
        wa_send_list_menu(user)
        return None
    except Exception as ex:
        return f"⚠️ No pude registrar: {ex}"

def handle_menu_selection(user, selection_id):
    if selection_id == "op_consultas":
        SESSION[user]["step"] = "consultas_menu"
        try:
            wa_send_buttons(
                user,
                "Manejo de Consultas:\nSelecciona una opción:",
                [
                    {"id": "c_hablar_doctor", "title": "Consulta IA"},    # <= 12
                    {"id": "c_orden_estudio", "title": "Orden Estudio"},  # <= 14
                    {"id": "c_videollamada",  "title": "Videollamada"}    # <= 12
                ]
            )
        except requests.HTTPError as e:
            app.logger.error("BUTTONS ERROR: %s", e)  # verás body=... con la causa
            wa_send_text(user, "⚠️ No pude mostrar el submenú. Intenta de nuevo.")
        return None

    if selection_id == "op_agendar":
        SESSION[user]["step"] = "agendar"
        CodigoEmp = "C30"
        dni = SESSION[user]["dni"]

        agenda = api_get_agenda(CodigoEmp, dni)
        app.logger.info("Citas Programadas API resp: %s", json.dumps(agenda, ensure_ascii=False))

        if not agenda:
            wa_send_list_menu(user)
            return "📅 No hay programación disponible."
            

        lines = ["📅 *Agenda disponible:*"]
        for item in agenda:
            paciente = item.get("Paciente", "(sin nombre)")
            codserv = "Consulta Externa" if item.get("CodServicio") == "CE" else "Especialidad"
            fecha = item.get("Fecha", "")
            hora = item.get("Hora", "")
            obs = item.get("Observacion", "")
            medico = item.get("Medico", "")

            lines.append(
                f"- Paciente: {dni} {paciente}\n"
                f"  Cita en: {codserv}\n"
                f"  Fecha: {fecha}\n"
                f"  Hora: {hora}\n"
                f"  Observación: {obs}\n"
                f"  Médico: {medico}\n"
            )

        SESSION[user]["paciente"] = paciente      # guarda el dict completo
        SESSION[user]["step"] = "main_menu"
        mensaje = "\n".join(lines)
        #mensaje = "Paciente: " + dni + " " + paciente + "\n 0️⃣. Cita en: " + codserv +"\n 1️⃣. Fecha: " + fecha + "\n 2️⃣. Hora Cita: " + hora + "\n 3️⃣. Observacion: " + obs + "\n 4️⃣. Medico de Atencion: " + medico
 
        wa_send_text(user, mensaje)
        try:
            wa_send_list_menu(user)
        except requests.HTTPError as e:
            app.logger.error("LIST ERROR: %s", e)  # mostrará body=... con la causa exacta
        return None

    if selection_id == "op_telefonos":
        SESSION[user]["step"] = "telefonos"
        tels = api_get_telefonos()
        lines = ["📞 *Teléfonos de Atención:*"]
        for t in tels:
            lines.append(f"- {t.get('label','')}: {t.get('numero','')}")
        SESSION[user]["step"] = "main_menu"
        wa_send_list_menu(user)
        return "\n".join(lines)

    return "❓ Opción no reconocida."

def handle_consultas_buttons(user, btn_id):
    if btn_id == "c_hablar_doctor":
        SESSION[user]["step"] = "consultas_chat"
        return "🩺 Escribe tu pregunta de ortopedia. (Soy IA, no reemplazo consulta médica)."
    if btn_id == "c_orden_estudio":
        SESSION[user]["step"] = "orden_estudio"
        return ("¿Qué estudio necesitas generar?\n"
                "- Rayos X\n- Resonancia\n- TAC\nEscribe uno.")
    if btn_id == "c_videollamada":
        # Construye un nombre de sala único y corto
        room = f"ortho-{uuid.uuid4().hex[:8]}"
        # Intenta poner el nombre del paciente (si existe) para mostrarlo en Jitsi
        paciente = SESSION[user].get("paciente") or {}
        nombre_paciente = paciente.get("Paciente") or paciente.get("nombre") or f"CC {SESSION[user].get('dni','')}"
        # Opcional: título de la reunión
        subject = "Videollamada Ortopedia"

        link = generate_jitsi_link(room, display_name=nombre_paciente, subject=subject)

        SESSION[user]["step"] = "main_menu"
        # Enviar botón CTA
        wa_send_cta_url(user, "Abrir sala de videollamada segura.", link, "Unirme a la videollamada")
        # Enviar también el link en texto (respaldo)
        wa_send_text(user, f"🔗 Enlace directo: {link}")
        # Volver a mostrar menú principal
        wa_send_list_menu(user)
        return None

    return "❓ Botón no reconocido."

def handle_consulta_ia(user, text):
    paciente = SESSION[user].get("paciente", {})
    ctx = f"Paciente: {paciente.get('nombre','(sin)')} CC {SESSION[user].get('dni')}"
    answer = ai_answer(text, context=ctx)
    # Sugerir volver al menú
    wa_send_list_menu(user)
    SESSION[user]["step"] = "main_menu"
    return answer

def handle_orden_estudio(user, text):
    estudio = text.strip().lower()
    valid = ["rayos x","rayosx","radiografía","resonancia","rm","tac","tomografía"]
    if not any(k in estudio for k in valid):
        return "❗ Indica un estudio válido (Rayos X, Resonancia, TAC)."
    # Genera un “link de orden” (puedes generar PDF y alojarlo)
    order_id = uuid.uuid4().hex[:10]
    order_url = f"https://tu-dominio/ordenes/{order_id}"
    wa_send_cta_url(user, f"Orden de estudio generada: {order_id}", order_url, "Ver orden")
    wa_send_list_menu(user)
    SESSION[user]["step"] = "main_menu"
    return None

def generate_jitsi_link(room_slug: str, display_name: str = "", subject: str = "") -> str:
    """
    Genera un link listo de Jitsi (meet.jit.si) con nombre sugerido y título opcional.
    - room_slug: nombre único de la sala (sin espacios).
    - display_name: nombre que Jitsi intentará prellenar (el usuario puede editarlo).
    - subject: título de la reunión (opcional).

    Notas:
    - En meet.jit.si los parámetros de #config y #userInfo son best-effort.
    - No se puede preasignar contraseña vía URL en meet.jit.si público.
    """
    base = os.getenv("VIDEO_BASE_URL", "https://meet.jit.si").rstrip("/")
    # Parametrización útil (prejoin activado y nombre sugerido)
    fragments = []
    if subject:
        fragments.append(f"config.subject={quote(subject)}")
    # Mostrar pantalla de pre-join (útil para elegir mic/cam)
    fragments.append("config.prejoinConfig.enabled=true")
    if display_name:
        fragments.append(f"userInfo.displayName={quote(display_name)}")
    frag = "#" + "&".join(fragments) if fragments else ""
    return f"{base}/{room_slug}{frag}"

# ---- helpers de fallback ----
def map_mainmenu_text_to_id(text: str):
    t = (text or "").strip().lower()
    if not t: 
        return None
    # admite "1", "1)", "1.", o el título completo
    if t.startswith("1") or "manejo de consultas" in t:
        return "op_consultas"
    if t.startswith("2") or "agendar" in t:
        return "op_agendar"
    if t.startswith("3") or "teléfonos" in t or "contact" in t:
        return "op_telefonos"
    return None

def map_consultas_text_to_btn(text: str):
    t = (text or "").strip().lower()
    if not t:
        return None
    if t.startswith("1") or "hablar con doctor" in t or "ia" in t:
        return "c_hablar_doctor"
    if t.startswith("2") or "orden estudio" in t or "orden" in t:
        return "c_orden_estudio"
    if t.startswith("3") or "videollamada" in t:
        return "c_videollamada"
    return None

# ---------- Webhook ----------
@app.route("/webhook", methods=["GET"])
def verify():
    # Para verificación en Meta
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def receive():
    data = request.get_json()
    # Depura en logs
    app.logger.info("Incoming: %s", json.dumps(data, ensure_ascii=False))

    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return "ok", 200

        msg = entry["messages"][0]
        wa_id = msg["from"]           # teléfono del usuario
        session = ensure_session(wa_id)

        # Captura selección de interactivos
        interactive = msg.get("interactive")
        if interactive:
            itype = interactive.get("type")
            if itype == "list_reply":
                sel_id = interactive["list_reply"]["id"]
                out = handle_menu_selection(wa_id, sel_id)
                if out: wa_send_text(wa_id, out)
                return "ok", 200
            elif itype == "button_reply":
                btn_id = interactive["button_reply"]["id"]
                out = handle_consultas_buttons(wa_id, btn_id)
                if out: wa_send_text(wa_id, out)
                return "ok", 200

        # Texto normal
        text = ""
        if msg.get("type") == "text":
            text = msg["text"]["body"].strip()

        # Máquina de estados básica
        step = session["step"]
        app.logger.info("MSG TYPE=%s INTERACTIVE=%s TEXT=%s", msg.get("type"), bool(msg.get("interactive")), text)

        # Fallback cuando el cliente envía texto en lugar de interactive.list_reply
        if step == "main_menu" and text:
            sel = map_mainmenu_text_to_id(text)
            if sel:
                out = handle_menu_selection(wa_id, sel)
                if out: wa_send_text(wa_id, out)
                return "ok", 200

        # Fallback cuando el cliente responde el submenú por texto
        if step == "consultas_menu" and text:
            btn = map_consultas_text_to_btn(text)
            if btn:
                out = handle_consultas_buttons(wa_id, btn)
                if out: wa_send_text(wa_id, out)
                return "ok", 200
        
        if step == "init":
            wa_send_text(wa_id, handle_init(wa_id))
        elif step == "ask_dni":
            out = handle_dni(wa_id, text)
            if out: wa_send_text(wa_id, out)
        elif step == "register_wait_name":
            out = handle_register_name(wa_id, text)
            if out: wa_send_text(wa_id, out)
        elif step == "consultas_menu":
            wa_send_text(wa_id, "Usa los botones para continuar.")
        elif step == "consultas_chat":
            out = handle_consulta_ia(wa_id, text)
            if out: wa_send_text(wa_id, out)
        elif step == "orden_estudio":
            out = handle_orden_estudio(wa_id, text)
            if out: wa_send_text(wa_id, out)
        else:
            # Cualquier otro caso: re-mostrar menú
            wa_send_list_menu(wa_id)

    except Exception as ex:
        app.logger.exception("Error processing webhook: %s", ex)

    return "ok", 200

# @app.route("/", methods=["GET"])
# def health():
#     return jsonify({"status":"ok","time": datetime.utcnow().isoformat()+"Z"})

@app.route('/')
def home():
    return jsonify({
        'status': 'ok',
        'message': 'Webhook de WhatsApp funcionando'
    })

@app.get("/diag")
def diag():
    try:
        r = requests.get(
            f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}",
            params={"access_token": WHATSAPP_TOKEN},
            timeout=20
        )
        ok = r.ok
        data = r.json()
    except Exception as e:
        ok = False
        data = {"error": str(e)}
    # Muestra longitudes para evitar exponer secretos completos
    return jsonify({
        "env": {
            "PHONE_NUMBER_ID": PHONE_NUMBER_ID,
            "TOKEN_len": len(WHATSAPP_TOKEN) if WHATSAPP_TOKEN else 0
        },
        "graph_check_ok": ok,
        "graph_response": data
    })


# @app.get("/")
# def root():
#     return {"ok": True, "msg": "WhatsApp backend running."}

if __name__ == "__main__":
    #app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
    app.run(debug=True)


