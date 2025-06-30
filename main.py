from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from gradio_client import Client
import pprint


app = FastAPI()

app.mount("/src", StaticFiles(directory="src"), name="src")

# Set up Jinja2 templates (using current directory for HTML files)
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("search.html", {"request": request})

@app.post("/search", response_class=HTMLResponse)
async def search_topics(request: Request, search_term: str = Form(...)):
    print(f"[LOG] Received search_term: {search_term}")

    client = Client("markmcrg/juristopic-backend")
    result = client.predict(
        search_term=search_term,
        api_name="/predict"
    )

    results_dict = {
        "topic_name": result[0],
        "top_words": result[1],
        "rep_docs": result[2]
    }

    print("[LOG] Parsed results_dict:")
    pprint.pprint(results_dict, indent=2, width=100)

    return templates.TemplateResponse("results.html", {"request": request, **results_dict})