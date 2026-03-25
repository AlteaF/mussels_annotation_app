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
    """Handles REST API calls to the private GitHub Data Repo."""
    url = f"https://api.github.com/repos/{REPO_OWNER_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    if method == "GET":
        return requests.get(url, headers=headers)
    return requests.put(url, headers=headers, json=json_data)

def upload_to_github(path, content_dict, message):
    """Pushes JSON to GitHub. Handles updates by fetching SHA first."""
    res = github_request("GET", path)
    sha = res.json().get("sha") if res.status_code == 200 else None
    
    content_json = json.dumps(content_dict, indent=2)
    content_base64 = base64.b64encode(content_json.encode()).decode()
    
    data = {"message": message, "content": content_base64}
    if sha:
        data["sha"] = sha
        
    res = github_request("PUT", path, data)
    return res.status_code in [200, 201]

def get_existing_annotation(path):
    """Downloads and decodes an existing JSON file from GitHub."""
    res = github_request("GET", path)
    if res.status_code == 200:
        content = base64.b64decode(res.json()["content"]).decode()
        return json.loads(content)
    return None

# --- SESSION STATE INITIALIZATION ---
if "user_name" not in st.session_state:
    st.session_state.update({
        "user_name": None, "img_idx": 0, "paused": False, 
        "elapsed": 0, "start_time": time.time(), "load_prev": False,
        "folder": None, "session_started": False
    })

# --- STEP 1: LOGIN & FOLDER MANAGEMENT ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotation Project", divider="rainbow")
    name_input = st.text_input("Enter your name to begin:").strip()

    if name_input:
        # Check GitHub for existing folders starting with this name
        res = github_request("GET", "") 
        existing_folders = []
        if res.status_code == 200:
            existing_folders = [f["name"] for f in res.json() if f["type"] == "dir" and f["name"].startswith(name_input)]
        
        if existing_folders:
            st.warning(f"Welcome back, {name_input}!")
            latest_folder = sorted(existing_folders)[-1]
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Continue Session ({latest_folder})"):
                    st.session_state.user_name = name_input
                    st.session_state.folder = latest_folder
                    st.session_state.session_started = True
                    # Find progress: count existing labels
                    res_folder = github_request("GET", latest_folder)
                    if res_folder.status_code == 200:
                        labeled_files = [f["name"] for f in res_folder.json() if "_labels.json" in f["name"]]
                        st.session_state.img_idx = len(labeled_files)
                    st.rerun()
            
            with col2:
                if st.button("Start Brand New Session"):
                    st.session_state.user_name = name_input
                    version = len(existing_folders) + 1
                    st.session_state.folder = f"{name_input}_v{version}"
                    st.session_state.session_started = True
                    st.rerun()
        else:
            if st.button("Start New Project"):
                st.session_state.user_name = name_input
                st.session_state.folder = f"{name_input}_v1"
                st.session_state.session_started = True
                st.rerun()
    st.stop()

# --- STEP 2: PREP IMAGES & UI ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

if st.session_state.img_idx >= len(images):
    st.balloons()
    st.success(f"Excellent work, {st.session_state.user_name}! All images are complete.")
    st.stop()

current_img = images[st.session_state.img_idx]
img_path = os.path.join(IMAGE_DIR, current_img)
pil_img = Image.open(img_path)

# UI Elements
st.progress(st.session_state.img_idx / len(images))
st.write(f"**User:** {st.session_state.user_name} | **Folder:** `{st.session_state.folder}` | **Image:** {st.session_state.img_idx + 1} / {len(images)}")

# --- STEP 3: INDIVIDUAL IMAGE RESUME LOGIC ---
label_path = f"{st.session_state.folder}/{current_img}_labels.json"
existing_data = get_existing_annotation(label_path)

initial_drawing = None
if existing_data and not st.session_state.load_prev:
    st.info(f"Annotations already exist for **{current_img}**.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load Previous Progress"):
            st.session_state.load_prev = True
            st.rerun()
    with c2:
        if st.button("Discard & Start New Version"):
            # If they discard, we branch the folder name immediately
            base = st.session_state.folder.split('_v')[0]
            match = re.search(r'_v(\d+)$', st.session_state.folder)
            new_v = int(match.group(1)) + 1 if match else 2
            st.session_state.folder = f"{base}_v{new_v}"
            st.session_state.load_prev = "fresh"
            st.rerun()
    st.stop()

# Convert normalized LS points back to Canvas pixels
if st.session_state.load_prev == True and existing_data:
    initial_drawing = {"objects": [
        {"type": "circle", "left": (r["value"]["x"] * pil_img.width / 100), 
         "top": (r["value"]["y"] * pil_img.height / 100), "radius": 4, "fill": "red"} 
        for r in existing_data["annotations"][0]["result"]
    ]}

# --- STEP 4: CANVAS & TIMER ---
with st.sidebar:
    st.header("Controls")
    if st.button("☕ Take a Break" if not st.session_state.paused else "▶️ Resume"):
        if not st.session_state.paused:
            st.session_state.elapsed += (time.time() - st.session_state.start_time)
        else:
            st.session_state.start_time = time.time()
        st.session_state.paused = not st.session_state.paused
        st.rerun()
    
    st.write("---")
    st.write(f"Current Image: {current_img}")
    st.write("Instruction: Click every **mussel** you see.")

if st.session_state.paused:
    st.warning("Application Paused. Your timer is stopped.")
else:
    canvas_result = st_canvas(
        background_image=pil_img,
        initial_drawing=initial_drawing,
        drawing_mode="point",
        key="canvas",
        height=pil_img.height,
        width=pil_img.width,
        stroke_width=2,
        stroke_color="#FF0000",
        display_toolbar=True,
        update_streamlit=True,
    )

    # --- STEP 5: SAVE & ADVANCE ---
    points = canvas_result.json_data["objects"] if canvas_result.json_data else []
    
    if st.button("Save & Next Image", disabled=(len(points) == 0), type="primary"):
        with st.spinner("Uploading to GitHub..."):
            # Encode image to Base64
            buf = BytesIO()
            pil_img.save(buf, format="JPEG")
            img_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"

            # Label Studio JSON
            ls_json = {
                "data": {"image": img_b64, "filename": current_img},
                "annotations": [{"result": [{
                    "original_width": pil_img.width, "original_height": pil_img.height,
                    "value": {"x": p["left"]/pil_img.width*100, "y": p["top"]/pil_img.height*100, "keypointlabels": ["mussel"]},
                    "from_name": "label", "to_name": "image", "type": "keypointlabels"
                } for p in points]}]
            }

            # Meta JSON
            active_time = st.session_state.elapsed + (time.time() - st.session_state.start_time)
            meta_json = {
                "image": current_img, 
                "duration_sec": round(active_time, 2), 
                "count": len(points),
                "timestamp": datetime.now().isoformat()
            }

            # Final Uploads
            success_ls = upload_to_github(label_path, ls_json, f"Update labels {current_img}")
            success_meta = upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta_json, f"Update meta {current_img}")

            if success_ls and success_meta:
                st.session_state.update({
                    "img_idx": st.session_state.img_idx + 1, 
                    "elapsed": 0, 
                    "start_time": time.time(), 
                    "load_prev": False
                })
                st.rerun()
            else:
                st.error("GitHub Error: Please check your Token permissions.")