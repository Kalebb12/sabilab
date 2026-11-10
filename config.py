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

# OpenAI-compatible LLM settings
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", LLM_MODEL)
LLM_MODEL_SCORING = os.getenv("LLM_MODEL_SCORING", LLM_MODEL)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
FALLBACK_BASE_URL = os.getenv("FALLBACK_BASE_URL", "")
FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

# Prompt versions
PROMPT_VERSION_READING = "v0.2"
PROMPT_VERSION_SCORING = "v0.2"
RUBRIC_VERSION = "v0.2"

# Reviewer password (server-side only, never sent to browser)
REVIEW_PASSWORD = os.getenv("REVIEW_PASSWORD", "")

# Message constraints and rate limit
MESSAGE_MAX_CHARS = 500
MESSAGE_RATE_LIMIT_SECONDS = 1.0

# USD per million tokens; unknown models are treated as free/undetermined.
LLM_MODEL_PRICES_PER_M = {
    "llama-3.3-70b-versatile": (0.59, 0.79),
}

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
