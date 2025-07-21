from dotenv import load_dotenv
import os
from pymongo import MongoClient
import requests

# Cargar variables de entorno
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

# 1. Buscar empleos desde la API
def test_api_rapidapi(query="data science", location="PE", num_pages=1, fields=None):
    """
    Busca empleos usando la API de JSearch (RapidAPI) y devuelve un máximo de `max_results`.
    """
    url = "https://jsearch.p.rapidapi.com/search"

    params = {
        "query": query,
        "page": "1",
        "num_pages": str(num_pages),
        "country": location
    }

    if fields:
        params["fields"] = ",".join(fields)

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        jobs = response.json().get("data", [])
        print(f"✅ Se encontraron {len(jobs)} empleos.")
        return jobs
    else:
        print(f"❌ Error {response.status_code}: {response.text}")
        return []

# 2. Guardar en MongoDB
def test_guardar_mongo(jobs):
    if not jobs:
        print("⚠️ No hay trabajos para guardar.")
        return

    client = MongoClient(MONGODB_URI)
    db = client["empleos_ia"]           # ✅ Tu base de datos
    collection = db["ofertas"]          # ✅ Tu colección

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

    print(f"✅ Se insertaron {insertados} nuevos documentos en MongoDB.")


# Ejecutar prueba
if __name__ == "__main__":

    campos = [
    "job_id", "job_title", "employer_name", "job_description", "job_city",
    "job_country", "job_apply_link", "job_posted_at_datetime_utc"
    ]

    jobs = test_api_rapidapi(query="machine learning", location="PE", num_pages=1, fields=campos)

    test_guardar_mongo(jobs)
