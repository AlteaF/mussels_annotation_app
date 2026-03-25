import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image
import os, json, time, requests, base64
from datetime import datetime
from io import BytesIO

# --- CONFIG ---
IMAGE_DIR = "images"
REPO_OWNER_REPO = st.secrets["DATA_REPO"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="Mussel Annotator Pro", layout="wide")

# --- SESSION STATE ---
if "user_name" not in st.session_state:
    st.session_state.update({
        "user_name": None, "img_idx": 0, "folder": None, 
        "session_started": False, "points": [], "mode": "Add"
    })

# --- GITHUB HELPERS (Unchanged) ---
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

# --- LOGIN LOGIC ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotation Project")
    name_input = st.text_input("Name:").strip()
    if name_input:
        res = github_request("GET", "")
        existing = [f["name"] for f in res.json() if f["name"].startswith(name_input)] if res.status_code == 200 else []
        if existing:
            latest = sorted(existing)[-1]
            c1, c2 = st.columns(2)
            if c1.button(f"Continue ({latest})"):
                st.session_state.update({"user_name": name_input, "folder": latest, "session_started": True})
                st.rerun()
            if c2.button("New Session"):
                st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v{len(existing)+1}", "session_started": True})
                st.rerun()
    st.stop()

# --- IMAGE PREP ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
if st.session_state.img_idx >= len(images):
    st.success("All Done!"); st.stop()

current_img = images[st.session_state.img_idx]
img_path = os.path.join(IMAGE_DIR, current_img)
pil_img = Image.open(img_path)
width, height = pil_img.size

# --- UI LAYOUT ---
st.title(f"🖼️ {current_img} ({st.session_state.img_idx+1}/{len(images)})")

# MODES AT THE TOP (As requested)
col_m1, col_m2, col_m3 = st.columns([2, 2, 6])
st.session_state.mode = col_m1.radio("Mode", ["Add Points", "Delete Points"], horizontal=True)
if col_m2.button("🗑️ Clear All"):
    st.session_state.points = []
    st.rerun()

# THE IMAGE (Huge and Responsive)
# This component returns the x, y of the click
value = streamlit_image_coordinates(pil_img, key="mussel_coord", use_container_width=True)

if value:
    # Convert click coordinates to percentage (0-100) to stay resolution-independent
    click_x = (value["x"] / value["width"]) * 100
    click_y = (value["y"] / value["height"]) * 100
    
    if st.session_state.mode == "Add Points":
        # Check if point already exists nearby to prevent double-clicks
        if not any(abs(p[0]-click_x) < 1 and abs(p[1]-click_y) < 1 for p in st.session_state.points):
            st.session_state.points.append([click_x, click_y])
            st.rerun()
    else:
        # Delete mode: find closest point and remove it
        st.session_state.points = [p for p in st.session_state.points if not (abs(p[0]-click_x) < 2 and abs(p[1]-click_y) < 2)]
        st.rerun()

# DRAW VISUAL FEEDBACK (Optional: uses an SVG overlay or just a list)
st.write(f"**Mussels identified:** {len(st.session_state.points)}")

# --- SAVE ---
if st.button("💾 SAVE & NEXT", type="primary", use_container_width=True):
    with st.spinner("Saving..."):
        res_list = [{
            "original_width": width, "original_height": height,
            "value": {"x": p[0], "y": p[1], "keypointlabels": ["mussel"]},
            "from_name": "label", "to_name": "image", "type": "keypointlabels"
        } for p in st.session_state.points]
        
        ls_json = {"data": {"image": "...", "filename": current_img}, "annotations": [{"result": res_list}]}
        label_path = f"{st.session_state.folder}/{current_img}_labels.json"
        
        if upload_to_github(label_path, ls_json, "Save"):
            st.session_state.img_idx += 1
            st.session_state.points = [] # Reset for next image
            st.rerun()
