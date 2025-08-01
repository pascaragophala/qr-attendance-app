from flask import Flask, request, render_template, redirect, url_for, send_file
from flask_qrcode import QRcode
import pandas as pd
from datetime import datetime, timedelta
import pytz
import uuid
import os
import io

app = Flask(__name__)
QRcode(app)

# Configuration
attendance_file = "attendance.csv"
sessions_file = "sessions.csv"
timezone = pytz.timezone('Africa/Johannesburg')  # SAST timezone
location = "STADIO Centurion, Room BL7"

# Initialize files
def init_files():
    if not os.path.exists(attendance_file):
        df = pd.DataFrame({
            "name": [], "student_id": [], "status": [], "timestamp": [], "location": []
        })
        df.to_csv(attendance_file, index=False)
    
    if not os.path.exists(sessions_file):
        sessions_df = pd.DataFrame(columns=[
            "session_id", "class_name", "class_code", "date", "start_time", 
            "end_time", "room", "lecturer", "qr_active", "created_at"
        ])
        sessions_df.to_csv(sessions_file, index=False)

# Get current time in SAST
def get_current_time():
    return datetime.now(timezone)

# Session management
def create_session(class_name, class_code, date, start_time, end_time, room, lecturer):
    session_id = str(uuid.uuid4())[:8]
    created_at = get_current_time().isoformat()
    
    new_session = pd.DataFrame([{
        "session_id": session_id,
        "class_name": class_name,
        "class_code": class_code,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "room": room,
        "lecturer": lecturer,
        "qr_active": True,
        "created_at": created_at
    }])
    
    if os.path.exists(sessions_file):
        sessions_df = pd.read_csv(sessions_file)
        sessions_df = pd.concat([sessions_df, new_session], ignore_index=True)
    else:
        sessions_df = new_session
    
    sessions_df.to_csv(sessions_file, index=False)
    return session_id

def get_active_sessions():
    if not os.path.exists(sessions_file):
        return pd.DataFrame()
    
    sessions_df = pd.read_csv(sessions_file)
    current_time = get_current_time()
    
    # Filter sessions that are still active (created within last 10 hours)
    sessions_df['created_at'] = pd.to_datetime(sessions_df['created_at'])
    active_sessions = sessions_df[
        (sessions_df['qr_active'] == True) & 
        (sessions_df['created_at'] >= (current_time - timedelta(hours=10))
    ]
    
    return active_sessions

def close_session(session_id):
    if not os.path.exists(sessions_file):
        return False
    
    sessions_df = pd.read_csv(sessions_file)
    if session_id in sessions_df['session_id'].values:
        sessions_df.loc[sessions_df['session_id'] == session_id, 'qr_active'] = False
        sessions_df.to_csv(sessions_file, index=False)
        return True
    return False

# Attendance handling
def submit_attendance(name_input, session_id):
    df = pd.read_csv(attendance_file)
    sessions_df = pd.read_csv(sessions_file)
    
    # Get session details
    session = sessions_df[sessions_df['session_id'] == session_id].iloc[0]
    class_code = session['class_code']
    
    # Check if student exists
    matches = df["name"].str.lower().str.contains(name_input.lower())
    if matches.any():
        idx = matches.idxmax()
        current_time = get_current_time().strftime("%d %B %Y, %I:%M %p")
        
        # Add attendance for this session
        if f"{class_code}_status" not in df.columns:
            df[f"{class_code}_status"] = None
            df[f"{class_code}_timestamp"] = None
        
        df.at[idx, f"{class_code}_status"] = "✔️"
        df.at[idx, f"{class_code}_timestamp"] = current_time
        df.at[idx, "location"] = location
        
        # Update main status if empty
        if pd.isna(df.at[idx, "status"]):
            df.at[idx, "status"] = "✔️"
            df.at[idx, "timestamp"] = current_time
        
        df.to_csv(attendance_file, index=False)
        return df.at[idx, "name"], "✔️"
    else:
        return name_input, "❌"

# Routes
@app.route('/')
def home():
    return redirect(url_for('lecturer_dashboard'))

@app.route('/lecturer', methods=['GET', 'POST'])
def lecturer_dashboard():
    if request.method == 'POST':
        if 'create_session' in request.form:
            class_name = request.form['class_name']
            class_code = request.form['class_code']
            date = request.form['date']
            start_time = request.form['start_time']
            end_time = request.form['end_time']
            room = request.form['room']
            lecturer = request.form['lecturer']
            
            session_id = create_session(
                class_name, class_code, date, start_time, end_time, room, lecturer
            )
            return redirect(url_for('view_qr', session_id=session_id))
        
        elif 'close_session' in request.form:
            session_id = request.form['session_id']
            close_session(session_id)
    
    active_sessions = get_active_sessions()
    return render_template('lecturer_dashboard.html', 
                         active_sessions=active_sessions.to_dict('records'))

@app.route('/qr/<session_id>')
def view_qr(session_id):
    sessions_df = pd.read_csv(sessions_file)
    session = sessions_df[sessions_df['session_id'] == session_id].iloc[0]
    
    qr_url = url_for('student_attendance', session_id=session_id, _external=True)
    return render_template('qr_display.html', 
                         session=session,
                         qr_url=qr_url,
                         session_id=session_id)

@app.route('/attendance/<session_id>', methods=['GET', 'POST'])
def student_attendance(session_id):
    sessions_df = pd.read_csv(sessions_file)
    session = sessions_df[sessions_df['session_id'] == session_id].iloc[0]
    
    message = ""
    if request.method == 'POST':
        name_input = request.form['name'].strip()
        marked_name, status = submit_attendance(name_input, session_id)
        if status == "✔️":
            message = f"{marked_name} marked as Present (✔️) for {session['class_name']}"
        else:
            message = f"{marked_name} not found. Marked as Absent (❌)"
    
    return render_template('student_attendance.html',
                         session=session,
                         message=message)

@app.route('/view_attendance', methods=['GET', 'POST'])
def view_attendance():
    sessions_df = pd.read_csv(sessions_file)
    
    if request.method == 'POST':
        session_id = request.form['session_id']
        session = sessions_df[sessions_df['session_id'] == session_id].iloc[0]
        class_code = session['class_code']
        
        df = pd.read_csv(attendance_file)
        if f"{class_code}_status" in df.columns:
            report_df = df[['name', f"{class_code}_status", f"{class_code}_timestamp"]]
            report_df = report_df.rename(columns={
                f"{class_code}_status": "Status",
                f"{class_code}_timestamp": "Timestamp"
            })
            
            if 'export' in request.form:
                output = io.StringIO()
                report_df.to_csv(output, index=False)
                output.seek(0)
                return send_file(
                    io.BytesIO(output.getvalue().encode()),
                    mimetype='text/csv',
                    as_attachment=True,
                    download_name=f"attendance_{class_code}_{session_id}.csv"
                )
            
            return render_template('attendance_report.html',
                                 report=report_df.to_dict('records'),
                                 session=session)
    
    return render_template('view_attendance.html',
                         sessions=sessions_df.to_dict('records'))

# Templates
@app.route('/templates/<template_name>')
def serve_template(template_name):
    templates = {
        'lecturer_dashboard.html': '''
            <!DOCTYPE html>
            <html>
            <head><title>Lecturer Dashboard</title></head>
            <body>
                <h1>Create New Session</h1>
                <form method="POST">
                    <input type="text" name="class_name" placeholder="Class Name" required>
                    <input type="text" name="class_code" placeholder="Class Code" required>
                    <input type="date" name="date" required>
                    <input type="time" name="start_time" required>
                    <input type="time" name="end_time" required>
                    <input type="text" name="room" placeholder="Room" required>
                    <input type="text" name="lecturer" placeholder="Lecturer" required>
                    <button type="submit" name="create_session">Create Session</button>
                </form>
                
                <h2>Active Sessions</h2>
                {% for session in active_sessions %}
                <div>
                    <h3>{{ session.class_name }} ({{ session.class_code }})</h3>
                    <p>Date: {{ session.date }} | Time: {{ session.start_time }} - {{ session.end_time }}</p>
                    <p>Room: {{ session.room }} | Lecturer: {{ session.lecturer }}</p>
                    <a href="{{ url_for('view_qr', session_id=session.session_id) }}">View QR Code</a>
                    <form method="POST" style="display:inline;">
                        <input type="hidden" name="session_id" value="{{ session.session_id }}">
                        <button type="submit" name="close_session">Close Session</button>
                    </form>
                </div>
                {% endfor %}
            </body>
            </html>
        ''',
        'qr_display.html': '''
            <!DOCTYPE html>
            <html>
            <head><title>QR Code - {{ session.class_name }}</title></head>
            <body style="text-align:center;">
                <h1>{{ session.class_name }} ({{ session.class_code }})</h1>
                <p>Date: {{ session.date }} | Time: {{ session.start_time }} - {{ session.end_time }}</p>
                <p>Scan this QR code to mark attendance</p>
                
                <div style="margin: 20px;">
                    {{ qrcode(qr_url) }}
                </div>
                
                <p>Session ID: {{ session_id }}</p>
                <a href="{{ url_for('lecturer_dashboard') }}">Back to Dashboard</a>
            </body>
            </html>
        ''',
        'student_attendance.html': '''
            <!DOCTYPE html>
            <html>
            <head><title>Attendance - {{ session.class_name }}</title></head>
            <body>
                <h1>{{ session.class_name }} Attendance</h1>
                <p>Date: {{ session.date }}</p>
                
                {% if message %}
                <p><strong>{{ message }}</strong></p>
                {% endif %}
                
                <form method="POST">
                    <input type="text" name="name" placeholder="Enter your full name" required>
                    <button type="submit">Submit</button>
                </form>
            </body>
            </html>
        ''',
        'view_attendance.html': '''
            <!DOCTYPE html>
            <html>
            <head><title>View Attendance</title></head>
            <body>
                <h1>View Attendance</h1>
                <form method="POST">
                    <select name="session_id" required>
                        {% for session in sessions %}
                        <option value="{{ session.session_id }}">
                            {{ session.class_name }} ({{ session.date }})
                        </option>
                        {% endfor %}
                    </select>
                    <button type="submit">View Attendance</button>
                    <button type="submit" name="export">Export CSV</button>
                </form>
            </body>
            </html>
        ''',
        'attendance_report.html': '''
            <!DOCTYPE html>
            <html>
            <head><title>Attendance Report</title></head>
            <body>
                <h1>Attendance Report for {{ session.class_name }}</h1>
                <p>Date: {{ session.date }}</p>
                
                <table border="1">
                    <tr>
                        <th>Name</th>
                        <th>Status</th>
                        <th>Timestamp</th>
                    </tr>
                    {% for record in report %}
                    <tr>
                        <td>{{ record.name }}</td>
                        <td>{{ record.Status }}</td>
                        <td>{{ record.Timestamp }}</td>
                    </tr>
                    {% endfor %}
                </table>
                
                <a href="{{ url_for('view_attendance') }}">Back</a>
            </body>
            </html>
        '''
    }
    return templates.get(template_name, "Template not found")

if __name__ == "__main__":
    init_files()
    app.run(debug=True)
