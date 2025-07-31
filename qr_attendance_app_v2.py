from flask import Flask, request, render_template_string
import pandas as pd
from datetime import datetime, timedelta
import uuid
import os

app = Flask(__name__)

attendance_file = "attendance.csv"
session_file = "session.txt"
location = "STADIO Centurion, Room BL7"

# Initialize attendance list
def init_attendance():
    if not os.path.exists(attendance_file):
        df = pd.DataFrame({
            "name": ["Alice Smith", "Bob Johnson", "Charlie Lee"],
            "status": [None, None, None],
            "timestamp": [None, None, None],
            "location": [None, None, None]
        })
        df.to_csv(attendance_file, index=False)

# Create a session
def create_session():
    session_id = str(uuid.uuid4())[:8]
    expires_at = datetime.now() + timedelta(minutes=10)
    with open(session_file, "w") as f:
        f.write(f"{session_id},{expires_at.isoformat()}")
    return session_id, expires_at

# Load session
def load_session():
    if not os.path.exists(session_file):
        return None, None
    with open(session_file, "r") as f:
        session_id, expires = f.read().strip().split(",")
    return session_id, datetime.fromisoformat(expires)

# Mark absentees after timeout
def mark_absentees():
    df = pd.read_csv(attendance_file)
    df["status"] = df["status"].fillna("❌")
    df["timestamp"] = df["timestamp"].fillna("")
    df["location"] = df["location"].fillna(location)
    df.to_csv(attendance_file, index=False)

# Handle attendance submission
def submit_attendance(name_input):
    df = pd.read_csv(attendance_file)
    matches = df["name"].apply(lambda full_name: name_input.lower() in full_name.lower())
    if matches.any():
        idx = matches.idxmax()
        df.at[idx, "status"] = "✔️"
        df.at[idx, "timestamp"] = datetime.now().strftime("%d %B %Y, %I:%M %p")
        df.at[idx, "location"] = location
        df.to_csv(attendance_file, index=False)
        return df.at[idx, "name"], "✔️"
    else:
        return name_input, "❌"

form_html = """
<!doctype html>
<title>QR Attendance</title>
<h2>Session Code: {{ session_id }}</h2>
<p>This code expires at: <strong>{{ expires_at }}</strong></p>
<form method="POST">
    <input type="text" name="name" placeholder="Enter your name" required>
    <input type="submit" value="Submit">
</form>
{% if message %}
<p><strong>{{ message }}</strong></p>
{% endif %}
"""

@app.route("/", methods=["GET", "POST"])
def index():
    session_id, expires_at = load_session()
    if not session_id or datetime.now() > expires_at:
        session_id, expires_at = create_session()
        mark_absentees()

    message = ""
    if request.method == "POST":
        name_input = request.form["name"].strip()
        marked_name, status = submit_attendance(name_input)
        if status == "✔️":
            message = f"{marked_name} marked as Present (✔️)"
        else:
            message = f"{marked_name} not found. Marked as Absent (❌)"

    return render_template_string(form_html, session_id=session_id, expires_at=expires_at.strftime("%d %B %Y, %I:%M %p"), message=message)

if __name__ == "__main__":
    init_attendance()
    create_session()
    app.run(debug=True)
