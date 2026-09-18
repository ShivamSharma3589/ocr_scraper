import os
from dotenv import load_dotenv

load_dotenv()

SERP_API_KEY=os.getenv("SERP_API_KEY", "YOUR_DEFAULT_API_KEY")