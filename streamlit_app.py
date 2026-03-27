import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw
import os, json, time, requests, base64
from datetime import datetime

# --- CONFIG ---
IMAGE_DIR = "images"
REPO_OWNER_REPO = st.secrets["DATA_REPO"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="Mussel Annotator Pro", layout="wide")

# --- CSS: REMOVE SCROLLING & HIDE "RUNNING" ---
st.markdown("""
    <style>
    .block-container { padding-top: 1rem !important; max-width: 95% !important; }
    /* Hide the 'Running/Connecting' element to stop the visual flicker */
    [data-testid="stStatusWidget"] { display: none !important; }
    /* Force image container to center */
    .stImage { display: flex; justify-content: center; }
    </style>
    """, unsafe_allow_html=True)

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
    data = {"message": message, "content": content_base64, "sha": sha} if sha else {"message": message, "content": content_base64}
    return github_request("PUT", path, data).status_code in [200, 201]

def get_existing_annotation(path):
    res = github_request("GET", path)
    if res.status_code == 200:
        return json.loads(base64.b64decode(res.json()["content"]).decode())
    return None

# --- SESSION STATE ---
if "points" not in st.session_state:
    st.session_state.update({"user_name": None, "img_idx": 0, "folder": None, "session_started": False, "points": [], "mode": "Add", "last_click": None})

# --- LOGIN (Simplified for brevity) ---
if not st.session_state.session_started:
    name_input = st.text_input("Enter Name:").strip()
    if name_input and st.button("Start"):
        st.session_state.update({"user_name": name_input, "folder": f"{name_input}_session", "session_started": True})
        st.rerun()
    st.stop()

# --- IMAGE LOADING ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.png', '.jpeg'))])
if st.session_state.img_idx >= len(images):
    st.success("Done!"); st.stop()

current_img = images[st.session_state.img_idx]

@st.cache_data
def get_pil_image(path):
    return Image.open(path).convert("RGB")

pil_img = get_pil_image(os.path.join(IMAGE_DIR, current_img))
orig_w, orig_h = pil_img.size

# --- THE FRAGMENT (THIS STOPS THE FULL PAGE FLASH) ---
@st.fragment
def annotation_area():
    # Use columns for a cleaner UI
    col1, col2 = st.columns([2, 1])
    with col1:
        mode = st.radio("Tool:", ["Add", "Delete"], horizontal=True)
    with col2:
        st.write(f"**Count:** {len(st.session_state.points)}")
        if st.button("🗑️ Reset"):
            st.session_state.points = []
            st.rerun()

    # Draw existing points
    draw_img = pil_img.copy()
    draw = ImageDraw.Draw(draw_img)
    point_rad = max(orig_w, orig_h) * 0.006
    for p in st.session_state.points:
        px, py = (p[0]/100)*orig_w, (p[1]/100)*orig_h
        draw.ellipse([px-point_rad, py-point_rad, px+point_rad, py+point_rad], fill="red", outline="white", width=3)

    # Image Display (width=1200 fixes the sideways scrolling)
    value = streamlit_image_coordinates(draw_img, width=1200, key=f"canvas_{st.session_state.img_idx}")

    if value:
        curr_x = (value["x"] / value["width"]) * 100
        curr_y = (value["y"] / value["height"]) * 100
        click_hash = f"{curr_x:.2f}{curr_y:.2f}"

        # Prevents double-triggering on same click
        if st.session_state.last_click != click_hash:
            st.session_state.last_click = click_hash
            if mode == "Add":
                st.session_state.points.append([curr_x, curr_y])
            else:
                st.session_state.points = [p for p in st.session_state.points if not (abs(p[0]-curr_x)<1.5 and abs(p[1]-curr_y)<1.5)]
            st.rerun() # This ONLY reruns the fragment! No flash for the rest of the page.

# Run the Fragment
st.subheader(f"Annotating: {current_img}")
annotation_area()

# --- SAVE BUTTON (Outside Fragment to move to next image) ---
if st.button("💾 SAVE & NEXT IMAGE", type="primary", use_container_width=True):
    # Prepare data for GitHub
    res_list = [{"value": {"x": p[0], "y": p[1]}, "type": "keypointlabels"} for p in st.session_state.points]
    save_data = {"image": current_img, "annotations": [{"result": res_list}]}
    
    label_path = f"{st.session_state.folder}/{current_img}_labels.json"
    if upload_to_github(label_path, save_data, "Add labels"):
        st.session_state.img_idx += 1
        st.session_state.points = []
        st.rerun()
