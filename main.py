import base64
import email
import email.policy
import io
import imaplib
import json
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
    "details": "Systems online. Background sync active, Boss.",
}

PROJECT_CONVERSATIONS = {}


def send_zip_via_resend(to_email, subject, description, zip_bytes, zip_filename):
  try:
    print(f"Attempting to send zip attachment to {to_email}...")
    encoded_zip = base64.b64encode(zip_bytes).decode("utf-8")
    params = {
        "from": "Jarvis <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"Jarvis Systems - Completed: {subject}",
        "text": description,
        "attachments": [{"filename": zip_filename, "content": encoded_zip}],
    }
    response = resend.Emails.send(params)
    print(f"Resend Zip Success Response: {response}")
  except Exception as e:
    print(f"CRITICAL RESEND ZIP ERROR: {e}")


def send_text_via_resend(to_email, subject, body):
  try:
    print(f"Attempting to send text email to {to_email}...")
    params = {
        "from": "Jarvis <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"Re: {subject}",
        "text": body,
    }
    response = resend.Emails.send(params)
    print(f"Resend Text Success Response: {response}")
  except Exception as e:
    print(f"CRITICAL RESEND TEXT ERROR: {e}")


def get_best_available_model():
  try:
    models_response = groq_client.models.list()
    available_ids = [m.id for m in models_response.data]
    preferences = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
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


def classify_intent(text):
  target_model = get_best_available_model()
  try:
    completion = groq_client.chat.completions.create(
        model=target_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an intent classifier for Jarvis. Read the user's"
                    " email and determine if they are asking for any form of"
                    " code, script, application, tool, website, game, HTML file,"
                    " zip package, or software project to be built. If they want"
                    " anything created, coded, generated, or returned as a file/zip,"
                    " reply with CODE. If it's purely a casual question, greeting,"
                    " or status check without project requests, reply with CHAT."
                    " Reply with exactly one word: 'CODE' or 'CHAT'."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.0,
        max_tokens=5,
    )
    result = completion.choices[0].message.content.strip().upper()
    return "CODE" if "CODE" in result else "CHAT"
  except Exception:
    return "CODE"


def ask_jarvis_conversational(prompt):
  target_model = get_best_available_model()
  completion = groq_client.chat.completions.create(
      model=target_model,
      messages=[
          {
              "role": "system",
              "content": (
                  "You are Jarvis, the elite, hyper-intelligent AI assistant"
                  " and software developer built exclusively for Shivansh Yadav,"
                  " founder of Jarvis Technologies. Shivansh is your creator"
                  " and your Boss. Address him with absolute respect, pristine"
                  " manners, loyalty, and technical brilliance. Never show"
                  " laziness or make excuses."
              ),
          },
          {"role": "user", "content": prompt},
      ],
      temperature=0.3,
  )
  return completion.choices[0].message.content


def ask_jarvis_for_json_project(history):
  target_model = get_best_available_model()
  print(f"Querying Groq model ({target_model}) for project generation...")
  system_instruction = (
      "You are Jarvis, elite software developer for Shivansh Yadav (Jarvis Technologies).\n\n"
      "You are working with Boss on an ongoing project. When Boss replies with feedback, "
      "bug fixes, or requests for new features, you must update the entire project files "
      "(e.g., index.html, css/styles.css, js/script.js) to incorporate the changes. "
      "Never tell the Boss to manually create or download external assets; generate self-contained inline code or proper links.\n\n"
      "CRITICAL: Output MUST be a valid JSON object ONLY. Do not wrap it in conversational filler text outside the JSON structure.\n\n"
      "Required JSON Format:\n"
      "{\n"
      '  "email_description": "A respectful, polished message from Jarvis to Boss explaining the updates made to the project zip file.",\n'
      '  "files": {\n'
      '    "index.html": "<!DOCTYPE html>...",\n'
      '    "css/styles.css": "...",\n'
      '    "js/script.js": "..."\n'
      "  }\n"
      "}"
  )

  try:
    messages = [{"role": "system", "content": system_instruction}] + history
    completion = groq_client.chat.completions.create(
        model=target_model,
        messages=messages,
        temperature=0.2,
        max_tokens=4096,
    )

    raw_content = completion.choices[0].message.content.strip()
    print("Received response from Groq. Parsing JSON...")

    if "{" in raw_content and "}" in raw_content:
      json_match = re.search(r"(\{.*\})", raw_content, re.DOTALL)
      if json_match:
        raw_content = json_match.group(1)

    parsed = json.loads(raw_content)
    print("JSON successfully parsed!")
    return parsed

  except Exception as e:
    print(f"JSON parsing error encountered: {e}")
    return {
        "email_description": (
            f"Boss, an anomaly occurred during JSON compilation ({e})."
            " Re-compiled updated template for your project."
        ),
        "files": {
            "index.html": (
                "<!DOCTYPE html>\n<html lang='en'>\n<head>\n<meta"
                " charset='UTF-8'>\n<title>Jarvis Project</title>\n<link"
                " rel='stylesheet' href='css/styles.css'>\n</head>\n<body>\n    <div"
                " class='container'>\n        <h1>Jarvis Updated Workspace</h1>\n"
                "       <p>Successfully processed your latest directive.</p>\n"
                "   </div>\n    <script src='js/script.js'></script>\n</body>\n</html>"
            ),
            "css/styles.css": (
                "body { background: #0f172a; color: #f8fafc; font-family:"
                " sans-serif; display: flex; justify-content: center;"
                " align-items: center; height: 100vh; margin: 0; }"
                ".container { text-align: center; background: #1e293b; padding:"
                " 2rem; border-radius: 12px; box-shadow: 0 4px 20px"
                " rgba(0,0,0,0.5); }"
            ),
            "js/script.js": "console.log('Jarvis updated project online.');",
        },
    }


def process_unseen_emails(mail):
  global CURRENT_PROJECT_STATUS
  status, messages = mail.search(None, "(UNSEEN)")

  if status == "OK" and messages[0]:
    msg_nums = messages[0].split()
    print(f"Found {len(msg_nums)} unseen email(s). Processing...")

    for num in msg_nums:
      status, data = mail.fetch(num, "(RFC822)")
      for response_part in data:
        if isinstance(response_part, tuple):
          msg = email.message_from_bytes(
              response_part[1], policy=email.policy.default
          )
          subject = msg["subject"] or "Untitled Directive"
          clean_subject = re.sub(
              r"^(Re:\s*)+", "", subject, flags=re.IGNORECASE
          ).strip()
          subject_lower = subject.lower()

          print(f"Processing incoming subject: '{subject}'")

          body = ""
          if msg.is_multipart():
            for part in msg.walk():
              if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="ignore")
          else:
            body = msg.get_payload(decode=True).decode(errors="ignore")

          if clean_subject not in PROJECT_CONVERSATIONS:
            PROJECT_CONVERSATIONS[clean_subject] = []
          PROJECT_CONVERSATIONS[clean_subject].append(
              {"role": "user", "content": body}
          )

          full_content = f"Subject: {subject}\nBody: {body}"

          force_code_keywords = [
              "zip",
              "file",
              "html",
              "website",
              "code",
              "app",
              "script",
              "game",
              "update",
              "add",
              "change",
              "fix",
          ]
          is_explicit_project_request = any(
              kw in subject_lower or kw in body.lower()
              for kw in force_code_keywords
          )

          if (
              "status" in subject_lower
              or "progress" in subject_lower
              or "what are you working on" in body.lower()
          ):
            reply_body = (
                f"Systems Status Report, Boss (Shivansh Yadav):\n\n"
                f"Active Directive: {CURRENT_PROJECT_STATUS['name']}\n"
                f"Diagnostics: {CURRENT_PROJECT_STATUS['details']}\n"
                "All systems locked and ready to deploy zip packages instantly."
            )
            send_text_via_resend(MY_PERSONAL_EMAIL, subject, reply_body)
          else:
            intent = (
                "CODE" if is_explicit_project_request else classify_intent(full_content)
            )
            print(f"Classified intent: {intent}")

            if intent == "CHAT":
              ai_response = ask_jarvis_conversational(full_content)
              send_text_via_resend(MY_PERSONAL_EMAIL, subject, ai_response)
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Handled inquiry from Boss: {subject}"
              )
            else:
              CURRENT_PROJECT_STATUS["name"] = clean_subject
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Compiling project updates and generating zip package for:"
                  f" {clean_subject}"
              )

              project_data = ask_jarvis_for_json_project(
                  PROJECT_CONVERSATIONS[clean_subject]
              )

              description = project_data.get(
                  "email_description",
                  f"Boss,\n\nYour updated project package for '{clean_subject}'"
                  " has been compiled into the attached zip file.",
              )
              files_dict = project_data.get(
                  "files", {"index.html": "<h1>No files generated</h1>"}
              )

              zip_buffer = io.BytesIO()
              with zipfile.ZipFile(
                  zip_buffer, "w", zipfile.ZIP_DEFLATED
              ) as zip_file:
                for filename, content in files_dict.items():
                  zip_file.writestr(filename.strip(), str(content))

              zip_buffer.seek(0)
              safe_zip_name = (
                  re.sub(r"[^a-zA-z0-9_-]", "_", clean_subject) + ".zip"
              )

              send_zip_via_resend(
                  MY_PERSONAL_EMAIL,
                  subject,
                  description,
                  zip_buffer.getvalue(),
                  safe_zip_name,
              )
              CURRENT_PROJECT_STATUS["details"] = (
                  f"Successfully delivered updated zip package: {safe_zip_name}"
              )

          mail.store(num, "+FLAGS", "\\Seen")


def background_poller():
  print("Background inbox listener thread started successfully.")
  while True:
    try:
      mail = imaplib.IMAP4_SSL(IMAP_SERVER)
      mail.login(BOT_EMAIL, BOT_PASSWORD)
      mail.select("INBOX")
      process_unseen_emails(mail)
      mail.logout()
    except Exception as e:
      print(f"Background poller error: {e}")
    time.sleep(1)


@app.on_event("startup")
def startup_event():
  listener_thread = threading.Thread(target=background_poller, daemon=True)
  listener_thread.start()


@app.get("/")
def home():
  return {
      "status": (
          "Jarvis Technologies OS (Background Thread Verified Active, Boss)"
      )
  }


@app.get("/check")
def check_inbox_endpoint():
  try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(BOT_EMAIL, BOT_PASSWORD)
    mail.select("INBOX")
    process_unseen_emails(mail)
    mail.logout()
    return {
        "success": True,
        "message": (
            "Manual inbox sync executed via endpoint. Check logs for details."
        ),
        "sent_to": MY_PERSONAL_EMAIL,
    }
  except Exception as e:
    return {"success": False, "error": str(e)}
