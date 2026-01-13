import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import os
import pprint
import requests
from typing import Any, Dict, List, Tuple, Optional
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


@app.get("/static/sc_cases_truncated_final_refit.csv")
async def serve_cases_csv() -> FileResponse:
    csv_path = os.path.join(os.path.dirname(__file__), "sc_cases_truncated_final_refit.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="Dataset not found")
    return FileResponse(csv_path, media_type="text/csv", filename="sc_cases_truncated_final_refit.csv")

LOG_TIMEZONE = datetime.timezone(datetime.timedelta(hours=8))

def log_with_timestamp(message: str) -> None:
    now = datetime.datetime.now(LOG_TIMEZONE)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] - {message}")

class WarmupRequest(BaseModel):
    trigger: Optional[str] = None

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
        response = requests.get(
            f"https://markemjuris--bertopic-search-service-fastapi-app.modal.run/healthz",
            timeout=120,
        )
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
    """Return hierarchy-ready data, IDs to auto-open, and selected topic ID."""

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

    open_topic_ids = list(dict.fromkeys(selected_path))  # preserve order, unique
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

def _find_closest_node(root_tree: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Return (id, data) for the first node flagged as closest within the hierarchy."""

    def traverse(node_id: str, node_data: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
        if bool(node_data.get("is_closest")):
            return str(node_id), node_data

        for child in node_data.get("children", []) or []:
            for child_id, child_data in child.items():
                if not isinstance(child_data, dict):
                    continue
                found = traverse(str(child_id), child_data)
                if found:
                    return found
        return None

    for root_id, root_data in root_tree.items():
        if not isinstance(root_data, dict):
            continue
        found = traverse(str(root_id), root_data)
        if found:
            return found
    return None

@app.post("/search", response_class=HTMLResponse)
async def search_topics(request: Request, search_term: str = Form(...)):
    print(f"[LOG] Received search_term: {search_term}")

    headers = {"Content-Type": "application/json"}

    payload = {
        "query": search_term,
        "levels_up": 2,
        "top_n": 3,

    }

    try:
        response = requests.post(
            f"https://markemjuris--bertopic-search-service-fastapi-app.modal.run/search",
            json=payload,
            headers=headers,
            timeout=300,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print("[ERROR] Topic service request failed:", exc)
        raise HTTPException(status_code=502, detail="Failed to fetch topics from upstream service") from exc

    try:
        response_data: Dict[str, Any] = response.json()
    except ValueError as exc:
        print("[ERROR] Invalid JSON from topic service:", exc)
        raise HTTPException(status_code=502, detail="Invalid response from upstream service") from exc

    raw_results = response_data.get("result")
    if raw_results is None:
        print("[ERROR] Missing 'result' field in response:")
        pprint.pprint(response_data, indent=2, width=100)
        raise HTTPException(status_code=502, detail="Unexpected response format from topic service")

    if isinstance(raw_results, dict):
        result_items: List[Dict[str, Any]] = [raw_results]
    elif isinstance(raw_results, list):
        result_items = [item for item in raw_results if isinstance(item, dict)]
    else:
        print("[ERROR] Unexpected 'result' type:", type(raw_results))
        raise HTTPException(status_code=502, detail="Unexpected response format from topic service")

    primary_entry = next(
        (item for item in result_items if isinstance(item.get("hierarchy"), dict)),
        None,
    )
    if primary_entry is None:
        print("[ERROR] No hierarchy-containing entries found in response:")
        pprint.pprint(raw_results, indent=2, width=100)
        raise HTTPException(status_code=502, detail="No hierarchy data returned by topic service")

    primary_hierarchy = primary_entry.get("hierarchy", {})
    primary_index = result_items.index(primary_entry)

    hierarchy: List[Dict[str, Any]] = []
    open_topic_ids: List[str] = []
    selected_topic_id: str = ""

    hierarchies_payload: Dict[str, Dict[str, Any]] = {}
    top_topics: List[Dict[str, Any]] = []

    for idx, item in enumerate(result_items):
        hierarchy_tree = item.get("hierarchy")
        if not isinstance(hierarchy_tree, dict) or not hierarchy_tree:
            continue

        hierarchy_key = f"hierarchy_{idx}"
        processed_hierarchy, open_ids, default_topic_id = _build_hierarchy(hierarchy_tree)
        hierarchies_payload[hierarchy_key] = {
            "hierarchy": processed_hierarchy,
            "open_topic_ids": open_ids,
            "selected_topic_id": default_topic_id,
        }

        if idx == primary_index:
            hierarchy = processed_hierarchy
            open_topic_ids = open_ids
            selected_topic_id = default_topic_id

        score = item.get("score")
        try:
            score_value = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_value = 0.0

        closest = _find_closest_node(hierarchy_tree)
        if closest is None:
            closest = next(
                (
                    (str(root_id), root_data)
                    for root_id, root_data in hierarchy_tree.items()
                    if isinstance(root_data, dict)
                ),
                None,
            )
        if closest is None:
            continue

        topic_id, topic_data = closest
        top_topics.append({
            "id": str(topic_id),
            "name": topic_data.get("Name", ""),
            "top_words": topic_data.get("Top_Words") or [],
            "score": score_value,
            "hierarchy_key": hierarchy_key,
        })

    if not hierarchy:
        raise HTTPException(status_code=502, detail="Empty result returned by topic service")

    node_index = _index_nodes(hierarchy)
    selected_topic = node_index.get(selected_topic_id, {})
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
        "all_hierarchies_json": json.dumps(hierarchies_payload),
        "initial_hierarchy_key": f"hierarchy_{primary_index}",
    }

    print("[LOG] Parsed hierarchy:")
    pprint.pprint({
        "selected_topic": selected_topic.get("name"),
        "open_topic_ids": open_topic_ids,
        "total_nodes": len(node_index),
    }, indent=2, width=100)

    return templates.TemplateResponse("results.html", context)
