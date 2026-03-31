from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import requests
import pdfplumber
import io
import os
import re
import sys

# Add parent directory to path to import screener_logic
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Try extracting logic from the existing screener_logic.py
try:
    from screener_logic import (
        extract_name, extract_email, extract_phone_number, extract_location,
        extract_skills_from_text, extract_education, extract_work_history,
        generate_llm_hr_summary, normalize_text, load_skill_library
    )
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import screener_logic: {e}")
    # We must raise this to stop the app and see the error in logs, otherwise it crashes later with NameError
    raise e

router = APIRouter()

# Load skills once
SKILL_LIBRARY = load_skill_library("../skills_library.txt")

class AnalyzeRequest(BaseModel):
    resume_url: str
    job_description: str

class AnalysisResult(BaseModel):
    candidate_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    score: float
    summary: str
    matched_skills: List[str]
    missing_skills: List[str]
    strengths: List[str]
    weaknesses: List[str]
    education: str
    years_experience: float

def download_file(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    raise HTTPException(status_code=400, detail="Could not download resume from provided URL")

def extract_text_from_pdf_bytes(file_bytes):
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

@router.post("/analyze", response_model=AnalysisResult)
async def analyze_resume(request: AnalyzeRequest):
    try:
        # 1. Download Resume
        file_bytes = download_file(request.resume_url)
        
        # 2. Extract Text
        text = extract_text_from_pdf_bytes(file_bytes)
        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
            
        # 3. Analyze (Using Logic from screener_logic.py)
        name = extract_name(text) or "Unknown Candidate"
        email = extract_email(text)
        phone = extract_phone_number(text)
        
        # Skill Matching
        resume_skills = set(extract_skills_from_text(text, SKILL_LIBRARY))
        jd_skills = set(extract_skills_from_text(request.job_description, SKILL_LIBRARY))
        
        matched_skills = list(resume_skills.intersection(jd_skills))
        missing_skills = list(jd_skills - resume_skills)
        
        # Simple Scoring Logic (Replace with your deep ML model if needed)
        score = 0.0
        if jd_skills:
            score = (len(matched_skills) / len(jd_skills)) * 100
        
        # Education & Experience
        education = extract_education(text)
        # Simplified experience calc for demo (screener_logic has complex one)
        experience = 0.0 
        
        # AI Summary (using the rule-based generator from logic)
        summary = generate_llm_hr_summary(
            name, score, experience, matched_skills, missing_skills, 
            cgpa=0.0, job_domain="general", tone="Professional"
        )
        
        return AnalysisResult(
            candidate_name=name,
            email=email,
            phone=phone,
            score=min(score, 100.0),
            summary=summary,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            strengths=matched_skills[:5], # Top 5 matched
            weaknesses=missing_skills[:5], # Top 5 missing
            education=education,
            years_experience=experience
        )

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
