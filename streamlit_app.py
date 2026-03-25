import streamlit as st
from streamlit_image_annotation import pointdet
from PIL import Image
import os
import json
import time
import requests
import base64
from datetime import datetime
from io import BytesIO

# --- CONFIGURATION ---
IMAGE_DIR = "images" 
REPO_OWNER_REPO = st.secrets["DATA_REPO"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="Mussel Annotator", layout="wide")

# --- ADVANCED CSS INJECTION ---
st.markdown("""
    <style>
    /* 1. Fix the Top Padding so the header isn't cut off */
    .block-container {
        padding-top: 3rem !important;
        max-width: 98% !important;
    }

    /* 2. Hide the Class/Label Dropdown (since you only have one class) */
    div[data-testid="stSelectbox"] {
        display: none !important;
    }

    /* 3. Re-style the Radio Buttons (Modes) and try to move them visually */
    /* Note: Streamlit doesn't allow easy re-ordering of internal component HTML, 
       so we make the "Save" button big and clear at the bottom instead. */
    
    .stButton button {
        background-color: #ff4b4b !important;
        color: white !important;
        font-weight: bold !important;
        height: 4rem !important;
        border-radius: 10px !important;
    }
    
    /* 4. Increase the font of the image counter */
    .img-header {
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

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
        "user_name": None, "img_idx": 0, "folder": None, 
        "session_started": False, "start_time": time.time()
    })

# --- STEP 1: LOGIN (Restored original logic) ---
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
    st.success("🎉 All images complete!"); st.stop()

current_img = images[st.session_state.img_idx]
img_path = os.path.join(IMAGE_DIR, current_img)
pil_img = Image.open(img_path)
orig_w, orig_h = pil_img.size

# --- STEP 3: ANNOTATION INTERFACE ---
st.markdown(f'<p class="img-header">🖼️ Image: {current_img} ({st.session_state.img_idx+1}/{len(images)})</p>', unsafe_allow_html=True)

label_path = f"{st.session_state.folder}/{current_img}_labels.json"
existing_data = get_existing_annotation(label_path)
pts_list, ids_list = [], []

if existing_data:
    for r in existing_data["annotations"][0]["result"]:
        pts_list.append([r['value']['x'], r['value']['y']])
        ids_list.append(0)

# Render the component
# We keep the "Transform/Delete" mode visible because it's required to delete points,
# but we move it to the sidebar if you want the image to be absolutely huge.
new_labels = pointdet(
    image_path=img_path,
    label_list=['mussel'],
    points=pts_list,
    labels=ids_list,
    use_space=True, 
    key=f"det_vfinal_{st.session_state.img_idx}"
)

# --- STEP 4: SAVE ---
if new_labels is not None:
    st.write(f"**Current Count:** {len(new_labels)} mussels")
    if st.button("💾 SAVE & NEXT IMAGE", type="primary", use_container_width=True):
        with st.spinner("Uploading to GitHub..."):
            buf = BytesIO()
            pil_img.save(buf, format="JPEG")
            img_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"

            res_list = [{
                "original_width": orig_w, "original_height": orig_h,
                "value": {"x": item['point'][0], "y": item['point'][1], "keypointlabels": ["mussel"]},
                "from_name": "label", "to_name": "image", "type": "keypointlabels"
            } for item in new_labels]

            ls_json = {"data": {"image": img_b64, "filename": current_img}, "annotations": [{"result": res_list}]}
            duration = round(time.time() - st.session_state.start_time, 2)
            meta_json = {"image": current_img, "duration_sec": duration, "count": len(new_labels), "timestamp": datetime.now().isoformat()}
            
            if upload_to_github(label_path, ls_json, "Labels") and upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta_json, "Meta"):
                st.session_state.update({"img_idx": st.session_state.img_idx + 1, "start_time": time.time()})
                st.rerun()
