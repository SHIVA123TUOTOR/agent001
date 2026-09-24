import base64
import email
import email.policy
import io
import imaplib
import json
import os
import re
import urllib.request
import zipfile
from fastapi import FastAPI
from google import genai

app = FastAPI()

IMAP_SERVER = "imap.gmail.com"
BOT_EMAIL = os.environ.get("BOT_EMAIL")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")
MY_PERSONAL_EMAIL = os.environ.get("MY_PERSONAL_EMAIL")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

CURRENT_PROJECT_STATUS = {
    "name": "No active project",
    "details": "Waiting for your first task email.",
}


def send_zip_via_resend(to_email, subject, description, zip_bytes, zip_filename):
  try:
    encoded_zip = base64.b64encode(zip_bytes).decode("utf-8")
    payload = {
        "from": "Jarvis <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"Jarvis Completed: {subject}",
        "text": description,
        "attachments": [{"filename": zip_filename, "content": encoded_zip}],
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
      response.read()
  except Exception as e:
    print(f"Cloud Email Error: {e}")


def send_text_via_resend(to_email, subject, body):
  try:
    payload = {
        "from": "Jarvis <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"Re: {subject}",
        "text": body,
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
      response.read()
  except Exception as e:
    print(f"Cloud Status Email Error: {e}")


def ask_jarvis_for_project(prompt):
  try:
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=(
            "You are Jarvis, an elite personal AI software developer. "
            f"The user requested this project/task: {prompt}\n\n"
            "Build a complete, working project. Separate your files using this exact format:\n"
            "=== FILE: filename.ext ===\n"
            "[file code/content here]\n"
            "==========================\n"
            "Provide all necessary files (e.g., main.py, requirements.txt, README.md)."
        ),
    )
    return response.text
  except Exception as e:
    return f"=== FILE: error.txt ===\nError with AI brain: {e}\n=========================="


@app.get("/")
def home():
  return {"status": "Jarvis Cloud Mail & Zip Server is Online!"}


@app.get("/check")
def check_inbox_endpoint():
  global CURRENT_PROJECT_STATUS
  processed_count = 0

  try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(BOT_EMAIL, BOT_PASSWORD)
    mail.select("inbox")

    status, messages = mail.search(None, "UNSEEN")

    if status == "OK" and messages[0]:
      for num in messages[0].split():
        status, data = mail.fetch(num, "(RFC822)")
        for response_part in data:
          if isinstance(response_part, tuple):
            msg = email.message_from_bytes(
                response_part[1], policy=email.policy.default
            )
            subject = msg["subject"] or "Untitled Project"
            subject_lower = subject.lower()

            body = ""
            if msg.is_multipart():
              for part in msg.walk():
                if part.get_content_type() == "text/plain":
                  body = part.get_payload(decode=True).decode(errors="ignore")
            else:
              body = msg.get_payload(decode=True).decode(errors="ignore")

            if (
                "status" in subject_lower
                or "progress" in subject_lower
                or "what are you working on" in body.lower()
            ):
              reply_body = (
                  f"Active Project: {CURRENT_PROJECT_STATUS['name']}\n\n"
                  f"Status Details:\n{CURRENT_PROJECT_STATUS['details']}"
              )
              send_text_via_resend(MY_PERSONAL_EMAIL, subject, reply_body)
            else:
              CURRENT_PROJECT_STATUS["name"] = subject
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Generating code files for request: {body}"
              )

              raw_ai_output = ask_jarvis_for_project(body)

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
                  zip_file.writestr("project_output.txt", raw_ai_output)

              zip_buffer.seek(0)
              safe_zip_name = (
                  re.sub(r"[^a-zA-Z0-9_-]", "_", subject) + ".zip"
              )

              description = (
                  f"Hello! Here is the completed project you requested.\n\n"
                  f"Project Name: {subject}\n"
                  f"Original Request: {body}\n\n"
                  f"All structured code files have been zipped and attached to this email."
              )

              send_zip_via_resend(
                  MY_PERSONAL_EMAIL,
                  subject,
                  description,
                  zip_buffer.getvalue(),
                  safe_zip_name,
              )
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Successfully completed and emailed zip: {safe_zip_name}"
              )

            mail.store(num, "+FLAGS", "\\Seen")
            processed_count += 1

    mail.logout()
    return {"success": True, "processed_tasks": processed_count}
  except Exception as e:
    return {"success": False, "error": str(e)}
