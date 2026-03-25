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

# --- CSS: ENSURE IMAGE STAYS IN BROWSER BOUNDS ---
st.markdown("""
    <style>
    .block-container { padding-top: 1rem !important; max-width: 95% !important; }
    /* This forces the image container to never exceed the screen width */
    .img-container {
        width: 100%;
        max-width: 100vw;
        overflow: hidden;
    }
    /* Hide the 'Running...' header to reduce flashing visual noise */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- CACHED IMAGE LOADER (CRITICAL FOR SPEED) ---
@st.cache_data
def load_and_resize_image(path):
    img = Image.open(path).convert("RGB")
    orig_size = img.size
    # Resize for display only (makes the app 10x faster)
    # We keep the aspect ratio but limit width to 1200px
    display_img = img.copy()
    display_img.thumbnail((1200, 1200)) 
    return display_img, orig_size

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

def get_existing_annotation(path):
    res = github_request("GET", path)
    if res.status_code == 200:
        return json.loads(base64.b64decode(res.json()["content"]).decode())
    return None

# --- INITIALIZE SESSION STATE ---
for key in ["user_name", "img_idx", "folder", "session_started", "points", "mode", "current_loaded_img"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "img_idx" else 0
if "points" not in st.session_state or st.session_state.points is None: st.session_state.points = []
if "mode" not in st.session_state or st.session_state.mode is None: st.session_state.mode = "Add Points"

# --- LOGIN ---
if not st.session_state.session_started:
    st.header("🦪 Mussel Annotator")
    name_input = st.text_input("Enter name:").strip()
    if name_input and st.button("Log In"):
        res = github_request("GET", "")
        existing = [f["name"] for f in res.json() if f["name"].startswith(name_input)] if res.status_code == 200 else []
        folder = f"{name_input}_v{len(existing)+1}"
        st.session_state.update({"user_name": name_input, "folder": folder, "session_started": True})
        st.rerun()
    st.stop()

# --- IMAGE PREP ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
if st.session_state.img_idx >= len(images):
    st.success("All Done!"); st.stop()

current_img = images[st.session_state.img_idx]
display_img, (orig_w, orig_h) = load_and_resize_image(os.path.join(IMAGE_DIR, current_img))

# --- LOAD POINTS ---
label_path = f"{st.session_state.folder}/{current_img}_labels.json"
if st.session_state.current_loaded_img != current_img:
    existing_data = get_existing_annotation(label_path)
    st.session_state.points = [[r['value']['x'], r['value']['y']] for r in existing_data["annotations"][0]["result"]] if existing_data else []
    st.session_state.current_loaded_img = current_img

# --- DRAW POINTS ---
draw_img = display_img.copy()
draw = ImageDraw.Draw(draw_img)
disp_w, disp_h = display_img.size
for p in st.session_state.points:
    # Scale percentage to the DISPLAY image size
    px, py = (p[0] / 100) * disp_w, (p[1] / 100) * disp_h
    r = 5 # Fixed size for speed
    draw.ellipse([px-r, py-r, px+r, py+r], fill="red", outline="white")

# --- UI ---
st.subheader(f"🖼️ {current_img} ({st.session_state.img_idx+1}/{len(images)})")
c1, c2, c3 = st.columns([2, 2, 4])
st.session_state.mode = c1.radio("Mode", ["Add Points", "Delete Points"], horizontal=True, label_visibility="collapsed")
if c2.button("🗑️ Reset"):
    st.session_state.points = []
    st.rerun()

# --- THE IMAGE (Inside a container for width control) ---
st.markdown('<div class="img-container">', unsafe_allow_html=True)
value = streamlit_image_coordinates(draw_img, key=f"c_{st.session_state.img_idx}_{len(st.session_state.points)}")
st.markdown('</div>', unsafe_allow_html=True)

if value:
    # Convert display pixels to percentage
    click_x = (value["x"] / disp_w) * 100
    click_y = (value["y"] / disp_h) * 100
    
    if st.session_state.mode == "Add Points":
        if not any(abs(p[0]-click_x) < 0.8 and abs(p[1]-click_y) < 0.8 for p in st.session_state.points):
            st.session_state.points.append([click_x, click_y])
            st.rerun()
    else:
        st.session_state.points = [p for p in st.session_state.points if not (abs(p[0]-click_x) < 2.0 and abs(p[1]-click_y) < 2.0)]
        st.rerun()

# --- SAVE ---
if st.button("💾 SAVE & NEXT", type="primary", use_container_width=True):
    res_list = [{"original_width": orig_w, "original_height": orig_h, "value": {"x": p[0], "y": p[1], "keypointlabels": ["mussel"]}, "from_name": "label", "to_name": "image", "type": "keypointlabels"} for p in st.session_state.points]
    if upload_to_github(label_path, {"annotations": [{"result": res_list}]}, "Labels"):
        st.session_state.img_idx += 1
        st.rerun()
