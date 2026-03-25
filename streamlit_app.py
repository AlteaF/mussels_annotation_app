import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import os
import json
import time
import requests
import base64
from datetime import datetime

# --- CONFIGURATION ---
IMAGE_DIR = "images"  # Folder in your code repo
REPO_OWNER_REPO = st.secrets["DATA_REPO"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="Image Annotator", layout="wide")

# --- HELPER FUNCTIONS ---

def get_images():
    """Reads images from the local folder alphabetically."""
    valid_exts = (".jpg", ".jpeg", ".png")
    imgs = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(valid_exts)])
    return imgs

def upload_to_github(path, content_dict, commit_message):
    """Pushes a dictionary as a JSON file to the private data repo."""
    url = f"https://api.github.com/repos/{REPO_OWNER_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Convert dict to JSON string then to Base64
    content_json = json.dumps(content_dict, indent=2)
    content_base64 = base64.b64encode(content_json.encode()).decode()
    
    data = {
        "message": commit_message,
        "content": content_base64
    }
    
    response = requests.put(url, headers=headers, json=data)
    return response.status_code in [201, 200]

def check_user_folder_version(base_name):
    """Checks if a user folder exists via API and increments version if needed."""
    # Simplified: for this MVP, we'll append a timestamp to the session to keep it unique
    if "user_folder" not in st.session_state:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        st.session_state.user_folder = f"{base_name}_{timestamp}"

# --- SESSION STATE INITIALIZATION ---
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "img_idx" not in st.session_state:
    st.session_state.img_idx = 0
if "paused" not in st.session_state:
    st.session_state.paused = False
if "elapsed_before_pause" not in st.session_state:
    st.session_state.elapsed_before_pause = 0
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

# --- STEP 1: LOGIN ---
if not st.session_state.user_name:
    st.header("Welcome to the Annotation Task", divider="rainbow")
    name_input = st.text_input("Please enter your name to begin:")
    if st.button("Start Session") and name_input:
        st.session_state.user_name = name_input.strip()
        check_user_folder_version(st.session_state.user_name)
        st.session_state.start_time = time.time()
        st.rerun()
    st.stop()

# --- STEP 2: ANNOTATION INTERFACE ---
images = get_images()

if st.session_state.img_idx >= len(images):
    st.balloons()
    st.success(f"Thank you, {st.session_state.user_name}! You have completed all images.")
    st.stop()

current_img_name = images[st.session_state.img_idx]
img_path = os.path.join(IMAGE_DIR, current_img_name)
pil_img = Image.open(img_path)

st.title(f"Annotating: {current_img_name}")
st.write(f"Hello **{st.session_state.user_name}**, thank you for helping!")

# --- TIMER LOGIC ---
if st.button("Take a Break" if not st.session_state.paused else "Resume Work"):
    if not st.session_state.paused:
        # Switching to Paused
        st.session_state.elapsed_before_pause += (time.time() - st.session_state.start_time)
        st.session_state.paused = True
    else:
        # Switching to Active
        st.session_state.start_time = time.time()
        st.session_state.paused = False
    st.rerun()

if st.session_state.paused:
    st.warning("Task is paused. Click 'Resume' to continue.")
else:
    # --- CANVAS ---
    st.info("Click on the image to add points. Use the 'Trash' icon on the canvas to reset if you make a mistake.")
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=3,
        stroke_color="#FF0000",
        background_image=pil_img,
        update_streamlit=True,
        height=pil_img.height,
        width=pil_img.width,
        drawing_mode="point",
        key="canvas",
    )

    # --- SAVE LOGIC ---
    points = [obj for obj in canvas_result.json_data["objects"]] if canvas_result.json_data else []
    
    col1, col2 = st.columns(2)
    with col1:
        save_btn = st.button("Save & Next Image", disabled=(len(points) == 0))

    if save_btn:
        total_time = st.session_state.elapsed_before_pause + (time.time() - st.session_state.start_time)
        
        # 1. Label Studio Format
        ls_format = {
            "data": {"image": current_img_name},
            "annotations": [{
                "result": [
                    {
                        "original_width": pil_img.width,
                        "original_height": pil_img.height,
                        "image_rotation": 0,
                        "value": {"x": p["left"] / pil_img.width * 100, "y": p["top"] / pil_img.height * 100, "keypointlabels": ["Point"]},
                        "type": "keypointlabels"
                    } for p in points
                ]
            }]
        }
        
        # 2. Metadata Format
        meta_format = {
            "image": current_img_name,
            "user": st.session_state.user_name,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(total_time, 2),
            "point_count": len(points)
        }

        # Upload files
        folder = st.session_state.user_folder
        success1 = upload_to_github(f"{folder}/{current_img_name}_labels.json", ls_format, f"Labels for {current_img_name}")
        success2 = upload_to_github(f"{folder}/{current_img_name}_meta.json", meta_format, f"Meta for {current_img_name}")

        if success1 and success2:
            st.success("Saved successfully!")
            st.session_state.img_idx += 1
            st.session_state.elapsed_before_pause = 0
            st.session_state.start_time = time.time()
            st.rerun()
        else:
            st.error("Failed to save to GitHub. Check your Token/Repo settings.")