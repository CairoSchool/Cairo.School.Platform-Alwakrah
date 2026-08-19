import os
import io
import json
from flask import Flask, render_template, request, send_file, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)

# إعدادات جوجل درايف
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

# الـ ID الخاص بفولدر "School Project" على جوجل درايف
ROOT_FOLDER_ID = '1iUwb6zf2EgxyIOw6uls1jrMySN2Qmq_p'

# --- نظام الذاكرة المؤقتة (Cache) لتسريع الموقع ---
search_cache = {}

def search_file_in_drive(folder_id, file_name):
    cache_key = f"{folder_id}_{file_name}"
    if cache_key in search_cache:
        return search_cache[cache_key]
        
    try:
        service = get_drive_service()
        query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
        results = service.files().list(q=query, pageSize=1, fields="files(id, name)").execute()
        files = results.get('files', [])
        if files:
            file_id = files[0]['id']
            search_cache[cache_key] = file_id
            return file_id
    except Exception as e:
        print(f"Error searching file: {e}")
    return None

def find_subfolder_id_by_name(parent_folder_id, folder_name):
    cache_key = f"folder_{parent_folder_id}_{folder_name}"
    if cache_key in search_cache:
        return search_cache[cache_key]
        
    try:
        service = get_drive_service()
        query = f"'{parent_folder_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, pageSize=1, fields="files(id)").execute()
        folders = results.get('files', [])
        if folders:
            folder_id = folders[0]['id']
            search_cache[cache_key] = folder_id
            return folder_id
    except Exception as e:
        print(f"Error finding subfolder: {e}")
    return None

def find_nested_file_in_drive(subfolder_name, file_name):
    cache_key = f"{subfolder_name}/{file_name}"
    if cache_key in search_cache:
        return search_cache[cache_key]

    try:
        service = get_drive_service()
        static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
        if not static_folder_id:
            return None
            
        schedules_folder_id = find_subfolder_id_by_name(static_folder_id, 'schedules')
        if not schedules_folder_id:
            return None
            
        section_folder_id = find_subfolder_id_by_name(schedules_folder_id, subfolder_name)
        if not section_folder_id:
            cert_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'certificates')
            if not cert_folder_id:
                cert_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, subfolder_name)
            if cert_folder_id:
                section_folder_id = cert_folder_id
            else:
                return None
            
        file_id = search_file_in_drive(section_folder_id, file_name)
        if file_id:
            search_cache[cache_key] = file_id
            return file_id
            
        return None
    except Exception as e:
        print(f"Error in smart search: {e}")
        return None

# --- البحث داخل المجلدات الفرعية الثلاثة (timeline, evaluations, finals) تحت exams_timeline ---
def find_exam_or_timeline_file(sub_folder_name, file_name):
    cache_key = f"exams_sub_{sub_folder_name}/{file_name}"
    if cache_key in search_cache:
        return search_cache[cache_key]

    try:
        service = get_drive_service()
        # 1. البحث عن مجلد static
        static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
        if not static_folder_id:
            return None
            
        # 2. البحث عن مجلد exams_timeline الرئيسي
        exams_main_id = find_subfolder_id_by_name(static_folder_id, 'exams_timeline')
        if not exams_main_id:
            exams_main_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'exams_timeline')
        if not exams_main_id:
            return None
            
        # 3. البحث عن المجلد الفرعي المطلوب (timeline أو evaluations أو finals)
        sub_folder_id = find_subfolder_id_by_name(exams_main_id, sub_folder_name)
        if not sub_folder_id:
            return None

        # 4. البحث عن الملف بالداخل
        file_id = search_file_in_drive(sub_folder_id, file_name)
        if file_id:
            search_cache[cache_key] = file_id
            return file_id
            
    except Exception as e:
        print(f"Error finding subfolder file: {e}")
    return None

# 1. الصفحة الرئيسية
@app.route("/")
def home():
    return render_template("index.html")

# 2. صفحة الجدول الزمني وجداول الاختبارات (البديلة للأنشطة)
@app.route("/exams_timeline", methods=["GET", "POST"])
def exams_timeline():
    timeline_file_id = None
    eval_file_id = None
    final_file_id = None
    
    eval_error = None
    final_error = None
    
    selected_term_eval = ""
    selected_eval_type = ""
    selected_term_final = ""

    if request.method == "POST":
        action_type = request.form.get("action_type")
        
        # أ) جدول اختبارات التقييمات (من مجلد evaluations)
        if action_type == "eval_submit":
            selected_term_eval = request.form.get("eval_term") # term1 أو term2
            selected_eval_type = request.form.get("eval_type") # eval1, eval2, eval3, eval4
            
            if selected_term_eval and selected_eval_type:
                filename = f"{selected_term_eval}_{selected_eval_type}.pdf"
                found_id = find_exam_or_timeline_file("evaluations", filename)
                if found_id:
                    eval_file_id = found_id
                else:
                    eval_error = "عذراً، جدول اختبار التقييم المطلوب غير متاح حالياً."
            else:
                eval_error = "يرجى اختيار الفصل الدراسي ونوع التقييم بدقة."

        # ب) جدول اختبار نهاية الفصل (من مجلد finals)
        elif action_type == "final_submit":
            selected_term_final = request.form.get("final_term") # term1 أو term2
            
            if selected_term_final:
                filename = f"{selected_term_final}_final.pdf"
                found_id = find_exam_or_timeline_file("finals", filename)
                if found_id:
                    final_file_id = found_id
                else:
                    final_error = "عذراً، جدول اختبار نهاية الفصل غير متاح حالياً."
            else:
                final_error = "يرجى اختيار الفصل الدراسي بدقة."

    # جلب الجدول الزمني الرئيسي (من مجلد timeline)
    timeline_file_id = find_exam_or_timeline_file("timeline", "timeline.pdf")

    return render_template("exams_timeline.html",
                           timeline_file_id=timeline_file_id,
                           eval_file_id=eval_file_id,
                           final_file_id=final_file_id,
                           eval_error=eval_error,
                           final_error=final_error,
                           selected_term_eval=selected_term_eval,
                           selected_eval_type=selected_eval_type,
                           selected_term_final=selected_term_final)

# 3 & 4. صفحة اختيار وعرض جدول الحصص
@app.route("/schedule_select", methods=["GET", "POST"])
def schedule_select():
    file_id = None
    error_message = None
    searched = False
    selected_section = ""
    selected_grade = ""

    if request.method == "POST":
        searched = True
        selected_section = request.form.get("section")
        selected_grade = request.form.get("grade")
        
        if selected_section and selected_grade:
            filename = f"{selected_grade}.pdf"
            found_id = find_nested_file_in_drive(selected_section, filename)

            if found_id:
                file_id = found_id
            else:
                error_message = f"عذراً، لا يوجد جدول متاح حالياً للفصل {selected_grade} في القسم."
        else:
            error_message = "يرجى اختيار القسم والفصل بدقة."

    return render_template("schedule_select.html", 
                           pdf_file_id=file_id, 
                           error_message=error_message, 
                           searched=searched,
                           selected_section=selected_section,
                           selected_grade=selected_grade)

# 5. صفحة الشهادات
@app.route("/certificate", methods=["GET", "POST"])
def certificate():
    file_id = None
    error_message = None

    if request.method == "POST":
        student_id = request.form.get("national_id")
        cert_type = request.form.get("cert_type")
        
        if student_id and cert_type:
            filename = f"{student_id}.pdf"
            found_id = find_nested_file_in_drive(cert_type, filename)

            if found_id:
                file_id = found_id
            else:
                error_message = "رقم الـ ID مدخل خطأ أو الشهادة غير متاحة حتى الآن. يرجى مراجعة إدارة المدرسة."
        else:
            error_message = "يرجى إدخال رقم الـ ID واختيار نوع الشهادة بدقة."

    return render_template("certificate.html", pdf_file_id=file_id, error_message=error_message)

# 6. مسار لجلب وعرض الملفات من جوجل درايف
@app.route('/drive/file/<file_id>')
def serve_drive_file(file_id):
    try:
        service = get_drive_service()
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType', 'application/octet-stream')

        request_download = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_download)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return send_file(fh, mimetype=mime_type)
    except Exception as e:
        return f"Error loading file: {e}", 404

# 7. صفحة اتصل بنا
@app.route("/contact")
def contact():
    return render_template("contact.html")

if __name__ == "__main__":
    app.run(debug=True)