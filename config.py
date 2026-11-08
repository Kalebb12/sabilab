"""Configuration settings for SabiLab."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = BASE_DIR / "scenarios"
DB_PATH = BASE_DIR / "sabilab.db"
STATIC_DIR = BASE_DIR / "static"

# Gemini API settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_PERSONA = "gemini-2.5-flash"
GEMINI_MODEL_SCORING = "gemini-2.5-pro"
GEMINI_API_BASE_URL = os.getenv("GEMINI_API_BASE_URL", "")

# Prompt versions
PROMPT_VERSION_READING = "v0.2"
PROMPT_VERSION_SCORING = "v0.2"
RUBRIC_VERSION = "v0.2"

# Session timing (in seconds)
TIMING_REAL = {
    "brief": 180,
    "huddle": 900,
    "twist_ratio": 0.5,
    "task": 300,
}

TIMING_DEMO = {
    "brief": 30,
    "huddle": 90,
    "twist_ratio": 0.5,
    "task": 60,
}
