import requests

class Notifier:

    def __init__(self, token, chat_id):

        self.token = token

        self.chat_id = chat_id

        self.url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, message):

        data = {

            "chat_id": self.chat_id,

            "text": message,

            "parse_mode": "HTML"

        }

        try:

            response = requests.post(self.url, data=data)

            if response.status_code == 200:

                print("تم إرسال التنبيه")

            else:

                print("خطأ في إرسال التنبيه:", response.text)

        except Exception as e:

            print("خطأ:", e)

if __name__ == "__main__":

    TOKEN = "8277810569:AAGlwrch1o2qp0uWG-ZjFIki37x2qjXFJMQ"

    CHAT_ID = "82483873"

    notifier = Notifier(TOKEN, CHAT_ID)

    notifier.send("البوت شغال وجاهز للتداول")

