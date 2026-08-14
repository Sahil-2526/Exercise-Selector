import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

# --- API INITIALIZATION ---
hf_token = os.environ.get("HF_TOKEN")
if hf_token:
    client = InferenceClient(token=hf_token)
else:
    st.warning("HF_TOKEN not found in environment variables or .env file.")
    client = None

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="AI Workout Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- SESSION STATE INITIALIZATION ---
if 'arsenal_df' not in st.session_state:
    st.session_state.arsenal_df = pd.DataFrame(
        columns=["Exercise Name", "Muscle Group/Day", "Equipment Needed", "Difficulty"]
    )

if 'progress_df' not in st.session_state:
    st.session_state.progress_df = pd.DataFrame(
        columns=["Exercise/Metric", "Value/Record", "Notes"]
    )

st.title("Dynamic Workout Generator")

# --- MAIN LAYOUT TABS ---
tab1, tab2, tab3 = st.tabs(["Manage Arsenal", "Get Workout", "Progress"])

# TAB 1: THE EXERCISE ARSENAL
with tab1:
    st.subheader("Your Exercise Library")
    st.markdown("Add your exercises using the form below or edit them directly in the table.")
    
    st.session_state.arsenal_df = st.data_editor(
        st.session_state.arsenal_df, 
        num_rows="dynamic", 
        use_container_width=True,
        key="arsenal_editor",
        disabled = True
    )
    
    st.divider()
    
    with st.expander("Add New Exercise to Arsenal"):
        with st.form("add_exercise_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                ex_name = st.text_input("Exercise Name")
                ex_muscle = st.selectbox("Muscle Group/Day", ["Chest", "Back", "Legs", "Shoulders", "Biceps", "Core", "Full Body"])
            
            with col2:
                ex_equip = st.selectbox("Equipment Needed", ["None (Bodyweight)", "Dumbbells", "Barbell", "Cables", "Court/Track"])
                ex_diff = st.selectbox("Difficulty", ["Beginner", "Intermediate", "Advanced"])
            
            submit_btn = st.form_submit_button("Add Exercise")
            
            if submit_btn and ex_name:
                new_row = pd.DataFrame({
                    "Exercise Name": [ex_name], 
                    "Muscle Group/Day": [ex_muscle], 
                    "Equipment Needed": [ex_equip], 
                    "Difficulty": [ex_diff]
                })
                st.session_state.arsenal_df = pd.concat([st.session_state.arsenal_df, new_row], ignore_index=True)
                st.success(f"Successfully added '{ex_name}' to your arsenal!")
                st.rerun()

# TAB 2: EXERCISE SELECTOR AND RECOMMENDATION
with tab2:
    st.subheader("Generate Custom Workout")
    st.markdown("The AI will automatically evaluate your logged progress records from Tab 3 to prescribe custom sets and intensity.")
    
    with st.form("hf_generator_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            target_group = st.selectbox("Target Muscle / Focus", ["Chest", "Back", "Legs", "Shoulders", "Core", "Full Body"])
        with col_b:
            has_gym = st.radio("Gym Access Today?", ["Yes", "No (Bodyweight only)"])
            
        generate_btn = st.form_submit_button("⚡ Generate Routine based on Progress History")

    if generate_btn:
        if not client:
            st.error("Cannot call Hugging Face API without a valid HF_TOKEN.")
        elif st.session_state.arsenal_df.empty:
            st.warning("Your exercise arsenal is empty! Please add some exercises in the 'Manage Arsenal' tab first.")
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
                            "Determine the exact number of sets, reps, and intensity for each exercise based on their recorded progress metrics."
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
                        
                        Instructions:
                        1. Review the user's progress records to deduce their baseline strength and max capabilities.
                        2. Select 3-4 exercises from the Arsenal matching the target focus.
                        3. Prescribe exact sets, reps/hold-times, and intensity tailored specifically to their stored progress values.
                        4. Provide 1 recommended addition (not in arsenal) with brief benefits.
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
                    
                    st.success("Routine Generated based on your Stored Progress!")
                    st.markdown(response.choices[0].message.content)
                    
                except Exception as e:
                    st.error(f"API Error: {e}")

# TAB 3: PROGRESS TRACKER
with tab3:
    st.subheader("Your Progress Log")
    st.markdown("Log your performance in plain text (e.g., 'I can do 40 pushups' or 'hit 100kg deadlift'). AI will extract and log it.")
    
    st.session_state.progress_df = st.data_editor(
        st.session_state.progress_df,
        num_rows="dynamic",
        use_container_width=True,
        key="progress_editor"
    )
    
    st.divider()
    
    with st.form("progress_extraction_form"):
        user_log_input = st.text_area("Log update (Natural Language)", placeholder="e.g., I did 40 pushups today and managed a 100kg deadlift.")
        extract_btn = st.form_submit_button("Extract & Add to Progress Table")
        
        if extract_btn:
            if not client:
                st.error("Cannot call Hugging Face API without a valid HF_TOKEN.")
            elif not user_log_input:
                st.warning("Please enter your performance log.")
            else:
                with st.spinner("Extracting metrics with AI..."):
                    extraction_messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are a data extraction assistant. Extract exercise names and their numeric values/counts/weights "
                                "from the user input. Return ONLY rows in a comma-separated format: "
                                "Exercise Name, Value/Record, Short Note. Do not include markdown code blocks or conversational filler."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Extract workout achievements from this text: '{user_log_input}'."
                        }
                    ]
                    
                    try:
                        extraction_response = client.chat.completions.create(
                            model="meta-llama/Llama-3.1-8B-Instruct",
                            messages=extraction_messages,
                            max_tokens=200,
                            temperature=0.1
                        )
                        
                        raw_output = extraction_response.choices[0].message.content.strip()
                        raw_output = raw_output.replace("```", "").replace("csv", "").strip()
                        
                        lines = raw_output.split('\n')
                        new_rows = []
                        for line in lines:
                            parts = [p.strip() for p in line.split(',')]
                            if len(parts) >= 2:
                                new_rows.append({
                                    "Exercise/Metric": parts[0],
                                    "Value/Record": parts[1],
                                    "Notes": parts[2] if len(parts) > 2 else user_log_input
                                })
                        
                        if new_rows:
                            new_df = pd.DataFrame(new_rows)
                            st.session_state.progress_df = pd.concat([st.session_state.progress_df, new_df], ignore_index=True)
                            st.success("Progress extracted and logged successfully!")
                            st.rerun()
                        else:
                            st.info("AI processed the text, but couldn't parse structured rows automatically. You can add them manually above.")
                            
                    except Exception as e:
                        st.error(f"Extraction Error: {e}")