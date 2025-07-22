# 🤖 Asistente de Empleos en Ciencia de Datos (Perú)

Este proyecto implementa un **agente conversacional inteligente** desarrollado con [LangChain](https://www.langchain.com/), que actúa como un asistente especializado en **ofertas laborales de Ciencia de Datos en Perú**.  
Permite al usuario explorar empleos, almacenarlos, resumirlos y recibir alertas por correo electrónico.

---

## 🚀 Funcionalidades principales

| Herramienta                  | Descripción                                                                 |
|-----------------------------|-----------------------------------------------------------------------------|
| `buscar_empleos`            | Consulta ofertas laborales usando la API de JSearch (RapidAPI).            |
| `guardar_empleos_mongo`     | Guarda las ofertas en una base de datos MongoDB evitando duplicados.       |
| `resumen_puestos_recientes` | Resume las ofertas recientes almacenadas y organiza la información.        |
| `enviar_resumen_email`      | Envía por correo electrónico un resumen de las ofertas más recientes.      |

El agente utiliza memoria persistente mediante `MemorySaver`, lo que le permite recordar interacciones pasadas dentro de una sesión de Streamlit.

---

## 🧱 Tecnologías utilizadas

- [Python 3.10+](https://www.python.org/)
- [LangChain](https://www.langchain.com/)
- [OpenAI API](https://platform.openai.com/)
- [MongoDB Atlas](https://www.mongodb.com/atlas)
- [RapidAPI (JSearch)](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
- [Streamlit](https://streamlit.io/)
- `smtplib` + `email` (para envío de correos)

---

## ⚙️ Instalación

1. **Clona el repositorio:**

```bash
git clone https://github.com/tu-usuario/asistente-empleos-ds.git
cd asistente-empleos-ds
