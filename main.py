@app.get("/check")
def check_inbox_endpoint():
  """This route checks your email when called by the cloud timer."""
  try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(BOT_EMAIL, BOT_PASSWORD)
    mail.select("inbox")

    # Fetch all unread messages safely without complex IMAP query strings
    status, messages = mail.search(None, "UNREAD")
    processed_count = 0

    for num in messages[0].split():
      status, data = mail.fetch(num, "(RFC822)")
      for response_part in data:
        if isinstance(response_part, tuple):
          msg = email.message_from_bytes(response_part[1])
          sender_header = msg.get("From", "")

          # Optional safety check: Ensure it's coming from your personal email
          if MY_PERSONAL_EMAIL and MY_PERSONAL_EMAIL.lower() not in sender_header.lower():
            continue  # Skip emails from other senders

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
          # Mark as read so it doesn't process again
          mail.store(num, "+FLAGS", "\\Seen")
          processed_count += 1

    mail.logout()
    return {"success": True, "processed_tasks": processed_count}
  except Exception as e:
    return {"success": False, "error": str(e)}
