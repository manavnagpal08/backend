from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
import firebase_admin
from firebase_admin import auth, credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

import json

# Initialize Firebase Admin if not already initialized
try:
    if not firebase_admin._apps:
        # Check if JSON content is provided via environment variable (BEST FOR RENDER)
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        
        if service_account_json:
            # Parse the JSON string
            service_account_info = json.loads(service_account_json)
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
            print("Firebase Admin initialized via Environment Variable ✅")
        else:
            # Fallback to local file path (Development local machine)
            key_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "../flutter_app/serviceAccountKey.json")
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred)
                print(f"Firebase Admin initialized via local file: {key_path} ✅")
            else:
                print("⚠️ Firebase Admin NOT initialized: No JSON or file path found.")
except Exception as e:
    print(f"❌ Firebase Admin initialization error: {e}")

class VerificationRequest(BaseModel):
    email: EmailStr
    name: str

def send_glassmorphic_email(email: str, name: str, link: str):
    sender_email = os.getenv("EMAIL_USER", "screenerpro.ai@gmail.com")
    sender_password = os.getenv("EMAIL_PASS", "udwi life nbdv kgdt")
    
    if not sender_email or not sender_password:
        print("Email credentials not configured")
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Verification Protocol Required - ScreenerPro AI"
    msg['From'] = f"ScreenerPro Security <{sender_email}>"
    msg['To'] = email

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Inter:wght@400;600&display=swap');
            body {{ margin: 0; padding: 0; background-color: #020617; font-family: 'Inter', sans-serif; }}
            .container {{ max-width: 600px; margin: 40px auto; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius: 24px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }}
            .header {{ background: linear-gradient(90deg, #06b6d4 0%, #f97316 100%); padding: 40px 20px; text-align: center; }}
            .logo-icon {{ font-size: 48px; margin-bottom: 20px; }}
            .content {{ padding: 48px; color: #f8fafc; text-align: center; }}
            h1 {{ font-family: 'Syne', sans-serif; font-size: 28px; font-weight: 800; margin-bottom: 24px; color: #ffffff; letter-spacing: -0.5px; }}
            p {{ font-size: 16px; line-height: 1.7; color: #94a3b8; margin-bottom: 32px; }}
            .button {{ display: inline-block; padding: 18px 36px; background: #ffffff; color: #020617; text-decoration: none; border-radius: 14px; font-weight: 700; font-size: 14px; letter-spacing: 0.5px; text-transform: uppercase; transition: all 0.3s ease; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }}
            .footer {{ padding: 32px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05); background: rgba(0,0,0,0.2); }}
            .footer-text {{ font-size: 12px; color: #64748b; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo-icon">🚀</div>
                <div style="font-family: 'Syne', sans-serif; font-weight: 800; color: white; font-size: 24px;">SCREENERPRO AI</div>
            </div>
            <div class="content">
                <h1>Verification Protocol Initialized</h1>
                <p>Hello {name},<br><br>Your identity is being synchronized with our global intelligence network. To complete your security clearance and access the full potential of ScreenerPro AI, please verify your email address below.</p>
                <a href="{link}" class="button">Authorize Identity</a>
                <p style="font-size: 13px; margin-top: 32px; color: #475569;">If the button above doesn't work, copy and paste this link into your browser:<br><span style="color: #06b6d4;">{link}</span></p>
            </div>
            <div class="footer">
                <div class="footer-text">© 2026 ScreenerPro AI. Secured by Quantum Encryption.<br>New Delhi, India</div>
            </div>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, email, msg.as_string())
        print(f"Verification email sent to {email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

@router.post("/send-verification")
async def send_verification(request: VerificationRequest, background_tasks: BackgroundTasks):
    try:
        # Generate the official Firebase verification link
        link = auth.generate_email_verification_link(request.email)
        
        # Add email sending to background tasks so API responds immediately
        background_tasks.add_task(send_glassmorphic_email, request.email, request.name, link)
        
        return {"status": "success", "message": "Verification email queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
