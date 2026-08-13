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

st.title("Dynamic Workout Generator")

# --- MAIN LAYOUT TABS ---
tab1, tab2 = st.tabs(["Manage Arsenal", "Get Workout"])

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
    
    with st.form("hf_generator_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            target_group = st.selectbox("Target Muscle / Focus", ["Chest", "Back", "Legs", "Shoulders", "Core", "Full Body"])
        with col_b:
            has_gym = st.radio("Gym Access Today?", ["Yes", "No (Bodyweight only)"])
            
        progress_text = st.text_area(
            "Describe your current progression (e.g., 'Can hold tuck planche for 5s, 15 pushups easy')."
        )
        
        generate_btn = st.form_submit_button(" Generate Routine")

    if generate_btn:
        if not client:
            st.error("Cannot call Hugging Face API without a valid HF_TOKEN.")
        elif st.session_state.arsenal_df.empty:
            st.warning("Your exercise arsenal is empty! Please add some exercises in the 'Manage Arsenal' tab first.")
        elif not progress_text:
            st.warning("Please provide your current progress/level notes.")
        else:
            with st.spinner("Processing with Hugging Face Inference API..."):
                arsenal_csv = st.session_state.arsenal_df.to_csv(index=False)
                
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert fitness coach and bio-mechanics specialist. "
                            "Analyze the user's strength level from their progress notes, "
                            "and build a workout strictly utilizing exercises from their provided arsenal."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"""
                        Target Focus: {target_group}
                        Gym Access Available: {has_gym}
                        User Progress: "{progress_text}"
                        
                        Available Arsenal (CSV):
                        {arsenal_csv}
                        
                        Instructions:
                        1. Select 3-4 exercises from the Arsenal matching the target focus.
                        2. Prescribe exact sets and reps scaled to their current progress.
                        3. Provide 1 recommended addition (not in arsenal) with brief benefits.
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
                    
                    st.success("Routine Generated!")
                    st.markdown(response.choices[0].message.content)
                    
                except Exception as e:
                    st.error(f"API Error: {e}")