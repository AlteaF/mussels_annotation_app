import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw
import os, json, time, requests, base64
from datetime import datetime
from io import BytesIO

# --- CONFIG ---
IMAGE_DIR = "images"
REPO_OWNER_REPO = st.secrets["DATA_REPO"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="Mussel Annotator Pro", layout="wide")

# --- CSS TO FIX PADDING ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem !important; max-width: 98% !important; }
    .stRadio > div { flex-direction: row; gap: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- GITHUB HELPERS ---
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
        "session_started": False, "points": [], "mode": "Add", "start_time": time.time()
    })

# --- LOGIN ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotation Project")
    name_input = st.text_input("Enter your name:").strip()
    if name_input:
        res = github_request("GET", "")
        existing = [f["name"] for f in res.json() if f["name"].startswith(name_input)] if res.status_code == 200 else []
        if existing:
            latest = sorted(existing)[-1]
            c1, c2 = st.columns(2)
            if c1.button(f"Continue ({latest})"):
                st.session_state.update({"user_name": name_input, "folder": latest, "session_started": True})
                res_f = github_request("GET", latest)
                if res_f.status_code == 200:
                    st.session_state.img_idx = len([f for f in res_f.json() if "_labels.json" in f["name"]])
                st.rerun()
            if c2.button("Start New Session"):
                st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v{len(existing)+1}", "session_started": True})
                st.rerun()
        elif st.button("Start Project"):
            st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v1", "session_started": True})
            st.rerun()
    st.stop()

# --- IMAGE PREP ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
if st.session_state.img_idx >= len(images):
    st.success("All Done!"); st.stop()

current_img = images[st.session_state.img_idx]
img_path = os.path.join(IMAGE_DIR, current_img)
pil_img = Image.open(img_path).convert("RGB")
width, height = pil_img.size

# --- LOAD PREVIOUS POINTS ---
label_path = f"{st.session_state.folder}/{current_img}_labels.json"
if not st.session_state.points:
    existing_data = get_existing_annotation(label_path)
    if existing_data:
        st.session_state.points = [[r['value']['x'], r['value']['y']] for r in existing_data["annotations"][0]["result"]]

# --- DRAWING OVERLAY ---
# Create a copy of the image and draw the points on it
draw_img = pil_img.copy()
draw = ImageDraw.Draw(draw_img)
for p in st.session_state.points:
    # Convert percentage back to pixel coordinates for drawing
    px = (p[0] / 100) * width
    py = (p[1] / 100) * height
    r = max(width, height) * 0.005 # Dynamic radius based on image size
    draw.ellipse([px-r, py-r, px+r, py+r], fill="red", outline="white", width=2)

# --- UI LAYOUT ---
st.subheader(f"🖼️ {current_img} ({st.session_state.img_idx+1}/{len(images)})")

# Mode & Controls at the top
c_m1, c_m2, c_m3 = st.columns([3, 2, 5])
st.session_state.mode = c_m1.radio("Selection Mode", ["Add Points", "Delete Points"], horizontal=True)
if c_m2.button("🗑️ Reset Image"):
    st.session_state.points = []
    st.rerun()

# THE IMAGE
# This will now be as wide as the container
value = streamlit_image_coordinates(draw_img, key=f"coord_{st.session_state.img_idx}", use_container_width=True)

if value:
    # Convert clicked pixel to percentage
    click_x = (value["x"] / value["width"]) * 100
    click_y = (value["y"] / value["height"]) * 100
    
    if st.session_state.mode == "Add Points":
        # Basic debounce: don't add if clicking same spot
        if not any(abs(p[0]-click_x) < 0.5 and abs(p[1]-click_y) < 0.5 for p in st.session_state.points):
            st.session_state.points.append([click_x, click_y])
            st.rerun()
    else:
        # Delete: remove points within 1.5% distance
        st.session_state.points = [p for p in st.session_state.points if not (abs(p[0]-click_x) < 1.5 and abs(p[1]-click_y) < 1.5)]
        st.rerun()

st.write(f"**Mussels found:** {len(st.session_state.points)}")

# --- SAVE ---
if st.button("💾 SAVE & NEXT", type="primary", use_container_width=True):
    with st.spinner("Saving..."):
        res_list = [{
            "original_width": width, "original_height": height,
            "value": {"x": p[0], "y": p[1], "keypointlabels": ["mussel"]},
            "from_name": "label", "to_name": "image", "type": "keypointlabels"
        } for p in st.session_state.points]
        
        ls_json = {"data": {"image": "...", "filename": current_img}, "annotations": [{"result": res_list}]}
        duration = round(time.time() - st.session_state.start_time, 2)
        meta_json = {"image": current_img, "duration_sec": duration, "count": len(st.session_state.points), "timestamp": datetime.now().isoformat()}
        
        if upload_to_github(label_path, ls_json, "Labels") and upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta_json, "Meta"):
            st.session_state.img_idx += 1
            st.session_state.points = [] 
            st.session_state.start_time = time.time()
            st.rerun()
