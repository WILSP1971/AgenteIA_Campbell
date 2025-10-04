import os, json, uuid, requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from datetime import datetime

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
              {"id": "op_agendar",   "title": "2) Agendar o Solicitar Citas"},
              {"id": "op_telefonos", "title": "3) Teléfonos de Atención"}
            ]
          }]
        }
      }
    }
    r = requests.post(wa_url("messages"), headers=wa_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def wa_send_buttons(to, text, buttons):
    # Botones rápidos (hasta 3)
    payload = {
      "messaging_product":"whatsapp",
      "to":to,
      "type":"interactive",
      "interactive":{
        "type":"button",
        "body":{"text": text},
        "action":{"buttons":[{"type":"reply","reply":{"id":b["id"],"title":b["title"]}} for b in buttons]}
      }
    }
    r = requests.post(wa_url("messages"), headers=wa_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def wa_send_cta_url(to, text, url, label="Abrir enlace"):
    # Botón CTA URL para videollamada/portal orden
    payload = {
      "messaging_product":"whatsapp",
      "to":to,
      "type":"interactive",
      "interactive":{
        "type":"cta_url",
        "body":{"text": text},
        "action":{"name":"cta_url","parameters":{"display_text":label,"url":url}}
      }
    }
    r = requests.post(wa_url("messages"), headers=wa_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

# ---------- Tu API (BD) ----------
def api_headers():
    return {"Authorization": f"Bearer {DB_API_KEY}"} if DB_API_KEY else {}

def api_get_paciente_by_dni(CodigoEmp,dni):
    try:
        api_url = DB_API_BASE 
        params = {"CodigoEmp": "C30", "criterio": dni}
        r = requests.get(api_url, params=params)
        
        #r = requests.get(f"{DB_API_BASE}/Pacientes?/{CodigoEmp}/{dni}", headers=api_headers(), timeout=20)
        if r.status_code == 404: return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def api_create_paciente(payload):
    r = requests.post(f"{DB_API_BASE}/Pacientes", headers=api_headers(), json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def api_get_agenda(CodigoEmp,dni):
    api_url = "https://appsintranet.esculapiosis.com/ApiCampbell/api/CitasProgramadas"
    params = {"CodigoEmp": "C30", "criterio": dni}
    r = requests.get(api_url, params=params)
    
    #r = requests.get(f"{DB_API_BASE}/CitasProgramadas?CodigoEmp={CodigoEmp}&dni={dni}", headers=api_headers(), timeout=20)
    r.raise_for_status()
    return r.json()

def api_get_telefonos():
    r = requests.get(f"{DB_API_BASE}/telefonos", headers=api_headers(), timeout=20)
    r.raise_for_status()
    return r.json()

# ---------- IA ----------
def ai_answer(prompt, context=None):
    # Unifica: si configuras OPENAI usa GPT; si configuras ANTHROPIC usa Claude.
    if OPENAI_API_KEY:
        import openai
        openai.api_key = OPENAI_API_KEY
        sys_prompt = (
            "Eres un asistente clínico de ortopedia. Responde claro y breve, "
            "con enfoque informativo; no reemplazas un diagnóstico médico. "
            "Incluye banderas rojas y sugerencias de exámenes de imagen cuando corresponda."
        )
        messages = [{"role":"system","content":sys_prompt}]
        if context: messages.append({"role":"system","content":f"Contexto paciente: {context}"})
        messages.append({"role":"user","content":prompt})
        # Modelo de ejemplo; ajusta al que tengas disponible
        resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=messages, temperature=0.2)
        return resp.choices[0].message["content"].strip()

    if ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        sys_prompt = (
            "Eres un asistente clínico de ortopedia. Responde claro y breve, "
            "no sustituyes diagnóstico. Señala banderas rojas."
        )
        content = f"{('Contexto: ' + context) if context else ''}\nPregunta: {prompt}"
        resp = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=600,
            temperature=0.2,
            system=sys_prompt,
            messages=[{"role":"user","content":content}]
        )
        return resp.content[0].text.strip()

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
    dni = "".join([c for c in text if c.isdigit()])
    if not dni:
        return "❗ Debes enviar solo números de cédula. Intenta de nuevo."
    SESSION[user]["dni"] = dni
    paciente = api_get_paciente_by_dni(CodigoEmp,dni)
    if paciente:
        SESSION[user]["paciente"] = paciente
        SESSION[user]["step"] = "main_menu"
        wa_send_text(user, f"✅ Encontrado: {paciente.get('Paciente','(sin nombre)')} (CC {dni})")
        wa_send_list_menu(user)
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
        wa_send_buttons(
            user,
            "Manejo de Consultas:\nSelecciona una opción:",
            [
                {"id":"c_hablar_doctor","title":"Hablar con Doctor (IA)"},
                {"id":"c_orden_estudio","title":"Generar Orden Estudio"},
                {"id":"c_videollamada","title":"Videollamada"}
            ]
        )
        return None

    if selection_id == "op_agendar":
        SESSION[user]["step"] = "agendar"
        CodigoEmp = "C30"
        dni = SESSION[user]["dni"]
        try:
            agenda = api_get_agenda(CodigoEmp,dni)
            if not agenda:
                return "📅 No hay programación disponible."
            lines = ["📅 *Agenda disponible:*"]
            # for item in agenda:
            #     lines.append(f"- {item.get('Fecha','')} {item.get('Hora','')} · {item.get('Medico','')}")
            # return "\n".join(lines)
            
            for item in agenda:
                Paciente = item["Paciente"]
                datoscitas = item["CodServicio"]
                Fecha_Cita = item["Fecha"]
                Hora_Cita = item["Hora"]
                Observacion_Cita = item["Observacion"]
                Medico = item["Medico"]
                if datoscitas == "CE":
                    CodServicio="Consulta Externa"
                else:
                    CodServicio = "Especialidad"

            lines.append(f"- Paciente: {dni} {Paciente}") + "\n" 
            lines.append(f"- Cita En: {CodServicio}") + "\n" 
            lines.append(f"- Fecha: {Fecha_Cita}") + "\n" 
            lines.append(f"- Hora:: {Hora_Cita}") + "\n" 
            lines.append(f"- Medico: {Medico}") + "\n" 
            lines.append(f"- Observacion: {Observacion_Cita}") + "\n" 
          
            #"Paciente: " + nocedula + " " + datospac + "\n 0️⃣. Cita en: " + CodServicio +"\n 1️⃣. Fecha: " + Fecha_Cita + "\n 2️⃣. Hora Cita: " + Hora_Cita + "\n 3️⃣. Observacion: " + Observacion_Cita + "\n 4️⃣. Medico de Atencion: " + Medico

        finally:
            wa_send_list_menu(user)
            SESSION[user]["step"] = "main_menu"

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
        room = f"ortho-{uuid.uuid4().hex[:8]}"
        link = f"{VIDEO_BASE_URL}/{room}"
        SESSION[user]["step"] = "main_menu"
        wa_send_cta_url(user, "Abrir sala de videollamada segura.", link, "Unirme a la videollamada")
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


