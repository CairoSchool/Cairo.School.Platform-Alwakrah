import os
from flask import Flask, render_template, request, send_from_directory

app = Flask(__name__)

# المجلد الأساسي للشهادات
CERT_FOLDER = os.path.join(os.getcwd(), 'certificates')

# 1. الصفحة الرئيسية
@app.route("/")
def home():
    return render_template("index.html")

# 2. صفحة الأنشطة
@app.route("/activities")
def activities():
    return render_template("activities.html")

# 3. صفحة جدول الحصص (تم تصحيح المسار ليتطابق مع القائمة والزرار)
@app.route("/schedule_select")
def schedule_select():
    return render_template("schedule_select.html")

# 4. صفحة الشهادات (النسخة الكاملة للبحث والاستخراج)
@app.route("/certificate", methods=["GET", "POST"])
def certificate():
    pdf_filename = None
    error_message = None

    if request.method == "POST":
        # تم توحيد اسم المتغير ليطابق الـ HTML (national_id)
        student_id = request.form.get("national_id")
        cert_type = request.form.get("cert_type")
        
        filename = f"{student_id}.pdf"
        file_path = os.path.join(CERT_FOLDER, cert_type, filename)

        if os.path.exists(file_path):
            pdf_filename = f"{cert_type}/{filename}"
        else:
            error_message = "رقم الـ ID مدخل خطأ أو الشهادة غير متاحة حتى الآن. يرجى مراجعة إدارة المدرسة."

    return render_template("certificate.html", pdf_filename=pdf_filename, error_message=error_message)

# 5. مسار لعرض ملفات الـ PDF
@app.route('/certificates/<path:filename>')
def serve_pdf(filename):
    return send_from_directory(CERT_FOLDER, filename)

# 6. صفحة اتصل بنا
@app.route("/contact")
def contact():
    return render_template("contact.html")

if __name__ == "__main__":
    app.run(debug=True)