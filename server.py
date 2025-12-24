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
import sys

# ===========================
# 1. CONFIGURATION
# ===========================
# Force output to print immediately (fixes missing logs on Render)
sys.stdout.reconfigure(line_buffering=True)

# Render gives us a specific PORT. We must use it.
# If running locally, we default to 8080.
PORT = int(os.environ.get("PORT", 8080))
DATA_FILE = "student_data.json"

# --- SECURE PASSWORD LOADING ---
try:
    import config
    MY_EMAIL = config.EMAIL
    MY_PASSWORD = config.PASSWORD
    TO_EMAIL = config.TO_EMAIL
    print("✅ Loaded credentials from local config.py")
except ImportError:
    MY_EMAIL = os.environ.get("MY_EMAIL")
    MY_PASSWORD = os.environ.get("MY_PASSWORD")
    TO_EMAIL = os.environ.get("TO_EMAIL")
    if MY_EMAIL:
        print("✅ Loaded credentials from Environment Variables")
    else:
        print("⚠️ WARNING: No credentials found! Email features will fail.")

# ===========================
# 2. EMAIL BOT
# ===========================
def send_email(subject, body):
    if not MY_EMAIL or not MY_PASSWORD:
        print("❌ Cannot send email: Credentials missing.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = MY_EMAIL
        msg['To'] = TO_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(MY_EMAIL, MY_PASSWORD)
        server.sendmail(MY_EMAIL, TO_EMAIL, msg.as_string())
        server.quit()
        print(f"📧 EMAIL SENT: {subject}")
    except Exception as e:
        print(f"❌ Email Error: {e}")

def email_bot_loop():
    print("--- 🤖 Email Bot Started (Background) ---")
    while True:
        try:
            now = datetime.datetime.now()
            # Check at 5:00 PM (17:00) OR 9:00 PM (21:00)
            if (now.hour == 17 or now.hour == 21) and now.minute == 0:
                print(f"⏰ Checking deadlines...")
                check_deadlines()
                time.sleep(65)
            time.sleep(30)
        except Exception as e:
            print(f"⚠️ Bot Loop Error: {e}")
            time.sleep(60)

def check_deadlines():
    if not os.path.exists(DATA_FILE): return
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        
        tasks = data.get("tasks", [])
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        due_tomorrow = [t for t in tasks if t['date'] == tomorrow_str]

        if due_tomorrow:
            subject = f"🔔 Reminder: {len(due_tomorrow)} Tasks Due Tomorrow!"
            body = f"Hello,\n\nYou have the following deadlines tomorrow ({tomorrow_str}):\n\n"
            for t in due_tomorrow:
                body += f" - [{t['type']}] {t['subject']}: {t['title']}\n"
            body += "\nGood luck!\nYour Dashboard Bot"
            send_email(subject, body)
    except Exception as e:
        print(f"❌ Error checking deadlines: {e}")

# ===========================
# 3. WEB SERVER
# ===========================
class MyRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/dashboard.html'
        
        if self.path == '/api/get_data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(b'{"tasks":[], "notes":{}}')
            return
        
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data.decode('utf-8'))

            data = {"tasks": [], "notes": {}}
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    try: data = json.load(f)
                    except: pass

            if self.path == '/api/save_task':
                data["tasks"].append(request_data)
            elif self.path == '/api/delete_task':
                data["tasks"] = [t for t in data["tasks"] if t['id'] != request_data['id']]
            elif self.path == '/api/save_note':
                key = request_data['key']
                note = request_data['note']
                if note.strip() == "":
                    if key in data["notes"]: del data["notes"][key]
                else:
                    data["notes"][key] = note

            with open(DATA_FILE, 'w') as f:
                json.dump(data, f, indent=4)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
        except Exception as e:
            print(f"❌ Server Error: {e}")
            self.send_response(500)
            self.end_headers()

if __name__ == "__main__":
    # Start Email Bot
    bot_thread = threading.Thread(target=email_bot_loop, daemon=True)
    bot_thread.start()

    # Start Web Server with robust binding
    print(f"🚀 Attempting to start server on 0.0.0.0:{PORT} ...")
    try:
        # Binding to "0.0.0.0" is crucial for Render
        server = socketserver.TCPServer(("0.0.0.0", PORT), MyRequestHandler)
        print("✅ Server started successfully!")
        server.serve_forever()
    except Exception as e:
        print(f"🔥 FATAL ERROR: Could not start server: {e}")
        # Keep script alive briefly to ensure logs are flushed to Render
        time.sleep(5)
        sys.exit(1)