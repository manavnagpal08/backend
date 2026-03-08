from fastapi import FastAPI
from pydantic import BaseModel
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EmailRequest(BaseModel):
    name: str
    email: str
    message: str
    category: str

class ApplicationEmailRequest(BaseModel):
    applicant_name: str
    applicant_email: str
    job_title: str
    company_name: str
    ai_score: float
    ai_decision: str

class InterviewAssignmentEmailRequest(BaseModel):
    candidate_name: str
    candidate_email: str
    topic: str
    company_name: str
    hr_name: str
    question_count: int
    interview_link: str
    assignment_id: str

@app.post("/send-email")
async def send_email(request: EmailRequest):
    sender_email = os.environ.get("EMAIL_USER", "screenerpro.ai@gmail.com")
    sender_password = os.environ.get("EMAIL_PASS", "udwi life nbdv kgdt")
    receiver_email = "screenerpro.ai@gmail.com"

    try:
        msg = MIMEMultipart()
        msg['From'] = f"ScreenerPro Feedback <{sender_email}>"
        msg['To'] = receiver_email
        msg['Subject'] = f"ScreenerPro Feedback: {request.category}"

        body = f"""
        New Feedback Received
        ---------------------
        Name: {request.name}
        Email: {request.email}
        Category: {request.category}
        
        Message:
        {request.message}
        """
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/send-application-email")
async def send_application_email(request: ApplicationEmailRequest):
    sender_email = os.environ.get("EMAIL_USER", "screenerpro.ai@gmail.com")
    sender_password = os.environ.get("EMAIL_PASS", "udwi life nbdv kgdt")

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Application Received — {request.job_title} at {request.company_name}"
        msg['From'] = f"ScreenerPro Careers <{sender_email}>"
        msg['To'] = request.applicant_email

        html_body = f"""
        <html>
          <body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Arial,sans-serif;">
            <div style="max-width:600px;margin:20px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
              <div style="background:linear-gradient(135deg,#2563eb,#1d4ed8);color:white;text-align:center;padding:30px 20px;">
                <h2 style="margin:0;">Application Received</h2>
                <p style="margin-top:5px;opacity:0.9;">{request.job_title} at {request.company_name}</p>
              </div>
              <div style="padding:30px;color:#374151;line-height:1.6;">
                <p>Dear {request.applicant_name},</p>
                <p>We've received your application for the <b>{request.job_title}</b> role.</p>
                <div style="background:#f9fafb;border:1px solid #e5e7eb;padding:15px;border-radius:10px;text-align:center;margin:20px 0;">
                  <div style="font-size:14px;color:#6b7280;">Your AI Match Score</div>
                  <div style="font-size:28px;font-weight:700;color:#059669;">{request.ai_score:.1f}%</div>
                  <div style="font-size:16px;font-weight:600;color:#065f46;">Decision: {request.ai_decision}</div>
                </div>
                <p>Our team will review your profile and get back to you soon.</p>
              </div>
              <div style="background:#f9fafb;padding:15px;text-align:center;font-size:12px;color:#6b7280;">
                © 2026 {request.company_name} Careers · Automated Message
              </div>
            </div>
          </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, request.applicant_email, msg.as_string())
        
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/send-interview-assignment-email")
async def send_interview_assignment_email(request: InterviewAssignmentEmailRequest):
    sender_email = os.environ.get("EMAIL_USER", "screenerpro.ai@gmail.com")
    sender_password = os.environ.get("EMAIL_PASS", "udwi life nbdv kgdt")

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Mock Interview Assigned - {request.topic}"
        msg['From'] = f"ScreenerPro Interviews <{sender_email}>"
        msg['To'] = request.candidate_email

        plain_body = f"""Hello {request.candidate_name},

You have been assigned a mock interview.

Company: {request.company_name}
Assigned by: {request.hr_name}
Topic: {request.topic}
Question Count: {request.question_count}
Assignment ID: {request.assignment_id}

Open interview:
{request.interview_link}

Please complete it at the earliest.
"""

        html_body = f"""
        <html>
          <body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif;">
            <div style="max-width:620px;margin:24px auto;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,0.12);">
              <div style="background:linear-gradient(135deg,#0f172a,#1d4ed8);padding:24px 20px;color:#ffffff;">
                <h2 style="margin:0;">Mock Interview Assigned</h2>
                <p style="margin:8px 0 0 0;opacity:0.9;">Topic: {request.topic}</p>
              </div>
              <div style="padding:24px;color:#1f2937;line-height:1.6;">
                <p>Hello <strong>{request.candidate_name}</strong>,</p>
                <p>You have received a new interview assignment.</p>
                <table style="width:100%;border-collapse:collapse;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;">
                  <tr><td style="padding:10px 12px;"><strong>Company</strong></td><td style="padding:10px 12px;">{request.company_name}</td></tr>
                  <tr><td style="padding:10px 12px;"><strong>Assigned by</strong></td><td style="padding:10px 12px;">{request.hr_name}</td></tr>
                  <tr><td style="padding:10px 12px;"><strong>Questions</strong></td><td style="padding:10px 12px;">{request.question_count}</td></tr>
                  <tr><td style="padding:10px 12px;"><strong>Assignment ID</strong></td><td style="padding:10px 12px;">{request.assignment_id}</td></tr>
                </table>
                <div style="margin-top:20px;text-align:center;">
                  <a href="{request.interview_link}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:10px;font-weight:700;">
                    Start Interview
                  </a>
                </div>
              </div>
              <div style="background:#f9fafb;padding:12px;text-align:center;font-size:12px;color:#6b7280;">
                Automated Interview Assignment Notice
              </div>
            </div>
          </body>
        </html>
        """

        msg.attach(MIMEText(plain_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, request.candidate_email, msg.as_string())

        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
