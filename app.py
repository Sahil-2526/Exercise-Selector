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