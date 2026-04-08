import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image, ImageDraw
import os, json, time, requests, base64
from datetime import datetime

# --- CONFIG ---
IMAGE_DIR = "images"
REPO_OWNER_REPO = st.secrets["DATA_REPO"]
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="Mussel Annotator Project", layout="wide")


theme_choice = st.sidebar.radio("Choose Theme", ["Light", "Dark"])

if theme_choice == "Dark":
    primary_bg = "#0E1117"
    secondary_bg = "#262730"
    text_col = "#FAFAFA"
    card_shadow = "rgba(255, 255, 255, 0.1)"
else:
    primary_bg = "#FFFFFF"
    secondary_bg = "#F0F2F6"
    text_col = "#31333F"
    card_shadow = "rgba(0, 0, 0, 0.05)"
    
# Note the f before the triple quotes!
st.markdown(f"""
    <style>
    .block-container {{ 
        padding-top: 3.5rem !important; 
        max-width: 98% !important; 
    }}
    
    [data-testid="stStatusWidget"] {{ display: none !important; }}

    /* Main App Background */
    .stApp {{
        background-color: {primary_bg} !important;
        color: {text_col} !important;
    }}

    /* --- EXPANDER FIX (TARGETING THE CLOSED STATE) --- */
    div[data-testid="stExpander"] {{
        background-color: {secondary_bg} !important;
        border: 1px solid rgba(255, 92, 0, 0.2) !important;
        border-radius: 8px !important;
    }}

    /* The header/clickable area */
    div[data-testid="stExpander"] summary {{
        background-color: {secondary_bg} !important;
        color: {text_col} !important;
    }}

    /* The icon/arrow */
    div[data-testid="stExpander"] svg {{
        fill: {text_col} !important;
    }}

    /* The content inside when open */
    div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
        background-color: {primary_bg} !important;
        color: {text_col} !important;
    }}

    /* --- BUTTONS --- */
    div.stButton > button {{
        background-color: {secondary_bg} !important;
        color: {text_col} !important;
        border: 1px solid #FF5C00 !important;
    }}

    div.stButton > button:hover {{
        border-color: #FF5C00 !important;
        color: #FF5C00 !important;
        background-color: {primary_bg} !important;
    }}

    /* --- INPUT BOXES --- */
    div[data-testid="stTextInput"] input {{
        background-color: {secondary_bg} !important;
        color: {text_col} !important;
        border: 1px solid rgba(255, 92, 0, 0.5) !important;
    }}

    /* --- GENERAL TEXT --- */
    label, .stMarkdown p, .stMarkdown li {{
        color: {text_col} !important;
    }}

    .label-statement {{ 
        font-size: 24px; 
        font-weight: bold; 
        color: #FF5C00; 
        margin-bottom: 5px; 
    }}
    
    .counter-box {{ 
        background-color: {secondary_bg}; 
        color: {text_col};
        padding: 12px; 
        border-radius: 8px; 
        border-left: 6px solid #FF5C00;
        margin-top: 10px;
        margin-bottom: 25px;
        font-size: 19px;
        font-weight: bold;
        box-shadow: 0px 2px 4px {card_shadow};
    }}
    
    .break-overlay {{
        background-color: #F5A038; 
        color: #F27013; 
        padding: 20px;
        border-radius: 10px; 
        text-align: center; 
        border: 2px solid #f5c6cb;
        margin: 20px 0; 
        font-size: 20px; 
        font-weight: bold;
    }}
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
    st.header("🦪 Mussel Annotation Project", divider="rainbow", text_alignment = "center")
    st.subheader("Hello and welcome to my annotation app. \n Thank you for participating and helping with my Master Thesis!",divider= "orange", text_alignment = "center")
    st.markdown("This project is focused on assessing annotation perfromance on **Mussels** images collected in the Limfjord, in Northern Jutland.")
    st.markdown("By annotating the images that will be presented, you will help me in the analysis of the data, which will be used for my Thesis.")
    st.markdown("Please finish the annotations by April 24th")
    st.markdown("The analysis will focus on mussel counting and time of annotation, thus the time will be recorded. Please take as much time as you need.")
    st.markdown("A \"Break\" function will be provided, such that the time will be stopped when needed.")
    st.markdown("For Dark Mode, click on the >> on the top left corner")
    st.markdown("Below, you can find a field in which to write your name. The name will be used to save your annotations and to collect previous ones. If you haven't finished in a previous session, or need to correct something choose \"Continue\".") 
    st.markdown("If it is your first time annotating but you are offered to continue with the annotations, please refresh the page and use a different name. Please remember if you use Capital letters or lower case ones.")
    st.markdown("""
    Please insert your name followed by an underscore (_) and one of three acronyms: 
    * ***MB*** - for Marine Biologist
    * ***CV*** - for Computer Vision expert or Data Scientist
    * ***NP*** - for anyone not belonging to the above categories
    """)
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
            <h1 style="color: #FF5B00;">🎉 Session Complete!</h1>
            <p style="font-size: 20px;">Thank you for helping with with the annotation, your work is really apreciated!</p>
            <p style="font-size: 20px;">You have successfully annotated all <b>{len(images)}</b> images.</p>
            <p>Data saved to: <b>{st.session_state.folder}</b></p>
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("⬅️ Back to Last Image"):
        st.session_state.img_idx = len(images) - 1
        st.rerun()
    if st.button("Start New Session"):
        st.session_state.clear()
        st.rerun()
    st.stop()

# NAVIGATION BOUNDS
if st.session_state.img_idx < 0: st.session_state.img_idx = 0
current_img = images[st.session_state.img_idx]

# --- THE COUNTER (Moved here to ensure visibility) ---

with st.expander("📖 Click here for the Project Guide & Instructions", expanded=True):
    st.subheader("Annotation guidelines and general informations", divider= "orange")

    st.markdown("""
    You are showed an image to annotate. 
    Your goal is to identify **Live Mussels** in the images, and put a point on each of them.  \n 
    A Live Mussel is defined as a Mussel that has the two parts of the shell that are clearly attached together, possibly with white tentacles coming out of the slightly open shell. 
    A clearly dead mussel would be only one part of the shell, and/or opened and clearly empty.
    Please refer to the examples if you have doubts.
    * To annotate an image, click in the center the subject (Mussels only).
    * Please click on each mussel you see in the image. Every time you click, it takes a second for the dot to appear. Thank you for your patience.
    * If you make an :red[error] for a point, you can click on the point and it will be deleted. 
    * The :green[timer] starts automatically at the first click on a mussel.
    * If you would like to take a :violet-background[break], please click on the "take a break button", so the timer stops.

    * If you are :orange[done] with the image, click :orange["Save and next"], and the next image will be shown.
    * If you need to look at :blue[previous] images, you can click on the :blue["previous"] button and the previous image will be shown. \n
    
    You can see your progress at the top of the image. 
    """)
    with st.expander("Visual examples of mussels for clarity"):
        ann_ex = "example_of_point_annotations.png"
        st.image(ann_ex, caption= "Example of annotated mussels")
        ex_live = "reasonably live.jpg"
        st.image(ex_live, caption= "Example of live mussels. \n The two parts of the shell are attached and tentcles are coming out")
        ex_empty = "empty.jpg"
        st.image(ex_empty, caption= "Example of empty shell. \n The two parts are attached but there is nothing inside. \n Otherwise, if there is only one part of the shell and it is empty.")
    
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
    c_info.write(f"**Current File:** **Total Points Found:** {len(st.session_state.points)}")
    
    if c_break.button("TAKE A BREAK", type="primary"):
        if st.session_state.active_start:
            st.session_state.total_elapsed += (time.time() - st.session_state.active_start)
            st.session_state.active_start = None
        st.session_state.on_break = True
        st.rerun()
    if c_reset.button("Reset Image"):
        st.session_state.points = []; st.rerun()

    draw_img = pil_img.copy()
    draw = ImageDraw.Draw(draw_img)
    r = max(orig_w, orig_h) * 0.0035
    for p in st.session_state.points:
        px, py = (p[0]/100)*orig_w, (p[1]/100)*orig_h
        draw.ellipse([px-r, py-r, px+r, py+r], fill="red", outline="white", width=1)

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

if col_prev.button("PREVIOUS", type="secondary", use_container_width=True):
    save_current_work()
    st.session_state.img_idx -= 1
    st.rerun()

if col_save.button("SAVE & NEXT", type="primary", use_container_width=True):
    save_current_work()
    st.session_state.img_idx += 1
    st.rerun()
