import streamlit as st
from streamlit_drawable_canvas import st_canvas
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

st.set_page_config(page_title="Mussel Annotator", layout="wide")

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
        "elapsed": 0, "start_time": time.time(), "load_prev": False, 
        "folder": None, "session_started": False
    })

# --- STEP 1: LOGIN ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotation Project", divider="rainbow")
    name_input = st.text_input("Enter your name:").strip()
    if name_input:
        res = github_request("GET", "")
        existing_folders = [f["name"] for f in res.json() if f["type"] == "dir" and f["name"].startswith(name_input)] if res.status_code == 200 else []
        if existing_folders:
            latest = sorted(existing_folders)[-1]
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Continue ({latest})"):
                    st.session_state.update({"user_name": name_input, "folder": latest, "session_started": True})
                    res_f = github_request("GET", latest)
                    if res_f.status_code == 200:
                        st.session_state.img_idx = len([f for f in res_f.json() if "_labels.json" in f["name"]])
                    st.rerun()
            with col2:
                if st.button("Start New Session"):
                    st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v{len(existing_folders)+1}", "session_started": True})
                    st.rerun()
        elif st.button("Start New Project"):
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

# 1. Get dimensions
orig_w, orig_h = pil_img.size

# 2. Force a web-friendly size (800px wide)
MAX_WIDTH = 800
scale = MAX_WIDTH / orig_w if orig_w > MAX_WIDTH else 1
disp_w, disp_h = int(orig_w * scale), int(orig_h * scale)

# 3. Create the Base64 string once
buffered = BytesIO()
# We resize the actual image OBJECT before converting to Base64
pil_img.resize((disp_w, disp_h)).save(buffered, format="PNG")
img_str = base64.b64encode(buffered.getvalue()).decode()
canvas_bg_url = f"data:image/png;base64,{img_str}"

# --- STEP 3: RESUME LOGIC ---
label_path = f"{st.session_state.folder}/{current_img}_labels.json"
existing_data = get_existing_annotation(label_path)
initial_drawing = None

if existing_data and not st.session_state.load_prev:
    st.info(f"Existing data found for {current_img}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load Previous"): st.session_state.load_prev = True; st.rerun()
    with c2:
        if st.button("New Version"): 
            st.session_state.folder = f"{st.session_state.folder.split('_v')[0]}_v{int(re.search(r'_v(\d+)$', st.session_state.folder).group(1))+1 if re.search(r'_v(\d+)$', st.session_state.folder) else 2}"
            st.session_state.load_prev = "fresh"; st.rerun()
    st.stop()

if st.session_state.load_prev == True and existing_data:
    initial_drawing = {"objects": [
        {"type": "circle", "left": (r["value"]["x"] * orig_w / 100) * scale, "top": (r["value"]["y"] * orig_h / 100) * scale, "radius": 4, "fill": "red"} 
        for r in existing_data["annotations"][0]["result"]
    ]}

# --- STEP 4: UI & CANVAS ---
st.write(f"**Current Image:** {current_img} ({st.session_state.img_idx+1}/{len(images)})")
st.subheader(f"Annotating: {current_img}")

if st.session_state.paused:
    st.warning("Paused.")
    if st.button("Resume"):
        st.session_state.start_time = time.time()
        st.session_state.paused = False
        st.rerun()
else:
    # Use a unique key that changes ONLY when the image index changes
    c_key = f"canvas_v3_{st.session_state.img_idx}"
    
    # We use a standard st.columns to constrain the width
    col_c, _ = st.columns([10, 1]) 
    with col_c:
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=2,
            stroke_color="#FF0000",
            background_image=None,      # <--- SET THIS TO NONE
            background_color=canvas_bg_url, # <--- TRICK: Pass the DataURL to background_color
            height=disp_h,
            width=disp_w,
            drawing_mode="point",
            point_display_radius=5,
            initial_drawing=initial_drawing,
            key=c_key,
            update_streamlit=True,
            display_toolbar=True,
        )

    if st.sidebar.button("☕ Take a Break"):
        st.session_state.elapsed += (time.time() - st.session_state.start_time)
        st.session_state.paused = True
        st.rerun()

    # --- STEP 5: SAVE ---
    points = canvas_result.json_data["objects"] if canvas_result.json_data else []
    if st.button("💾 Save & Next Image", disabled=(len(points) == 0), type="primary"):
        with st.spinner("Saving to GitHub..."):
            buf = BytesIO()
            pil_img.save(buf, format="JPEG")
            img_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"

            ls_json = {
                "data": {"image": img_b64, "filename": current_img},
                "annotations": [{"result": [{
                    "original_width": orig_w, "original_height": orig_h,
                    "value": {
                        "x": (p["left"] / scale) / orig_w * 100, 
                        "y": (p["top"] / scale) / orig_h * 100, 
                        "keypointlabels": ["mussel"]
                    },
                    "from_name": "label", "to_name": "image", "type": "keypointlabels"
                } for p in points]}]
            }
            active_time = st.session_state.elapsed + (time.time() - st.session_state.start_time)
            meta_json = {"image": current_img, "duration_sec": round(active_time, 2), "count": len(points), "timestamp": datetime.now().isoformat()}
            
            if upload_to_github(label_path, ls_json, "Labels") and upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta_json, "Meta"):
                st.session_state.update({"img_idx": st.session_state.img_idx + 1, "elapsed": 0, "start_time": time.time(), "load_prev": False})
                st.rerun()
