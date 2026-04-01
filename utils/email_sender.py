import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER

class EmailReporter:
    def __init__(self):
        self.sender = EMAIL_SENDER
        self.password = EMAIL_PASSWORD
        self.receiver = EMAIL_RECEIVER

    def can_send(self):
        return bool(self.sender and self.password and self.receiver)

    def send_vision_report(self, subject: str, html_content: str):
        if not self.can_send():
            print("⚠️ إعدادات الإيميل غير مكتملة في config.py أو .env")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender
            msg['To'] = self.receiver

            # إضافة المحتوى بتنسيق HTML
            part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(part)

            # الاتصال بـ Gmail SMTP Server
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.receiver, msg.as_string())
            
            print("✅ تم إرسال تقرير الرؤية عبر الإيميل بنجاح.")
            return True
        except Exception as e:
            print(f"❌ فشل إرسال تقرير الإيميل: {e}")
            return False
