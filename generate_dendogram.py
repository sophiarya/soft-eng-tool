"""
Generate a clean hierarchical JSON for D3.js
from hierarchy_table.csv (using *_Name columns).
"""

import pandas as pd
import json

# =====================================================
# 1. Load CSV
# =====================================================
df = pd.read_csv("hierarchy_table.csv")

required_cols = {
    "Parent_ID", "Parent_Name",
    "Child_Left_ID", "Child_Left_Name",
    "Child_Right_ID", "Child_Right_Name",
    "Distance"
}
if not required_cols.issubset(df.columns):
    raise ValueError(f"CSV must contain: {required_cols}")

# =====================================================
# 2. Build mapping of nodes
# =====================================================
nodes = {}

for _, row in df.iterrows():
    parent_id = int(row["Parent_ID"])
    parent_name = row["Parent_Name"]

    left_id = int(row["Child_Left_ID"])
    left_name = row["Child_Left_Name"]

    right_id = int(row["Child_Right_ID"])
    right_name = row["Child_Right_Name"]

    # ensure parent exists
    if parent_id not in nodes:
        nodes[parent_id] = {"id": parent_id, "name": parent_name, "children": []}

    # add children as placeholders
    if left_id not in nodes:
        nodes[left_id] = {"id": left_id, "name": left_name}
    if right_id not in nodes:
        nodes[right_id] = {"id": right_id, "name": right_name}

    # link children to parent
    nodes[parent_id]["children"] = [nodes[left_id], nodes[right_id]]

# =====================================================
# 3. Find root node (a parent that’s not any child)
# =====================================================
all_parents = set(df["Parent_ID"].astype(int))
all_children = set(df["Child_Left_ID"].astype(int)) | set(df["Child_Right_ID"].astype(int))
root_id_candidates = list(all_parents - all_children)
root_id = root_id_candidates[0] if root_id_candidates else list(all_parents)[0]

root = nodes[root_id]

# =====================================================
# 4. Save JSON (clean structure)
# =====================================================
with open("static/topic_hierarchy.json", "w", encoding="utf-8") as f:
    json.dump(root, f, ensure_ascii=False, indent=2)

print("✅ topic_hierarchy.json generated with real topic titles!")
