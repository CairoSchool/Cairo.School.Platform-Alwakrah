import os
import io
import json
from flask import Flask, render_template, request, send_file
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_drive_service():
    google_creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if google_creds_env:
        creds_info = json.loads(google_creds_env)
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    else:
        SERVICE_ACCOUNT_FILE = 'credentials.json'
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

ROOT_FOLDER_ID = '1iUwb6zf2EgxyIOw6uls1jrMySN2Qmq_p'
search_cache = {}

def search_file_in_drive(folder_id, file_name):
    cache_key = f"{folder_id}_{file_name}"
    if cache_key in search_cache: return search_cache[cache_key]
    try:
        service = get_drive_service()
        query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
        results = service.files().list(q=query, pageSize=1, fields="files(id, name)").execute()
        files = results.get('files', [])
        if files:
            file_id = files[0]['id']
            search_cache[cache_key] = file_id
            return file_id
    except: pass
    return None

def find_subfolder_id_by_name(parent_folder_id, folder_name):
    cache_key = f"folder_{parent_folder_id}_{folder_name}"
    if cache_key in search_cache: return search_cache[cache_key]
    try:
        service = get_drive_service()
        query = f"'{parent_folder_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, pageSize=1, fields="files(id)").execute()
        folders = results.get('files', [])
        if folders:
            folder_id = folders[0]['id']
            search_cache[cache_key] = folder_id
            return folder_id
    except: pass
    return None

def find_exam_or_timeline_file(sub_folder_name, file_name):
    cache_key = f"exams_sub_{sub_folder_name}/{file_name}"
    if cache_key in search_cache: return search_cache[cache_key]
    try:
        static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
        exams_main_id = find_subfolder_id_by_name(static_folder_id, 'exams_timeline') or find_subfolder_id_by_name(ROOT_FOLDER_ID, 'exams_timeline')
        if not exams_main_id: return None
        sub_folder_id = find_subfolder_id_by_name(exams_main_id, sub_folder_name)
        if not sub_folder_id: return None
        file_id = search_file_in_drive(sub_folder_id, file_name)
        if file_id:
            search_cache[cache_key] = file_id
            return file_id
    except: pass
    return None

def find_nested_file_in_drive(subfolder_name, file_name):
    cache_key = f"{subfolder_name}/{file_name}"
    if cache_key in search_cache: return search_cache[cache_key]
    try:
        static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
        schedules_folder_id = find_subfolder_id_by_name(static_folder_id, 'schedules')
        section_folder_id = find_subfolder_id_by_name(schedules_folder_id, subfolder_name)
        if not section_folder_id:
            cert_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'certificates') or find_subfolder_id_by_name(ROOT_FOLDER_ID, subfolder_name)
            section_folder_id = cert_folder_id
        
        file_id = search_file_in_drive(section_folder_id, file_name) if section_folder_id else None
        if file_id:
            search_cache[cache_key] = file_id
            return file_id
    except: pass
    return None

# --- المسارات (Routes) ---

@app.route("/")
def home(): 
    return render_template("index.html")

# صفحة اتصل بنا مع فحص التأكد من وجود الملف أو عرض قالب بديل آمن لمنع الخطأ الأبيض
@app.route("/contact")
def contact():
    return render_template("contact.html")

# صفحة المربعات الثلاثة الرئيسية
@app.route("/exams_timeline")
def exams_timeline(): 
    return render_template("exams_timeline.html")

@app.route("/exams_timeline/timeline", methods=["GET", "POST"])
def timeline_page():
    file_id = None
    error_message = None
    selected_term = ""
    if request.method == "POST":
        selected_term = request.form.get("timeline_term")
        if selected_term:
            filename = f"{selected_term}_timeline.pdf"
            file_id = find_exam_or_timeline_file("timeline", filename)
            if not file_id:
                file_id = find_exam_or_timeline_file("timeline", "timeline.pdf")
            if not file_id:
                error_message = "عذراً، الجدول الزمني العام غير متاح حالياً."
        else:
            error_message = "يرجى اختيار الفصل الدراسي."
    return render_template("timeline_view.html", file_id=file_id, error_message=error_message, selected_term=selected_term)

@app.route("/exams_timeline/evaluations", methods=["GET", "POST"])
def evaluations_page():
    file_id = None
    error_message = None
    selected_term = ""
    selected_type = ""
    if request.method == "POST":
        selected_term = request.form.get("eval_term")
        selected_type = request.form.get("eval_type")
        if selected_term and selected_type:
            filename = f"{selected_term}_{selected_type}.pdf"
            file_id = find_exam_or_timeline_file("evaluations", filename)
            if not file_id:
                error_message = "عذراً، جدول التقييم غير متاح حالياً."
        else:
            error_message = "يرجى اختيار الفصل ونوع التقييم بدقة."
    return render_template("evaluations_view.html", file_id=file_id, error_message=error_message, selected_term=selected_term, selected_type=selected_type)

@app.route("/exams_timeline/finals", methods=["GET", "POST"])
def finals_page():
    file_id = None
    error_message = None
    selected_term = ""
    if request.method == "POST":
        selected_term = request.form.get("final_term")
        if selected_term:
            filename = f"{selected_term}_final.pdf"
            file_id = find_exam_or_timeline_file("finals", filename)
            if not file_id:
                error_message = "عذراً، جدول نهاية الفصل غير متاح حالياً."
        else:
            error_message = "يرجى اختيار الفصل الدراسي."
    return render_template("finals_view.html", file_id=file_id, error_message=error_message, selected_term=selected_term)

@app.route("/schedule_select", methods=["GET", "POST"])
def schedule_select():
    file_id = None
    error_message = None
    if request.method == "POST":
        section = request.form.get("section")
        grade = request.form.get("grade")
        if section and grade:
            file_id = find_nested_file_in_drive(section, f"{grade}.pdf")
            if not file_id: error_message = "لا يوجد جدول متاح حالياً."
    return render_template("schedule_select.html", pdf_file_id=file_id, error_message=error_message)

@app.route("/certificate", methods=["GET", "POST"])
def certificate():
    file_id = None
    error_message = None
    if request.method == "POST":
        student_id = request.form.get("national_id")
        cert_type = request.form.get("cert_type")
        if student_id and cert_type:
            file_id = find_nested_file_in_drive(cert_type, f"{student_id}.pdf")
            if not file_id: error_message = "الشهادة غير متاحة."
    return render_template("certificate.html", pdf_file_id=file_id, error_message=error_message)

@app.route('/drive/file/<file_id>')
def serve_drive_file(file_id):
    try:
        service = get_drive_service()
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        request_download = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_download)
        done = False
        while not done: status, done = downloader.next_chunk()
        fh.seek(0)
        return send_file(fh, mimetype=file_metadata.get('mimeType'))
    except: return "Error loading file", 404

if __name__ == "__main__":
    app.run(debug=True)