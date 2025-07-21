from dotenv import load_dotenv
import os
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core. prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool, StructuredTool, tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pymongo import MongoClient
import requests


# ------------ CAMPOS COMUNES -------------
CAMPOS_EMPLEO = [
    "job_id", "job_title", "employer_name", "job_description", "job_city",
    "job_country", "job_apply_link", "job_posted_at_datetime_utc"
]

# ------------ TOOL 1: Buscar empleos -------------
@tool
def buscar_empleos(query: str = "data science", location: str = "PE") -> str:
    """Busca empleos desde la API de JSearch usando RapidAPI y devuelve el número de empleos encontrados."""

    try:
        url = "https://jsearch.p.rapidapi.com/search"
        params = {
            "query": query,
            "page": "1",
            "num_pages": "1",
            "country": location,
            "fields": ",".join(CAMPOS_EMPLEO)
        }
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            jobs = response.json().get("data", [])
            return f"Se encontraron {len(jobs)} empleos."
        else:
            return f"Error {response.status_code}: No se pudo acceder a la API."
    except Exception as e:
        return f"Excepción al buscar empleos: {str(e)}"

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
def resumen_jobs_mongo(mongo_uri: str) -> str:
    """Genera un resumen de las ofertas laborales nuevas almacenadas en MongoDB."""

    try:
        client = MongoClient(mongo_uri)
        db = client["empleos_ia"]
        collection = db["ofertas"]

        jobs = list(collection.find({"resumido": False}).sort("job_posted_at_datetime_utc", -1).limit(10))

        if not jobs:
            return "No hay ofertas nuevas para resumir."

        texto_jobs = "\n\n".join([
            f"{job['job_title']} en {job['employer_name']}, {job.get('job_city', 'sin ciudad')} ({job['job_country']})\n{job['job_description'][:300]}..."
            for job in jobs
        ])

        model = ChatOpenAI(temperature=0, model="gpt-4o")
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un asistente profesional que resume ofertas laborales para un boletín diario."),
            ("human", "Resume las siguientes ofertas de empleo:\n\n{ofertas}")
        ])

        chain = prompt | model
        resumen = chain.invoke({"ofertas": texto_jobs})

        for job in jobs:
            collection.update_one({"_id": job["_id"]}, {"$set": {"resumido": True}})

        return resumen.content

    except Exception as e:
        return f"Error al generar resumen: {str(e)}"

# ------------ Agente con memoria -------------
tolkit = [buscar_empleos, guardar_empleos_mongo, resumen_jobs_mongo]
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


agent_executor = create_react_agent(model, tolkit, checkpointer=memory, prompt=prompt)


# ------------ Ejecución ejemplo -------------
if __name__ == "__main__":
    config = {"configurable": {"thread_id": "empleos_peru_01"}}

    for step in agent_executor.stream(
        {"messages": "Busca empleos en Perú y guardalos en la base de datos."},
        config,
        stream_mode="values",
    ):
        step["messages"][-1].pretty_print()
