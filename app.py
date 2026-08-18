import streamlit as st
import pandas as pd
import os
import json
import re
import difflib 
import calendar
from datetime import datetime, timedelta
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# Load local .env file if it exists
load_dotenv()

# --- API INITIALIZATION ---
hf_token = os.environ.get("HF_TOKEN")
if hf_token:
    client = InferenceClient(token=hf_token)
else:
    st.warning("HF_TOKEN not found in environment variables or .env file.")
    client = None

# --- JSON PARSING HELPER ---
def parse_json_output(output_str, is_array=True):
    """Robust JSON parser with regex fallback to handle AI hallucinations."""
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

# --- PAGE CONFIGURATION & CUSTOM CSS ---
st.set_page_config(
    page_title="Workout Engine",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Theme: Shadow & Silk (Navy Slate, Lavender, Mid-Dark Panels)
st.markdown("""
    <style>
        .stApp {
            background-color: #1a1a24;
            color: #e0e0eb;
        }
        header {
            background-color: transparent !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }
        .stTabs [data-baseweb="tab"] {
            color: #8c8c9e;
            height: 50px;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 4px 4px 0px 0px;
            gap: 1px;
            padding-top: 10px;
            padding-bottom: 10px;
        }
        .stTabs [aria-selected="true"] {
            color: #b5b0d4 !important;
            border-bottom: 2px solid #b5b0d4 !important;
        }
        .stButton>button {
            background-color: #2a2a3b;
            color: #b5b0d4;
            border: 1px solid #4d4d6b;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #b5b0d4;
            color: #1a1a24;
            border: 1px solid #b5b0d4;
        }
        .stTextInput>div>div>input, .stTextArea>div>div>textarea {
            background-color: #2a2a3b !important;
            color: #ffffff !important;
            border: 1px solid #4d4d6b !important;
        }
        .stSelectbox>div>div>div {
            background-color: #2a2a3b !important;
            color: #ffffff !important;
        }
        div[data-testid="stExpander"] {
            background-color: #2a2a3b;
            border: 1px solid #4d4d6b;
            border-radius: 8px;
        }
        .motivational-quote {
            font-style: italic;
            color: #b5b0d4;
            border-left: 3px solid #b5b0d4;
            padding-left: 10px;
            margin-bottom: 20px;
        }
        .muscle-tag {
            background-color: #2a2a3b;
            border: 1px solid #4d4d6b;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            color: #b5b0d4;
            margin-right: 5px;
            display: inline-block;
        }
        .congrats-banner {
            background-color: #2e7d32;
            border: 1px solid #4caf50;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: center;
            box-shadow: 0 0 15px #4caf50;
            animation: glow 1.5s ease-in-out infinite alternate;
        }
        @keyframes glow {
            from { box-shadow: 0 0 10px #4caf50; }
            to { box-shadow: 0 0 20px #81c784, 0 0 30px #4caf50; }
        }
    </style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if 'arsenal_df' not in st.session_state:
    st.session_state.arsenal_df = pd.DataFrame(
        columns=["Exercise Name", "Muscle Group/Day", "Equipment Needed"]
    )

if 'progress_df' not in st.session_state:
    st.session_state.progress_df = pd.DataFrame(
        columns=["Date", "Exercise/Metric", "Weight", "Reps", "Notes"]
    )

if 'user_goals' not in st.session_state:
    st.session_state.user_goals = [] 

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

st.title("Dynamic Workout Generator")
st.markdown("<div class='motivational-quote'>Surpass your limits. Master the fundamentals. Build the handstand, perfect the shot, trust the routine.</div>", unsafe_allow_html=True)

# --- AUTOMATED GOAL EVALUATION ENGINE ---
if st.session_state.user_goals and not st.session_state.progress_df.empty:
    goals_to_remove = []
    achieved_messages = []
    
    # Filter out legacy string goals to prevent crashes
    st.session_state.user_goals = [g for g in st.session_state.user_goals if isinstance(g, dict)]
    
    for idx, goal in enumerate(st.session_state.user_goals):
        ex_name = goal["exercise"]
        metric = goal["metric"]
        target = goal["target"]
        
        matches = st.session_state.progress_df[
            st.session_state.progress_df["Exercise/Metric"].astype(str).str.lower() == ex_name.lower()
        ]
        
        for _, row in matches.iterrows():
            val_str = str(row[metric])
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", val_str)
            if numbers:
                val = float(numbers[0])
                if val >= target:
                    achieved_messages.append(f"You crushed your goal of {target} {metric} on {ex_name.title()}!")
                    if idx not in goals_to_remove:
                        goals_to_remove.append(idx)
    
    if achieved_messages:
        for msg in achieved_messages:
            st.markdown(f"""
            <div class="congrats-banner">
                <h3 style="color: #ffffff; margin: 0; text-transform: uppercase; letter-spacing: 1px;">CONGRATULATIONS!</h3>
                <p style="color: #e8f5e9; font-size: 1.1em; margin-top: 5px; margin-bottom: 0;">{msg}</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Remove completed goals starting from the highest index
        for idx in sorted(goals_to_remove, reverse=True):
            st.session_state.user_goals.pop(idx)


# --- MAIN LAYOUT TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["Progress & Arsenal", "AI Generator", "Active Session", "Streaks & Goals"])

# ==========================================
# TAB 1: PROGRESS TRACKER & ARSENAL
# ==========================================
with tab1:
    st.subheader("Your Progress Log")
    st.markdown("Log your performance in plain text. Exercises will update here and auto-add to your Arsenal if missing.")
    
    st.session_state.progress_df = st.data_editor(
        st.session_state.progress_df,
        num_rows="dynamic",
        use_container_width=True,
        key="progress_editor"
    )
    
    with st.form("progress_extraction_form"):
        user_log_input = st.text_area("Log update (Natural Language)", placeholder="I played basketball for 2 hours, practiced handstands, and did 40 pushups.")
        extract_btn = st.form_submit_button("Extract & Sync Tables")
        
        if extract_btn:
            if not client:
                st.error("Cannot call Hugging Face API without a valid HF_TOKEN.")
            elif not user_log_input:
                st.warning("Please enter your performance log.")
            else:
                with st.spinner("Extracting metrics and analyzing data..."):
                    extraction_messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are an expert fitness data analyst. Extract exercises and metrics from the user input. "
                                "CRITICAL: Correct any spelling mistakes in the exercise names. "
                                "For every exercise, infer: "
                                "1. Muscle Group (Provide the PRECISE anatomical muscle targeted, e.g., Biceps, Upper Chest, Rear Delts, Glutes, Hamstrings). Do not use broad categories. "
                                "2. Equipment (Choose ONE: None (Bodyweight), Dumbbells, Barbell, Cables, Court/Track, Machine) "
                                "OUTPUT FORMAT: You must respond ONLY with a valid JSON array containing objects. "
                                "Each object must use these exact keys: 'name', 'weight', 'reps', 'muscle', 'equipment'. "
                                "CRITICAL METRIC RULES: "
                                "- If a metric (weight or reps) is NOT explicitly stated for a specific exercise, you MUST output '-'. Do not guess or carry over numbers from previous exercises. "
                                "- If the exercise is bodyweight (like pushups, pullups, planche, handstands), set 'weight' strictly to '-'. "
                                "Do not include any markdown formatting, backticks, or extra text."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Extract workout achievements from this text: '{user_log_input}'"
                        }
                    ]
                    
                    try:
                        extraction_response = client.chat.completions.create(
                            model="meta-llama/Llama-3.1-8B-Instruct",
                            messages=extraction_messages,
                            max_tokens=400,
                            temperature=0.1 
                        )
                        
                        raw_output = extraction_response.choices[0].message.content
                        extracted_data = parse_json_output(raw_output, is_array=True)
                        
                        if not extracted_data:
                            st.error("JSON Parsing Error: The AI did not return a valid format. Please reword your log and try again.")
                        else:
                            updated_count = 0
                            added_count = 0
                            arsenal_added_count = 0
                            
                            current_date = datetime.now().strftime("%Y-%m-%d")
                            
                            existing_progress = [str(x) for x in st.session_state.progress_df['Exercise/Metric'].tolist()]
                            existing_arsenal = [str(x) for x in st.session_state.arsenal_df['Exercise Name'].tolist()]
                            
                            for item in extracted_data:
                                ex_name = str(item.get("name", "Unknown Exercise"))
                                ex_weight = str(item.get("weight", "-"))
                                ex_reps = str(item.get("reps", "-"))
                                ex_muscle = str(item.get("muscle", "Full Body"))
                                ex_equip = str(item.get("equipment", "None (Bodyweight)"))
                                
                                # Update Progress Table
                                close_matches_prog = difflib.get_close_matches(ex_name.lower(), [e.lower() for e in existing_progress], n=1, cutoff=0.75)
                                
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

                                # Update Arsenal Table
                                close_matches_ars = difflib.get_close_matches(ex_name.lower(), [e.lower() for e in existing_arsenal], n=1, cutoff=0.75)
                                
                                if not close_matches_ars:
                                    new_ars_row = pd.DataFrame([{"Exercise Name": ex_name, "Muscle Group/Day": ex_muscle, "Equipment Needed": ex_equip}])
                                    st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_ars_row], ignore_index=True)
                                    existing_arsenal.append(ex_name)
                                    arsenal_added_count += 1
                            
                            if updated_count > 0 or added_count > 0:
                                st.success(f"Log Synced. {added_count} progress added, {updated_count} updated. {arsenal_added_count} exercises auto-added to Arsenal.")
                                st.rerun()
                                
                    except Exception as e:
                        st.error(f"Extraction Error: {e}")

    st.divider()

    # --- PART B: THE EXERCISE ARSENAL ---
    st.subheader("Your Exercise Library")
    
    st.session_state.arsenal_df = st.data_editor(
        st.session_state.arsenal_df, 
        num_rows="dynamic", 
        use_container_width=True,
        key="arsenal_editor"
    )
    
    with st.expander("Manually Add New Exercise to Arsenal"):
        with st.form("add_exercise_form"):
            col1, col2 = st.columns(2)
            with col1:
                ex_name = st.text_input("Exercise Name")
                ex_muscle = st.text_input("Precise Target Muscle", placeholder="e.g., Upper Chest, Rear Delts, Biceps")
            with col2:
                ex_equip = st.selectbox("Equipment Needed", ["None (Bodyweight)", "Dumbbells", "Barbell", "Cables", "Court/Track"])
            
            submit_btn = st.form_submit_button("Add / Update Exercise")
            
            if submit_btn and ex_name:
                mask = (
                    (st.session_state.arsenal_df["Exercise Name"].astype(str).str.lower() == ex_name.lower()) &
                    (st.session_state.arsenal_df["Muscle Group/Day"] == ex_muscle) &
                    (st.session_state.arsenal_df["Equipment Needed"] == ex_equip)
                )
                if mask.any():
                    st.success(f"Exercise '{ex_name}' already exists in your arsenal.")
                else:
                    new_row = pd.DataFrame([{"Exercise Name": ex_name, "Muscle Group/Day": ex_muscle, "Equipment Needed": ex_equip}])
                    st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_row], ignore_index=True)
                    st.success(f"Successfully added '{ex_name}' to your arsenal.")
                st.rerun()


# ==========================================
# TAB 2: WORKOUT GENERATOR
# ==========================================
with tab2:
    st.subheader("Generate Custom Workout")
    st.markdown("The AI will evaluate your logged progress and natural language goals to prescribe a custom routine.")
    
    with st.form("hf_generator_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            target_group = st.text_input("What do you want to train today?", placeholder="e.g., Push day, basketball conditioning, upper body, handstand prep")
        with col_b:
            has_gym = st.radio("Gym Access Today?", ["Yes", "No (Bodyweight only)"])
            
        generate_btn = st.form_submit_button("Generate Routine")

    if generate_btn:
        if not client:
            st.error("Cannot call Hugging Face API without a valid HF_TOKEN.")
        elif not target_group:
            st.warning("Please specify a target focus.")
        elif st.session_state.arsenal_df.empty:
            st.warning("Your exercise arsenal is empty. Add exercises in the Progress & Arsenal tab first.")
        else:
            st.session_state.current_target_group = target_group
            
            with st.spinner("Analyzing progress history and generating routine..."):
                arsenal_csv = st.session_state.arsenal_df.to_csv(index=False)
                progress_csv = st.session_state.progress_df.to_csv(index=False) if not st.session_state.progress_df.empty else "No progress logged yet."
                
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert fitness coach and bio-mechanics specialist. "
                            "Analyze the user's natural language Target Focus and build a workout utilizing appropriate exercises from their provided arsenal. "
                            "CRITICAL INSTRUCTION: You MUST output a valid JSON object. Follow this exact JSON schema strictly: "
                            "{"
                            "\"routine_text\": \"String detailing the motivation, sets, reps, and intensity recommendations.\", "
                            "\"arsenal_exercises\": ["
                            "   {\"name\": \"Exercise from Arsenal CSV\", \"specific_target\": \"Precise muscle part (e.g., Upper Chest, Front Delts)\"}"
                            "], "
                            "\"recommended_exercises\": ["
                            "   {\"name\": \"Exact New Exercise Name 1\", \"muscle\": \"Precise Muscle Target\", \"equipment\": \"Equipment Needed\"},"
                            "   {\"name\": \"Exact New Exercise Name 2\", \"muscle\": \"Precise Muscle Target\", \"equipment\": \"Equipment Needed\"},"
                            "   {\"name\": \"Exact New Exercise Name 3\", \"muscle\": \"Precise Muscle Target\", \"equipment\": \"Equipment Needed\"},"
                            "   {\"name\": \"Exact New Exercise Name 4\", \"muscle\": \"Precise Muscle Target\", \"equipment\": \"Equipment Needed\"},"
                            "   {\"name\": \"Exact New Exercise Name 5\", \"muscle\": \"Precise Muscle Target\", \"equipment\": \"Equipment Needed\"}"
                            "]"
                            "}"
                            "CRITICAL RULES: "
                            "1. Match the semantic meaning of the Target Focus. If they ask for 'Push day', select chest, shoulders, and triceps exercises. "
                            "2. Select UP TO 4 exercises from the Arsenal. If there are only 1 or 2 matching exercises in the Arsenal, return ONLY those. Do NOT pad the list with unrelated exercises. "
                            "3. You MUST provide exactly 5 recommended exercises that target the chosen focus but are NOT in the Arsenal CSV. "
                            "4. For recommended_exercises 'name', provide ONLY the exact name of the exercise."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"""
                        Target Focus: {target_group}
                        Gym Access Available: {has_gym}
                        
                        User Progress History Records:
                        {progress_csv}
                        
                        Available Arsenal:
                        {arsenal_csv}
                        """
                    }
                ]
                
                try:
                    response = client.chat.completions.create(
                        model="meta-llama/Llama-3.1-8B-Instruct",
                        messages=messages,
                        max_tokens=1000,
                        temperature=0.4
                    )
                    
                    raw_output = response.choices[0].message.content
                    generated_data = parse_json_output(raw_output, is_array=False)
                    
                    if not generated_data:
                        st.error("JSON Parsing Error: The AI did not return a strict format. Please try generating again.")
                    else:
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
                        
                        st.success("Routine Generated. Navigate to the 'Active Session' tab to start tracking.")
                        
                except Exception as e:
                    st.error(f"API Error: {e}")
                    
    if st.session_state.generated_routine_text:
        st.markdown(st.session_state.generated_routine_text)


# ==========================================
# TAB 3: ACTIVE SESSION
# ==========================================
with tab3:
    st.subheader("Active Training Session")
    
    if not st.session_state.active_checklist and not st.session_state.recommended_exercises:
        st.info("No active routine. Use the AI Generator tab to create one.")
    else:
        col_tracker, col_routine = st.columns([1, 1], gap="large")
        
        with col_tracker:
            st.markdown("### Execution Checklist")
            st.caption("Check off your exercises as you complete them.")
            
            all_completed = True
            
            if not st.session_state.active_checklist:
                st.info("No exercises from Arsenal match your target.")
            else:
                for task in list(st.session_state.active_checklist.keys()):
                    is_checked = st.checkbox(task, value=st.session_state.active_checklist[task], key=f"chk_{task}")
                    st.session_state.active_checklist[task] = is_checked
                    if not is_checked:
                        all_completed = False

            if st.session_state.recommended_exercises:
                st.divider()
                st.markdown("#### Discover & Add Recommendations")
                st.caption("Click + to add a recommendation directly to your Arsenal and Active Checklist.")
                
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
                            new_row = pd.DataFrame([{
                                "Exercise Name": rec_name,
                                "Muscle Group/Day": rec_muscle,
                                "Equipment Needed": rec_equip
                            }])
                            st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_row], ignore_index=True)
                        
                        st.session_state.recommended_exercises.pop(idx)
                        st.rerun()

            st.divider()
            
            if all_completed and len(st.session_state.active_checklist) > 0:
                st.success("All exercises completed. Excellent work.")
                if st.button("Mark Workout as Done"):
                    new_prog_row = pd.DataFrame([{
                        "Date": datetime.now().strftime("%Y-%m-%d"),
                        "Exercise/Metric": "Daily Workout Completed",
                        "Weight": "-",
                        "Reps": "1",
                        "Notes": "Routine finished via Active Session."
                    }])
                    st.session_state.progress_df = pd.concat([st.session_state.progress_df, new_prog_row], ignore_index=True)
                    st.session_state.active_checklist = {}
                    st.session_state.generated_routine_text = ""
                    st.session_state.specific_targets = {}
                    st.session_state.recommended_exercises = []
                    st.success("Progress saved. Your active streak has been updated.")
                    st.rerun()

        with col_routine:
            st.markdown("### Suggested Plan Details")
            st.markdown(st.session_state.generated_routine_text)
            
            st.divider()
            st.markdown("#### Targeted Muscles (Active Checklist)")
            
            if st.session_state.active_checklist:
                for task in st.session_state.active_checklist.keys():
                    spec_target = st.session_state.specific_targets.get(task, st.session_state.current_target_group)
                    st.markdown(f"**{task}:** <span class='muscle-tag'>{spec_target}</span>", unsafe_allow_html=True)
            else:
                st.caption("No exercises in active checklist.")


# ==========================================
# TAB 4: STREAKS & GOALS
# ==========================================
with tab4:
    st.markdown("<div style='display: flex; justify-content: flex-end; margin-bottom: 20px;'>", unsafe_allow_html=True)
    if st.button("Quick Log: Mark Today as Complete"):
        new_prog_row = pd.DataFrame([{
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Exercise/Metric": "Daily Workout Completed",
            "Weight": "-",
            "Reps": "1",
            "Notes": "Quick Log."
        }])
        st.session_state.progress_df = pd.concat([st.session_state.progress_df, new_prog_row], ignore_index=True)
        st.success("Today marked as complete.")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    col_streak, col_goals = st.columns([3, 2], gap="large")
    
    # --- CALENDAR STREAK ---
    with col_streak:
        st.subheader("Monthly Consistency")
        
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
            <div style="display: flex; align-items: center; gap: 10px; margin-top: 10px; margin-bottom: 5px;">
                <svg viewBox="0 0 24 24" width="42" height="42" fill="#b5b0d4" style="filter: drop-shadow(0px 0px 8px #b5b0d4);">
                    <path d="M12 2C12 2 7 7 7 13C7 15.76 9.24 18 12 18C14.76 18 17 15.76 17 13C17 7 12 2 12 2ZM12 16C10.9 16 10 15.1 10 14C10 12.9 12 10 12 10C12 10 14 11.9 14 14C14 15.1 13.1 16 12 16Z"/>
                </svg>
                <h2 style="color: #b5b0d4; text-shadow: 0 0 10px #b5b0d4, 0 0 20px #8c8c9e; font-weight: 900; margin: 0;">
                    {current_streak} DAYS
                </h2>
            </div>
            """
        else:
            streak_html = f"""
            <div style="display: flex; align-items: center; gap: 10px; margin-top: 10px; margin-bottom: 5px;">
                <svg viewBox="0 0 24 24" width="42" height="42" fill="#2a2a3b">
                    <path d="M12 2C12 2 7 7 7 13C7 15.76 9.24 18 12 18C14.76 18 17 15.76 17 13C17 7 12 2 12 2ZM12 16C10.9 16 10 15.1 10 14C10 12.9 12 10 12 10C12 10 14 11.9 14 14C14 15.1 13.1 16 12 16Z"/>
                </svg>
                <h2 style="color: #4d4d6b; font-weight: 900; margin: 0;">
                    {current_streak} DAYS
                </h2>
            </div>
            """
            
        st.markdown(streak_html, unsafe_allow_html=True)
        st.caption("Your streak increments only when you Mark a Workout as Done.")
        st.write("")
        
        today = datetime.now()
        cal = calendar.monthcalendar(today.year, today.month)
        month_name = calendar.month_name[today.month]
        
        st.markdown(f"#### {month_name} {today.year}")

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        
        header_cols = st.columns(7)
        for i, d_name in enumerate(day_names):
            header_cols[i].markdown(f"<div style='text-align: center; font-weight: bold; color: #b5b0d4; margin-bottom: 10px;'>{d_name}</div>", unsafe_allow_html=True)
            
        for week in cal:
            week_cols = st.columns(7)
            for i, day in enumerate(week):
                if day == 0:
                    week_cols[i].write("")
                else:
                    current_date = datetime(today.year, today.month, day).date()
                    
                    if current_date in workout_dates:
                        week_cols[i].markdown(f"<div style='text-align: center; background-color: #2a2a3b; border: 1px solid #b5b0d4; color: #b5b0d4; border-radius: 6px; padding: 12px; margin-bottom: 5px;'><b>{day}</b><br>Done</div>", unsafe_allow_html=True)
                    elif current_date == today.date():
                        week_cols[i].markdown(f"<div style='text-align: center; background-color: #b5b0d4; color: #1a1a24; border-radius: 6px; padding: 12px; margin-bottom: 5px;'><b>{day}</b><br>Today</div>", unsafe_allow_html=True)
                    else:
                        week_cols[i].markdown(f"<div style='text-align: center; background-color: #1a1a24; border: 1px solid #4d4d6b; border-radius: 6px; padding: 12px; margin-bottom: 5px; color: #8c8c9e;'>{day}</div>", unsafe_allow_html=True)

    # --- GOALS MANAGEMENT ---
    with col_goals:
        st.subheader("Active Goals")
        
        with st.form("add_goal_form"):
            col_g1, col_g2, col_g3 = st.columns([2, 1, 1])
            with col_g1:
                new_goal_ex = st.text_input("Exercise", placeholder="e.g., deadlift")
            with col_g2:
                new_goal_metric = st.selectbox("Target Type", ["Weight", "Reps"])
            with col_g3:
                new_goal_val = st.number_input("Target Value", min_value=1.0, value=50.0)
                
            if st.form_submit_button("Add Target"):
                if new_goal_ex:
                    st.session_state.user_goals = [g for g in st.session_state.user_goals if isinstance(g, dict)]
                    st.session_state.user_goals.append({
                        "exercise": new_goal_ex.strip(),
                        "metric": new_goal_metric,
                        "target": new_goal_val
                    })
                    st.rerun()
                    
        st.divider()
        
        if not st.session_state.user_goals:
            st.info("No active goals. Set a target above to get started.")
        else:
            st.session_state.user_goals = [g for g in st.session_state.user_goals if isinstance(g, dict)]
            for i, goal in enumerate(st.session_state.user_goals):
                g_col1, g_col2 = st.columns([4, 1])
                g_col1.markdown(f"**{i+1}. {goal['exercise'].title()}** | Target: {goal['target']} {goal['metric']}")
                
                if g_col2.button("Delete", key=f"del_goal_{i}"):
                    st.session_state.user_goals.pop(i)
                    st.rerun()