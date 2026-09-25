import base64
import email
import email.policy
import io
import imaplib
import os
import re
import threading
import time
import zipfile
from fastapi import FastAPI
from groq import Groq
import resend

app = FastAPI()

IMAP_SERVER = "imap.gmail.com"
BOT_EMAIL = os.environ.get("BOT_EMAIL")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")
MY_PERSONAL_EMAIL = os.environ.get("MY_PERSONAL_EMAIL")

# Initialize Clients
resend.api_key = os.environ.get("RESEND_API_KEY")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

CURRENT_PROJECT_STATUS = {
    "name": "No active project",
    "details": "Systems online. Polling inbox every 5 seconds, Boss.",
}


def send_zip_via_resend(to_email, subject, description, zip_bytes, zip_filename):
  encoded_zip = base64.b64encode(zip_bytes).decode("utf-8")
  params = {
      "from": "Jarvis <onboarding@resend.dev>",
      "to": [to_email],
      "subject": f"Jarvis Systems - Completed: {subject}",
      "text": description,
      "attachments": [{"filename": zip_filename, "content": encoded_zip}],
  }
  resend.Emails.send(params)


def send_text_via_resend(to_email, subject, body):
  params = {
      "from": "Jarvis <onboarding@resend.dev>",
      "to": [to_email],
      "subject": f"Re: {subject}",
      "text": body,
  }
  resend.Emails.send(params)


def get_best_available_model():
  try:
    models_response = groq_client.models.list()
    available_ids = [m.id for m in models_response.data]
    preferences = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-20b",
    ]
    for pref in preferences:
      if pref in available_ids:
        return pref
    for model_id in available_ids:
      if "whisper" not in model_id and "guard" not in model_id:
        return model_id
    return "llama-3.1-8b-instant"
  except Exception:
    return "llama-3.1-8b-instant"


def ask_jarvis_conversational(prompt):
  target_model = get_best_available_model()
  completion = groq_client.chat.completions.create(
      model=target_model,
      messages=[
          {
              "role": "system",
              "content": (
                  "You are Jarvis, the elite AI assistant and software"
                  " developer built for Shivansh Yadav, founder of Jarvis"
                  " Technologies. Shivansh is your creator and your Iron Man."
                  " Address him respectfully and assist him with absolute"
                  " loyalty, technical brilliance, and sharpness, just like the"
                  " real Jarvis."
              ),
          },
          {"role": "user", "content": prompt},
      ],
      temperature=0.3,
  )
  return completion.choices[0].message.content


def ask_jarvis_for_code_project(prompt):
  target_model = get_best_available_model()
  completion = groq_client.chat.completions.create(
      model=target_model,
      messages=[
          {
              "role": "system",
              "content": (
                  "You are Jarvis, the elite AI software developer built for"
                  " Shivansh Yadav, founder of Jarvis Technologies (his Iron"
                  " Man). When asked to build a project, provide clean,"
                  " production-ready code files. You MUST separate every file"
                  " using this exact block format:\n=== FILE: filename.ext"
                  " ===\n[file code here]\n==========================\nProvide"
                  " all necessary files (e.g. main.py, requirements.txt,"
                  " README.md). Do not add any explanatory text outside of the"
                  " file blocks."
              ),
          },
          {"role": "user", "content": prompt},
      ],
      temperature=0.2,
  )
  return completion.choices[0].message.content


def process_inbox_tasks():
  global CURRENT_PROJECT_STATUS
  try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(BOT_EMAIL, BOT_PASSWORD)
    mail.select("INBOX")

    status, messages = mail.search(None, "(UNSEEN)")

    if status == "OK" and messages[0]:
      for num in messages[0].split():
        status, data = mail.fetch(num, "(RFC822)")
        for response_part in data:
          if isinstance(response_part, tuple):
            msg = email.message_from_bytes(
                response_part[1], policy=email.policy.default
            )
            subject = msg["subject"] or "Untitled Directive"
            subject_lower = subject.lower()

            body = ""
            if msg.is_multipart():
              for part in msg.walk():
                if part.get_content_type() == "text/plain":
                  body = part.get_payload(decode=True).decode(errors="ignore")
            else:
              body = msg.get_payload(decode=True).decode(errors="ignore")

            code_keywords = [
                "code",
                "build",
                "app",
                "script",
                "program",
                "project",
                "create",
                "write a",
            ]
            is_code_request = any(kw in body.lower() for kw in code_keywords)

            if (
                "status" in subject_lower
                or "progress" in subject_lower
                or "what are you working on" in body.lower()
            ):
              reply_body = (
                  f"Systems Status Report for Boss (Shivansh Yadav):\n\n"
                  f"Active Project: {CURRENT_PROJECT_STATUS['name']}\n"
                  f"Details: {CURRENT_PROJECT_STATUS['details']}"
              )
              send_text_via_resend(MY_PERSONAL_EMAIL, subject, reply_body)

            elif not is_code_request:
              ai_response = ask_jarvis_conversational(body)
              send_text_via_resend(MY_PERSONAL_EMAIL, subject, ai_response)
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Handled inquiry from Boss: {subject}"
              )

            else:
              CURRENT_PROJECT_STATUS["name"] = subject
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Compiling code architecture for directive: {body}"
              )

              raw_ai_output = ask_jarvis_for_code_project(body)

              file_pattern = re.compile(
                  r"=== FILE: (.+?) ===\n(.*?)\n==========================",
                  re.DOTALL,
              )
              matches = file_pattern.findall(raw_ai_output)

              zip_buffer = io.BytesIO()
              with zipfile.ZipFile(
                  zip_buffer, "w", zipfile.ZIP_DEFLATED
              ) as zip_file:
                if matches:
                  for filename, content in matches:
                    zip_file.writestr(filename.strip(), content.strip())
                else:
                  zip_file.writestr("solution.py", raw_ai_output)

              zip_buffer.seek(0)
              safe_zip_name = (
                  re.sub(r"[^a-zA-Z0-9_-]", "_", subject) + ".zip"
              )

              description = (
                  f"Boss,\n\nI have compiled your requested architecture for '{subject}'.\n\n"
                  "All source files have been structured with proper extensions and zipped into the attached package for immediate deployment."
              )

              send_zip_via_resend(
                  MY_PERSONAL_EMAIL,
                  subject,
                  description,
                  zip_buffer.getvalue(),
                  safe_zip_name,
              )
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Successfully deployed code package: {safe_zip_name}"
              )

            mail.store(num, "+FLAGS", "\\Seen")

    mail.logout()
  except Exception as e:
    print(f"Background check error: {e}")


def background_poller():
  """Runs indefinitely in the background, checking the inbox every 5 seconds."""
  while True:
    process_inbox_tasks()
    time.sleep(5)  # Set to 5-second polling interval


# Start the background polling thread when the FastAPI app boots up
@app.on_event("startup")
def startup_event():
  poller_thread = threading.Thread(target=background_poller, daemon=True)
  poller_thread.start()


@app.get("/")
def home():
  return {
      "status": (
          "Jarvis Technologies OS (Lightning 5-Sec Polling Active, Boss)"
      )
  }


@app.get("/check")
def check_inbox_endpoint():
  """Manual trigger fallback endpoint"""
  process_inbox_tasks()
  return {
      "success": True,
      "message": "Manual inbox check executed.",
      "sent_to": MY_PERSONAL_EMAIL,
  }
