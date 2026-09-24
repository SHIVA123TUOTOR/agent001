import email
import imaplib
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI
from google import genai

# 1. Initialize FastAPI app first
app = FastAPI()

# 2. Configurations & Environment Variables
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
BOT_EMAIL = os.environ.get("BOT_EMAIL")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")
MY_PERSONAL_EMAIL = os.environ.get("MY_PERSONAL_EMAIL")

# 3. Initialize Gemini Client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def ask_jarvis(prompt):
  try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            "You are Jarvis, an elite personal AI software developer. "
            "The user gave you this task/project request: "
            f"{prompt}\n\nWrite out the clean code structure, file names, and"
            " implementation guide."
        ),
    )
    return response.text
  except Exception as e:
    return f"Error with AI brain: {e}"


def send_email(subject, body):
  msg = MIMEMultipart()
  msg["From"] = BOT_EMAIL
  msg["To"] = MY_PERSONAL_EMAIL
  msg["Subject"] = f"Jarvis Report: {subject}"
  msg.attach(MIMEText(body, "plain"))

  server = smtplib.SMTP(SMTP_SERVER, 587)
  server.starttls()
  server.login(BOT_EMAIL, BOT_PASSWORD)
  server.sendmail(BOT_EMAIL, MY_PERSONAL_EMAIL, msg.as_string())
  server.quit()


# 4. API Routes
@app.get("/")
def home():
  return {"status": "Jarvis Cloud Server is Online!"}


@app.get("/check")
def check_inbox_endpoint():
  try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(BOT_EMAIL, BOT_PASSWORD)
    mail.select("inbox")

    # Use UNSEEN for standard Gmail IMAP unread filtering
    status, messages = mail.search(None, "UNSEEN")
    processed_count = 0

    if status == "OK" and messages[0]:
      for num in messages[0].split():
        status, data = mail.fetch(num, "(RFC822)")
        for response_part in data:
          if isinstance(response_part, tuple):
            msg = email.message_from_bytes(response_part[1])
            subject = msg["subject"] or "Untitled Project"

            body = ""
            if msg.is_multipart():
              for part in msg.walk():
                if part.get_content_type() == "text/plain":
                  body = part.get_payload(decode=True).decode(errors="ignore")
            else:
              body = msg.get_payload(decode=True).decode(errors="ignore")

            ai_result = ask_jarvis(body)
            send_email(subject, ai_result)
            mail.store(num, "+FLAGS", "\\Seen")
            processed_count += 1

    mail.logout()
    return {"success": True, "processed_tasks": processed_count}
  except Exception as e:
    return {"success": False, "error": str(e)}
