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
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# Load local .env file if it exists
load_dotenv()

# --- DATABASE INITIALIZATION ---
def get_db_connection():
    return sqlite3.connect("workout_engine.db")

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            arsenal TEXT,
            progress TEXT,
            goals TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- DEFAULT USER DATA (EMPTY ARSENAL) ---
DEFAULT_ARSENAL = pd.DataFrame(columns=["Exercise Name", "Muscle Group/Day", "Equipment Needed"])
DEFAULT_PROGRESS = pd.DataFrame(columns=["Date", "Exercise/Metric", "Weight", "Reps", "Notes"])

# --- API INITIALIZATION WITH AUTO-FALLBACK ---
hf_token = os.environ.get("HF_TOKEN")
client = None
if hf_token:
    try:
        client = InferenceClient(token=hf_token)
    except Exception:
        client = None

# --- MASTER EXERCISE BANK (For Local Recommendations Fallback) ---
MASTER_EXERCISE_BANK = {
    "chest": [
        {"name": "Incline Dumbbell Press", "muscle": "Upper Chest", "equipment": "Dumbbells"},
        {"name": "Chest Fly", "muscle": "Pectorals", "equipment": "None (Bodyweight)"},
        {"name": "Cable Fly", "muscle": "Lower Chest", "equipment": "Cables"},
        {"name": "Dumbbell Chest Press", "muscle": "Mid Chest", "equipment": "Dumbbells"},
        {"name": "Decline Pushup", "muscle": "Upper Chest", "equipment": "None (Bodyweight)"},
        {"name": "Dips", "muscle": "Lower Chest", "equipment": "None (Bodyweight)"}
    ],
    "back": [
        {"name": "Lat Pulldown", "muscle": "Lats", "equipment": "Cables"},
        {"name": "Seated Row", "muscle": "Mid Back", "equipment": "Cables"},
        {"name": "Bent-Over Barbell Row", "muscle": "Rhomboids", "equipment": "Barbell"},
        {"name": "Face Pull", "muscle": "Rear Delts", "equipment": "Cables"},
        {"name": "T-Bar Row", "muscle": "Upper Back", "equipment": "Barbell"},
        {"name": "Straight-Arm Pulldown", "muscle": "Lats", "equipment": "Cables"}
    ],
    "legs": [
        {"name": "Bulgarian Split Squat", "muscle": "Quads / Glutes", "equipment": "Dumbbells"},
        {"name": "Romanian Deadlift", "muscle": "Hamstrings", "equipment": "Barbell"},
        {"name": "Leg Press", "muscle": "Quads", "equipment": "Machine"},
        {"name": "Standing Calf Raise", "muscle": "Calves", "equipment": "None (Bodyweight)"},
        {"name": "Goblet Squat", "muscle": "Quads", "equipment": "Dumbbells"},
        {"name": "Walking Lunges", "muscle": "Glutes / Quads", "equipment": "Dumbbells"}
    ],
    "shoulders": [
        {"name": "Dumbbell Lateral Raise", "muscle": "Side Delts", "equipment": "Dumbbells"},
        {"name": "Arnold Press", "muscle": "Front Delts", "equipment": "Dumbbells"},
        {"name": "Overhead Barbell Press", "muscle": "Front Delts", "equipment": "Barbell"},
        {"name": "Upright Row", "muscle": "Side Delts", "equipment": "Barbell"},
        {"name": "Rear Delt Fly", "muscle": "Rear Delts", "equipment": "Dumbbells"},
        {"name": "Cable Front Raise", "muscle": "Front Delts", "equipment": "Cables"}
    ],
    "arms": [
        {"name": "Hammer Curl", "muscle": "Biceps / Brachialis", "equipment": "Dumbbells"},
        {"name": "Tricep Overhead Extension", "muscle": "Triceps", "equipment": "Dumbbells"},
        {"name": "Preacher Curl", "muscle": "Biceps", "equipment": "Barbell"},
        {"name": "Skull Crushers", "muscle": "Triceps", "equipment": "Barbell"},
        {"name": "Concentration Curl", "muscle": "Biceps", "equipment": "Dumbbells"},
        {"name": "Tricep Dips", "muscle": "Triceps", "equipment": "None (Bodyweight)"}
    ],
    "core": [
        {"name": "Plank", "muscle": "Transverse Abdominis", "equipment": "None (Bodyweight)"},
        {"name": "Russian Twist", "muscle": "Obliques", "equipment": "None (Bodyweight)"},
        {"name": "Ab Wheel Rollout", "muscle": "Abs", "equipment": "Machine"},
        {"name": "Bicycle Crunches", "muscle": "Obliques", "equipment": "None (Bodyweight)"},
        {"name": "Toes to Bar", "muscle": "Lower Abs", "equipment": "None (Bodyweight)"}
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
                return None
        return None

# --- IMPROVED LOCAL FALLBACK PARSER ---
def parse_log_locally(user_input):
    clauses = re.split(r'[,;\n]|\band\b', user_input)
    parsed_results = []
    
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
            
        weights = re.findall(r'(\d+(?:\.\d+)?)\s*(?:kg|lbs)', clause, re.IGNORECASE)
        ex_weight = f"{weights[0]}kg" if weights else "-"
        
        clause_no_wt = re.sub(r'\d+(?:\.\d+)?\s*(?:kg|lbs)', '', clause, flags=re.IGNORECASE).strip()
        
        numbers = re.findall(r'\b\d+\b', clause_no_wt)
        
        ex_name = re.sub(r'\b\d+\b', '', clause_no_wt).strip()
        ex_name = re.sub(r'\s+', ' ', ex_name) 
        
        if not ex_name or len(ex_name) < 2:
            continue
            
        reps = numbers[0] if numbers else "-"
            
        parsed_results.append({
            "name": ex_name,
            "weight": ex_weight,
            "reps": reps,
            "muscle": "Full Body",
            "equipment": "None (Bodyweight)"
        })
    return parsed_results

# --- PAGE CONFIGURATION & MASTER UI STYLING ---
st.set_page_config(
    page_title="Workout Engine",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

        .stApp {
            background-color: #0f0f13;
            color: #f1f1f6;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }
        header {
            background-color: transparent !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 12px;
            background-color: rgba(26, 26, 36, 0.6);
            padding: 8px 16px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.05);
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
            border: 1px solid rgba(255, 255, 255, 0.1);
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
        .stTextInput>div>div>input, .stTextArea>div>div>textarea {
            background-color: #1a1a24 !important;
            color: #ffffff !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 10px !important;
        }
        .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
            border-color: #b5b0d4 !important;
            box-shadow: 0 0 0 1px #b5b0d4 !important;
        }
        .stSelectbox>div>div>div {
            background-color: #1a1a24 !important;
            color: #ffffff !important;
            border-radius: 10px !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
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
        .auth-container {
            max-width: 420px;
            margin: 80px auto;
            padding: 40px;
            background-color: rgba(26, 26, 36, 0.8);
            backdrop-filter: blur(12px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
        }
    </style>
""", unsafe_allow_html=True)

# --- USER PERSISTENCE LOGIC ---
if 'logged_in_user' not in st.session_state:
    st.session_state.logged_in_user = None

# --- AUTHENTICATION SCREEN ---
if not st.session_state.logged_in_user:
    st.markdown("<div class='auth-container'>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; font-weight: 800; margin-bottom: 8px;'>Workout Engine</h2>", unsafe_allow_html=True)
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
            conn = get_db_connection()
            c = conn.cursor()
            
            if auth_mode == "Register Account":
                c.execute("SELECT username FROM users WHERE username=?", (username_input,))
                if c.fetchone():
                    st.error("Username already registered. Please login.")
                else:
                    ars_json = DEFAULT_ARSENAL.to_json(orient="records")
                    prog_json = DEFAULT_PROGRESS.to_json(orient="records")
                    goals_json = json.dumps([])
                    
                    c.execute("INSERT INTO users (username, password, arsenal, progress, goals) VALUES (?, ?, ?, ?, ?)",
                              (username_input, password_input, ars_json, prog_json, goals_json))
                    conn.commit()
                    st.session_state.logged_in_user = username_input
                    st.success(f"Workspace initialized for {username_input}!")
                    st.rerun()
            else:
                c.execute("SELECT password FROM users WHERE username=?", (username_input,))
                row = c.fetchone()
                if row:
                    if row[0] == password_input:
                        st.session_state.logged_in_user = username_input
                        st.success(f"Welcome back, {username_input}!")
                        st.rerun()
                    else:
                        st.error("Invalid password.")
                else:
                    st.error("Account not found. Please register.")
            conn.close()
            
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# --- LOAD CURRENT USER WORKSPACE FROM SQL DB ---
current_user = st.session_state.logged_in_user

if 'data_loaded' not in st.session_state or st.session_state.data_loaded != current_user:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT arsenal, progress, goals FROM users WHERE username=?", (current_user,))
    row = c.fetchone()
    conn.close()
    
    if row:
        try:
            ars_df = pd.read_json(io.StringIO(row[0]), orient="records")
            if ars_df.empty:
                ars_df = DEFAULT_ARSENAL.copy()
        except:
            ars_df = DEFAULT_ARSENAL.copy()
            
        try:
            prog_df = pd.read_json(io.StringIO(row[1]), orient="records")
            if prog_df.empty:
                prog_df = DEFAULT_PROGRESS.copy()
        except:
            prog_df = DEFAULT_PROGRESS.copy()
            
        st.session_state.arsenal_df = ars_df
        st.session_state.progress_df = prog_df
        st.session_state.user_goals = json.loads(row[2]) if row[2] else []
    else:
        st.session_state.arsenal_df = DEFAULT_ARSENAL.copy()
        st.session_state.progress_df = DEFAULT_PROGRESS.copy()
        st.session_state.user_goals = []
        
    st.session_state.data_loaded = current_user

# Other runtime state variables
if 'generated_routine_text' not in st.session_state:
    st.session_state.generated_routine_text = ""
if 'active_checklist' not in st.session_state:
    st.session_state.active_checklist = {}
if 'specific_targets' not in st.session_state:
    st.session_state.specific_targets = {}
if 'recommended_exercises' not in st.session_state:
    st.session_state.recommended_exercises = []
if 'current_target_group' not in st.session_state:
    st.session_state.current_target_group = "Full Body"

# Helper function to persist state changes back to SQL database
def save_user_state():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET arsenal=?, progress=?, goals=? WHERE username=?", (
        st.session_state.arsenal_df.to_json(orient="records"),
        st.session_state.progress_df.to_json(orient="records"),
        json.dumps(st.session_state.user_goals),
        current_user
    ))
    conn.commit()
    conn.close()

# Top Bar Workspace Header & Logout Action
top_col1, top_col2 = st.columns([5, 1])
with top_col1:
    st.title(f"Workout Engine — [{current_user.upper()}]")
with top_col2:
    st.write("")
    if st.button("Sign Out", use_container_width=True):
        save_user_state()
        st.session_state.logged_in_user = None
        st.session_state.data_loaded = None
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
    
    st.session_state.progress_df = st.data_editor(
        st.session_state.progress_df,
        num_rows="dynamic",
        use_container_width=True,
        key="progress_editor"
    )
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
                                    "Do not include any markdown formatting, backticks, or extra text."
                                )
                            },
                            {
                                "role": "user",
                                "content": f"Extract workout achievements from this text: '{user_log_input}'"
                            }
                        ]
                        extraction_response = client.chat.completions.create(
                            model="meta-llama/Llama-3.1-8B-Instruct",
                            messages=extraction_messages,
                            max_tokens=400,
                            temperature=0.1 
                        )
                        extracted_data = parse_json_output(extraction_response.choices[0].message.content, is_array=True)
                    except Exception:
                        extracted_data = None 
                
                if not extracted_data:
                    extracted_data = parse_log_locally(user_log_input)
                    st.toast("Parsed via local deterministic engine.", icon="⚡")

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
                    ex_muscle = str(item.get("muscle", "Full Body"))
                    ex_equip = str(item.get("equipment", "None (Bodyweight)"))
                    
                    if not ex_name or ex_name.lower() == "none":
                        continue
                    
                    close_matches_prog = difflib.get_close_matches(ex_name.lower(), [e.lower() for e in existing_progress], n=1, cutoff=0.7)
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

                    close_matches_ars = difflib.get_close_matches(ex_name.lower(), [e.lower() for e in existing_arsenal], n=1, cutoff=0.7)
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

    with st.expander("Manually Add Exercise"):
        with st.form("add_exercise_form"):
            col1, col2 = st.columns(2)
            with col1:
                ex_name = st.text_input("Exercise Name")
                ex_muscle = st.text_input("Target Muscle", placeholder="e.g., Upper Chest, Rear Delts")
            with col2:
                ex_equip = st.selectbox("Equipment", ["None (Bodyweight)", "Dumbbells", "Barbell", "Cables", "Court/Track"])
            
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
    
    with st.form("hf_generator_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            target_group = st.text_input("Target Focus", placeholder="e.g., Chest, Biceps, Lats, Quads")
        with col_b:
            has_gym = st.radio("Gym Access Today?", ["Yes", "No (Bodyweight only)"])
            
        generate_btn = st.form_submit_button("Generate Routine")

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
                    arsenal_csv = valid_arsenal.to_csv(index=False) if not valid_arsenal.empty else "No matching exercises."
                    progress_csv = st.session_state.progress_df.to_csv(index=False) if not st.session_state.progress_df.empty else "No progress logged yet."
                    
                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are an expert fitness coach. Output a valid JSON object strictly matching this schema: "
                                "{"
                                "\"routine_text\": \"String detailing motivation and recommendations.\", "
                                "\"arsenal_exercises\": [{\"name\": \"Exercise from CSV\", \"specific_target\": \"Muscle part\"}], "
                                "\"recommended_exercises\": [{\"name\": \"New Exercise\", \"muscle\": \"Muscle\", \"equipment\": \"Equipment\"}]"
                                "}"
                                "Provide exactly 5 recommended exercises not in CSV."
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
                    except Exception:
                        generated_data = None

            if not generated_data:
                target_key = target_group.lower().strip()
                arsenal = st.session_state.arsenal_df
                matched_rows = arsenal[arsenal["Muscle Group/Day"].astype(str).str.lower().str.contains(target_key, na=False) | 
                                       arsenal["Exercise Name"].astype(str).str.lower().str.contains(target_key, na=False)]
                
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
                    if item["name"].lower() not in existing_names:
                        recs.append(item)

                generated_data = {
                    "routine_text": f"Locally generated routine for **{target_group.title()}**. Complete all items to secure your streak.",
                    "arsenal_exercises": arsenal_exs,
                    "recommended_exercises": recs[:5]
                }

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
                    rec_equip = rec.get("equipment", "None (Bodyweight)")
                    
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
                    new_prog_row = pd.DataFrame([{"Date": datetime.now().strftime("%Y-%m-%d"), "Exercise/Metric": "Daily Workout Completed", "Weight": "-", "Reps": "1", "Notes": "Completed session"}])
                    st.session_state.progress_df = pd.concat([st.session_state.progress_df, new_prog_row], ignore_index=True)
                    st.session_state.active_checklist = {}
                    st.session_state.generated_routine_text = ""
                    st.session_state.specific_targets = {}
                    st.session_state.recommended_exercises = []
                    save_user_state()
                    st.success("Session saved! Streak updated.")
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
        new_prog_row = pd.DataFrame([{"Date": datetime.now().strftime("%Y-%m-%d"), "Exercise/Metric": "Daily Workout Completed", "Weight": "-", "Reps": "1", "Notes": "Quick Log"}])
        st.session_state.progress_df = pd.concat([st.session_state.progress_df, new_prog_row], ignore_index=True)
        save_user_state()
        st.success("Today logged successfully.")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    col_streak, col_goals = st.columns([3, 2], gap="large")
    
    with col_streak:
        st.subheader("Consistency Heatmap")
        if not st.session_state.progress_df.empty:
            df_filtered = st.session_state.progress_df[st.session_state.progress_df["Exercise/Metric"] == "Daily Workout Completed"]
            workout_dates = sorted(pd.to_datetime(df_filtered["Date"]).dt.date.unique(), reverse=True)
        else:
            workout_dates = []

        today_date = datetime.now().date()
        yesterday_date = today_date - timedelta(days=1)
        
        current_streak = 0
        if workout_dates:
            if workout_dates[0] == today_date:
                current_streak = 1
                check_date = yesterday_date
                idx = 1
            elif workout_dates[0] == yesterday_date:
                current_streak = 1
                check_date = yesterday_date - timedelta(days=1)
                idx = 1
            else:
                idx = 0
                check_date = None
            
            if current_streak > 0:
                while idx < len(workout_dates) and workout_dates[idx] == check_date:
                    current_streak += 1
                    check_date -= timedelta(days=1)
                    idx += 1

        if current_streak >= 1:
            streak_html = f"""
            <div style="display: flex; align-items: center; gap: 12px; margin-top: 10px; margin-bottom: 5px;">
                <svg viewBox="0 0 24 24" width="40" height="40" fill="#b5b0d4" style="filter: drop-shadow(0px 0px 10px #b5b0d4);">
                    <path d="M12 2C12 2 7 7 7 13C7 15.76 9.24 18 12 18C14.76 18 17 15.76 17 13C17 7 12 2 12 2ZM12 16C10.9 16 10 15.1 10 14C10 12.9 12 10 12 10C12 10 14 11.9 14 14C14 15.1 13.1 16 12 16Z"/>
                </svg>
                <h2 style="color: #b5b0d4; text-shadow: 0 0 12px rgba(181,176,212,0.4); font-weight: 800; margin: 0;">
                    {current_streak} DAY ACTIVE STREAK
                </h2>
            </div>
            """
        else:
            streak_html = f"""
            <div style="display: flex; align-items: center; gap: 12px; margin-top: 10px; margin-bottom: 5px;">
                <svg viewBox="0 0 24 24" width="40" height="40" fill="#2a2a3b">
                    <path d="M12 2C12 2 7 7 7 13C7 15.76 9.24 18 12 18C14.76 18 17 15.76 17 13C17 7 12 2 12 2ZM12 16C10.9 16 10 15.1 10 14C10 12.9 12 10 12 10C12 10 14 11.9 14 14C14 15.1 13.1 16 12 16Z"/>
                </svg>
                <h2 style="color: #4d4d6b; font-weight: 800; margin: 0;">
                    {current_streak} DAY ACTIVE STREAK
                </h2>
            </div>
            """
            
        st.markdown(streak_html, unsafe_allow_html=True)
        st.caption("Streak increases when you complete and log a training session.")
        st.write("")
        
        today = datetime.now()
        cal = calendar.monthcalendar(today.year, today.month)
        month_name = calendar.month_name[today.month]
        st.markdown(f"#### {month_name} {today.year}")
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        
        header_cols = st.columns(7)
        for i, d_name in enumerate(day_names):
            header_cols[i].markdown(f"<div style='text-align: center; font-weight: 600; color: #8c8c9e; margin-bottom: 8px; font-size: 0.85rem;'>{d_name}</div>", unsafe_allow_html=True)
            
        for week in cal:
            week_cols = st.columns(7)
            for i, day in enumerate(week):
                if day == 0:
                    week_cols[i].write("")
                else:
                    current_date = datetime(today.year, today.month, day).date()
                    if current_date in workout_dates:
                        week_cols[i].markdown(f"<div style='text-align: center; background-color: #2a2a3b; border: 1px solid #b5b0d4; color: #b5b0d4; border-radius: 8px; padding: 10px; margin-bottom: 6px; font-size: 0.9rem;'><b>{day}</b><br><span style='font-size:0.75rem;'>Done</span></div>", unsafe_allow_html=True)
                    elif current_date == today.date():
                        week_cols[i].markdown(f"<div style='text-align: center; background-color: #b5b0d4; color: #0f0f13; border-radius: 8px; padding: 10px; margin-bottom: 6px; font-size: 0.9rem;'><b>{day}</b><br><span style='font-size:0.75rem; font-weight:700;'>Today</span></div>", unsafe_allow_html=True)
                    else:
                        week_cols[i].markdown(f"<div style='text-align: center; background-color: rgba(26,26,36,0.6); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 10px; margin-bottom: 6px; color: #5f5f73; font-size: 0.9rem;'><b>{day}</b></div>", unsafe_allow_html=True)

    with col_goals:
        st.subheader("Milestone Goals")
        with st.form("add_goal_form"):
            new_goal = st.text_input("Define a target goal", placeholder="e.g., Handstand hold for 10s")
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

import sqlite3

conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT name FROM sqlite_master
    WHERE type='table' AND name NOT LIKE 'sqlite_%'
""")

tables = [row[0] for row in cursor.fetchall()]

for table in tables:
    cursor.execute(f'DELETE FROM "{table}"')

conn.commit()
conn.close()