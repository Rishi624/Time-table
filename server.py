import http.server
import socketserver
import json
import threading
import time
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, timedelta
import os


PORT = int(os.environ.get("PORT", 8080))
DATA_FILE = "student_data.json"

# --- SECURE PASSWORD LOADING ---
try:
    # Try to import from local file (Laptop)
    import config
    MY_EMAIL = config.EMAIL
    MY_PASSWORD = config.PASSWORD
    TO_EMAIL = config.TO_EMAIL
    print("✅ Loaded credentials from local config.py")
except ImportError:
    # If file not found (Render), load from Environment Variables
    MY_EMAIL = os.environ.get("MY_EMAIL")
    MY_PASSWORD = os.environ.get("MY_PASSWORD")
    TO_EMAIL = os.environ.get("TO_EMAIL")
    print("✅ Loaded credentials from Environment Variables")

# Check if keys are missing
if not MY_EMAIL or not MY_PASSWORD:
    print("⚠️ WARNING: Email credentials are missing!")