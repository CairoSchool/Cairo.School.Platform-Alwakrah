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
        exams_main_id = find_subfolder_id_by_name(static_folder_id, 'exams_timeline') if static_folder_id else None
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
        schedules_folder_id = find_subfolder_id_by_name(static_folder_id, 'schedules') if static_folder_id else None
        section_folder_id = find_subfolder_id_by_name(schedules_folder_id, subfolder_name) if schedules_folder_id else None
        
        if not section_folder_id:
            cert_root_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'certificates')
            if cert_root_id:
                section_folder_id = find_subfolder_id_by_name(cert_root_id, subfolder_name)
        
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

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/exams_timeline")
def exams_timeline(): 
    return render_template("exams_timeline.html")

@app.route("/exams_timeline/timeline", methods=["GET"])
def timeline_page():
    file_id = None
    error_message = None
    
    # اسم الملف الثابت للجدول الزمني العام داخل مجلد timeline
    filename = "timeline.pdf"
    file_id = find_exam_or_timeline_file("timeline", filename)
    
    if not file_id:
        error_message = "عذراً، الجدول الزمني غير متاح حالياً."
        
    return render_template("timeline_view.html", file_id=file_id, error_message=error_message)

@app.route("/exams_timeline/evaluations", methods=["GET", "POST"])
def evaluations_page():
    file_id = None
    error_message = None
    searched = False
    selected_term = ""
    selected_eval = ""
    
    if request.method == "POST":
        searched = True
        selected_term = request.form.get("eval_term") # مثال: term1 أو term2
        selected_eval = request.form.get("eval_type") # مثال: eval1, eval2, eval3, eval4
        
        print(f"DEBUG EVAL - Term: {selected_term}")
        print(f"DEBUG EVAL - Eval Type: {selected_eval}")
        
        if selected_term and selected_eval:
            # تكوين اسم الملف تماماً كما طلبت (مثال: term1_eval1.pdf أو term2_eval3.pdf)
            filename = f"{selected_term}_{selected_eval}.pdf"
            print(f"DEBUG EVAL - Target filename: {filename}")
            
            # تسلسل المجلدات: static -> exams_timeline -> evaluations
            static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
            exams_main_id = find_subfolder_id_by_name(static_folder_id, 'exams_timeline') if static_folder_id else None
            eval_folder_id = find_subfolder_id_by_name(exams_main_id, 'evaluations') if exams_main_id else None
            
            # ربط term1 بـ term_1، و term2 بـ term_2
            term_folder_name = "term_1" if selected_term == "term1" else "term_2"
            term_subfolder_id = find_subfolder_id_by_name(eval_folder_id, term_folder_name) if eval_folder_id else None
            
            print(f"DEBUG EVAL - term_subfolder_id: {term_subfolder_id}")
            
            if term_subfolder_id:
                file_id = search_file_in_drive(term_subfolder_id, filename)
                print(f"DEBUG EVAL - Found file_id: {file_id}")
                
            if not file_id:
                error_message = "عذراً، هذا التقييم غير متاح حالياً."
        else:
            error_message = "يرجى اختيار الفصل والتقييم."
            
    return render_template("evaluations_view.html", 
                           searched=searched, 
                           file_id=file_id, 
                           error_message=error_message, 
                           selected_term=selected_term, 
                           selected_type=selected_eval)

@app.route("/exams_timeline/finals", methods=["GET", "POST"])
def finals_page():
    file_id = None
    error_message = None
    selected_term = ""
    if request.method == "POST":
        selected_term = request.form.get("final_term")
        print(f"DEBUG: Selected term is: {selected_term}") # طباعة الفصل المختار
        if selected_term:
            filename = f"{selected_term}_final.pdf"
            print(f"DEBUG: Target filename is: {filename}") # طباعة اسم الملف المطلوب
            
            static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
            print(f"DEBUG: static_folder_id: {static_folder_id}")
            
            exams_main_id = find_subfolder_id_by_name(static_folder_id, 'exams_timeline') if static_folder_id else None
            print(f"DEBUG: exams_main_id: {exams_main_id}")
            
            finals_folder_id = find_subfolder_id_by_name(exams_main_id, 'finals') if exams_main_id else None
            print(f"DEBUG: finals_folder_id: {finals_folder_id}")
            
            term_folder_id = find_subfolder_id_by_name(finals_folder_id, selected_term) if finals_folder_id else None
            print(f"DEBUG: term_folder_id ({selected_term}): {term_folder_id}")
            
            if term_folder_id:
                file_id = search_file_in_drive(term_folder_id, filename)
                print(f"DEBUG: Found file_id: {file_id}")
                
            if not file_id:
                error_message = "عذراً، جدول نهاية الفصل غير متاح حالياً."
        else:
            error_message = "يرجى اختيار الفصل الدراسي."
    return render_template("finals_view.html", file_id=file_id, error_message=error_message, selected_term=selected_term)

@app.route("/schedule_select", methods=["GET", "POST"])
def schedule_select():
    pdf_file_id = None
    error_message = None
    searched = False  # مهم جداً
    selected_section = ""
    selected_grade = ""
    
    if request.method == "POST":
        searched = True  # تحويله إلى True لأن المستخدم ضغط بحث
        selected_section = request.form.get("section")
        selected_grade = request.form.get("grade")
        
        if selected_section and selected_grade:
            filename = f"{selected_grade}.pdf" # أو حسب اسم الملف في درايف
            
            # تتبع مجلدات الجداول: static -> schedules -> section -> grade.pdf
            static_folder_id = find_subfolder_id_by_name(ROOT_FOLDER_ID, 'static')
            schedules_main_id = find_subfolder_id_by_name(static_folder_id, 'schedules') if static_folder_id else None
            section_folder_id = find_subfolder_id_by_name(schedules_main_id, selected_section) if schedules_main_id else None
            
            if section_folder_id:
                pdf_file_id = search_file_in_drive(section_folder_id, filename)
                
            if not pdf_file_id:
                error_message = "عذراً، لم يتم العثور على جدول لهذا الفصل حالياً."
        else:
            error_message = "يرجى اختيار القسم والفصل بدقة."
            
    return render_template("schedule_select.html", 
                           searched=searched, 
                           pdf_file_id=pdf_file_id, 
                           error_message=error_message, 
                           selected_section=selected_section, 
                           selected_grade=selected_grade)

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