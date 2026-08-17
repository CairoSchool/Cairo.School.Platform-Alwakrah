import os
import io
import json
from flask import Flask, render_template, request, send_file
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)

# إعدادات جوجل درايف
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_drive_service():
    # التحقق مما إذا كان متغير البيئة على Render موجوداً
    google_creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    
    if google_creds_env:
        # قراءة البيانات من متغيرات البيئة على Render
        creds_info = json.loads(google_creds_env)
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    else:
        # قراءة الملف محلياً من جهازك (عند التشغيل على جهازك الشخصي)
        SERVICE_ACCOUNT_FILE = 'credentials.json'
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        
    return build('drive', 'v3', credentials=creds)

# الـ ID الخاص بفولدر "School Project" على جوجل درايف
ROOT_FOLDER_ID = '1iUwb6zf2EgxyIOw6uls1jrMySN2Qmq_p'

def search_file_in_drive(folder_id, file_name):
    try:
        service = get_drive_service()
        # البحث عن الملف داخل الفولدر بالاسم
        query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
        results = service.files().list(q=query, pageSize=1, fields="files(id, name)").execute()
        files = results.get('files', [])
        if files:
            return files[0]['id']
    except Exception as e:
        print(f"Error searching file: {e}")
    return None

def find_nested_file_in_drive(subfolder_name, file_name):
    try:
        service = get_drive_service()
        
        # 1. البحث عن المجلد الفرعي داخل المجلد الرئيسي ROOT_FOLDER_ID
        folder_query = f"'{ROOT_FOLDER_ID}' in parents and name = '{subfolder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        folder_results = service.files().list(q=folder_query, pageSize=1, fields="files(id)").execute()
        folders = folder_results.get('files', [])
        
        if not folders:
            return None
            
        subfolder_id = folders[0]['id']
        
        # 2. البحث عن الملف داخل المجلد الفرعي المحدد بدقة
        file_query = f"'{subfolder_id}' in parents and name = '{file_name}' and trashed = false"
        file_results = service.files().list(q=file_query, pageSize=1, fields="files(id, name)").execute()
        files = file_results.get('files', [])
        
        if files:
            return files[0]['id']
            
        return None
    except Exception as e:
        print(f"Error in smart search: {e}")
        return None

# 1. الصفحة الرئيسية
@app.route("/")
def home():
    return render_template("index.html")

# 2. صفحة الأنشطة
@app.route("/activities")
def activities():
    return render_template("activities.html")

# 3. صفحة اختيار جدول الحصص
@app.route("/schedule_select")
def schedule_select():
    return render_template("schedule_select.html")

# 4. صفحة عرض جدول الحصص وسحب الملف من الدرايف
@app.route("/display_schedule", methods=["GET", "POST"])
def display_schedule():
    file_id = None
    error_message = None

    if request.method == "POST":
        section = request.form.get("section") # القسم
        grade = request.form.get("grade")     # الفصل
        
        filename = f"{grade}.pdf"
        # نبحث في الدرايف: المجلد الفرعي هو القسم، والملف هو اسم الفصل
        found_id = find_nested_file_in_drive(section, filename)

        if found_id:
            file_id = found_id
        else:
            error_message = f"عذراً، لا يوجد جدول متاح حالياً للفصل {grade} في القسم {section}."

    return render_template("display_schedule.html", pdf_file_id=file_id, error_message=error_message)

# 5. صفحة الشهادات وسحب الملف من الدرايف
@app.route("/certificate", methods=["GET", "POST"])
def certificate():
    file_id = None
    error_message = None

    if request.method == "POST":
        student_id = request.form.get("national_id")
        cert_type = request.form.get("cert_type")
        
        filename = f"{student_id}.pdf"
        # نبحث في الدرايف: المجلد الفرعي هو نوع الشهادة، والملف هو رقم الـ ID
        found_id = find_nested_file_in_drive(cert_type, filename)

        if found_id:
            file_id = found_id
        else:
            error_message = "رقم الـ ID مدخل خطأ أو الشهادة غير متاحة حتى الآن. يرجى مراجعة إدارة المدرسة."

    return render_template("certificate.html", pdf_file_id=file_id, error_message=error_message)

# 6. مسار لجلب وعرض ملف الـ PDF من جوجل درايف مباشرة للمستخدم
@app.route('/drive/file/<file_id>')
def serve_drive_file(file_id):
    try:
        service = get_drive_service()
        request_download = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_download)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return send_file(fh, mimetype='application/pdf')
    except Exception as e:
        return f"Error loading file: {e}", 404

# 7. صفحة اتصل بنا
@app.route("/contact")
def contact():
    return render_template("contact.html")

if __name__ == "__main__":
    app.run(debug=True)