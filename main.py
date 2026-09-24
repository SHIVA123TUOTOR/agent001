import email
import email.policy
import io
import imaplib
import os
import re
import smtplib
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI
from google import genai

app = FastAPI()

IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465  # Port 465 bypasses Render's port 587 block

BOT_EMAIL = os.environ.get("BOT_EMAIL")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")
MY_PERSONAL_EMAIL = os.environ.get("MY_PERSONAL_EMAIL")

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Store current project state in memory
CURRENT_PROJECT_STATUS = {
    "name": "No active project",
    "details": "Waiting for your first task email.",
}


def send_zip_email(to_email, subject, description, zip_bytes, zip_filename):
  try:
    msg = MIMEMultipart()
    msg["From"] = BOT_EMAIL
    msg["To"] = to_email
    msg["Subject"] = f"Jarvis Completed: {subject}"

    # Attach description text
    msg.attach(MIMEText(description, "plain"))

    # Attach the Zip file
    zip_attachment = MIMEApplication(zip_bytes, Name=zip_filename)
    zip_attachment["Content-Disposition"] = (
        f'attachment; filename="{zip_filename}"'
    )
    msg.attach(zip_attachment)

    # Send via SMTP_SSL on port 465
    server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    server.login(BOT_EMAIL, BOT_PASSWORD)
    server.sendmail(BOT_EMAIL, to_email, msg.as_string())
    server.quit()
  except Exception as e:
    print(f"SMTP Error: {e}")


def ask_jarvis_for_project(prompt):
  try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
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
  return {"status": "Jarvis Mail & Zip Server is Online!"}


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

            # Extract email body text
            body = ""
            if msg.is_multipart():
              for part in msg.walk():
                if part.get_content_type() == "text/plain":
                  body = part.get_payload(decode=True).decode(errors="ignore")
            else:
              body = msg.get_payload(decode=True).decode(errors="ignore")

            # Check if user is asking for progress/status
            if (
                "status" in subject_lower
                or "progress" in subject_lower
                or "what are you working on" in body.lower()
            ):
              reply_body = (
                  f"Active Project: {CURRENT_PROJECT_STATUS['name']}\n\n"
                  f"Status Details:\n{CURRENT_PROJECT_STATUS['details']}"
              )
              status_msg = MIMEMultipart()
              status_msg["From"] = BOT_EMAIL
              status_msg["To"] = MY_PERSONAL_EMAIL
              status_msg["Subject"] = f"Re: {subject}"
              status_msg.attach(MIMEText(reply_body, "plain"))

              server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
              server.login(BOT_EMAIL, BOT_PASSWORD)
              server.sendmail(BOT_EMAIL, MY_PERSONAL_EMAIL, status_msg.as_string())
              server.quit()

            else:
              # Update current project state
              CURRENT_PROJECT_STATUS["name"] = subject
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Generating code files for request: {body}"
              )

              # Generate code structure from Gemini
              raw_ai_output = ask_jarvis_for_project(body)

              # Parse files using the === FILE: name === format
              file_pattern = re.compile(
                  r"=== FILE: (.+?) ===\n(.*?)\n==========================",
                  re.DOTALL,
              )
              matches = file_pattern.findall(raw_ai_output)

              # Create an in-memory zip file
              zip_buffer = io.BytesIO()
              with zipfile.ZipFile(
                  zip_buffer, "w", zipfile.ZIP_DEFLATED
              ) as zip_file:
                if matches:
                  for filename, content in matches:
                    zip_file.writestr(filename.strip(), content.strip())
                else:
                  # Fallback if AI didn't format cleanly
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

              # Send the zip file via email
              send_zip_email(
                  MY_PERSONAL_EMAIL,
                  subject,
                  description,
                  zip_buffer.getvalue(),
                  safe_zip_name,
              )

              CURRENT_PROJECT_STATUS["details"] = (
                  f"Successfully completed and emailed zip file: {safe_zip_name}"
              )

            # Mark email as read
            mail.store(num, "+FLAGS", "\\Seen")
            processed_count += 1

    mail.logout()
    return {"success": True, "processed_tasks": processed_count}
  except Exception as e:
    return {"success": False, "error": str(e)}
