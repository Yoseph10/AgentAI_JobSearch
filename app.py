import streamlit as st
from dotenv import load_dotenv
import os
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core. prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool, StructuredTool, tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pymongo import MongoClient
from email.message import EmailMessage
import smtplib
import requests


# ------------ CAMPOS COMUNES -------------
CAMPOS_EMPLEO = [
    "job_id", "job_title", "employer_name", "job_description", "job_city",
    "job_country", "job_apply_link", "job_posted_at_datetime_utc"
]

# ------------ TOOL 1: Buscar empleos -------------
@tool
def buscar_empleos(query: str = "data science", location: str = "PE") -> str:
    """Busca empleos y muestra los títulos sin guardarlos en MongoDB. Esta herramienta se emplea únicamente cuando
    el usuario solicita ver empleos nuevos y no pide que se guarden los empleos en la Base de Datos."""
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {"query": query, "page": "1", "num_pages": "1", "country": location}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return f"Error al buscar empleos: {response.status_code}"

    empleos = response.json().get("data", [])
    return "\n".join([f"- {e['job_title']} en {e['employer_name']}" for e in empleos]) or "No se encontraron empleos."


# ------------ TOOL 2: Guardar en MongoDB -------------
@tool
def guardar_empleos_mongo(query: str = "data science", location: str = "PE") -> str:
    """Obtiene empleos desde la API y los guarda en MongoDB. Marca como nuevos los que no existían.
    Esta herramienta se emplea cuando el usuario solicita guardar los empleos en la Base de Datos."""

    try:
        url = "https://jsearch.p.rapidapi.com/search"
        params = {
            "query": query,
            "page": "1",
            "num_pages": "1",
            "country": location#,
            #"fields": ",".join(CAMPOS_EMPLEO)
        }
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
        }
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            return f"Error en API: {response.status_code}"

        jobs = response.json().get("data", [])
        if not jobs:
            return "No se encontraron trabajos."

        client = MongoClient(MONGODB_URI)
        db = client["empleos_ia"]
        collection = db["ofertas"]

        insertados = 0
        for job in jobs:
            job["resumido"] = False
            result = collection.update_one(
                {"job_id": job["job_id"]},
                {"$set": job},
                upsert=True
            )
            if result.upserted_id:
                insertados += 1

        return f"Se guardaron {len(jobs)} empleos en MongoDB ({insertados} nuevos)."

    except Exception as e:
        return f"Error al guardar en MongoDB: {str(e)}"

# ------------ TOOL 3: Resumir desde MongoDB -------------
@tool
def resumen_puestos_recientes(limite: int = 10) -> str:
    """
    Recupera los últimos 'limite' registros de MongoDB y genera un resumen estructurado de cada oferta:
    - Puesto
    - Link de aplicación
    - Breve resumen de descripción
    - Nivel de experiencia
    - Fecha de publicación
    """
    try:
        client = MongoClient(MONGODB_URI)
        db = client["empleos_ia"]
        collection = db["ofertas"]

        # Obtener los últimos N registros ordenados por _id de inserción (si no hay fecha)
        jobs = list(collection.find().sort("_id", -1).limit(limite))

        if not jobs:
            return "No se encontraron registros recientes en la base de datos."

        # Preparar el texto para enviar al modelo
        items = []
        for job in jobs:
            descripcion_corta = job.get("job_description", "")[:600].replace("\n", " ").strip()
            fecha = job.get("job_posted_at_datetime_utc") or "No especificada"
            texto = f"""\
            Puesto: {job.get('job_title', 'N/A')}
            Empresa: {job.get('employer_name', 'N/A')}
            Link: {job.get('job_apply_link', 'N/A')}
            Fecha de publicación: {fecha}
            Descripción del puesto:
            {descripcion_corta}
    """
            items.append(texto)

        bloque_puestos = "\n---\n".join(items)

        # PROMPT nuevo más detallado
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un analista laboral experto en tecnología. Recibiste una lista de nuevas oportunidades laborales."),
            ("human",
             "Resume la siguiente lista de ofertas de empleo de forma estructurada.\n"
             "Para cada oferta, proporciona un resumen claro con los siguientes elementos:\n"
             "- Título del puesto\n"
             "- Empresa\n"
             "- Enlace de aplicación\n"
             "- Requisitos clave o experiencia solicitada\n"
             "- Breve descripción del rol\n"
             "- Fecha de publicación (si está disponible)\n\n"
             "Ofertas:\n{puestos}")
        ])

        model = ChatOpenAI(temperature=0.3, model="gpt-4o")
        chain = prompt | model
        resumen = chain.invoke({"puestos": bloque_puestos})

        return resumen.content

    except Exception as e:
        return f"Error al generar resumen de puestos: {str(e)}"

# ------------ TOOL 4: Enviar resumen por correo  -------------

@tool
def enviar_resumen_email(destinatario: str = "") -> str:
    """
    Recupera los últimos puestos desde MongoDB, genera un resumen y lo envía por email.
    Si no se proporciona un correo, solicita al usuario que indique uno.
    Esta herramienta se emplea cuando el usuario solicita recibir un resumen por correo electrónico.
    """
    try:
        if not destinatario.strip():
            return "¿A qué correo electrónico deseas que te envíe el resumen?"

        resumen = resumen_puestos_recientes.invoke({"limite": 10})
        if not resumen or "Error" in resumen:
            return "No se pudo generar el resumen para enviar por correo."

        remitente = EMAIL_FROM
        clave_app = EMAIL_PASSWORD

        msg = EmailMessage()
        msg["Subject"] = "Resumen de empleos recientes en Ciencia de Datos"
        msg["From"] = remitente
        msg["To"] = destinatario
        msg.set_content(resumen)

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(remitente, clave_app)
            smtp.send_message(msg)

        return f"Resumen enviado correctamente a {destinatario}."

    except Exception as e:
        return f"Error al enviar correo: {str(e)}"



# ------------ Agente con memoria -------------
toolkit = [buscar_empleos, guardar_empleos_mongo, resumen_puestos_recientes, enviar_resumen_email]
model = ChatOpenAI(model="gpt-4o", temperature=0.3)

# --- MODIFICACIÓN CLAVE PARA LA MEMORIA EN STREAMLIT ---
# Almacena MemorySaver en st.session_state para que persista a través de recargas.
if "memory_saver" not in st.session_state:
    st.session_state["memory_saver"] = MemorySaver()

# Usa la instancia de MemorySaver almacenada en session_state
memory = st.session_state["memory_saver"]

# El prompt como lo definimos en la última corrección, sin 'chat_history' o 'input' explícitos.
prompt = ChatPromptTemplate.from_messages([
    ("system",
        """Eres un agente experto en gestión de ofertas de empleo relacionadas con Ciencia de Datos en Perú.
Puedes usar herramientas para buscar empleos en una API, guardar resultados en MongoDB y generar resúmenes.

Las respuestas deben ser claras y concisas, pero amables y empáticas.

Tu tarea es decidir en cada paso si necesitas usar una herramienta para avanzar.

Si el usuario solicita ver empleos que no sea de Ciencia de Datos, comenta que no es tu especialidad y sugiere buscar en otra parte.
"""
    ),
    MessagesPlaceholder("messages"), # Aquí es donde create_react_agent inyecta los mensajes, incluyendo el historial.
])


agent_executor = create_react_agent(model, toolkit, checkpointer=memory, prompt=prompt)


# ---------- Interfaz Streamlit ----------
st.set_page_config(page_title="Asistente de Empleos", page_icon="🤖")
st.title("🤖 Asistente de Empleos en Ciencia de Datos")

if "history" not in st.session_state:
    st.session_state["history"] = []

# 🔁 Mostrar historial anterior
for mensaje in st.session_state["history"]:
    with st.chat_message(mensaje["role"]):
        st.markdown(mensaje["content"])

user_input = st.chat_input("Escribe algo...")

if user_input:
    st.session_state["history"].append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        output = ""
        try:
            # Puedes usar un thread_id fijo para una sola sesión de usuario o generar uno dinámico
            # Para una app de un solo usuario, "streamlit_empleos" está bien.
            # Para múltiples usuarios, considera algo como f"streamlit_empleos_{st.session_state.session_id}"
            config = {"configurable": {"thread_id": "streamlit_empleos"}}

            all_messages = []
            # Pasamos HumanMessage(content=user_input) a 'messages'
            # create_react_agent y MemorySaver se encargarán del historial automáticamente.
            for paso in agent_executor.stream({"messages": [HumanMessage(content=user_input)]}, config, stream_mode="values"):
                all_messages.extend(paso["messages"])

            if all_messages:
                # El último mensaje de 'all_messages' contendrá la respuesta final del asistente.
                final_assistant_message = all_messages[-1].content
                st.markdown(final_assistant_message)
                output = final_assistant_message
            else:
                st.markdown("No se generó ninguna respuesta.")

        except Exception as e:
            st.error(f"Error: {e}")
            output = f"Error: {e}"

    st.session_state["history"].append({"role": "assistant", "content": output})
