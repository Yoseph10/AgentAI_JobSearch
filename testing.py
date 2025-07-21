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
    """Busca empleos y muestra los títulos sin guardarlos en MongoDB."""
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
    """Obtiene empleos desde la API y los guarda en MongoDB. Marca como nuevos los que no existían."""

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
    Recupera los últimos 'limite' registros de MongoDB y genera un resumen de los puestos de trabajo encontrados.
    """
    try:
        client = MongoClient(MONGODB_URI)
        db = client["empleos_ia"]
        collection = db["ofertas"]

        # Obtener los últimos N registros insertados
        jobs = list(collection.find().sort("job_posted_at_datetime_utc", -1).limit(limite))

        if not jobs:
            return "No se encontraron registros recientes en la base de datos."

        # Construir texto de entrada con solo título y empresa
        texto_jobs = "\n".join([
            f"- {job['job_title']} en {job['employer_name']}" for job in jobs
        ])

        model = ChatOpenAI(temperature=0, model="gpt-4o")

        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un asistente profesional que analiza el mercado laboral."),
            ("human", "Con base en esta lista de puestos recientes, genera un resumen breve de las oportunidades de trabajo disponibles:\n\n{puestos}")
        ])

        chain = prompt | model
        resumen = chain.invoke({"puestos": texto_jobs})

        return resumen.content

    except Exception as e:
        return f"Error al generar resumen de puestos: {str(e)}"

# ------------ TOOL 4: Enviar resumen por correo  -------------

@tool
def enviar_resumen_email(destinatario: str = "") -> str:
    """
    Recupera los últimos puestos desde MongoDB, genera un resumen y lo envía por email.
    Si no se proporciona un correo, solicita al usuario que indique uno.
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
model = ChatOpenAI(model="gpt-4o")

# Memoria de corto plazo
#memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
memory = MemorySaver()


prompt = ChatPromptTemplate.from_messages([
    ("system",
        """Eres un agente experto en gestión de ofertas de empleo relacionadas con Ciencia de Datos en Perú.
Puedes usar herramientas para buscar empleos en una API, guardar resultados en MongoDB y generar resúmenes.

Tu tarea es decidir en cada paso si necesitas usar una herramienta para avanzar.
"""
    ),
    ("human", "{messages}"),
])


agent_executor = create_react_agent(model, toolkit, checkpointer=memory, prompt=prompt)


# ------------ Ejecución ejemplo -------------

def main():
    print("🤖 Bienvenido al asistente de empleos en Ciencia de Datos.")
    print("Escribe 'salir' para terminar la conversación.\n")

    config = {"configurable": {"thread_id": "empleos_peru_01"}}

    while True:
        entrada = input("Tú: ")

        if entrada.lower() in ["salir", "exit"]:
            print("Asistente: ¡Hasta pronto! 👋")
            break

        if not entrada.strip():
            print("Asistente: Por favor, escribe algo.")
            continue

        # Flujo del agente con memoria
        try:
            for paso in agent_executor.stream(
                {"messages": entrada},
                config,
                stream_mode="values"
            ):
                respuesta = paso["messages"][-1].content
                if respuesta:
                    print(f"Asistente: {respuesta}")
        except Exception as e:
            print(f"Asistente: Ocurrió un error: {e}")


if __name__ == "__main__":
    main()
