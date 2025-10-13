"""
Generate a clean hierarchical JSON for D3.js
from a flat table with columns:
Node_ID, Name, Type, Top_Words, Representative_Docs, Parent_ID
"""

import pandas as pd
import json
import math
import ast
from collections import defaultdict

# =============================
# 1) Load CSV
# =============================
df = pd.read_csv("helper_df.csv")

required_cols = {"Node_ID", "Name", "Type", "Top_Words", "Representative_Docs", "Parent_ID"}
missing = required_cols - set(df.columns)
if missing:
    raise ValueError(f"CSV must contain columns: {sorted(required_cols)} (missing: {sorted(missing)})")

# Normalize IDs to strings so joins are consistent even if CSV mixes ints/floats/NaN
def norm_id(v):
    if pd.isna(v) or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)

df["Node_ID"] = df["Node_ID"].apply(norm_id)
df["Parent_ID"] = df["Parent_ID"].apply(norm_id)

# =============================
# 2) Clean + parse fields
# =============================
def clean_name(s):
    if pd.isna(s):
        return ""
    s = str(s)
    return s.strip().strip('"').rstrip("_")

df["Name"] = df["Name"].apply(clean_name)

def parse_list_field(x):
    if isinstance(x, list):
        return x
    if pd.isna(x):
        return []
    s = str(x).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            val = ast.literal_eval(s)
            return val if isinstance(val, list) else [s]
        except Exception:
            return [s]
    return [s] if s else []

df["Top_Words"] = df["Top_Words"].apply(parse_list_field)

# parse Representative_Docs safely (list of dicts)
def parse_docs_field(x):
    if pd.isna(x):
        return []
    s = str(x).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            val = ast.literal_eval(s)
            if isinstance(val, list):
                # ensure valid dicts
                return [d for d in val if isinstance(d, dict)]
        except Exception:
            pass
    return []

df["Representative_Docs"] = df["Representative_Docs"].apply(parse_docs_field)

# =============================
# 3) Build nodes dictionary
# =============================
nodes = {}
children_of = defaultdict(list)
has_parent = set()

for _, row in df.iterrows():
    nid = row["Node_ID"]
    if nid is None:
        continue

    nodes[nid] = {
        "id": nid,
        "name": row["Name"],
        "type": row["Type"],
        "top_words": row["Top_Words"],
        "representative_docs": row["Representative_Docs"],
        "children": []
    }

    pid = row["Parent_ID"]
    if pid:
        children_of[pid].append(nid)
        has_parent.add(nid)

# placeholder parents
for pid in children_of.keys():
    if pid not in nodes:
        nodes[pid] = {
            "id": pid,
            "name": f"(Missing parent {pid})",
            "type": "placeholder",
            "top_words": [],
            "representative_docs": [],
            "children": []
        }

# =============================
# 4) Link children
# =============================
for pid, child_ids in children_of.items():
    parent_node = nodes[pid]
    parent_node["children"] = [nodes[cid] for cid in child_ids if cid in nodes]

# =============================
# 5) Find root(s)
# =============================
all_ids = set(nodes.keys())
root_ids = sorted(all_ids - has_parent)

def to_tree(root_id):
    return nodes[root_id]

if len(root_ids) == 1:
    root = to_tree(root_ids[0])
else:
    root = {
        "id": "root",
        "name": "Root",
        "type": "virtual",
        "top_words": [],
        "representative_docs": [],
        "children": [to_tree(rid) for rid in root_ids]
    }

# =============================
# 6) Clean up strings to avoid stray quotes
# =============================
def clean_json_strings(obj):
    if isinstance(obj, dict):
        return {k: clean_json_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_json_strings(v) for v in obj]
    elif isinstance(obj, str):
        return obj.strip().strip('"').strip("'")
    return obj

root = clean_json_strings(root)

# =============================
# 7) Save JSON
# =============================
out_path = "static/topic_hierarchy_v2.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(root, f, ensure_ascii=False, indent=2)

print(f"✅ Wrote {out_path} with {len(nodes)} nodes and Representative_Docs included.")
