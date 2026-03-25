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

# --- CUSTOM CSS FOR CLEAN UI ---
st.markdown("""
    <style>
    /* Hide the class selector dropdown and the mode radio buttons */
    div[data-testid="stSelectbox"], 
    div[data-testid="stRadio"] {
        display: none !important;
    }
    
    /* Make the container wider */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 95%;
    }

    /* Style the Save button to be large and prominent */
    .stButton button {
        width: 100%;
        height: 3em;
        font-size: 20px !important;
        font-weight: bold !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- GITHUB API HELPERS (Keep your existing functions here) ---
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

# --- LOGIN (Abbreviated for brevity) ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotator", divider="rainbow")
    name_input = st.text_input("Enter your name:").strip()
    if name_input:
        # (Insert your existing folder logic here)
        st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v1", "session_started": True})
        st.rerun()
    st.stop()

# --- IMAGE PREP ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
if st.session_state.img_idx >= len(images):
    st.success("🎉 All images complete!"); st.stop()

current_img = images[st.session_state.img_idx]
img_path = os.path.join(IMAGE_DIR, current_img)
pil_img = Image.open(img_path)
orig_w, orig_h = pil_img.size

# --- MAIN UI LAYOUT ---
col_main, col_side = st.columns([8, 2])

with col_main:
    st.subheader(f"🖼️ {current_img} ({st.session_state.img_idx+1}/{len(images)})")
    
    # Load existing
    label_path = f"{st.session_state.folder}/{current_img}_labels.json"
    existing_data = get_existing_annotation(label_path)
    pts_list, ids_list = [], []
    if existing_data:
        for r in existing_data["annotations"][0]["result"]:
            pts_list.append([r['value']['x'], r['value']['y']])
            ids_list.append(0)

    # THE ANNOTATOR
    # 'use_space=True' allows user to toggle points with the spacebar
    new_labels = pointdet(
        image_path=img_path,
        label_list=['mussel'], # Only one class
        points=pts_list,
        labels=ids_list,
        use_space=True, 
        key=f"det_v6_{st.session_state.img_idx}"
    )

with col_side:
    st.info("💡 **Instructions**\n- Click to add points\n- Drag points to move\n- 'Del' key to remove a point")
    st.write(f"**Points Found:** {len(new_labels) if new_labels else 0}")
    
    if new_labels is not None:
        if st.button("💾 SAVE & NEXT", type="primary"):
            with st.spinner("Syncing..."):
                res_list = [{
                    "original_width": orig_w, "original_height": orig_h,
                    "value": {"x": item['point'][0], "y": item['point'][1], "keypointlabels": ["mussel"]},
                    "from_name": "label", "to_name": "image", "type": "keypointlabels"
                } for item in new_labels]

                ls_json = {"data": {"image": "b64_placeholder", "filename": current_img}, "annotations": [{"result": res_list}]}
                meta_json = {"image": current_img, "count": len(new_labels), "timestamp": datetime.now().isoformat()}
                
                if upload_to_github(label_path, ls_json, "Labels") and upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta_json, "Meta"):
                    st.session_state.img_idx += 1
                    st.session_state.start_time = time.time()
                    st.rerun()
