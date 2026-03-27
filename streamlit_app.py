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

# --- CSS: CLEAN UI & NO FLASH ---
st.markdown("""
    <style>
    /* 1. Increase padding so text isn't cut off at the top */
    .block-container { 
        padding-top: 3.5rem !important; 
        max-width: 98% !important; 
    }
    
    [data-testid="stStatusWidget"] { display: none !important; }
    
    .label-statement { 
        font-size: 24px; 
        font-weight: bold; 
        color: #007BFF; 
        margin-bottom: 5px; 
    }
    
    /* 2. Added margin-top to ensure it's below the top bar */
    .counter-box { 
        background-color: #f0f2f6; 
        padding: 12px; 
        border-radius: 8px; 
        border-left: 6px solid #007BFF;
        margin-top: 10px;
        margin-bottom: 25px;
        font-size: 19px;
        font-weight: bold;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
    }
    
    .break-overlay {
        background-color: #f8d7da; color: #721c24; padding: 20px;
        border-radius: 10px; text-align: center; border: 2px solid #f5c6cb;
        margin: 20px 0; font-size: 20px; font-weight: bold;
    }
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
        try:
            content = json.loads(base64.b64decode(res.json()["content"]).decode())
            if "annotations" in content and len(content["annotations"]) > 0:
                ann = content["annotations"][0]
                items = ann.get("result", content.get("annotations", []))
                return [[r['value']['x'], r['value']['y']] for r in items if 'value' in r]
        except Exception as e:
            st.error(f"Error reading existing labels: {e}")
    return []

# --- SESSION STATE ---
if "points" not in st.session_state:
    st.session_state.update({
        "user_name": None, "img_idx": 0, "folder": None, "session_started": False, 
        "points": [], "last_click": None, "current_loaded_img": None,
        "active_start": None, "total_elapsed": 0.0, "on_break": False
    })

# --- STEP 1: LOGIN & SESSION RESUME ---
if not st.session_state.session_started:
    st.markdown("<br>", unsafe_allow_html=True)
    st.header("🦪 Mussel Annotation Project", divider="rainbow")
    st.markdown("Hello and welcome to my annotation app. \n Thank you for participating and helping with my Master Thesis!!")
    st.markdown("The goal of this process is to assess the performance of human annotation for mussels in the Limfjord.")
    st.markdown("This will help me analyse the annotator performance and assess the time required to annotate each image")
    st.markdown("Please note that the time required for annotation is recorded, and please take as much time as you need.")
    st.markdown("First thing you are asked to write your name in the field below. Use the same name every time you log in.")
    st.markdown("If you have annotated images before, you will be asked if you want to continue with the previous work or start a new one.")
    st.markdown("")
    name_input = st.text_input("Enter your name:").strip()
    if name_input:
        res = github_request("GET", "")
        existing = [f["name"] for f in res.json() if f["type"] == "dir" and f["name"].startswith(name_input)] if res.status_code == 200 else []
        col1, col2 = st.columns(2)
        if existing:
            latest = sorted(existing)[-1]
            if col1.button(f"Continue ({latest})"):
                res_f = github_request("GET", latest)
                idx = len([f for f in res_f.json() if "_labels.json" in f["name"]]) if res_f.status_code == 200 else 0
                st.session_state.update({"user_name": name_input, "folder": latest, "img_idx": idx, "session_started": True})
                st.rerun()
        if col2.button("Start New Session"):
            v_num = len(existing) + 1
            st.session_state.update({"user_name": name_input, "folder": f"{name_input}_v{v_num}", "img_idx": 0, "session_started": True})
            st.rerun()
    st.stop()

# --- STEP 2: IMAGE LOADING & COMPLETION CHECK ---
images = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

# COMPLETION PAGE
if st.session_state.img_idx >= len(images):
    st.balloons()
    st.markdown(f"""
        <div style="text-align: center; padding: 50px;">
            <h1 style="color: #28a745;">🎉 Session Complete!</h1>
            <p style="font-size: 20px;">Thank you for helping with with the annotation, your work is really apreciated!</p>
            <p style="font-size: 20px;">You have successfully annotated all <b>{len(images)}</b> images.</p>
            <p>Data saved to: <b>{st.session_state.folder}</b></p>
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("⬅️ Back to Last Image"):
        st.session_state.img_idx = len(images) - 1
        st.rerun()
    if st.button("🚪 Start New Session"):
        st.session_state.clear()
        st.rerun()
    st.stop()

# NAVIGATION BOUNDS
if st.session_state.img_idx < 0: st.session_state.img_idx = 0
current_img = images[st.session_state.img_idx]

# --- THE COUNTER (Moved here to ensure visibility) ---

st.markdown("""
<div class="counter-box">
You are showed an image to annotate. 
\n Please click on each mussel you see in the image. Every time you click, it takes a second for the dot to appear. Thank you for your patience. \n
The :green[timer] starts from the first click on a mussel. \n
If you are :violet[done] with the image, click :violet["Save and next"], and the next image will be shown. \n
If you would like to take a :orange[break], please click on the "take a break button", so the timer stops. \n
If you need to look at :blue[previous] images, you can click on the :blue["previous"] button and the previous image will be shown. \n
If you make an :red[error] for a point, you can click on the point and it will be deleted. 

You can see your progress at the top of the image. 
</div>""")
st.markdown(f"""
    <div class="counter-box">
        You are at image {st.session_state.img_idx + 1} out of {len(images)}
    </div>
    """, unsafe_allow_html=True)
# LOAD DATA FROM GITHUB IF IMAGE CHANGED
if st.session_state.current_loaded_img != current_img:
    path = f"{st.session_state.folder}/{current_img}_labels.json"
    st.session_state.points = get_existing_annotation(path)
    st.session_state.current_loaded_img = current_img
    st.session_state.total_elapsed = 0.0
    st.session_state.active_start = None

pil_img = Image.open(os.path.join(IMAGE_DIR, current_img)).convert("RGB")
orig_w, orig_h = pil_img.size

# --- STEP 3: THE FRAGMENT (ZERO FLASH) ---
@st.fragment
def annotation_engine():
    st.markdown('<p class="label-statement">Labeling: Mussel</p>', unsafe_allow_html=True)
    
    if st.session_state.on_break:
        st.markdown('<div class="break-overlay">☕ ON BREAK: Timer Paused</div>', unsafe_allow_html=True)
        if st.button("RE-START LABELING", use_container_width=True):
            st.session_state.on_break = False
            if st.session_state.points: st.session_state.active_start = time.time()
            st.rerun()
        st.stop()

    c_info, c_break, c_reset = st.columns([3, 1, 1])
    c_info.write(f"**Current File:** {current_img} | **Total Points:** {len(st.session_state.points)}")
    
    if c_break.button("TAKE A BREAK"):
        if st.session_state.active_start:
            st.session_state.total_elapsed += (time.time() - st.session_state.active_start)
            st.session_state.active_start = None
        st.session_state.on_break = True
        st.rerun()
    if c_reset.button("Reset Image"):
        st.session_state.points = []; st.rerun()

    draw_img = pil_img.copy()
    draw = ImageDraw.Draw(draw_img)
    r = max(orig_w, orig_h) * 0.007
    for p in st.session_state.points:
        px, py = (p[0]/100)*orig_w, (p[1]/100)*orig_h
        draw.ellipse([px-r, py-r, px+r, py+r], fill="red", outline="white", width=3)

    value = streamlit_image_coordinates(draw_img, width=1200, key=f"img_{st.session_state.img_idx}")

    if value:
        cx, cy = (value["x"]/value["width"])*100, (value["y"]/value["height"])*100
        click_hash = f"{cx:.2f}{cy:.2f}"
        if st.session_state.last_click != click_hash:
            st.session_state.last_click = click_hash
            if st.session_state.active_start is None: st.session_state.active_start = time.time()
            
            # TARGETED DELETE LOGIC
            found_idx = -1
            for i, p in enumerate(st.session_state.points):
                if abs(p[0]-cx) < 2.5 and abs(p[1]-cy) < 2.5:
                    found_idx = i; break
            
            if found_idx != -1: st.session_state.points.pop(found_idx)
            else: st.session_state.points.append([cx, cy])
            st.rerun()

annotation_engine()

# --- STEP 4: NAVIGATION & SAVE ---
st.markdown("---")
col_prev, col_save = st.columns([1, 4])

def save_current_work():
    dur = st.session_state.total_elapsed
    if st.session_state.active_start: dur += (time.time() - st.session_state.active_start)
    res_list = [{"value": {"x": p[0], "y": p[1], "label": "mussel"}} for p in st.session_state.points]
    meta = {"image": current_img, "count": len(st.session_state.points), "duration_sec": round(dur, 2), "annotator": st.session_state.user_name}
    upload_to_github(f"{st.session_state.folder}/{current_img}_labels.json", {"image": current_img, "annotations": res_list}, "Save")
    upload_to_github(f"{st.session_state.folder}/{current_img}_meta.json", meta, "Meta")

if col_prev.button("PREVIOUS", use_container_width=True):
    save_current_work()
    st.session_state.img_idx -= 1
    st.rerun()

if col_save.button("SAVE & NEXT", type="primary", use_container_width=True):
    save_current_work()
    st.session_state.img_idx += 1
    st.rerun()
