import base64
import email
import email.policy
import io
import imaplib
import os
import re
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
    "details": "Waiting for your first task email.",
}


def send_zip_via_resend(to_email, subject, description, zip_bytes, zip_filename):
  encoded_zip = base64.b64encode(zip_bytes).decode("utf-8")
  params = {
      "from": "Jarvis <onboarding@resend.dev>",
      "to": [to_email],
      "subject": f"Jarvis Code: {subject}",
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
                  "You are Jarvis, an elite personal AI software developer and"
                  " assistant. Answer the user's questions clearly, helpfully,"
                  " and concisely via email."
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
                  "You are Jarvis, an elite personal AI software developer."
                  " When asked to build or write code for a project, provide"
                  " clean, production-ready code files. You MUST separate every"
                  " file using this exact block format:\n=== FILE:"
                  " filename.ext ===\n[file code here]\n==========================\nProvide"
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


@app.get("/")
def home():
  return {"status": "Jarvis Conversational & Code Server is Online!"}


@app.get("/check")
def check_inbox_endpoint():
  global CURRENT_PROJECT_STATUS
  processed_count = 0

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
            subject = msg["subject"] or "Untitled Request"
            subject_lower = subject.lower()

            body = ""
            if msg.is_multipart():
              for part in msg.walk():
                if part.get_content_type() == "text/plain":
                  body = part.get_payload(decode=True).decode(errors="ignore")
            else:
              body = msg.get_payload(decode=True).decode(errors="ignore")

            # Check if user is asking for code/project vs conversational reply
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
                  f"Active Project: {CURRENT_PROJECT_STATUS['name']}\n\n"
                  f"Status Details:\n{CURRENT_PROJECT_STATUS['details']}"
              )
              send_text_via_resend(MY_PERSONAL_EMAIL, subject, reply_body)

            elif not is_code_request:
              # Conversational question / answer response via email text
              ai_response = ask_jarvis_conversational(body)
              send_text_via_resend(MY_PERSONAL_EMAIL, subject, ai_response)
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Answered conversational email: {subject}"
              )

            else:
              # Code generation task -> parse files and attach zip
              CURRENT_PROJECT_STATUS["name"] = subject
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Writing code files for request: {body}"
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
                  # Fallback if pattern is slightly off
                  zip_file.writestr("solution.py", raw_ai_output)

              zip_buffer.seek(0)
              safe_zip_name = (
                  re.sub(r"[^a-zA-Z0-9_-]", "_", subject) + ".zip"
              )

              description = (
                  f"Hello Shivansh,\n\nHere is your requested code project: '{subject}'.\n\n"
                  "All structured source files have been extracted cleanly into separate files and zipped in the attachment for direct use."
              )

              send_zip_via_resend(
                  MY_PERSONAL_EMAIL,
                  subject,
                  description,
                  zip_buffer.getvalue(),
                  safe_zip_name,
              )
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Successfully completed and emailed code zip: {safe_zip_name}"
              )

            mail.store(num, "+FLAGS", "\\Seen")
            processed_count += 1

    mail.logout()
    return {
        "success": True,
        "processed_tasks": processed_count,
        "sent_to": MY_PERSONAL_EMAIL,
    }
  except Exception as e:
    return {"success": False, "error_details": str(e)}
