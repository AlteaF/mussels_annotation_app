import streamlit as st
# The correct import path for version 0.8.0
from streamlit_image_annotation.point_annotation import point_annotation

from PIL import Image
import os
import json
import time
import requests
import base64
from datetime import datetime
from io import BytesIO
import re

# --- CONFIGURATION ---
IMAGE_DIR = "images" 
REPO_OWNER_REPO = st.secrets["DATA_REPO"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="Mussel Annotator v2", layout="wide")

# --- GITHUB API HELPERS ---
def github_request(method, path, json_data=None):
    url = f"https://api.github.com/repos/{REPO_OWNER_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    if method == "GET": return requests.get(url, headers=headers)
    return requests.put(url, headers=headers, json=json_data)

def upload_to_github(path, content_dict, message):
    res = github_request("GET", path)
    sha = res.json().get("sha") if res.status_code == 200 else None
    content_base64 = base64.b64encode(json.dumps(content_dict, indent=2).encode()).decode()
    data = {"message": message, "content": content_base64}
    if sha: data["sha"] = sha
    return github_request("PUT", path, data).status_code in [200, 201]

def get_existing_annotation(path):
    res = github_request("GET", path)
    if res.status_code == 200:
        return json.loads(base64.b64decode(res.json()["content"]).decode())
    return None

# --- SESSION STATE ---
if "user_name" not in st.session_state:
    st.session_state.update({
        "user_name": None, "img_idx": 0, "paused": False, 
        "elapsed": 0, "start_time": time.time(), "folder": None, "session_started": False
    })

# --- STEP 1: LOGIN ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotator", divider="rainbow")
    name_input = st.text_input("Enter your name:").strip()
    if name_input:
        res = github_request("GET", "")
        existing = [f["name"] for f in res.json() if f["type"] == "dir" and f["name"].startswith(name_input)] if res.status_code == 200 else []
        if existing:
            latest = sorted(existing)[-1]
            c1, c2 = st.columns(2)
            with c1:
                if st.button(f"Continue ({latest})"):
                    st.session_state.update({"user_name": name_input, "folder": latest, "session_started": True})
                    res_f = github_request("GET", latest)
                    if res_f.status_code == 200:
                        st.session_state.img_idx = len([f for f in res_f.json() if "_labels.json" in f["name"]])
                    st.rerun()
            with col2:
                if st.button("New Session"):
                    st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v{len(existing)+1}", "session_started": True})
                    st.rerun()
        elif st.button("Start Project"):
            st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v1", "session_started": True})
            st.rerun()
    st.stop()

# --- STEP 2: IMAGE PREP ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
if st.session_state.img_idx >= len(images):
    st.success("All images complete!"); st.stop()

current_img = images[st.session_state.img_idx]
img_path = os.path.join(IMAGE_DIR, current_img)
pil_img = Image.open(img_path)
orig_w, orig_h = pil_img.size

# --- STEP 3: ANNOTATION INTERFACE ---
st.write(f"**Current Image:** {current_img} ({st.session_state.img_idx+1}/{len(images)})")

label_path = f"{st.session_state.folder}/{current_img}_labels.json"
existing_data = get_existing_annotation(label_path)
initial_points = []
if existing_data:
    for r in existing_data["annotations"][0]["result"]:
        # Map back to 'x', 'y' format for the tool
        initial_points.append({'x': r['value']['x'], 'y': r['value']['y'], 'label': 'mussel'})

# Use the image path directly
# The key must change per image to reset the UI
new_points = point_annotation(
    image_path=img_path,
    labels=['mussel'],
    initial_point_list=initial_points,
    allow_empty=True,
    key=f"annotator_v5_{st.session_state.img_idx}"
)

# --- STEP 4: SAVE LOGIC ---
if new_points is not None:
    # Logic only proceeds if the user interacts with the tool
    if st.button("💾 Save & Next Image", type="primary"):
        with st.spinner("Saving to GitHub..."):
            buf = BytesIO()
            pil_img.save(buf, format="JPEG")
            img_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"

            ls_json = {
                "data": {"image": img_b64, "filename": current_img},
                "annotations": [{"result": [{
                    "original_width": orig_w, "original_height": orig_h,
                    "value": {"x": p['x'], "y": p['y'], "keypointlabels": ["mussel"]},
                    "from_name": "label", "to_name": "image", "type": "keypointlabels"
                } for p in new_points]}]
            }
            
            duration = round(time.time() - st.session_state.start_time, 2)
            meta_json = {"image": current_img, "duration_sec": duration, "count": len(new_points), "timestamp": datetime.now().isoformat()}
            
            if upload_to_github(label_path, ls_json, "Labels") and upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta_json, "Meta"):
                st.session_state.update({"img_idx": st.session_state.img_idx + 1, "start_time": time.time()})
                st.rerun()
