"""
Privacy Policy Analyzer
-----------------------
A beginner-friendly Streamlit app that sends a pasted privacy policy
to Google Gemini and shows a plain-English analysis.
"""

# --- Imports ---
# os: read environment variables (like the API key)
# pathlib.Path: build a file path that works on any computer
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types


# --- Page setup ---
# This must run before other Streamlit commands.
# page_title is the text in the browser tab.
st.set_page_config(
    page_title="Privacy Policy Analyzer",
    page_icon="🔒",
    layout="centered",
)


# --- Load the API key ---
# load_dotenv() reads a local .env file into environment variables.
# We never print the key. If .env is missing (typical on Streamlit Cloud),
# we fall back to st.secrets.
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    # st.secrets looks for .streamlit/secrets.toml during deployment.
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = None


# --- Load the system prompt ---
# Path(__file__).parent is the folder that contains this app.py file.
# That way we always find prompt.txt, even if you run the app from another folder.
prompt_path = Path(__file__).parent / "prompt.txt"
try:
    system_instruction = prompt_path.read_text(encoding="utf-8")
except FileNotFoundError:
    system_instruction = ""
    st.error("Could not find prompt.txt. Make sure it is in the same folder as app.py.")


# --- Helper: send the policy to Gemini ---
def analyze_policy(policy_text: str) -> str:
    """Call Gemini with the system prompt and the user's privacy policy text."""
    # Create a client that authenticates with our API key.
    client = genai.Client(api_key=api_key)

    # generate_content sends the request.
    # system_instruction tells the model HOW to answer (from prompt.txt).
    # contents is the privacy policy the user pasted.
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=policy_text,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
        ),
    )

    # response.text is the model's answer as a string.
    return response.text


# --- Sidebar disclaimer ---
with st.sidebar:
    st.header("Disclaimer")
    st.write(
        "This tool is **not legal advice**. It is an automated summary "
        "meant for learning and general understanding only."
    )
    st.write(
        "Do **not** paste confidential information, internal drafts, "
        "or documents you are not allowed to share."
    )


# --- Main page ---
st.title("Privacy Policy Analyzer")
st.write(
    "Paste a privacy policy below and click **Analyze**. "
    "The app will explain, in plain English, what data is collected, "
    "who it is shared with, and what rights you may have."
)

# A large box so long policies are easy to paste.
policy_text = st.text_area(
    "Privacy policy text",
    height=300,
    placeholder="Paste the full privacy policy here...",
)

# The button that starts the analysis.
if st.button("Analyze", type="primary"):
    # Remove extra spaces at the start/end so a box of only spaces counts as empty.
    cleaned_text = policy_text.strip()

    if not api_key:
        st.error(
            "No API key found. Add GEMINI_API_KEY to your .env file locally, "
            "or to Streamlit secrets when deploying."
        )
    elif not system_instruction:
        st.error("The system prompt could not be loaded, so analysis cannot run.")
    elif not cleaned_text:
        st.warning("Please paste a privacy policy into the text box first.")
    elif len(cleaned_text) < 500:
        # Short text like "TikTok privacy policy" is not a real policy.
        # Skip the API so the model cannot fill in from general knowledge.
        st.warning(
            "Please paste the full text of a privacy policy. "
            "A name, link, or short summary is not enough to analyze."
        )
    elif len(cleaned_text) > 100_000:
        st.error(
            "That text is over 100,000 characters. Please paste a shorter excerpt."
        )
    else:
        # st.spinner shows a waiting message until the code inside finishes.
        try:
            with st.spinner("Analyzing the privacy policy..."):
                analysis = analyze_policy(cleaned_text)
            # Render Gemini's structured answer as Markdown (headings, bullets, etc.).
            st.markdown(analysis)
        except Exception:
            # Catch API / network problems so the app does not crash.
            st.error(
                "Something went wrong while contacting the analysis service. "
                "Please try again in a moment. If it keeps failing, check your "
                "API key and internet connection."
            )
