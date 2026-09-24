import email
import imaplib
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI
from google import genai

app = FastAPI()

# Cloud configuration (These will be loaded securely from Render's settings)
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
BOT_EMAIL = os.environ.get("BOT_EMAIL")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")
MY_PERSONAL_EMAIL = os.environ.get("MY_PERSONAL_EMAIL")

# Initialize Gemini Client
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


@app.get("/")
def home():
  return {"status": "Jarvis Cloud Server is Online!"}


@app.get("/check")
def check_inbox_endpoint():
  """This route checks your email when called by the cloud timer."""
  try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(BOT_EMAIL, BOT_PASSWORD)
    mail.select("inbox")

    status, messages = mail.search(None, f'(UNREAD FROM "{MY_PERSONAL_EMAIL}")')
    processed_count = 0

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

          # Generate code via Gemini
          ai_result = ask_jarvis(body)
          # Send back report
          send_email(subject, ai_result)
          # Mark as read
          mail.store(num, "+FLAGS", "\\Seen")
          processed_count += 1

    mail.logout()
    return {"success": True, "processed_tasks": processed_count}
  except Exception as e:
    return {"success": False, "error": str(e)}
