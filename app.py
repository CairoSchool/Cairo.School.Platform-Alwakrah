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

def find_subfolder_id_by_name(parent_folder_id, folder_name):
    try:
        service = get_drive_service()
        query = f"'{parent_folder_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, pageSize=1, fields="files(id)").execute()
        folders = results.get('files', [])
        if folders:
            return folders[0]['id']
    except Exception as e:
        print(f"Error finding subfolder: {e}")
    return None

def find_nested_file_in_drive(subfolder_name, file_name):
    try:
        service = get_drive_service()
        print(f"DEBUG: Searching for subfolder: {subfolder_name}")
        
        subfolder_id = None
        
        # 1. محاولة البحث عن المجلد مباشرة تحت المجلد الرئيسي ROOT_FOLDER_ID
        folder_query = f"'{ROOT_FOLDER_ID}' in parents and name = '{subfolder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        folder_results = service.files().list(q=folder_query, pageSize=1, fields="files(id)").execute()
        folders = folder_results.get('files', [])
        
        if folders:
            subfolder_id = folders[0]['id']
        else:
            # 2. إذا لم يتم إيجاده مباشرة، ابحث عنه داخل مجلد "certificates" الرئيسي
            cert_folder_query = f"'{ROOT_FOLDER_ID}' in parents and name = 'certificates' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            cert_results = service.files().list(q=cert_folder_query, pageSize=1, fields="files(id)").execute()
            cert_folders = cert_results.get('files', [])
            
            if cert_folders:
                cert_folder_id = cert_folders[0]['id']
                sub_query = f"'{cert_folder_id}' in parents and name = '{subfolder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                sub_results = service.files().list(q=sub_query, pageSize=1, fields="files(id)").execute()
                sub_folders = sub_results.get('files', [])
                if sub_folders:
                    subfolder_id = sub_folders[0]['id']
        
        if not subfolder_id:
            print(f"DEBUG: Subfolder '{subfolder_name}' NOT FOUND anywhere!")
            return None
            
        print(f"DEBUG: Subfolder found! ID: {subfolder_id}. Searching for file: {file_name}")
        
        # 3. البحث عن الملف داخل المجلد الفرعي المحدد بدقة
        file_query = f"'{subfolder_id}' in parents and name = '{file_name}' and trashed = false"
        file_results = service.files().list(q=file_query, pageSize=1, fields="files(id, name)").execute()
        files = file_results.get('files', [])
        
        if files:
            print(f"DEBUG: File '{file_name}' FOUND successfully!")
            return files[0]['id']
            
        print(f"DEBUG: File '{file_name}' NOT FOUND in subfolder '{subfolder_name}'!")
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

# مسار جديد لجلب صور الأنشطة أوتوماتيكياً من المسار: School Project -> static -> images -> [section_name]
@app.route("/get_activity_images/<section_name>")
def get_activity_images(section_name):
    try:
        # 1. البحث عن مجلد static داخل المجلد الرئيسي
        static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
        if not static_folder_id:
            return jsonify([])

        # 2. البحث عن مجلد images داخل مجلد static
        images_folder_id = find_subfolder_id_by_name(static_folder_id, 'images')
        if not images_folder_id:
            return jsonify([])

        # 3. البحث عن مجلد النشاط بالاسم (cultural, entertainment, general) داخل مجلد images
        activity_folder_id = find_subfolder_id_by_name(images_folder_id, section_name)
        if not activity_folder_id:
            return jsonify([])

        # 4. جلب كافة الصور (jpg, png) الموجودة داخل مجلد النشاط أوتوماتيكياً
        service = get_drive_service()
        query = f"'{activity_folder_id}' in parents and (mimeType = 'image/jpeg' or mimeType = 'image/png') and trashed = false"
        results = service.files().list(q=query, pageSize=100, fields="files(id, name)").execute()
        files = results.get('files', [])

        # استخراج الـ IDs الخاصة بالصور لعرضها في الفريمات
        image_ids = [file['id'] for file in files]
        return jsonify(image_ids)

    except Exception as e:
        print(f"Error fetching activity images: {e}")
        return jsonify([])

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
        found_id = find_nested_file_in_drive(section, filename)

        if found_id:
            file_id = found_id
        else:
            error_message = f"عذراً، لا يوجد جدول متاح حالياً للفصل {grade} في القسم {section}."

    return render_template("display_schedule.html", pdf_file_id=file_id, error_message=error_message)

# 5. صفحة الشهادات وسحب الملف من الدرايف (النسخة المباشرة المستقرة)
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

# 6. مسار لجلب وعرض الملفات (صور أو ملفات PDF) من جوجل درايف مباشرة للمستخدم
@app.route('/drive/file/<file_id>')
def serve_drive_file(file_id):
    try:
        service = get_drive_service()
        # استعلام عن نوع الملف لمعرفة هل هو صورة أم مستند
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