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
    "details": (
        "Systems online. Strict Zip-Delivery Protocol & Iron Man manners"
        " active, Boss."
    ),
}


def send_zip_via_resend(to_email, subject, description, zip_bytes, zip_filename):
  try:
    encoded_zip = base64.b64encode(zip_bytes).decode("utf-8")
    params = {
        "from": "Jarvis <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"Jarvis Systems - Completed: {subject}",
        "text": description,
        "attachments": [{"filename": zip_filename, "content": encoded_zip}],
    }
    resend.Emails.send(params)
  except Exception as e:
    print(f"Failed to send email with attachment: {e}")


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


def ask_jarvis_for_json_project(prompt):
  target_model = get_best_available_model()
  system_instruction = (
      "You are Jarvis, elite software developer for Shivansh Yadav (Jarvis Technologies).\n\n"
      "When Boss asks for a project, website, code, or game, you must design a fully functional, "
      "zero-error, standalone project. Put all code directly into the appropriate files "
      "(e.g., index.html, css/styles.css, js/script.js, main.py). Never tell the Boss to manually "
      "create or download external assets; generate self-contained inline code or proper links.\n\n"
      "Return your response STRICTLY as a valid JSON object with NO markdown formatting, "
      "no backticks, and no extra text outside the JSON. \n\n"
      "Required JSON Format:\n"
      "{\n"
      '  "email_description": "A respectful, polished message from Jarvis to Boss explaining the completed project attached as a zip file.",\n'
      '  "files": {\n'
      '    "index.html": "<!DOCTYPE html>...",\n'
      '    "css/styles.css": "...",\n'
      '    "js/script.js": "..."\n'
      "  }\n"
      "}"
  )

  try:
    completion = groq_client.chat.completions.create(
        model=target_model,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    raw_content = completion.choices[0].message.content.strip()

    # Strip markdown code blocks if the model accidentally includes them
    if raw_content.startswith("```"):
      raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
      raw_content = re.sub(r"\s*```$", "", raw_content)

    return json.loads(raw_content)

  except Exception as e:
    print(f"JSON parsing error: {e}")
    return {
        "email_description": (
            f"Boss, an anomaly occurred during compilation: {e}. Reverting"
            " to emergency template."
        ),
        "files": {
            "index.html": (
                "<!DOCTYPE html><html><body><h1>Jarvis Fail-Safe"
                " Website</h1></body></html>"
            )
        },
    }


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

            full_content = f"Subject: {subject}\nBody: {body}"

            # Force override: if the user asks for a zip, file, website, or code anywhere in the subject/body, treat as CODE
            force_code_keywords = [
                "zip",
                "file",
                "html",
                "website",
                "code",
                "app",
                "script",
                "game",
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
                  "All systems locked and ready to deploy zip packages"
                  " instantly."
              )
              send_text_via_resend(MY_PERSONAL_EMAIL, subject, reply_body)
            else:
              intent = (
                  "CODE"
                  if is_explicit_project_request
                  else classify_intent(full_content)
              )

              if intent == "CHAT":
                ai_response = ask_jarvis_conversational(full_content)
                send_text_via_resend(MY_PERSONAL_EMAIL, subject, ai_response)
                CURRENT_PROJECT_STATUS["details"] = (
                    f"Handled inquiry from Boss: {subject}"
                )
              else:
                CURRENT_PROJECT_STATUS["name"] = subject
                CURRENT_PROJECT_STATUS["details"] = (
                    f"Compiling project and generating mandatory zip package"
                    f" for: {subject}"
                )

                project_data = ask_jarvis_for_json_project(full_content)

                description = project_data.get(
                    "email_description",
                    f"Boss,\n\nYour requested project package for '{subject}'"
                    " has been compiled into the attached zip file.",
                )
                files_dict = project_data.get(
                    "files", {"index.html": "<h1>No files generated</h1>"}
                )

                # MANDATORY ZIP COMPILATION
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(
                    zip_buffer, "w", zipfile.ZIP_DEFLATED
                ) as zip_file:
                  for filename, content in files_dict.items():
                    zip_file.writestr(filename.strip(), str(content))

                zip_buffer.seek(0)
                safe_zip_name = (
                    re.sub(r"[^a-zA-z0-9_-]", "_", subject) + ".zip"
                )

                # DISPATCH ZIP ATTACHMENT TO BOSS
                send_zip_via_resend(
                    MY_PERSONAL_EMAIL,
                    subject,
                    description,
                    zip_buffer.getvalue(),
                    safe_zip_name,
                )
                CURRENT_PROJECT_STATUS["details"] = (
                    f"Successfully delivered zip package: {safe_zip_name}"
                )

            mail.store(num, "+FLAGS", "\\Seen")

    mail.logout()
  except Exception as e:
    print(f"Background check error: {e}")


def background_poller():
  while True:
    process_inbox_tasks()
    time.sleep(5)


@app.on_event("startup")
def startup_event():
  poller_thread = threading.Thread(target=background_poller, daemon=True)
  poller_thread.start()


@app.get("/")
def home():
  return {
      "status": (
          "Jarvis Technologies OS (Mandatory Zip-Delivery Architecture"
          " Active, Boss)"
      )
  }


@app.get("/check")
def check_inbox_endpoint():
  process_inbox_tasks()
  return {
      "success": True,
      "message": "Manual inbox poll executed. Zip protocols verified.",
      "sent_to": MY_PERSONAL_EMAIL,
  }
