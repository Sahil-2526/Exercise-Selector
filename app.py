import streamlit as st
import pandas as pd
import os
import json
import re
import difflib 
import calendar
import sqlite3
import io
from datetime import datetime, timedelta
from huggingface_hub import InferenceClient

# Optional: Load local .env file if it exists (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- PAGE CONFIGURATION & MASTER UI STYLING ---
st.set_page_config(
    page_title="Keep Working Out",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Refined "Shadow & Silk" Aesthetic & Mobile Responsiveness
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

        .stApp {
            background-color: #0f0f13; 
            color: #f1f1f6;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }
        header { background-color: transparent !important; }
        
        .stTabs [data-baseweb="tab-list"] {
            gap: 12px;
            background-color: rgba(26, 26, 36, 0.6);
            padding: 8px 16px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            flex-wrap: wrap; 
        }
        .stTabs [data-baseweb="tab"] {
            color: #8c8c9e;
            height: 44px;
            background-color: transparent;
            border-radius: 8px;
            font-weight: 600;
            padding: 0px 20px;
            transition: all 0.2s ease;
        }
        .stTabs [aria-selected="true"] {
            color: #ffffff !important;
            background-color: #2a2a3b !important;
            border-bottom: none !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        .stButton>button {
            background-color: #2a2a3b;
            color: #e0e0eb;
            border: 1px solid rgba(181, 176, 212, 0.2); 
            border-radius: 10px;
            font-weight: 600;
            padding: 0.5rem 1rem;
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            background-color: #b5b0d4; 
            color: #0f0f13;
            border-color: #b5b0d4;
            transform: translateY(-1px);
        }
        .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div>div {
            background-color: #1a1a24 !important;
            color: #ffffff !important;
            border: 1px solid rgba(181, 176, 212, 0.1) !important;
            border-radius: 10px !important;
        }
        .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
            border-color: #b5b0d4 !important;
            box-shadow: 0 0 0 1px #b5b0d4 !important;
        }
        div[data-testid="stExpander"] {
            background-color: #1a1a24;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
        }
        .motivational-quote {
            font-style: italic;
            color: #9d99c7;
            background: linear-gradient(90deg, rgba(42,42,59,0.4) 0%, rgba(26,26,36,0) 100%);
            border-left: 4px solid #b5b0d4;
            padding: 12px 16px;
            border-radius: 0 8px 8px 0;
            margin-bottom: 24px;
            font-size: 0.95rem;
        }
        .muscle-tag {
            background-color: rgba(42, 42, 59, 0.8);
            border: 1px solid rgba(181, 176, 212, 0.2);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.85em;
            color: #d1ccf8;
            margin-right: 6px;
            display: inline-block;
            font-weight: 500;
        }
        
        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 8px;
            margin-top: 10px;
        }
        .calendar-day-header {
            text-align: center;
            font-weight: 600;
            color: #8c8c9e;
            margin-bottom: 4px;
            font-size: 0.85rem;
        }
        .calendar-day {
            text-align: center;
            border-radius: 8px;
            padding: 10px 4px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            min-height: 64px;
        }
        .calendar-day.done {
            background-color: #b5b0d4;
            color: #0f0f13;
            box-shadow: 0 0 12px rgba(181, 176, 212, 0.4);
        }
        .calendar-day.today {
            background-color: transparent;
            border: 2px dashed #b5b0d4;
            color: #b5b0d4;
        }
        .calendar-day.inactive {
            background-color: rgba(26,26,36,0.6);
            border: 1px solid rgba(255,255,255,0.05);
            color: #5f5f73;
        }
        .calendar-day.empty {
            background-color: transparent;
            border: none;
        }

        @media (max-width: 768px) {
            .calendar-grid { gap: 4px; }
            .calendar-day { min-height: 50px; padding: 6px 2px; }
            .calendar-day b { font-size: 0.9rem; }
            .calendar-day span { font-size: 0.65rem !important; }
            .stTabs [data-baseweb="tab-list"] { padding: 4px; }
            .stTabs [data-baseweb="tab"] { padding: 0px 10px; font-size: 0.85rem; }
        }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE INITIALIZATION ---
def get_db_connection():
    return sqlite3.connect("workout_engine.db", check_same_thread=False)

def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT,
                arsenal TEXT,
                progress TEXT,
                goals TEXT,
                streaks TEXT
            )
        ''')
        # Backward compatibility: Add streaks column if it doesn't exist
        try:
            conn.execute("ALTER TABLE users ADD COLUMN streaks TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        conn.commit()

init_db()

# --- DEFAULT USER DATA ---
DEFAULT_ARSENAL = pd.DataFrame(columns=["Exercise Name", "Muscle Group/Day", "Equipment Needed"])
DEFAULT_PROGRESS = pd.DataFrame(columns=["Date", "Exercise/Metric", "Weight", "Reps"])

# --- DEPLOYMENT-READY HUGGING FACE API INITIALIZATION ---
hf_token = None
try:
    hf_token = st.secrets["HF_TOKEN"]
except (FileNotFoundError, KeyError):
    hf_token = os.environ.get("HF_TOKEN")

client = InferenceClient(token=hf_token) if hf_token else None

# --- MASTER EXERCISE BANK (Updated to Yes/No) ---
MASTER_EXERCISE_BANK = {
    "chest": [
        {"name": "Incline Dumbbell Press", "muscle": "Upper Chest", "equipment": "Yes"},
        {"name": "Chest Fly", "muscle": "Pectorals", "equipment": "No"},
        {"name": "Cable Fly", "muscle": "Lower Chest", "equipment": "Yes"},
        {"name": "Dumbbell Chest Press", "muscle": "Mid Chest", "equipment": "Yes"},
        {"name": "Decline Pushup", "muscle": "Upper Chest", "equipment": "No"},
        {"name": "Dips", "muscle": "Lower Chest", "equipment": "No"}
    ],
    "back": [
        {"name": "Lat Pulldown", "muscle": "Lats", "equipment": "Yes"},
        {"name": "Seated Row", "muscle": "Mid Back", "equipment": "Yes"},
        {"name": "Bent-Over Barbell Row", "muscle": "Rhomboids", "equipment": "Yes"},
        {"name": "Face Pull", "muscle": "Rear Delts", "equipment": "Yes"},
        {"name": "T-Bar Row", "muscle": "Upper Back", "equipment": "Yes"},
        {"name": "Straight-Arm Pulldown", "muscle": "Lats", "equipment": "Yes"}
    ],
    "legs": [
        {"name": "Bulgarian Split Squat", "muscle": "Quads / Glutes", "equipment": "Yes"},
        {"name": "Romanian Deadlift", "muscle": "Hamstrings", "equipment": "Yes"},
        {"name": "Leg Press", "muscle": "Quads", "equipment": "Yes"},
        {"name": "Standing Calf Raise", "muscle": "Calves", "equipment": "No"},
        {"name": "Goblet Squat", "muscle": "Quads", "equipment": "Yes"},
        {"name": "Walking Lunges", "muscle": "Glutes / Quads", "equipment": "Yes"}
    ],
    "shoulders": [
        {"name": "Dumbbell Lateral Raise", "muscle": "Side Delts", "equipment": "Yes"},
        {"name": "Arnold Press", "muscle": "Front Delts", "equipment": "Yes"},
        {"name": "Overhead Barbell Press", "muscle": "Front Delts", "equipment": "Yes"},
        {"name": "Upright Row", "muscle": "Side Delts", "equipment": "Yes"},
        {"name": "Rear Delt Fly", "muscle": "Rear Delts", "equipment": "Yes"},
        {"name": "Cable Front Raise", "muscle": "Front Delts", "equipment": "Yes"}
    ],
    "arms": [
        {"name": "Hammer Curl", "muscle": "Biceps / Brachialis", "equipment": "Yes"},
        {"name": "Tricep Overhead Extension", "muscle": "Triceps", "equipment": "Yes"},
        {"name": "Preacher Curl", "muscle": "Biceps", "equipment": "Yes"},
        {"name": "Skull Crushers", "muscle": "Triceps", "equipment": "Yes"},
        {"name": "Concentration Curl", "muscle": "Biceps", "equipment": "Yes"},
        {"name": "Tricep Dips", "muscle": "Triceps", "equipment": "No"}
    ],
    "core": [
        {"name": "Plank", "muscle": "Transverse Abdominis", "equipment": "No"},
        {"name": "Russian Twist", "muscle": "Obliques", "equipment": "No"},
        {"name": "Ab Wheel Rollout", "muscle": "Abs", "equipment": "Yes"},
        {"name": "Bicycle Crunches", "muscle": "Obliques", "equipment": "No"},
        {"name": "Toes to Bar", "muscle": "Lower Abs", "equipment": "No"}
    ],
    "calisthenics": [
        {"name": "Push to Handstand Progression", "muscle": "Shoulders / Core", "equipment": "No"},
        {"name": "Pike Pushups", "muscle": "Front Delts", "equipment": "No"},
        {"name": "Frog Stand", "muscle": "Balance / Shoulders", "equipment": "No"},
        {"name": "L-Sit Hold", "muscle": "Core / Triceps", "equipment": "No"}
    ]
}

# --- JSON PARSING HELPER ---
def parse_json_output(output_str, is_array=True):
    if not output_str:
        return None
    output_str = output_str.strip()
    if output_str.startswith("```json"):
        output_str = output_str[7:-3].strip()
    elif output_str.startswith("```"):
        output_str = output_str[3:-3].strip()
    
    try:
        return json.loads(output_str)
    except json.JSONDecodeError:
        pattern = r'\[.*\]' if is_array else r'\{.*\}'
        match = re.search(pattern, output_str, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        return None

# --- LOCAL FALLBACK PARSER ---
def parse_log_locally(user_input):
    user_input = user_input.lower()
    user_input = re.sub(r'\band\b|\bthen\b|&', ',', user_input)
    clauses = [c.strip() for c in re.split(r'[,;\n]', user_input) if c.strip()]
    
    parsed_results = []
    
    muscle_map = {
        "Shoulders": ["pike", "shoulder", "press", "raise", "delt", "overhead", "handstand", "hspu", "frog", "planche"],
        "Arms": ["curl", "bicep", "tricep", "extension", "dip", "skullcrusher", "hammer"],
        "Core": ["plank", "crunch", "core", "ab", "twist", "situp", "sit-up", "l-sit", "hollow", "russian", "roller", "toes to bar"],
        "Back": ["pullup", "pull-up", "row", "lat", "back", "deadlift", "chinup", "chin-up", "muscle up", "shrug"],
        "Legs": ["squat", "leg", "lunge", "calf", "calves", "quad", "hamstring", "pistol", "glute", "stepup", "romanian"],
        "Chest": ["pushup", "push-up", "bench", "chest", "fly", "pec", "cable crossover"]
    }
    
    for clause in clauses:
        weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|lbs|kilos)', clause)
        ex_weight = f"{weight_match.group(1)}{weight_match.group(2)}" if weight_match else "-"
        
        reps_match = re.search(r'(\d+)\s*(?:x|\*|sets? of)\s*(\d+)', clause)
        if reps_match:
            ex_reps = f"{reps_match.group(1)}x{reps_match.group(2)}"
            clause_clean = re.sub(r'\d+\s*(?:x|\*|sets? of)\s*\d+', '', clause)
        else:
            clause_clean = clause
            numbers = re.findall(r'\b\d+\b', re.sub(r'\d+(?:\.\d+)?\s*(?:kg|lbs|kilos)', '', clause_clean))
            ex_reps = numbers[0] if numbers else "-"
            
        clause_clean = re.sub(r'\d+(?:\.\d+)?\s*(?:kg|lbs|kilos)', '', clause_clean)
        ex_name = re.sub(r'\b\d+\b', '', clause_clean).strip()
        ex_name = re.sub(r'[^a-z\s-]', '', ex_name) 
        ex_name = re.sub(r'\s+', ' ', ex_name).title() 
        
        if not ex_name or len(ex_name) < 2:
            continue
            
        name_lower = ex_name.lower()
        
        inferred_muscle = "Add Manually"
        
        for group, keywords in muscle_map.items():
            if any(re.search(rf'\b{kw}\b', name_lower) for kw in keywords):
                inferred_muscle = group
                break
                
        # Smart Equipment Detection based on extracted weight
        inferred_equip = "Yes" if ex_weight != "-" else "No"

        parsed_results.append({
            "name": ex_name,
            "weight": ex_weight,
            "reps": ex_reps,
            "muscle": inferred_muscle,
            "equipment": inferred_equip
        })
        
    return parsed_results

# --- SESSION STATE INITIALIZATION ---
default_states = {
    'logged_in_user': None,
    'generated_routine_text': "",
    'active_checklist': {},
    'specific_targets': {},
    'recommended_exercises': [],
    'current_target_group': "Full Body",
    'hf_quota_exhausted': False,
    'streak_dates': [] # SEPARATE STREAK DATABASE
}

for key, val in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- AUTHENTICATION SCREEN ---
if not st.session_state.logged_in_user:
    st.markdown("<br><br>", unsafe_allow_html=True) 
    
    _, auth_col, _ = st.columns([1, 2.5, 1]) 
    
    with auth_col:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center; font-weight: 800; margin-bottom: 8px;'>Keep Working Out</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #8c8c9e; font-size: 0.9rem; margin-bottom: 24px;'>Secure Workspace Authentication</p>", unsafe_allow_html=True)
            
            auth_mode = st.radio("Mode", ["Login", "Register Account"], horizontal=True, label_visibility="collapsed")
            st.write("")
            username_input = st.text_input("Username", placeholder="Enter your username").strip()
            password_input = st.text_input("Password", type="password", placeholder="Enter your secure password").strip()
            st.write("")
            
            if st.button("Access Workspace", use_container_width=True):
                if not username_input or not password_input:
                    st.warning("Please provide both username and password.")
                else:
                    with get_db_connection() as conn:
                        c = conn.cursor()
                        
                        if auth_mode == "Register Account":
                            c.execute("SELECT username FROM users WHERE username=?", (username_input,))
                            if c.fetchone():
                                st.error("Username already registered. Please login.")
                            else:
                                c.execute("SELECT password FROM users WHERE password=?", (password_input,))
                                if c.fetchone():
                                    st.error("This password is already in use by another account. Please choose a unique password.")
                                else:
                                    ars_json = DEFAULT_ARSENAL.to_json(orient="records")
                                    prog_json = DEFAULT_PROGRESS.to_json(orient="records")
                                    goals_json = json.dumps([])
                                    streaks_json = json.dumps([])
                                    
                                    c.execute("INSERT INTO users (username, password, arsenal, progress, goals, streaks) VALUES (?, ?, ?, ?, ?, ?)",
                                              (username_input, password_input, ars_json, prog_json, goals_json, streaks_json))
                                    conn.commit()
                                    
                                    st.session_state.logged_in_user = username_input
                                    st.success(f"Workspace initialized for {username_input}!")
                                    st.rerun()
                        else:
                            c.execute("SELECT password FROM users WHERE username=?", (username_input,))
                            row = c.fetchone()
                            if row and row[0] == password_input:
                                st.session_state.logged_in_user = username_input
                                st.success(f"Welcome back, {username_input}!")
                                st.rerun()
                            elif row:
                                st.error("Invalid password.")
                            else:
                                st.error("Account not found. Please register.")
            
    st.stop()

# --- LOAD CURRENT USER WORKSPACE FROM SQL DB ---
current_user = st.session_state.logged_in_user

if 'data_loaded' not in st.session_state or st.session_state.data_loaded != current_user:
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT arsenal, progress, goals, streaks FROM users WHERE username=?", (current_user,))
        row = c.fetchone()
    
    if row:
        try:
            ars_df = pd.read_json(io.StringIO(row[0]), orient="records")
            ars_df = ars_df if not ars_df.empty else DEFAULT_ARSENAL.copy()
        except:
            ars_df = DEFAULT_ARSENAL.copy()
            
        try:
            prog_df = pd.read_json(io.StringIO(row[1]), orient="records")
            prog_df = prog_df if not prog_df.empty else DEFAULT_PROGRESS.copy()
        except:
            prog_df = DEFAULT_PROGRESS.copy()
            
        st.session_state.arsenal_df = ars_df
        st.session_state.progress_df = prog_df
        st.session_state.user_goals = json.loads(row[2]) if row[2] else []
        st.session_state.streak_dates = json.loads(row[3]) if len(row) > 3 and row[3] else []
    else:
        st.session_state.arsenal_df = DEFAULT_ARSENAL.copy()
        st.session_state.progress_df = DEFAULT_PROGRESS.copy()
        st.session_state.user_goals = []
        st.session_state.streak_dates = []
        
    st.session_state.data_loaded = current_user

def save_user_state():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET arsenal=?, progress=?, goals=?, streaks=? WHERE username=?", (
            st.session_state.arsenal_df.to_json(orient="records"),
            st.session_state.progress_df.to_json(orient="records"),
            json.dumps(st.session_state.user_goals),
            json.dumps(st.session_state.streak_dates),
            current_user
        ))
        conn.commit()

# --- TOP BAR WORKSPACE & DYNAMIC QUOTA BADGE ---
top_col1, top_col2, top_col3 = st.columns([4, 3, 1])
with top_col1:
    st.title(f"Keep Working Out — [{current_user.upper()}]")

badge_placeholder = top_col2.empty()

def render_api_badge():
    if not client:
        badge_placeholder.markdown("<div style='background-color: rgba(250, 204, 21, 0.1); border: 1px solid #facc15; color: #facc15; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; display: inline-block; margin-top: 15px;'>● LOCAL OFFLINE MODE</div>", unsafe_allow_html=True)
    elif st.session_state.hf_quota_exhausted:
        badge_placeholder.markdown("<div style='background-color: rgba(248, 113, 113, 0.1); border: 1px solid #f87171; color: #f87171; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; display: inline-block; margin-top: 15px;'>● AI QUOTA EXHAUSTED - PLEASE ADD EXERCISE MANUALLY</div>", unsafe_allow_html=True)
    else:
        badge_placeholder.markdown("<div style='background-color: rgba(74, 222, 128, 0.1); border: 1px solid #4ade80; color: #4ade80; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; display: inline-block; margin-top: 15px;'>● HUGGING FACE AI ACTIVE</div>", unsafe_allow_html=True)

render_api_badge()

with top_col3:
    st.write("")
    if st.button("Sign Out", use_container_width=True):
        save_user_state()
        for key in ['logged_in_user', 'data_loaded', 'generated_routine_text', 'active_checklist', 'specific_targets', 'recommended_exercises', 'hf_quota_exhausted', 'streak_dates']:
            st.session_state.pop(key, None)
        st.rerun()

st.markdown("<div class='motivational-quote'>Surpass your limits. Master the fundamentals. Your isolated workout records are synced securely.</div>", unsafe_allow_html=True)

# --- MAIN LAYOUT TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["Progress & Arsenal", "Routine Generator", "Active Session", "Streaks & Goals"])

# ==========================================
# TAB 1: PROGRESS TRACKER & ARSENAL
# ==========================================
with tab1:
    st.subheader("Performance Logs")
    st.markdown("Log your performance in plain text. Metrics sync instantly to your history and library.")
    
    # Ensure Notes are stripped out if they still accidentally exist in the session state
    display_df = st.session_state.progress_df.copy()
    if "Notes" in display_df.columns:
        display_df = display_df.drop(columns=["Notes"])
        
    edited_df = st.data_editor(
        display_df,
        num_rows="dynamic",
        use_container_width=True,
        key="progress_editor"
    )
    
    st.session_state.progress_df = edited_df
    save_user_state()
    
    with st.form("progress_extraction_form"):
        user_log_input = st.text_area("Log update (Natural Language)", placeholder="10 pushup, 30 kg bicep curl 10, 40 kg deadlift")
        extract_btn = st.form_submit_button("Extract & Sync Tables")
        
        if extract_btn:
            if not user_log_input:
                st.warning("Please enter your performance log.")
            else:
                extracted_data = None
                
                if client:
                    try:
                        extraction_messages = [
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert fitness data analyst. Extract exercises and metrics accurately. "
                                    "Match the precise repetition count to each specific exercise clause. If missing, output '-'. "
                                    "OUTPUT FORMAT: You must respond ONLY with a valid JSON array containing objects. "
                                    "Each object must use these exact keys: 'name', 'weight', 'reps', 'muscle', 'equipment'. "
                                    "For 'equipment', strictly output 'Yes' if a weight is mentioned or required, otherwise output 'No'. "
                                    "Do not include any markdown formatting, backticks, or extra text."
                                )
                            },
                            {
                                "role": "user",
                                "content": f"Extract workout achievements from this text: '{user_log_input}'"
                            }
                        ]
                        response = client.chat.completions.create(
                            model="meta-llama/Llama-3.1-8B-Instruct",
                            messages=extraction_messages,
                            max_tokens=400,
                            temperature=0.1 
                        )
                        extracted_data = parse_json_output(response.choices[0].message.content, is_array=True)
                        st.session_state.hf_quota_exhausted = False
                    except Exception:
                        extracted_data = None 
                        st.session_state.hf_quota_exhausted = True
                        render_api_badge() 
                
                if not extracted_data:
                    extracted_data = parse_log_locally(user_log_input)
                    st.toast("Parsed via local offline engine.", icon="⚡")
                else:
                    st.toast("Parsed via Hugging Face AI.", icon="🧠")

                updated_count = 0
                added_count = 0
                arsenal_added_count = 0
                current_date = datetime.now().strftime("%Y-%m-%d")
                
                existing_progress = [str(x) for x in st.session_state.progress_df['Exercise/Metric'].tolist()]
                existing_arsenal = [str(x) for x in st.session_state.arsenal_df['Exercise Name'].tolist()]
                
                for item in extracted_data:
                    ex_name = str(item.get("name", "Unknown Exercise")).strip()
                    ex_weight = str(item.get("weight", "-")).strip()
                    ex_reps = str(item.get("reps", "-")).strip()
                    ex_muscle = str(item.get("muscle", "Add Manually"))
                    
                    ex_equip = "Yes" if ex_weight != "-" and ex_weight != "" else "No"
                    
                    if not ex_name or ex_name.lower() == "none":
                        continue
                    
                    close_matches_prog = difflib.get_close_matches(ex_name.lower(), [e.lower() for e in existing_progress], n=1, cutoff=0.85)
                    if close_matches_prog:
                        matched_ex = close_matches_prog[0]
                        match_idx = st.session_state.progress_df[st.session_state.progress_df['Exercise/Metric'].astype(str).str.lower() == matched_ex.lower()].index
                        idx = match_idx[0]
                        st.session_state.progress_df.at[idx, 'Date'] = current_date
                        st.session_state.progress_df.at[idx, 'Weight'] = ex_weight
                        st.session_state.progress_df.at[idx, 'Reps'] = ex_reps
                        updated_count += 1
                    else:
                        new_prog_row = pd.DataFrame([{"Date": current_date, "Exercise/Metric": ex_name, "Weight": ex_weight, "Reps": ex_reps}])
                        st.session_state.progress_df = pd.concat([st.session_state.progress_df, new_prog_row], ignore_index=True)
                        added_count += 1

                    close_matches_ars = difflib.get_close_matches(ex_name.lower(), [e.lower() for e in existing_arsenal], n=1, cutoff=0.85)
                    if not close_matches_ars:
                        new_ars_row = pd.DataFrame([{"Exercise Name": ex_name, "Muscle Group/Day": ex_muscle, "Equipment Needed": ex_equip}])
                        st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_ars_row], ignore_index=True)
                        existing_arsenal.append(ex_name)
                        arsenal_added_count += 1
                
                save_user_state()
                st.success(f"Sync complete. {added_count} logs added, {updated_count} updated. {arsenal_added_count} added to library.")
                st.rerun()

    st.divider()

    st.subheader("Exercise Arsenal Library")
    st.session_state.arsenal_df = st.data_editor(
        st.session_state.arsenal_df, 
        num_rows="dynamic", 
        use_container_width=True,
        key="arsenal_editor"
    )
    save_user_state()

    with st.expander("Manually Add Exercise (Form)"):
        with st.form("add_exercise_form"):
            col1, col2 = st.columns(2)
            with col1:
                ex_name = st.text_input("Exercise Name")
                ex_muscle = st.text_input("Target Muscle", placeholder="e.g., Upper Chest, Rear Delts")
            with col2:
                ex_equip = st.selectbox("Equipment Needed", ["No", "Yes"])
            
            submit_btn = st.form_submit_button("Add Exercise")
            if submit_btn and ex_name:
                new_row = pd.DataFrame([{"Exercise Name": ex_name, "Muscle Group/Day": ex_muscle, "Equipment Needed": ex_equip}])
                st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_row], ignore_index=True)
                save_user_state()
                st.success(f"Added '{ex_name}' to Arsenal.")
                st.rerun()

# ==========================================
# TAB 2: WORKOUT GENERATOR
# ==========================================
with tab2:
    st.subheader("Routine Generator")
    st.markdown("Define your focus for today. Powered by dynamic inference with automated offline fallback.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        # Dynamically extract, split by commas/slashes, and sort unique muscle groups
        raw_muscles = st.session_state.arsenal_df['Muscle Group/Day'].dropna().astype(str).tolist()
        muscle_set = set()
        
        for m_str in raw_muscles:
            # Splits strings like "Chest, Shoulders" or "Quads / Glutes" into separate items
            for part in re.split(r'[,/]', m_str):
                clean_part = part.strip()
                if clean_part and clean_part.lower() != "add manually":
                    # Title case ensures 'chest' and 'Chest' combine into one option
                    muscle_set.add(clean_part.title())
                    
        existing_muscles = sorted(list(muscle_set))
        
        selected_focus = st.selectbox("Select Target Focus (From Library)", ["-- Type Custom Below --"] + existing_muscles)
        custom_focus = st.text_input("Or Type New Focus", placeholder="Write new muscle group and press enter...")

        if selected_focus == "+ Add Custom Focus...":
            target_group = st.text_input("↳ Enter Custom Muscle Group", placeholder="e.g., Forearms, Neck...")
        else:
            target_group = selected_focus
            
    with col_b:
        has_gym = st.radio("Gym Access Today?", ["Yes", "No (Bodyweight only)"])
        
    st.write("") # Extra padding
    generate_btn = st.button("Generate Routine", use_container_width=True)

    if generate_btn:
        if not target_group:
            st.warning("Please specify a target focus.")
        else:
            st.session_state.current_target_group = target_group
            generated_data = None
            
            if client:
                with st.spinner("Analyzing progress..."):
                    valid_arsenal = st.session_state.arsenal_df[
                        st.session_state.arsenal_df["Muscle Group/Day"].astype(str).str.contains(target_group, case=False, na=False)
                    ]
                    
                    if "No" in has_gym:
                        valid_arsenal = valid_arsenal[valid_arsenal["Equipment Needed"].astype(str).str.strip().str.upper() == "NO"]
                        
                    arsenal_csv = valid_arsenal.to_csv(index=False) if not valid_arsenal.empty else "No matching exercises."
                    
                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are an expert fitness coach. Output a valid JSON object strictly matching this schema: "
                                "{"
                                "\"routine_text\": \"String detailing motivation and recommendations.\", "
                                "\"arsenal_exercises\": [{\"name\": \"Exercise from CSV\", \"specific_target\": \"Muscle part\"}], "
                                "\"recommended_exercises\": [{\"name\": \"New Exercise\", \"muscle\": \"Muscle\", \"equipment\": \"Yes or No\"}]"
                                "}"
                                "Provide exactly 5 recommended exercises not in CSV. Ensure 'equipment' strictly returns 'Yes' or 'No'."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Target Focus: {target_group}, Gym: {has_gym}\nArsenal:\n{arsenal_csv}"
                        }
                    ]
                    try:
                        response = client.chat.completions.create(
                            model="meta-llama/Llama-3.1-8B-Instruct",
                            messages=messages,
                            max_tokens=1000,
                            temperature=0.4
                        )
                        generated_data = parse_json_output(response.choices[0].message.content, is_array=False)
                        st.session_state.hf_quota_exhausted = False
                    except Exception:
                        generated_data = None
                        st.session_state.hf_quota_exhausted = True
                        render_api_badge() 

            if not generated_data:
                target_key = target_group.lower().strip()
                arsenal = st.session_state.arsenal_df
                
                matched_rows = arsenal[arsenal["Muscle Group/Day"].astype(str).str.lower().str.contains(target_key, na=False) | 
                                       arsenal["Exercise Name"].astype(str).str.lower().str.contains(target_key, na=False)]
                
                if "No" in has_gym:
                    matched_rows = matched_rows[matched_rows["Equipment Needed"].astype(str).str.strip().str.upper() == "NO"]
                
                arsenal_exs = []
                for _, row in matched_rows.head(4).iterrows():
                    arsenal_exs.append({"name": row["Exercise Name"], "specific_target": row["Muscle Group/Day"]})
                
                bank_key = "chest"
                for cat in MASTER_EXERCISE_BANK.keys():
                    if cat in target_key:
                        bank_key = cat
                        break
                bank_list = MASTER_EXERCISE_BANK.get(bank_key, MASTER_EXERCISE_BANK["chest"])
                existing_names = [str(x).lower() for x in arsenal["Exercise Name"].tolist()]
                
                recs = []
                for item in bank_list:
                    if "No" in has_gym and str(item.get("equipment", "")).strip().lower() != "no":
                        continue
                    if item["name"].lower() not in existing_names:
                        recs.append(item)

                generated_data = {
                    "routine_text": f"Locally generated routine for **{target_group.title()}**. Complete all items to secure your streak.",
                    "arsenal_exercises": arsenal_exs,
                    "recommended_exercises": recs[:5]
                }
                st.toast("Routine built via local offline engine.", icon="⚡")
            else:
                st.toast("Routine built via Hugging Face AI.", icon="🧠")

            st.session_state.generated_routine_text = generated_data.get("routine_text", "Workout routine generated.")
            st.session_state.active_checklist = {}
            st.session_state.specific_targets = {}
            
            for ex_obj in generated_data.get("arsenal_exercises", []):
                ex_name = ex_obj.get("name")
                spec_target = ex_obj.get("specific_target", target_group)
                if ex_name:
                    st.session_state.active_checklist[ex_name] = False
                    st.session_state.specific_targets[ex_name] = spec_target
                
            st.session_state.recommended_exercises = generated_data.get("recommended_exercises", [])
            save_user_state()
            st.success("Routine built successfully. Proceed to 'Active Session' to track execution.")

    if st.session_state.generated_routine_text:
        st.markdown(st.session_state.generated_routine_text)

# ==========================================
# TAB 3: ACTIVE SESSION
# ==========================================
with tab3:
    st.subheader("Active Training Workspace")
    if not st.session_state.active_checklist and not st.session_state.recommended_exercises:
        st.info("No active session initialized. Use the Generator tab first.")
    else:
        col_tracker, col_routine = st.columns([1, 1], gap="large")
        with col_tracker:
            st.markdown("### Execution Checklist")
            all_completed = True
            
            if not st.session_state.active_checklist:
                st.info("No matching Arsenal exercises found. Select from recommendations below.")
            else:
                for task in list(st.session_state.active_checklist.keys()):
                    is_checked = st.checkbox(task, value=st.session_state.active_checklist[task], key=f"chk_{task}")
                    st.session_state.active_checklist[task] = is_checked
                    if not is_checked:
                        all_completed = False

            if st.session_state.recommended_exercises:
                st.divider()
                st.markdown("#### Curated Recommendations")
                recs_to_show = list(st.session_state.recommended_exercises)
                for idx, rec in enumerate(recs_to_show):
                    rec_name = rec.get("name", "Unknown Exercise")
                    rec_muscle = rec.get("muscle", st.session_state.current_target_group)
                    rec_equip = str(rec.get("equipment", "No")).strip().title()
                    
                    rec_col1, rec_col2 = st.columns([4, 1])
                    rec_col1.markdown(f"**{rec_name}**")
                    if rec_col2.button("+", key=f"add_rec_{idx}"):
                        st.session_state.active_checklist[rec_name] = False
                        st.session_state.specific_targets[rec_name] = rec_muscle
                        
                        existing_arsenal = [str(x).lower() for x in st.session_state.arsenal_df['Exercise Name'].tolist()]
                        if str(rec_name).lower() not in existing_arsenal:
                            new_row = pd.DataFrame([{"Exercise Name": rec_name, "Muscle Group/Day": rec_muscle, "Equipment Needed": rec_equip}])
                            st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_row], ignore_index=True)
                            
                        save_user_state()
                        st.session_state.recommended_exercises.pop(idx)
                        st.rerun()

            st.divider()
            if all_completed and len(st.session_state.active_checklist) > 0:
                st.success("All exercises checked off.")
                if st.button("Mark Workout as Done"):
                    # ONLY logs to the dedicated streak database. DOES NOT add to Progress logs!
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    if today_str not in st.session_state.streak_dates:
                        st.session_state.streak_dates.append(today_str)
                        
                    st.session_state.active_checklist = {}
                    st.session_state.generated_routine_text = ""
                    st.session_state.specific_targets = {}
                    st.session_state.recommended_exercises = []
                    save_user_state()
                    st.success("Session completed! Streak secured.")
                    st.rerun()

        with col_routine:
            st.markdown("### Plan Breakdown")
            st.markdown(st.session_state.generated_routine_text)
            st.divider()
            st.markdown("#### Anatomical Focus")
            if st.session_state.active_checklist:
                for task in st.session_state.active_checklist.keys():
                    spec_target = st.session_state.specific_targets.get(task, st.session_state.current_target_group)
                    st.markdown(f"**{task}:** <span class='muscle-tag'>{spec_target}</span>", unsafe_allow_html=True)
            else:
                st.caption("No items in checklist.")

# ==========================================
# TAB 4: STREAKS & GOALS
# ==========================================
with tab4:
    st.markdown("<div style='display: flex; justify-content: flex-end; margin-bottom: 20px;'>", unsafe_allow_html=True)
    if st.button("Quick Log: Mark Today as Complete"):
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if today_str not in st.session_state.streak_dates:
            st.session_state.streak_dates.append(today_str)
            save_user_state()
            
        st.success("Today marked as complete! Streak secured.")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    col_streak, col_goals = st.columns([3, 2], gap="large")
    
    with col_streak:
        st.subheader("Consistency Heatmap")
        
        # PULL FROM NEW DEDICATED STREAK DB
        workout_dates = sorted([datetime.strptime(d, "%Y-%m-%d").date() for d in st.session_state.streak_dates], reverse=True)
        today_date = datetime.now().date()
        yesterday_date = today_date - timedelta(days=1)
        
        current_streak = 0
        is_today_done = today_date in workout_dates
        
        check_date = today_date if is_today_done else yesterday_date
        
        for d in workout_dates:
            if d == check_date:
                current_streak += 1
                check_date -= timedelta(days=1)
            elif d > check_date:
                continue 
            else:
                break

        if current_streak > 0:
            if is_today_done:
                badge_color = "#4ade80" 
                text_shadow = "0 0 12px rgba(74, 222, 128, 0.4)"
                streak_title = f"{current_streak} DAY STREAK SECURED"
            else:
                badge_color = "#facc15" 
                text_shadow = "0 0 12px rgba(250, 204, 21, 0.4)"
                streak_title = f"{current_streak} DAY STREAK (WAITING ON TODAY)"
                
            streak_html = f"""
            <div style="display: flex; align-items: center; gap: 12px; margin-top: 10px; margin-bottom: 5px;">
                <svg viewBox="0 0 24 24" width="40" height="40" fill="{badge_color}" style="filter: drop-shadow({text_shadow});">
                    <path d="M12 2C12 2 7 7 7 13C7 15.76 9.24 18 12 18C14.76 18 17 15.76 17 13C17 7 12 2 12 2ZM12 16C10.9 16 10 15.1 10 14C10 12.9 12 10 12 10C12 10 14 11.9 14 14C14 15.1 13.1 16 12 16Z"/>
                </svg>
                <h2 style="color: {badge_color}; text-shadow: {text_shadow}; font-weight: 800; margin: 0; font-size: 1.4rem;">
                    {streak_title}
                </h2>
            </div>
            """
        else:
            streak_html = f"""
            <div style="display: flex; align-items: center; gap: 12px; margin-top: 10px; margin-bottom: 5px;">
                <svg viewBox="0 0 24 24" width="40" height="40" fill="#4d4d6b">
                    <path d="M12 2C12 2 7 7 7 13C7 15.76 9.24 18 12 18C14.76 18 17 15.76 17 13C17 7 12 2 12 2ZM12 16C10.9 16 10 15.1 10 14C10 12.9 12 10 12 10C12 10 14 11.9 14 14C14 15.1 13.1 16 12 16Z"/>
                </svg>
                <h2 style="color: #4d4d6b; font-weight: 800; margin: 0; font-size: 1.4rem;">
                    0 DAY ACTIVE STREAK
                </h2>
            </div>
            """
            
        st.markdown(streak_html, unsafe_allow_html=True)
        st.caption("Streak increases only when you complete and log a training session.")
        st.write("")
        
        today = datetime.now()
        cal = calendar.monthcalendar(today.year, today.month)
        month_name = calendar.month_name[today.month]
        st.markdown(f"#### {month_name} {today.year}")
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        
        cal_html = '<div class="calendar-grid">'
        for d_name in day_names:
            cal_html += f'<div class="calendar-day-header">{d_name}</div>'
            
        for week in cal:
            for day in week:
                if day == 0:
                    cal_html += '<div class="calendar-day empty"></div>'
                else:
                    current_date = datetime(today.year, today.month, day).date()
                    if current_date in workout_dates:
                        cal_html += f'<div class="calendar-day done" style="background-color: #4ade80; color: #0f0f13; box-shadow: 0 0 12px rgba(74, 222, 128, 0.4);"><b>{day}</b><span style="font-size:0.75rem; font-weight:800; margin-top: 2px;">Done</span></div>'
                    elif current_date == today.date():
                        cal_html += f'<div class="calendar-day today" style="border: 2px dashed #facc15; color: #facc15;"><b>{day}</b><span style="font-size:0.75rem; font-weight:700; margin-top: 2px;">Pending</span></div>'
                    else:
                        cal_html += f'<div class="calendar-day inactive"><b>{day}</b></div>'
                        
        cal_html += '</div>'
        st.markdown(cal_html, unsafe_allow_html=True)

    with col_goals:
        st.subheader("Milestone Goals")
        with st.form("add_goal_form"):
            new_goal = st.text_input("Define a target goal", placeholder="e.g., Master the push to handstand")
            if st.form_submit_button("Add Goal"):
                if new_goal:
                    st.session_state.user_goals.append(new_goal)
                    save_user_state()
                    st.rerun()
                    
        st.divider()
        if not st.session_state.user_goals:
            st.info("No active goals defined.")
        else:
            for i, goal in enumerate(st.session_state.user_goals):
                g_col1, g_col2 = st.columns([4, 1])
                g_col1.markdown(f"**{i+1}.** {goal}")
                if g_col2.button("Del", key=f"del_goal_{i}"):
                    st.session_state.user_goals.pop(i)
                    save_user_state()
                    st.rerun()