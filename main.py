import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import os
import pprint
import requests
from typing import Any, Dict, List, Tuple
from pydantic import BaseModel

app = FastAPI()

# serve files in the `src` folder (images, topic_hierarchy.html, etc.)
app.mount("/src", StaticFiles(directory="src"), name="src")

# serve CSS, JS and other static assets from the dedicated `static/` folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates (using current directory for HTML files)
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("search.html", {"request": request})

API_BASE_URL = os.getenv(
    "JURISTOPIC_API_BASE",
    "https://markmcrg--bertopic-search-service-fastapi-app.modal.run",
)
API_KEY = os.getenv("JURISTOPIC_API_KEY")

LOG_TIMEZONE = datetime.timezone(datetime.timedelta(hours=8))

def log_with_timestamp(message: str) -> None:
    now = datetime.datetime.now(LOG_TIMEZONE)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] - {message}")

class WarmupRequest(BaseModel):
    trigger: str | None = None

@app.post("/search/warmup")
async def warmup_search(payload: WarmupRequest):
    trigger = (payload.trigger or "focus").strip().lower()
    if trigger == "start-new-search":
        log_message = "Start new search clicked"
    elif trigger == "click":
        log_message = "Search bar clicked"
    else:
        log_message = "Search bar focused"

    log_with_timestamp(f"{log_message}, calling /healthz...")

    try:
        response = requests.get(f"{API_BASE_URL}/healthz", timeout=120)
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = str(exc)
        response_text = getattr(getattr(exc, "response", None), "text", "")
        if response_text:
            detail = f"{detail} | {response_text.strip()}"
        log_with_timestamp(f"/healthz response: ERROR {detail}")
        return {"status": "error", "detail": detail}

    single_line = " ".join(response.text.split()) if response.text else ""
    log_with_timestamp(f"/healthz response: {single_line}")
    return {"status": "ok"}

def _build_hierarchy(result_tree: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str], str]:
    closest_paths: List[List[str]] = []

    def build_node(node_id: str, node_data: Dict[str, Any], ancestors: List[str]) -> Dict[str, Any]:
        children = []
        for child in node_data.get("children", []) or []:
            for child_id, child_data in child.items():
                children.append(build_node(str(child_id), child_data, ancestors + [node_id]))

        is_closest = bool(node_data.get("is_closest"))
        if is_closest:
            closest_paths.append(ancestors + [node_id])

        return {
            "id": str(node_id),
            "name": node_data.get("Name", ""),
            "top_words": node_data.get("Top_Words", []),
            "representative_docs": node_data.get("Representative_Docs", []),
            "is_closest": is_closest,
            "children": children,
        }

    hierarchy: List[Dict[str, Any]] = []
    for root_id, root_data in (result_tree or {}).items():
        hierarchy.append(build_node(str(root_id), root_data, []))

    if not hierarchy:
        raise HTTPException(status_code=502, detail="Empty result returned by topic service")

    selected_path = closest_paths[0] if closest_paths else [hierarchy[0]["id"]]
    selected_topic_id = selected_path[-1]

    open_topic_ids = list(dict.fromkeys(selected_path))
    return hierarchy, open_topic_ids, selected_topic_id

def _index_nodes(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    def traverse(node: Dict[str, Any]) -> None:
        index[node["id"]] = node
        for child in node.get("children", []):
            traverse(child)
    for node in nodes:
        traverse(node)
    return index

@app.post("/search", response_class=HTMLResponse)
async def search_topics(request: Request, search_term: str = Form(...)):
    print(f"[LOG] Received search_term: {search_term}")

    # --- MOCK MODE (No API key needed) ---
    print("[MOCK] Using local fake response instead of remote topic service.")
    response_data = {
        "result": {
            "1": {
                "Name": "Liability of Public Officers",
                "Top_Words": ["negligence", "liability", "public", "employee", "duty"],
                "Representative_Docs": [
                    {"case_number": "G.R. 123456", "case_title": "People v. Dela Cruz", "case_link": "#"},
                    {"case_number": "G.R. 654321", "case_title": "Santos v. Commission", "case_link": "#"}
                ],
                "is_closest": True,
                "children": []
            },
            "2": {
                "Name": "Administrative Negligence",
                "Top_Words": ["administrative", "disciplinary", "sanction", "civil service"],
                "Representative_Docs": [
                    {"case_number": "G.R. 111111", "case_title": "Civil Service v. Reyes", "case_link": "#"}
                ],
                "is_closest": False,
                "children": []
            },
            "3": {
                "Name": "Criminal Negligence",
                "Top_Words": ["reckless", "imprudence", "criminal", "liability"],
                "Representative_Docs": [
                    {"case_number": "G.R. 222222", "case_title": "People v. Santos", "case_link": "#"}
                ],
                "is_closest": False,
                "children": []
            }
        }
    }

    result_tree = response_data.get("result")
    hierarchy, open_topic_ids, selected_topic_id = _build_hierarchy(result_tree)
    node_index = _index_nodes(hierarchy)
    selected_topic = node_index.get(selected_topic_id, {})

    # Mock top-3 topics with similarity scores for UI display
    top_topics = [
        {"name": node_index.get("1", {}).get("name", "Topic 1"), "top_words": node_index.get("1", {}).get("top_words", []), "score": 0.93},
        {"name": node_index.get("2", {}).get("name", "Topic 2"), "top_words": node_index.get("2", {}).get("top_words", []), "score": 0.87},
        {"name": node_index.get("3", {}).get("name", "Topic 3"), "top_words": node_index.get("3", {}).get("top_words", []), "score": 0.81},
    ]

    context = {
        "request": request,
        "search_term": search_term,
        "hierarchy": hierarchy,
        "open_topic_ids": open_topic_ids,
        "selected_topic_id": selected_topic_id,
        "selected_topic_name": selected_topic.get("name", ""),
        "selected_docs": selected_topic.get("representative_docs", []),
        "top_topics": top_topics,
        "hierarchy_json": json.dumps(hierarchy),
    }

    print("[LOG] Parsed hierarchy:")
    pprint.pprint({
        "selected_topic": selected_topic.get("name"),
        "open_topic_ids": open_topic_ids,
        "total_nodes": len(node_index),
    }, indent=2, width=100)

    return templates.TemplateResponse("results.html", context)
