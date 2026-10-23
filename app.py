"""
Privacy Policy Analyzer
-----------------------
A beginner-friendly Streamlit app that sends a pasted privacy policy
to Google Gemini and shows a plain-English analysis.
"""

# --- Imports ---
# os: read environment variables (like the API key)
# pathlib.Path: build a file path that works on any computer
# time: pause between retries when Gemini is busy
import os
import time
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


# Main model, then a lighter Flash-Lite backup if the main one stays busy.
PRIMARY_MODEL = "gemini-flash-latest"
BACKUP_MODEL = "gemini-flash-lite-latest"
# Wait 2s, then 4s, then 8s before each of the 3 retries.
RETRY_WAITS_SECONDS = [2, 4, 8]


def is_unavailable_error(err: Exception) -> bool:
    """Return True if Gemini reported HTTP 503 / UNAVAILABLE (high demand)."""
    code = getattr(err, "code", None)
    status = str(getattr(err, "status", "") or "").upper()
    text = str(err).upper()
    if code == 503 or status == "UNAVAILABLE":
        return True
    return "503" in text and ("UNAVAILABLE" in text or "HIGH DEMAND" in text)


# --- Helper: stream the Gemini answer in pieces ---
def analyze_policy_stream(policy_text: str, model_name: str):
    """Yield chunks of Gemini's answer as they arrive.

    A generator (this function uses `yield`) hands back one piece at a time
    instead of waiting for the full response. Streamlit can show each piece
    on screen immediately.
    """
    # Create a client that authenticates with our API key.
    client = genai.Client(api_key=api_key)

    # generate_content_stream is like generate_content, but it returns
    # an iterator of chunks instead of one finished answer.
    stream = client.models.generate_content_stream(
        model=model_name,
        contents=policy_text,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
        ),
    )

    # Each chunk may or may not contain text. Skip empty ones.
    for chunk in stream:
        piece = chunk.text
        if piece:
            yield piece


def stream_analysis(policy_text: str) -> None:
    """Stream the analysis, retrying on 503, then trying Flash-Lite once.

    Raises the last error if every attempt fails, so the caller can show
    the right on-screen message.
    """
    last_error = None

    # 1 first try + 3 retries (waits of 2, 4, then 8 seconds).
    for attempt in range(1 + len(RETRY_WAITS_SECONDS)):
        try:
            st.write_stream(analyze_policy_stream(policy_text, PRIMARY_MODEL))
            return
        except Exception as err:
            print(type(err).__name__, err)
            if not is_unavailable_error(err):
                raise
            last_error = err
            # After the last retry, stop waiting and try the backup model.
            if attempt >= len(RETRY_WAITS_SECONDS):
                break
            wait_seconds = RETRY_WAITS_SECONDS[attempt]
            with st.spinner(
                f"The AI service is busy. Retrying in {wait_seconds} seconds..."
            ):
                time.sleep(wait_seconds)

    # One extra try with the lighter free-tier Flash-Lite model.
    try:
        st.write_stream(analyze_policy_stream(policy_text, BACKUP_MODEL))
    except Exception as err:
        print(type(err).__name__, err)
        if last_error is not None and is_unavailable_error(err):
            raise last_error from err
        raise


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
        # Stream the answer so headings and bullets appear as they are generated.
        try:
            stream_analysis(cleaned_text)
        except Exception as err:
            # Catch API / network problems so the app does not crash.
            # Print the real error in the terminal only (never the API key).
            print(type(err).__name__, err)
            if is_unavailable_error(err):
                st.error(
                    "The AI service is busy right now. Please try again in a minute."
                )
            else:
                st.error(
                    "Something went wrong while contacting the analysis service. "
                    "Please try again in a moment. If it keeps failing, check your "
                    "API key and internet connection."
                )
