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
import pymongo

# ===========================
# 1. CONFIGURATION
# ===========================
# Force logs to appear immediately in Render
sys.stdout.reconfigure(line_buffering=True)
PORT = int(os.environ.get("PORT", 8080))

# --- DATABASE CONNECTION ---
MONGO_URI = os.environ.get("MONGO_URI")
client = None
db = None

if MONGO_URI:
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client.student_dashboard
        # Test the connection immediately
        client.admin.command('ping')
        print("✅ Connected to MongoDB Atlas!")
    except Exception as e:
        print(f"❌ MongoDB Connection Failed: {e}")
        db = None 
else:
    print("⚠️ WARNING: MONGO_URI not found.")

# --- SECURE PASSWORD LOADING ---
try:
    import config
    MY_EMAIL = config.EMAIL
    MY_PASSWORD = config.PASSWORD
    TO_EMAIL = config.TO_EMAIL
except ImportError:
    # If config.py is missing (like on Render), use Environment Variables
    MY_EMAIL = os.environ.get("MY_EMAIL")
    MY_PASSWORD = os.environ.get("MY_PASSWORD")
    TO_EMAIL = os.environ.get("TO_EMAIL")

# ===========================
# 2. EMAIL BOT
# ===========================
def send_email(subject, body):
    if not MY_EMAIL or not MY_PASSWORD:
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
    print("--- 🤖 Email Bot Started ---")
    while True:
        try:
            now = datetime.datetime.now()
            # Render Server Time (UTC) is 5.5 hours behind India.
            # 11:30 UTC = 5:00 PM IST
            # 15:30 UTC = 9:00 PM IST
            if (now.hour == 11 or now.hour == 15) and now.minute == 30:
                check_deadlines()
                time.sleep(65) # Wait >1 min so we don't double send
            
            time.sleep(30)
        except Exception as e:
            print(f"⚠️ Bot Error: {e}")
            time.sleep(60)

def check_deadlines():
    if db is None: return
    try:
        tasks_collection = db.tasks
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        due_tomorrow = list(tasks_collection.find({"date": tomorrow_str}))

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
        # Serve dashboard.html by default
        if self.path == '/':
            self.path = '/dashboard.html'
        
        # API: Fetch Data
        if self.path == '/api/get_data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            if db is not None:
                try:
                    # Fetch all tasks (exclude MongoDB internal ID)
                    tasks = list(db.tasks.find({}, {"_id": 0}))
                    
                    # Fetch all notes and format them
                    notes_cursor = db.notes.find({}, {"_id": 0})
                    notes = {item["key"]: item["note"] for item in notes_cursor}
                    
                    response_data = {"tasks": tasks, "notes": notes}
                    self.wfile.write(json.dumps(response_data).encode())
                except Exception as e:
                    print(f"❌ Database Read Error: {e}")
                    self.wfile.write(b'{"tasks":[], "notes":{}}')
            else:
                self.wfile.write(b'{"tasks":[], "notes":{}}')
            return
        
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data.decode('utf-8'))

            if db is None:
                self.send_response(500)
                self.end_headers()
                return

            # API: Add Task
            if self.path == '/api/save_task':
                db.tasks.insert_one(request_data)
                
            # API: Delete Task (Used for "Completed" button)
            elif self.path == '/api/delete_task':
                db.tasks.delete_one({"id": request_data['id']})

            # API: Update Task (Used for "Extend Time" button)
            elif self.path == '/api/update_task':
                db.tasks.update_one(
                    {"id": request_data['id']},
                    {"$set": {"date": request_data['date']}}
                )
                
            # API: Save Note
            elif self.path == '/api/save_note':
                key = request_data['key']
                note = request_data['note']
                if note.strip() == "":
                    db.notes.delete_one({"key": key})
                else:
                    db.notes.update_one(
                        {"key": key}, 
                        {"$set": {"note": note, "key": key}}, 
                        upsert=True
                    )

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
        except Exception as e:
            print(f"❌ Server Error: {e}")
            self.send_response(500)
            self.end_headers()

if __name__ == "__main__":
    # Start Email Bot in background thread
    bot_thread = threading.Thread(target=email_bot_loop, daemon=True)
    bot_thread.start()

    print(f"🚀 Starting server on 0.0.0.0:{PORT} ...")
    try:
        server = socketserver.TCPServer(("0.0.0.0", PORT), MyRequestHandler)
        print("✅ Server started!")
        server.serve_forever()
    except Exception as e:
        print(f"🔥 FATAL ERROR: {e}")
        time.sleep(5)
        sys.exit(1)