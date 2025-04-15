import os
from pathlib import Path

# Configuration
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_NIM_API_URL = "http://localhost:8003/v1/infer"
DEFAULT_RESULTS_DIR = Path(__file__).parent / Path("results")
DB_PATH = "data.duckdb"
