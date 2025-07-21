from pymongo import MongoClient
import pprint
from dotenv import load_dotenv
import os

# Cargar variables de entorno
load_dotenv()

# Conexión a MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGODB_URI)

db = client["empleos_ia"]  # Nombre de la base de datos
collection = db["ofertas"]  # Nombre de la colección

# Contar y mostrar el número total de documentos
total_docs = collection.count_documents({})
print(f"📊 Total de documentos en la colección 'ofertas': {total_docs}")

# Recuperar y mostrar los primeros 10 documentos
print("\n📄 Primeros 10 documentos guardados en MongoDB:")
for doc in collection.find().limit(10):
    pprint.pprint(doc)
