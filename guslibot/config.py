import os
import json

from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
DBNAME = os.getenv("DBNAME")
STORAGE_LOCATION = os.getenv("STORAGE_LOCATION")

