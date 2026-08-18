import streamlit as st
import pandas as pd
import os
import json
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

if 'recommended_exercise' not in st.session_state:
    st.session_state.recommended_exercise = None

if 'recommended_added' not in st.session_state:
    st.session_state.recommended_added = False

st.title("Dynamic Workout Generator")
st.markdown("<div class='motivational-quote'>Surpass your limits. Master the fundamentals. Build the handstand, perfect the shot, trust the routine.</div>", unsafe_allow_html=True)

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
                                "1. Muscle Group (Choose ONE: Chest, Back, Legs, Shoulders, Core, Full Body) "
                                "2. Equipment (Choose ONE: None (Bodyweight), Dumbbells, Barbell, Cables, Court/Track, Machine) "
                                "OUTPUT FORMAT: You must respond ONLY with a valid JSON array containing objects. "
                                "Each object must use these exact keys: 'name', 'weight', 'reps', 'muscle', 'equipment'. "
                                "CRITICAL METRIC RULES: "
                                "- If the exercise is bodyweight (like pushups, pullups, planche, handstands), set 'weight' strictly to '-'. "
                                "- If reps are not mentioned but weight is, set 'reps' to '-'. "
                                "- If time/hold is mentioned instead of reps, place that in the 'reps' key. "
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
                        
                        raw_output = extraction_response.choices[0].message.content.strip()
                        
                        if raw_output.startswith("```json"):
                            raw_output = raw_output[7:-3].strip()
                        elif raw_output.startswith("```"):
                            raw_output = raw_output[3:-3].strip()
                            
                        extracted_data = json.loads(raw_output)
                        
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
                            close_matches_prog = difflib.get_close_matches(
                                ex_name.lower(), 
                                [e.lower() for e in existing_progress], 
                                n=1, 
                                cutoff=0.75
                            )
                            
                            if close_matches_prog:
                                matched_ex = close_matches_prog[0]
                                match_idx = st.session_state.progress_df[
                                    st.session_state.progress_df['Exercise/Metric'].astype(str).str.lower() == matched_ex.lower()
                                ].index
                                
                                idx = match_idx[0]
                                st.session_state.progress_df.at[idx, 'Date'] = current_date
                                st.session_state.progress_df.at[idx, 'Weight'] = ex_weight
                                st.session_state.progress_df.at[idx, 'Reps'] = ex_reps
                                updated_count += 1
                            else:
                                new_prog_row = pd.DataFrame([{
                                    "Date": current_date,
                                    "Exercise/Metric": ex_name,
                                    "Weight": ex_weight,
                                    "Reps": ex_reps
                                }])
                                st.session_state.progress_df = pd.concat([st.session_state.progress_df, new_prog_row], ignore_index=True)
                                added_count += 1

                            # Update Arsenal Table
                            close_matches_ars = difflib.get_close_matches(
                                ex_name.lower(), 
                                [e.lower() for e in existing_arsenal], 
                                n=1, 
                                cutoff=0.75
                            )
                            
                            if not close_matches_ars:
                                new_ars_row = pd.DataFrame({
                                    "Exercise Name": [ex_name], 
                                    "Muscle Group/Day": [ex_muscle], 
                                    "Equipment Needed": [ex_equip]
                                })
                                st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_ars_row], ignore_index=True)
                                existing_arsenal.append(ex_name)
                                arsenal_added_count += 1
                        
                        if updated_count > 0 or added_count > 0:
                            st.success(f"Log Synced! ({added_count} progress added, {updated_count} updated. {arsenal_added_count} exercises auto-added to Arsenal.)")
                            st.rerun()
                        else:
                            st.info("AI couldn't extract valid data. Please try again.")
                            
                    except json.JSONDecodeError as je:
                        st.error(f"JSON Parsing Error: The AI did not return a strict format. Try rewording your log. Details: {je}")
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
                ex_muscle = st.selectbox("Muscle Group/Day", ["Chest", "Back", "Legs", "Shoulders", "Core", "Full Body"])
            
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
                    new_row = pd.DataFrame({
                        "Exercise Name": [ex_name], 
                        "Muscle Group/Day": [ex_muscle], 
                        "Equipment Needed": [ex_equip]
                    })
                    st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_row], ignore_index=True)
                    st.success(f"Successfully added '{ex_name}' to your arsenal!")
                
                st.rerun()


# ==========================================
# TAB 2: WORKOUT GENERATOR
# ==========================================
with tab2:
    st.subheader("Generate Custom Workout")
    st.markdown("The AI will evaluate your logged progress to prescribe custom sets and intensity.")
    
    with st.form("hf_generator_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            target_group = st.selectbox("Target Muscle / Focus", ["Chest", "Back", "Legs", "Shoulders", "Core", "Full Body"])
        with col_b:
            has_gym = st.radio("Gym Access Today?", ["Yes", "No (Bodyweight only)"])
            
        generate_btn = st.form_submit_button("Generate Routine")

    if generate_btn:
        if not client:
            st.error("Cannot call Hugging Face API without a valid HF_TOKEN.")
        elif st.session_state.arsenal_df.empty:
            st.warning("Your exercise arsenal is empty. Add exercises in the Progress & Arsenal tab first.")
        else:
            with st.spinner("Analyzing progress history and generating routine..."):
                arsenal_csv = st.session_state.arsenal_df.to_csv(index=False)
                progress_csv = st.session_state.progress_df.to_csv(index=False) if not st.session_state.progress_df.empty else "No progress logged yet."
                
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert fitness coach and bio-mechanics specialist. "
                            "Analyze the user's stored progress history data table to evaluate their strength levels, "
                            "and build a workout strictly utilizing exercises from their provided arsenal. "
                            "Determine the exact number of sets, reps, and intensity for each exercise. "
                            "CRITICAL INSTRUCTION: You MUST output a valid JSON object. Do NOT wrap in markdown blocks. "
                            "Follow this exact JSON schema: "
                            "{"
                            "\"routine_text\": \"String detailing the motivation, sets, reps, and intensity recommendations.\", "
                            "\"arsenal_exercises\": [\"Array of 3-4 exercise names selected strictly from the Arsenal CSV\"], "
                            "\"recommended_exercise\": {"
                            "\"name\": \"Name of 1 new exercise NOT in the Arsenal\", "
                            "\"muscle\": \"Primary Muscle Group\", "
                            "\"equipment\": \"Equipment Needed\""
                            "}"
                            "}"
                        )
                    },
                    {
                        "role": "user",
                        "content": f"""
                        Target Focus: {target_group}
                        Gym Access Available: {has_gym}
                        
                        User Progress History Records (CSV):
                        {progress_csv}
                        
                        Available Arsenal (CSV):
                        {arsenal_csv}
                        """
                    }
                ]
                
                try:
                    response = client.chat.completions.create(
                        model="meta-llama/Llama-3.1-8B-Instruct",
                        messages=messages,
                        max_tokens=800,
                        temperature=0.7
                    )
                    
                    raw_output = response.choices[0].message.content.strip()
                    
                    if raw_output.startswith("```json"):
                        raw_output = raw_output[7:-3].strip()
                    elif raw_output.startswith("```"):
                        raw_output = raw_output[3:-3].strip()
                        
                    generated_data = json.loads(raw_output)
                    
                    st.session_state.generated_routine_text = generated_data.get("routine_text", "Workout routine generated.")
                    
                    st.session_state.active_checklist = {}
                    for ex in generated_data.get("arsenal_exercises", []):
                        st.session_state.active_checklist[ex] = False
                        
                    st.session_state.recommended_exercise = generated_data.get("recommended_exercise", None)
                    st.session_state.recommended_added = False
                    
                    st.success("Routine Generated! Navigate to the 'Active Session' tab to start tracking.")
                    
                except json.JSONDecodeError as je:
                    st.error("AI output parsing failed. The model did not return strict JSON. Please try generating again.")
                except Exception as e:
                    st.error(f"API Error: {e}")
                    
    if st.session_state.generated_routine_text:
        st.markdown(st.session_state.generated_routine_text)


# ==========================================
# TAB 3: ACTIVE SESSION
# ==========================================
with tab3:
    st.subheader("Active Training Session")
    
    if not st.session_state.active_checklist and not st.session_state.recommended_exercise:
        st.info("No active routine. Use the AI Generator tab to create one.")
    else:
        col_tracker, col_routine = st.columns([1, 1], gap="large")
        
        with col_tracker:
            st.markdown("### Execution Checklist")
            st.caption("Check off your exercises as you complete them.")
            
            all_completed = True
            
            # Display Arsenal Exercises Checkboxes
            for task in list(st.session_state.active_checklist.keys()):
                is_checked = st.checkbox(task, value=st.session_state.active_checklist[task], key=f"chk_{task}")
                st.session_state.active_checklist[task] = is_checked
                if not is_checked:
                    all_completed = False

            # Display Recommended Exercise
            if st.session_state.recommended_exercise:
                rec = st.session_state.recommended_exercise
                rec_name = rec.get("name", "Unknown Recommended Exercise")
                
                st.divider()
                st.markdown("#### Recommended Addition")
                
                if not st.session_state.recommended_added:
                    rec_col1, rec_col2 = st.columns([4, 1])
                    rec_col1.markdown(f"**{rec_name}**")
                    if rec_col2.button("+", key="add_rec_btn"):
                        # Add to active checklist
                        st.session_state.active_checklist[rec_name] = False
                        st.session_state.recommended_added = True
                        
                        # Insert into Arsenal if missing
                        existing_arsenal = [str(x).lower() for x in st.session_state.arsenal_df['Exercise Name'].tolist()]
                        if rec_name.lower() not in existing_arsenal:
                            new_row = pd.DataFrame([{
                                "Exercise Name": rec_name,
                                "Muscle Group/Day": rec.get("muscle", "Full Body"),
                                "Equipment Needed": rec.get("equipment", "None (Bodyweight)")
                            }])
                            st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_row], ignore_index=True)
                            
                        st.rerun()
                    
                    # If recommended isn't added, it doesn't count against completion, but we show it.
                else:
                    # It was added, so it renders in the loop above. But if we need to ensure it's tracked:
                    pass

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
                    st.session_state.recommended_exercise = None
                    st.session_state.recommended_added = False
                    st.success("Progress saved. Your active streak has been updated.")
                    st.rerun()

        with col_routine:
            st.markdown("### Suggested Plan Details")
            st.markdown(st.session_state.generated_routine_text)


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
            workout_dates = sorted(pd.to_datetime(st.session_state.progress_df["Date"]).dt.date.unique(), reverse=True)
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
        st.caption("Your streak stays active as long as you log a workout today or yesterday.")
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
            new_goal = st.text_input("Define a new goal", placeholder="e.g., Target 50 pushups")
            if st.form_submit_button("Add Target"):
                if new_goal:
                    st.session_state.user_goals.append(new_goal)
                    st.rerun()
                    
        st.divider()
        
        if not st.session_state.user_goals:
            st.info("No active goals. Set a target above to get started.")
        else:
            for i, goal in enumerate(st.session_state.user_goals):
                g_col1, g_col2 = st.columns([4, 1])
                g_col1.markdown(f"**{i+1}.** {goal}")
                
                if g_col2.button("Delete", key=f"del_goal_{i}"):
                    st.session_state.user_goals.pop(i)
                    st.rerun()