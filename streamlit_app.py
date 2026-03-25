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

# --- CSS: FIX WIDTH AND HEADERS ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem !important; max-width: 95% !important; }
    /* Force image to fit browser width */
    .stImage img { max-width: 100% !important; height: auto !important; }
    /* Reduce visual noise during 'Running' */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
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

# --- SESSION STATE INITIALIZATION ---
if "user_name" not in st.session_state:
    st.session_state.update({
        "user_name": None, "img_idx": 0, "folder": None, 
        "session_started": False, "points": [], "mode": "Add Points", 
        "start_time": time.time(), "current_loaded_img": None
    })

# --- STEP 1: RESTORED ORIGINAL LOGIN LOGIC ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotation Project")
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

# Use Cache for Image Loading to stop re-reading from disk
@st.cache_data
def get_pil_image(path):
    return Image.open(path).convert("RGB")

pil_img = get_pil_image(img_path)
width, height = pil_img.size

# --- STEP 3: DATA LOADING ---
label_path = f"{st.session_state.folder}/{current_img}_labels.json"
if st.session_state.current_loaded_img != current_img:
    existing_data = get_existing_annotation(label_path)
    if existing_data:
        st.session_state.points = [[r['value']['x'], r['value']['y']] for r in existing_data["annotations"][0]["result"]]
    else:
        st.session_state.points = []
    st.session_state.current_loaded_img = current_img

# --- STEP 4: DRAWING ---
draw_img = pil_img.copy()
draw = ImageDraw.Draw(draw_img)
# Draw points
for p in st.session_state.points:
    px, py = (p[0] / 100) * width, (p[1] / 100) * height
    r = max(width, height) * 0.005
    draw.ellipse([px-r, py-r, px+r, py+r], fill="red", outline="white", width=2)

# --- STEP 5: UI LAYOUT ---
st.subheader(f"🖼️ {current_img} ({st.session_state.img_idx+1}/{len(images)})")

c_m1, c_m2, c_m3 = st.columns([3, 2, 5])
st.session_state.mode = c_m1.radio("Mode", ["Add Points", "Delete Points"], horizontal=True, label_visibility="collapsed")
if c_m2.button("🗑️ Reset Image"):
    st.session_state.points = []
    st.rerun()

# IMPORTANT: Key is fixed per image index to prevent the "random reload" flash
value = streamlit_image_coordinates(
    draw_img, 
    key=f"fixed_annotator_{st.session_state.img_idx}"
)

if value:
    # Logic to prevent reload loop: only act if click is new
    click_x = (value["x"] / value["width"]) * 100
    click_y = (value["y"] / value["height"]) * 100
    
    if st.session_state.mode == "Add Points":
        # Only add if not already there (prevents double-triggering)
        if not any(abs(p[0]-click_x) < 0.6 and abs(p[1]-click_y) < 0.6 for p in st.session_state.points):
            st.session_state.points.append([click_x, click_y])
            st.rerun()
    else:
        # Delete mode
        new_pts = [p for p in st.session_state.points if not (abs(p[0]-click_x) < 2.0 and abs(p[1]-click_y) < 2.0)]
        if len(new_pts) != len(st.session_state.points):
            st.session_state.points = new_pts
            st.rerun()

st.write(f"**Mussels found:** {len(st.session_state.points)}")

# --- STEP 6: SAVE ---
if st.button("💾 SAVE & NEXT", type="primary", use_container_width=True):
    with st.spinner("Saving..."):
        res_list = [{
            "original_width": width, "original_height": height,
            "value": {"x": p[0], "y": p[1], "keypointlabels": ["mussel"]},
            "from_name": "label", "to_name": "image", "type": "keypointlabels"
        } for p in st.session_state.points]
        
        ls_json = {"data": {"image": "...", "filename": current_img}, "annotations": [{"result": res_list}]}
        duration = round(time.time() - st.session_state.start_time, 2)
        meta_json = {"image": current_img, "count": len(st.session_state.points), "timestamp": datetime.now().isoformat()}
        
        if upload_to_github(label_path, ls_json, "Labels") and upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta_json, "Meta"):
            st.session_state.img_idx += 1
            # Explicitly clear points and current image to force next load
            st.session_state.points = []
            st.session_state.current_loaded_img = None 
            st.session_state.start_time = time.time()
            st.rerun()
