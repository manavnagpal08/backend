import re
import os
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer
import nltk
import collections
from sklearn.metrics.pairwise import cosine_similarity
import urllib.parse
import uuid
from io import BytesIO # Needed for extract_text_from_file
import pandas as pd # Needed for pd.notna in generate_llm_hr_summary
import random # Needed for random.choice in generate_llm_hr_summary
import traceback # Needed for detailed error logging in process_single_resume_logic

# --- OCR Specific Imports ---
from PIL import Image
import pytesseract

from pdf2image import convert_from_bytes
import shutil # For shutil.which in get_tesseract_cmd (though not used directly in this file, it's a utility for OCR setup)

# CRITICAL: Disable Hugging Face tokenizers parallelism to avoid deadlocks with ProcessPoolExecutor
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Global NLTK download check (should run once)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

# Define global constants (moved from screener.py)
MASTER_CITIES = set([
    "Bengaluru", "Mumbai", "Delhi", "Chennai", "Hyderabad", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
    "Chandigarh", "Kochi", "Coimbatore", "Nagpur", "Bhopal", "Indore", "Gurgaon", "Noida", "Surat", "Visakhapatnam",
    "Patna", "Vadodara", "Ghaziabad", "Ludhiana", "Agra", "Nashik", "Faridabad", "Meerut", "Rajkot", "Varanasi",
    "Srinagar", "Aurangabad", "Dhanbad", "Amritsar", "Allahabad", "Ranchi", "Jamshedpur", "Gwalior", "Jabalpur",
    "Vijayawada", "Jodhpur", "Raipur", "Kota", "Guwahati", "Thiruvananthapuram", "Mysuru", "Hubballi-Dharwad",
    "Mangaluru", "Belagavi", "Davangere", "Ballari", "Tumakuru", "Shivamogga", "Bidar", "Hassan", "Gadag-Betageri",
    "Chitradurga", "Udupi", "Kolar", "Mandya", "Chikkamagaluru", "Koppal", "Chamarajanagar", "Yadgir", "Raichur",
    "Kalaburagi", "Bengaluru Rural", "Dakshina Kannada", "Uttara Kannada", "Kodagu", "Chikkaballapur", "Ramanagara",
    "Bagalkot", "Gadag", "Haveri", "Vijayanagara", "Krishnagiri", "Vellore", "Salem", "Erode", "Tiruppur", "Madurai",
    "Tiruchirappalli", "Thanjavur", "Dindigad", "Kanyakumari", "Thoothukudi", "Tirunelveli", "Nagercoil", "Puducherry",
    "Panaji", "Margao", "Vasco da Gama", "Mapusa", "Ponda", "Bicholim", "Curchorem", "Sanquelim", "Valpoi", "Pernem",
    "Quepem", "Canacona", "Mormugao", "Sanguem", "Dharbandora", "Tiswadi", "Salcete", "Bardez",
    "London", "New York", "Paris", "Berlin", "Tokyo", "Sydney", "Toronto", "Vancouver", "Singapore", "Dubai",
    "San Francisco", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego",
    "Dallas", "San Jose", "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte", "Indianapolis",
    "Seattle", "Denver", "Washington D.C.", "Boston", "Nashville", "El Paso", "Detroit", "Oklahoma City",
    "Portland", "Las Vegas", "Memphis", "Louisville", "Baltimore", "Milwaukee", "Albuquerque", "Tucson",
    "Fresno", "Sacramento", "Mesa", "Atlanta", "Kansas City", "Colorado Springs", "Raleigh", "Miami", "Omaha",
    "Virginia Beach", "Long Beach", "Oakland", "Minneapolis", "Tulsa", "Wichita", "New Orleans", "Cleveland",
    "Tampa", "Honolulu", "Anaheim", "Santa Ana", "St. Louis", "Riverside", "Lexington", "Pittsburgh", "Cincinnati",
    "Anchorage", "Plano", "Newark", "Orlando", "Irvine", "Garland", "Hialeah", "Scottsdale", "North Las Vegas",
    "Chandler", "Laredo", "Chula Vista", "Madison", "Reno", "Buffalo", "Durham", "Rochester", "Winston-Salem",
    "St. Petersburg", "Jersey City", "Toledo", "Lincoln", "Greensboro", "Boise", "Richmond", "Stockton",
    "San Bernardino", "Des Moines", "Modesto", "Fayetteville", "Shreveport", "Akron", "Tacoma", "Aurora",
    "Oxnard", "Fontana", "Montgomery", "Little Rock", "Grand Rapids", "Springfield", "Yonkers", "Augusta",
    "Mobile", "Port St. Lucie", "Denton", "Spokane", "Chattanooga", "Worcester", "Providence", "Fort Lauderdale",
    "Chesapeake", "Fremont", "Baton Rouge", "Santa Clarita", "Birmingham", "Glendale", "Huntsville",
    "Salt Lake City", "Frisco", "McKinney", "Grand Prairie", "Overland Park", "Brownsville", "Killeen",
    "Pasadena", "Olathe", "Dayton", "Savannah", "Fort Collins", "Naples", "Gainesville", "Lakeland", "Sarasota",
    "Daytona Beach", "Melbourne", "Clearwater", "St. Augustine", "Key West", "Fort Myers", "Cape Coral",
    "Coral Springs", "Pompano Beach", "Miami Beach", "West Palm Beach", "Boca Raton", "Fort Pierce",
    "Port Orange", "Kissimmee", "Sanford", "Ocala", "Bradenton", "Palm Bay", "Deltona", "Largo",
    "Deerfield Beach", "Boynton Beach", "Coconut Creek", "Sunrise", "Plantation", "Davie", "Miramar",
    "Hollywood", "Pembroke Pines", "Coral Gables", "Doral", "Aventura", "Sunny Isles Beach", "North Miami",
    "Miami Gardens", "Homestead", "Cutler Bay", "Pinecrest", "Kendall", "Richmond Heights", "West Kendall",
    "East Kendall", "South Miami", "Sweetwater", "Opa-locka", "Florida City", "Golden Glades", "Leisure City",
    "Princeton", "West Perrine", "Naranja", "Goulds", "South Miami Heights", "Country Walk", "The Crossings",
    "Three Lakes", "Richmond West", "Palmetto Bay", "Palmetto Estates", "Perrine", "Cutler Ridge", "Westview",
    "Gladeview", "Brownsville", "Liberty City", "West Little River", "Pinewood", "Ojus", "Ives Estates",
    "Highland Lakes", "Sunny Isles Beach", "Golden Beach", "Bal Harbour", "Surfside", "Bay Harbor Islands",
    "Indian Creek", "North Bay Village", "Biscayne Park", "El Portal", "Miami Shores", "North Miami Beach",
    "Aventura"
])

# Job domain classifier
def detect_job_domain(jd_title, jd_text):
    text = (jd_title + " " + jd_text).lower()
    if any(k in text for k in ["accountant", "finance", "ca", "cpa", "audit", "tax", "financial"]):
        return "finance"
    elif any(k in text for k in ["data scientist", "analytics", "ml", "ai", "machine learning", "deep learning", "nlp", "computer vision"]):
        return "data_science"
    elif any(k in text for k in ["developer", "engineer", "react", "python", "java", "software", "web", "frontend", "backend", "fullstack"]):
        return "software"
    elif any(k in text for k in ["recruiter", "talent acquisition", "hr", "human resources", "people operations", "onboarding"]):
        return "hr"
    elif any(k in text for k in ["designer", "photoshop", "figma", "ux", "ui", "illustrator", "graphic"]):
        return "design"
    else:
        return "general"

# Load ML models once (without st.cache_resource)
# This model will be loaded when screener_logic.py is imported
try:
    global_sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    print(f"ERROR: Could not load SentenceTransformer model in screener_logic.py: {e}")
    global_sentence_model = None # Set to None if loading fails

# New function to load skill library (without st.error)
def load_skill_library(file_path="skills_library.txt"):
    """Loads a list of skills from a text file, one skill per line."""
    if not os.path.exists(file_path):
        print(f"ERROR: {file_path} not found. Skills library will be empty.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip().lower() for line in f if line.strip()]

# New skill extraction function
def extract_skills_from_text(text, skill_library):
    """
    Extracts skills from text by checking for their presence in the provided skill_library.
    This performs a simple substring check.
    """
    text = text.lower()
    found_skills = set()
    # Prioritize multi-word skills first to avoid partial matches
    sorted_skill_library = sorted(skill_library, key=len, reverse=True)
    for skill in sorted_skill_library:
        # Use regex with word boundaries to ensure whole word match
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text):
            found_skills.add(skill)
    return list(found_skills)


# Pre-compile regex patterns for efficiency
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.\w+')
PHONE_PATTERN = re.compile(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')
CGPA_PATTERN = re.compile(r'(?:cgpa|gpa|grade point average)\s*[:\s]*(\d+\.\d+)(?:\s*[\/of]{1,4}\s*(\d+\.\d+|\d+))?|(\d+\.\d+)(?:\s*[\/of]{1,4}\s*(\d+\.\d+|\d+))?\s*(?:cgpa|gpa)')
EXP_DATE_PATTERNS = [
    re.compile(r'(\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[,]*\s*\d{4})\s*(?:to|–|—|-)\s*(present|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[,]*\s*\d{4})', re.IGNORECASE),
    re.compile(r'(\b\d{4})\s*(?:to|–|—|-)\s*(present|\b\d{4})', re.IGNORECASE)
]
EXP_YEARS_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(\+)?\s*(year|yrs|years)\b')
EXP_FALLBACK_PATTERN = re.compile(r'experience[^\d]{0,10}(\d+(?:\.\d+)?)')
NAME_EXCLUDE_TERMS = {
    "linkedin", "github", "portfolio", "resume", "cv", "profile", "contact", "email", "phone",
    "mobile", "number", "tel", "telephone", "address", "website", "site", "social", "media",
    "url", "link", "blog", "personal", "summary", "about", "objective", "dob", "birth", "age",
    "nationality", "gender", "location", "city", "country", "pin", "zipcode", "state", "whatsapp",
    "skype", "telegram", "handle", "id", "details", "connection", "reach", "network", "www",
    "https", "http", "contactinfo", "connect", "reference", "references","fees","Bangalore, Karnataka",
    "resume", "cv", "curriculum vitae", "resume of", "cv of", "summary", "about",
    "objective", "declaration", "personal profile", "profile", "career objective",
    "introduction", "bio", "statement", "overview",

    # Education & academic
    "education", "qualifications", "academic", "certification", "certifications", "degree",
    "school", "college", "university", "diploma", "graduate", "graduation", "passed", "gpa",
    "cgpa", "marks", "percentage", "year", "pass", "exam", "results", "board",

    # Skills and tools
    "skills", "technical", "technologies", "tools", "software", "programming",
    "languages", "frameworks", "libraries", "databases", "methodologies", "platforms",
    "proficient", "knowledge", "experience", "exposure", "tools used", "framework",

    # Software/product/tool names (block spaCy NER mistakes)
    "zoom", "slack", "google", "microsoft", "excel", "word", "docs", "teams", "powerpoint",
    "notion", "jupyter", "linux", "windows", "android", "firebase", "oracle", "git", "github",
    "bitbucket", "jira", "confluence", "sheets", "trello", "figma", "canva", "sql", "mysql",
    "postgres", "mongodb", "hadoop", "spark", "kubernetes", "docker", "aws", "azure", "gcp",

    # Job/work section
    "experience", "internship", "work", "professional", "employment", "company",
    "role", "designation", "job", "project", "responsibilities", "position",
    "organization", "industry", "client", "team", "department",

    # Hobbies/extra
    "interests", "hobbies", "achievements", "awards", "activities", "extra curricular",
    "certified", "certificates", "participation", "strengths", "weaknesses", "languages known",

    # Location examples
    "bangalore", "delhi", "mumbai", "chennai", "hyderabad", "pune", "kolkata", "india",
    "remote", "new york", "california", "london", "tokyo", "berlin", "canada", "germany",

    # Misc
    "fees", "salary", "expected", "compensation", "passport", "visa", "availability",
    "notice period", "relocate", "relocation", "travel", "timing", "schedule", "full-time", "part-time",

    # Filler/common false-positive content
    "available", "required", "requested", "relevant", "coursework", "summary", "hello",
    "introduction", "dear", "regards", "thanks", "thank you", "please", "objective", "kindly"
}
# Re-enabled EDU_MATCH_PATTERN and EDU_FALLBACK_PATTERN for the new extract_education function
EDU_MATCH_PATTERN = re.compile(r'([A-Za-z0-9.,()&\-\s]+?(university|college|institute|school)[^–\n]{0,50}[–\-—]?\s*(expected\s*)?\d{4})', re.IGNORECASE)
EDU_FALLBACK_PATTERN = re.compile(r'([A-Za-z0-9.,()&\-\s]+?(b\.tech|m\.tech|b\.sc|m\.sc|bca|bba|mba|ph\.d)[^–\n]{0,50}\d{4})', re.IGNORECASE)

WORK_HISTORY_SECTION_PATTERN = re.compile(r'(?:experience|work history|employment history)\s*(\n|$)', re.IGNORECASE)
JOB_BLOCK_SPLIT_PATTERN = re.compile(r'\n(?=[A-Z][a-zA-Z\s,&\.]+(?:\s(?:at|@))?\s*[A-Z][a-zA-Z\s,&\.]*\s*(?:-|\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}))', re.IGNORECASE)
DATE_RANGE_MATCH_PATTERN = re.compile(r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4})\s*[-–]\s*(present|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4})', re.IGNORECASE)
TITLE_COMPANY_MATCH_PATTERN = re.compile(r'([A-Z][a-zA-Z\s,\-&.]+)\s+(?:at|@)\s+([A-Z][a-zA-Z\s,\-&.]+)')
COMPANY_TITLE_MATCH_PATTERN = re.compile(r'^([A-Z][a-zA-Z\s,\-&.]+),\s*([A-Z][a-zA-Z\s,\-&.]+)')
POTENTIAL_ORG_MATCH_PATTERN = re.compile(r'^[A-Z][a-zA-Z\s,\-&.]+')
PROJECT_SECTION_KEYWORDS = re.compile(r'(projects|personal projects|key projects|portfolio|selected projects|major projects|academic projects|relevant projects)\s*(\n|$)', re.IGNORECASE)
FORBIDDEN_TITLE_KEYWORDS = [
    'skills gained', 'responsibilities', 'reflection', 'summary',
    'achievements', 'capabilities', 'what i learned', 'tools used'
]
PROJECT_TITLE_START_PATTERN = re.compile(r'^[•*-]?\s*\d+[\).:-]?\s')
LANGUAGE_SECTION_PATTERN = re.compile(r'\b(languages|language skills|linguistic abilities|known languages)\s*[:\-]?\s*\n?', re.IGNORECASE)


# Keywords to ignore (education, extra)
EDUCATION_TERMS = {
    'education', 'b.tech', 'b.e', 'bachelor', 'xii', '10th', '12th',
    'school', 'cgpa', 'percentage', 'intermediate', 'class x', 'class xii',
    'graduation', 'degree', 'college', 'university', 'high school', 'gpa'
}

# Keywords that indicate experience
WORK_TERMS = {
    'intern', 'engineer', 'developer', 'consultant', 'manager', 'data analyst',
    'researcher', 'scientist', 'assistant', 'officer', 'specialist', 'freelancer',
    'technician', 'trainer', 'administrator'
}

# Regex patterns for date ranges
EXP_DATE_PATTERNS = [
    re.compile(r'(\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[,]*\s*\d{4})\s*(?:to|–|—|-)\s*(present|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[,]*\s*\d{4})', re.IGNORECASE),
    re.compile(r'(\b\d{4})\s*(?:to|–|—|-)\s*(present|\b\d{4})', re.IGNORECASE)
]

# Additional fallback numeric patterns
EXP_YEARS_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(\+)?\s*(year|yrs|years)\b')
EXP_FALLBACK_PATTERN = re.compile(r'experience[^\d]{0,10}(\d+(?:\.\d+)?)')

def normalize_text(text):
    text = text.lower()
    text = text.replace('–', '-').replace('—', '-').replace(' to ', ' - ')
    text = re.sub(r'[,:\n]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def extract_years_of_experience(text):
    text = normalize_text(text)
    now = datetime.now()
    total_months = 0

    for pattern in EXP_DATE_PATTERNS:
        for match in pattern.finditer(text):
            start_str, end_str = match.groups()
            span_start = match.start()
            surrounding_text = text[max(0, span_start - 100):span_start + 100]

            # Count only if it's near a work term and NOT education
            if any(w in surrounding_text for w in WORK_TERMS) and not any(e in surrounding_text for e in EDUCATION_TERMS):
                try:
                    start_date = datetime.strptime(start_str.strip().replace(',', ''), '%B %Y')
                except:
                    try:
                        start_date = datetime.strptime(start_str.strip().replace(',', ''), '%b %Y')
                    except:
                        try:
                            start_date = datetime(int(start_str.strip()), 1, 1)
                        except:
                            continue

                if end_str.lower().strip() == 'present':
                    end_date = now
                else:
                    try:
                        end_date = datetime.strptime(end_str.strip().replace(',', ''), '%B %Y')
                    except:
                        try:
                            end_date = datetime.strptime(end_str.strip().replace(',', ''), '%b %Y')
                        except:
                            try:
                                end_date = datetime(int(end_str.strip()), 12, 31)
                            except:
                                continue

                if start_date > now:
                    continue
                if end_date > now:
                    end_date = now

                delta_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
                total_months += max(delta_months, 0)

    # If nothing found, try fallback numeric pattern
    if total_months > 0:
        return round(total_months / 12, 1)

    match = EXP_YEARS_PATTERN.search(text) or EXP_FALLBACK_PATTERN.search(text)
    if match:
        return float(match.group(1))

    return 0.0


def extract_email(text):
    text = text.lower()

    # Correct common typos in email domains
    text = text.replace("gmaill.com", "gmail.com").replace("gmai.com", "gmail.com")
    text = text.replace("yah00", "yahoo").replace("outiook", "outlook")
    text = text.replace("coim", "com").replace("hotmai", "hotmail")

    # Remove any characters not typically found in email addresses or whitespace
    text = re.sub(r'[^\w\s@._+-]', ' ', text)

    possible_emails = EMAIL_PATTERN.findall(text)

    if possible_emails:
        for email in possible_emails:
            # Prioritize common email providers or specific keywords if needed
            if "gmail" in email:
                return email
        # If no specific priority match, return the first found email
        return possible_emails[0]
    
    return None

def extract_phone_number(text):
    match = PHONE_PATTERN.search(text)
    return match.group(0) if match else None

def extract_location(text):
    found_locations = set()
    text_lower = text.lower()

    sorted_cities = sorted(list(MASTER_CITIES), key=len, reverse=True)

    for city in sorted_cities:
        pattern = r'\b' + re.escape(city.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found_locations.add(city)

    if found_locations:
        return ", ".join(sorted(list(found_locations)))
    return "Not Found"

def extract_name(text):
    lines = text.strip().splitlines()
    if not lines:
        return None

    # Common noise terms and address words
    EXCLUDE_TERMS = {
        "email", "e-mail", "phone", "mobile", "contact", "linkedin", "github",
        "portfolio", "website", "profile", "summary", "objective", "education",
        "skills", "projects", "certifications", "achievements", "experience",
        "dob", "date of birth", "address", "resume", "cv", "career", "gender",
        "marital", "nationality", "languages", "language", "score", "cgpa",
        "bengaluru", "bangalore", "karnataka", "anekal", "india", "pin", "zipcode"
    }

    PREFIX_CLEANER = re.compile(r"^(name[\s:\-]*|mr\.?|ms\.?|mrs\.?)", re.IGNORECASE)

    potential_names = []

    for line in lines[:10]:
        original_line = line.strip()
        if not original_line:
            continue

        cleaned_line = PREFIX_CLEANER.sub('', original_line).strip()
        cleaned_line = re.sub(r'[^A-Za-z\s]', '', cleaned_line)

        if any(term in cleaned_line.lower() for term in EXCLUDE_TERMS):
            continue

        words = cleaned_line.split()

        if 1 < len(words) <= 4 and all(w.isalpha() for w in words):
            if all(w.istitle() or w.isupper() for w in words):
                potential_names.append(cleaned_line)

    if potential_names:
        return max(potential_names, key=len).title()

    return None

def extract_cgpa(text):
    text = text.lower()
    
    matches = CGPA_PATTERN.findall(text)

    for match in matches:
        if match[0] and match[0].strip():
            raw_cgpa = float(match[0])
            scale = float(match[1]) if match[1] else None
        elif match[2] and match[2].strip():
            raw_cgpa = float(match[2])
            scale = float(match[3]) if match[3] else None
        else:
            continue

        if scale and scale not in [0, 1]:
            normalized_cgpa = (raw_cgpa / scale) * 4.0
            return round(normalized_cgpa, 2)
        elif raw_cgpa <= 4.0:
            return round(raw_cgpa, 2)
        elif raw_cgpa <= 10.0:
            return round((raw_cgpa / 10.0) * 4.0, 2)
        
    return None

def extract_education(text):
    """
    Extract a clean single-line education summary from resume.
    E.g., "B.Tech in CSE, Alliance University, Bangalore – 2028"
    """
    text = text.replace('\r', '').replace('\t', ' ')
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]

    education_section = ''
    capture = False

    for line in lines:
        line_lower = line.lower()
        if any(h in line_lower for h in ['education', 'academic background', 'qualifications']):
            capture = True
            continue
        if capture and any(h in line_lower for h in ['experience', 'skills', 'certifications', 'projects', 'languages']):
            break
        if capture:
            education_section += line + ' '

    education_section = education_section.strip()

    # Try matching full pattern: degree + college + year
    edu_match = EDU_MATCH_PATTERN.search(education_section)
    if edu_match:
        # Convert all groups to string, handling None explicitly
        return ' '.join([g if g is not None else '' for g in edu_match.groups()]).strip()

    # Try fallback: degree + year
    fallback_match = EDU_FALLBACK_PATTERN.search(education_section)
    if fallback_match:
        # Convert all groups to string, handling None explicitly
        return ' '.join([g if g is not None else '' for g in fallback_match.groups()]).strip()

    # Fallback to first line in section
    fallback_line = education_section.split('.')[0].strip()
    return fallback_line if fallback_line else "Not Found"
    

def extract_work_history(text):
    work_history_section_matches = WORK_HISTORY_SECTION_PATTERN.finditer(text)
    work_details = []
    
    start_index = -1
    for match in work_history_section_matches:
        start_index = match.end()
        break

    if start_index != -1:
        sections = ['education', 'skills', 'projects', 'certifications', 'awards', 'publications']
        end_index = len(text)
        for section in sections:
            section_match = re.search(r'\b' + re.escape(section) + r'\b', text[start_index:], re.IGNORECASE)
            if section_match:
                end_index = start_index + section_match.start()
                break
        
        work_text = text[start_index:end_index].strip()
        
        job_blocks = JOB_BLOCK_SPLIT_PATTERN.split(work_text)
        
        for block in job_blocks:
            block = block.strip()
            if not block:
                continue
            
            company = None
            title = None
            start_date = None
            end_date = None

            date_range_match = DATE_RANGE_MATCH_PATTERN.search(block)
            if date_range_match:
                start_date = date_range_match.group(1)
                end_date = date_range_match.group(2)
                block = block.replace(date_range_match.group(0), '').strip()

            lines = block.split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue

                title_company_match = TITLE_COMPANY_MATCH_PATTERN.search(line)
                if title_company_match:
                    title = title_company_match.group(1).strip()
                    company = title_company_match.group(2).strip()
                    break
                
                company_title_match = COMPANY_TITLE_MATCH_PATTERN.search(line)
                if company_title_match:
                    company = company_title_match.group(1).strip()
                    title = company_title_match.group(2).strip()
                    break
                
                if not company and not title:
                    potential_org_match = POTENTIAL_ORG_MATCH_PATTERN.search(line)
                    if potential_org_match and len(potential_org_match.group(0).split()) > 1:
                        if not company: company = potential_org_match.group(0).strip()
                        elif not title: title = potential_org_match.group(0).strip()
                        break

            if company or title or start_date or end_date:
                work_details.append({
                    "Company": company,
                    "Title": title,
                    "Start Date": start_date,
                    "End Date": end_date
                })
    return work_details

def extract_project_details(text, skill_library):
    """
    Extracts real project entries from resume text.
    Returns a list of dicts: Title, Description, Technologies Used
    """

    project_details = []

    text = text.replace('\r', '').replace('\t', ' ')
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]

    # Step 1: Isolate project section
    project_section_match = PROJECT_SECTION_KEYWORDS.search(text)

    if not project_section_match:
        project_text = text[:1000]  # fallback to first 1000 chars
        start_index = 0
    else:
        start_index = project_section_match.end()
        sections = ['education', 'skills', 'certifications', 'awards', 'publications', 'interests', 'hobbies']
        end_index = len(text)
        for section in sections:
            m = re.search(r'\b' + re.escape(section) + r'\b', text[start_index:], re.IGNORECASE)
            if m:
                end_index = start_index + m.start()
                break
        project_text = text[start_index:end_index].strip()

    if not project_text:
        return []

    lines = [line.strip() for line in project_text.split('\n') if line.strip()]
    current_project = {"Project Title": None, "Description": [], "Technologies Used": set()}

    for i, line in enumerate(lines):
        line_lower = line.lower()
        words = line.split()
        num_words = len(words)

        # Skip all-uppercase names or headers (unless very short, e.g., for acronyms)
        if re.match(r'^[A-Z\s]{5,}$', line) and num_words <= 4:
            continue

        is_title = False
        # Condition 1: Starts with a bullet/number or "project" keyword
        if PROJECT_TITLE_START_PATTERN.match(line) or line_lower.startswith("project"):
            is_title = True
        # Condition 2: Title-case appearance, reasonable length, not all caps, not forbidden keyword
        elif (
            3 <= num_words <= 15 and
            not any(kw in line_lower for kw in FORBIDDEN_TITLE_KEYWORDS) and
            not line.isupper() and
            line.istitle() # Check if it's mostly Title Case
        ):
            is_title = True
            # Additional check: if it looks like a date range, it's probably a job title, not project
            if DATE_RANGE_MATCH_PATTERN.search(line):
                is_title = False

        is_url = re.match(r'https?://', line_lower)

        # New Project Begins
        if is_title or is_url:
            if current_project["Project Title"] or current_project["Description"]:
                full_desc = "\n".join(current_project["Description"])
                techs = extract_skills_from_text(full_desc, skill_library)
                current_project["Technologies Used"].update(techs)

                # If no title was explicitly set, try to infer from the first description line
                if not current_project["Project Title"] and current_project["Description"]:
                    first_desc_line = current_project["Description"][0]
                    if len(first_desc_line.split()) <= 10 and first_desc_line.istitle() and not any(kw in first_desc_line.lower() for kw in FORBIDDEN_TITLE_KEYWORDS):
                        current_project["Project Title"] = first_desc_line
                        current_project["Description"] = current_project["Description"][1:]

                project_details.append({
                    "Project Title": current_project["Project Title"] if current_project["Project Title"] else "Unnamed Project",
                    "Description": full_desc.strip(),
                    "Technologies Used": ", ".join(sorted(current_project["Technologies Used"]))
                })

            current_project = {"Project Title": line, "Description": [], "Technologies Used": set()}
        else:
            current_project["Description"].append(line)

    # Add last project
    if current_project["Project Title"] or current_project["Description"]:
        full_desc = "\n".join(current_project["Description"])
        techs = extract_skills_from_text(full_desc, skill_library)
        current_project["Technologies Used"].update(techs)

        # If no title was explicitly set for the last project, try to infer
        if not current_project["Project Title"] and current_project["Description"]:
            first_desc_line = current_project["Description"][0]
            if len(first_desc_line.split()) <= 10 and first_desc_line.istitle() and not any(kw in first_desc_line.lower() for kw in FORBIDDEN_TITLE_KEYWORDS):
                current_project["Project Title"] = first_desc_line
                current_project["Description"] = current_project["Description"][1:]

        project_details.append({
            "Project Title": current_project["Project Title"] if current_project["Project Title"] else "Unnamed Project",
            "Description": full_desc.strip(),
            "Technologies Used": ", ".join(sorted(current_project["Technologies Used"]))
        })

    return project_details


def extract_languages(text):
    """
    Extracts known languages from resume text.
    Returns a comma-separated string of detected languages or 'Not Found'.
    """
    languages_list = set()
    cleaned_full_text = clean_text(text)

    # De-duplicated, lowercase language set
    all_languages = list(set([
        "english", "hindi", "spanish", "french", "german", "mandarin", "japanese", "arabic",
        "russian", "portuguese", "italian", "korean", "bengali", "marathi", "telugu", "tamil",
        "gujarati", "urdu", "kannada", "odia", "malayalam", "punjabi", "assamese", "kashmiri",
        "sindhi", "sanskrit", "dutch", "swedish", "norwegian", "danish", "finnish", "greek",
        "turkish", "hebrew", "thai", "vietnamese", "indonesian", "malay", "filipino", "swahili",
        "farsi", "persian", "polish", "ukrainian", "romanian", "czech", "slovak", "hungarian",
        "chinese", "tagalog", "nepali", "sinhala", "burmese", "khmer", "lao", "pashto", "dari",
        "uzbek", "kazakh", "azerbaijani", "georgian", "armenian", "albanian", "serbian",
        "croatian", "bosnian", "bulgarian", "macedonian", "slovenian", "estonian", "latvian",
        "lithuanian", "icelandic", "irish", "welsh", "gaelic", "maltese", "esperanto", "latin",
        "ancient greek", "modern greek", "yiddish", "romani", "catalan", "galician", "basque",
        "breton", "cornish", "manx", "frisian", "luxembourgish", "sami", "romansh", "sardinian",
        "corsican", "occitan", "provencal", "walloon", "flemish", "afrikaans", "zulu", "xhosa",
        "sesotho", "setswana", "shona", "ndebele", "venda", "tsonga", "swati", "kikuyu",
        "luganda", "kinyarwanda", "kirundi", "lingala", "kongo", "yoruba", "igbo", "hausa"
    ]))

    sorted_all_languages = sorted(all_languages, key=len, reverse=True)

    # Step 1: Try to locate a language-specific section
    section_match = LANGUAGE_SECTION_PATTERN.search(cleaned_full_text)

    if section_match:
        start_index = section_match.end()
        # Optional: stop at next known section
        stop_words = ['education', 'experience', 'skills', 'certifications', 'awards', 'publications', 'interests', 'hobbies']
        end_index = len(cleaned_full_text)
        for stop in stop_words:
            m = re.search(r'\b' + re.escape(stop) + r'\b', cleaned_full_text[start_index:], re.IGNORECASE)
            if m:
                end_index = start_index + m.start()
                break

        language_chunk = cleaned_full_text[start_index:end_index]
    else:
        language_chunk = cleaned_full_text

    # Step 2: Match known languages
    for lang in sorted_all_languages:
        # Use word boundaries for exact matches and allow for common suffixes like " (fluent)"
        pattern = r'\b' + re.escape(lang) + r'(?:\s*\(?[a-z\s,-]+\)?)?\b'
        if re.search(pattern, language_chunk, re.IGNORECASE):
            if lang == "de":
                languages_list.add("German")
            else:
                languages_list.add(lang.title())

    return ", ".join(sorted(languages_list)) if languages_list else "Not Mentioned"


def format_work_history(work_list):
    if not work_list:
        return "Not Found"
    formatted_entries = []
    for entry in work_list:
        parts = []
        if entry.get("Title"):
            parts.append(f"• **{entry['Title']}**")
        if entry.get("Company"):
            parts.append(f"{entry['Company']}")
        if entry.get("Start Date") and entry.get("End Date"):
            parts.append(f"({entry['Start Date']} - {entry['End Date']})")
        elif entry.get("Start Date"):
            parts.append(f"(Since {entry['Start Date']})")
        formatted_entries.append(" ".join(parts).strip())
    return "\n".join(formatted_entries) if formatted_entries else "Not Found"

def format_project_details(proj_list):
    if not proj_list:
        return "Not Found"
    formatted_entries = []
    for entry in proj_list:
        parts = []
        if entry.get("Project Title"):
            parts.append(f"• **{entry['Project Title']}**")
        if entry.get("Technologies Used"):
            parts.append(f"({entry['Technologies Used']})")
        if entry.get("Description") and entry["Description"].strip():
            desc_snippet = entry["Description"].split('\n')[0][:100] + "..." if len(entry["Description"]) > 100 else entry["Description"]
            parts.append(f'"{desc_snippet}"')
        formatted_entries.append(" ".join(parts).strip())
    return "\n".join(formatted_entries) if formatted_entries else "Not Found"

def generate_llm_hr_summary(name, score, experience, matched_skills, missing_skills, cgpa, job_domain, tone="Professional"):
    summary_parts = []

    # Map job_domain to a more descriptive role_tag
    role_tag_map = {
        "finance": "finance-focused",
        "data_science": "data science-oriented",
        "software": "software development-centric",
        "hr": "human resources-aligned",
        "design": "design-specialized",
        "general": "well-rounded"
    }
    role_tag = role_tag_map.get(job_domain, "general")

    cgpa_str = f"a CGPA of {cgpa:.2f} on a 4.0 scale" if pd.notna(cgpa) else "no specific CGPA mentioned"

    # 1. Opening Statement
    if tone == "Professional":
        summary_parts.append(
            f"{name} presents as a {role_tag} candidate with approximately {experience} years of experience and {cgpa_str}."
        )
    elif tone == "Friendly":
        summary_parts.append(
            f"Meet {name}, a {role_tag} professional with about {experience} years under their belt, and they've achieved {cgpa_str}."
        )
    elif tone == "Critical":
        summary_parts.append(
            f"Analysis of {name}'s profile reveals {experience} years of experience and {cgpa_str}, with a {role_tag} focus."
        )

    # 2. Highlighted Strengths
    if matched_skills:
        focus_skills = ', '.join(matched_skills[:5])
        if tone == "Professional":
            strength_openers = [
                f"The candidate demonstrates strong alignment in key technical areas such as: {focus_skills}.",
                f"Core proficiencies identified include: {focus_skills}.",
                f"Notable strengths encompass: {focus_skills}."
            ]
        elif tone == "Friendly":
            strength_openers = [
                f"They're really strong in areas like: {focus_skills}.",
                f"Their top skills are definitely: {focus_skills}.",
                f"You'll find them excelling in: {focus_skills}."
            ]
        elif tone == "Critical":
            strength_openers = [
                f"Some relevant proficiencies include: {focus_skills}.",
                f"Skills present are: {focus_skills}.",
                f"Identified capabilities: {focus_skills}."
            ]
        summary_parts.append(random.choice(strength_openers))

    # 3. Score Interpretation
    if score >= 85:
        if tone == "Professional":
            summary_parts.append("This is an exceptional profile with clear alignment to the role requirements. The candidate is highly likely to thrive with minimal onboarding.")
        elif tone == "Friendly":
            summary_parts.append("Wow, this candidate is a fantastic match! They're super aligned with what we're looking for and should hit the ground running.")
        elif tone == "Critical":
            summary_parts.append("The profile shows strong alignment, indicating a high probability of successful integration into the role.")
    elif score >= 70:
        if tone == "Professional":
            summary_parts.append("This is a strong match with most key requirements met. The candidate is suitable for a technical interview.")
        elif tone == "Friendly":
            summary_parts.append("A solid match! They've got most of what we need and are definitely worth a chat.")
        elif tone == "Critical":
            summary_parts.append("The candidate meets a majority of the core competencies, warranting further evaluation.")
    elif score >= 50:
        if tone == "Professional":
            summary_parts.append("This profile shows potential but lacks alignment in some critical areas. Further assessment is recommended.")
        elif tone == "Friendly":
            summary_parts.append("They've got some good stuff, but there are a few gaps. Might need a closer look or some development.")
        elif tone == "Critical":
            summary_parts.append("Identified gaps in key areas suggest a need for more rigorous screening or consideration for alternative roles.")
    else:
        if tone == "Professional":
            summary_parts.append("This candidate may not currently align with the role’s expectations. Consider for future openings or roles with a different skill set.")
        elif tone == "Friendly":
            summary_parts.append("Not quite the right fit for this one, but keep them in mind for other opportunities!")
        elif tone == "Critical":
            summary_parts.append("The candidate's profile presents significant deviations from the required competencies, rendering them unsuitable for the current vacancy.")

    # 4. Areas to Improve
    if missing_skills:
        if tone == "Professional":
            summary_parts.append(
                f"To increase alignment with this role, the candidate could focus on gaining expertise in: {', '.join(missing_skills[:4])}."
            )
        elif tone == "Friendly":
            summary_parts.append(
                f"If they brush up on {', '.join(missing_skills[:4])}, they'd be even stronger!"
            )
        elif tone == "Critical":
            summary_parts.append(
                f"Deficiencies were noted in: {', '.join(missing_skills[:4])}."
            )

    # 5. Career Fit Tag (Additional Insight)
    if experience > 10:
        if tone == "Professional":
            summary_parts.append("Additional insight: Given their extensive experience, the candidate may be suitable for senior or lead roles beyond the scope of the current opening.")
        elif tone == "Friendly":
            summary_parts.append("Just a thought: With all that experience, they might be a great fit for a more senior or leadership position!")
        elif tone == "Critical":
            summary_parts.append("Observation: The candidate's experience level suggests potential overqualification for this specific role; consider higher-tier positions.")
    elif experience < 1 and score >= 60: # Only suggest entry-level if they still scored reasonably well
        if tone == "Professional":
            summary_parts.append("Additional insight: This appears to be an early-career candidate, ideal for internships or entry-level roles where foundational skills are valued.")
        elif tone == "Friendly":
            summary_parts.append("Heads up: This looks like a fresh face, perfect for an internship or a junior role!")
        elif tone == "Critical":
            summary_parts.append("Observation: The candidate's limited experience suggests suitability for entry-level positions only.")

    return " ".join(summary_parts)


def compute_production_match_score(jd_text, resume_text, jd_skills, matched_skills, _model=None):
    # Normalize and clean
    jd_clean = ' '.join(jd_text.lower().split())
    resume_clean = ' '.join(resume_text.lower().split())

    # Exact match score (using the new formula)
    exact_score = round(len(matched_skills) / (len(jd_skills) + 1e-6) * 100, 2)

    # Semantic score using model
    if _model is None:
        _model = global_sentence_model # Use the globally loaded model
        if _model is None: # Fallback if global model failed to load
            _model = SentenceTransformer("all-MiniLM-L6-v2")
    emb1 = _model.encode(jd_clean)
    emb2 = _model.encode(resume_clean)
    semantic_score = cosine_similarity([emb1], [emb2])[0][0] * 100

    final_score = (0.6 * semantic_score) + (0.4 * exact_score)
    return round(final_score, 2), round(semantic_score, 2), round(exact_score, 2)


def create_mailto_link(recipient_email, candidate_name, job_title="Job Opportunity", sender_name="Recruiting Team"):
    subject = urllib.parse.quote(f"Invitation for Interview - {job_title} - {candidate_name}")
    body = urllib.parse.quote(f"""Dear {candidate_name},

We were very impressed with your profile and would like to invite you for an interview for the {job_title} position.

Best regards,

The {sender_name}""")
    return f"mailto:{recipient_email}?subject={subject}&body={body}"

# Wrapper for extract_text_from_file to be used with ProcessPoolExecutor
def _extract_text_wrapper(file_info):
    file_data_bytes, file_name, file_type = file_info
    text = extract_text_from_file(file_data_bytes, file_name, file_type)
    return file_name, text

# Updated function to extract certifications as per user's request
def extract_certifications(text):
    """
    Extracts certification-related phrases from resume text.
    Returns a list of unique certifications found.
    """
    # Sample list of known certifications (extend this based on your app's database)
    KNOWN_CERTIFICATIONS = [
        "AWS Certified", "AWS Certified Solutions Architect", "AWS Certified Developer",
        "Google Professional Data Engineer", "Google Cloud Certified", "GCP Certified",
        "Certified Data Scientist", "Azure Fundamentals", "Microsoft Certified",
        "Certified Ethical Hacker", "CEH", "CISSP", "CompTIA Security+",
        "Certified Scrum Master", "CSM", "PMP", "Project Management Professional",
        "Six Sigma", "Lean Six Sigma", "TOGAF", "ITIL Foundation",
        "Certified Kubernetes Administrator", "CKA",
        "TensorFlow Developer", "DeepLearning.AI", "Machine Learning by Stanford",
        "CS50", "IBM Data Science", "Google ML Crash Course", "HackerRank Certified",
        "Udemy", "Coursera", "edX", "LinkedIn Learning", "NPTEL", "Scaler", "DataCamp",
        "Python for Everybody", "SQL for Data Science", "HarvardX", "MITx", "AI For Everyone"
    ]

    # Optional pattern for capturing general "Certification in XYZ"
    GENERIC_CERT_PATTERN = re.compile(r'\b(certification|certificate|certified)\s*(in|of)?\s*([\w\s\-\+&\.]{2,100})', re.IGNORECASE)


    found_certifications = set()
    text_clean = text.replace('\r', '').replace('\t', ' ')
    lower_text = text_clean.lower()

    # Match known certifications
    for cert in KNOWN_CERTIFICATIONS:
        if cert.lower() in lower_text:
            found_certifications.add(cert)

    # Match generic "Certification in XYZ"
    for match in GENERIC_CERT_PATTERN.finditer(text_clean):
        full_cert = match.group(0).strip()
        if 4 < len(full_cert) < 100:
            found_certifications.add(full_cert)

    return sorted(found_certifications) if found_certifications else ["Not Found"]

# New function to check timeline consistency - NO LONGER USED FOR CALCULATION
def check_timeline_consistency(work_history_raw):
    """
    Checks for significant gaps (more than 3 years) in the parsed work history.
    Returns True if no large gaps, False otherwise.
    """
    if not work_history_raw or len(work_history_raw) < 2:
        return True # No gaps to check if less than 2 entries

    parsed_dates = []
    for entry in work_history_raw:
        start_str = entry.get("Start Date")
        end_str = entry.get("End Date")

        try:
            # Attempt to parse start date
            if start_str:
                try:
                    start_date = datetime.strptime(start_str.strip().replace(',', ''), '%B %Y')
                except ValueError:
                    try:
                        start_date = datetime.strptime(start_str.strip().replace(',', ''), '%b %Y')
                    except ValueError:
                        start_date = datetime(int(start_str.strip()), 1, 1) # Assume January for year-only
            else:
                start_date = None

            # Attempt to parse end date
            if end_str and end_str.lower() != 'present':
                try:
                    end_date = datetime.strptime(end_str.strip().replace(',', ''), '%B %Y')
                except ValueError:
                    try:
                        end_date = datetime.strptime(end_str.strip().replace(',', ''), '%b %Y')
                    except ValueError:
                        end_date = datetime(int(end_str.strip()), 12, 31) # Assume December for year-only
            else:
                end_date = datetime.now() # 'present' means current date

            if start_date and end_date:
                parsed_dates.append((start_date, end_date))
        except Exception:
            # Skip entries that cannot be parsed
            continue

    if not parsed_dates or len(parsed_dates) < 2:
        return True # Not enough valid entries to check for gaps

    # Sort entries by start date
    parsed_dates.sort(key=lambda x: x[0])

    for i in range(len(parsed_dates) - 1):
        current_end = parsed_dates[i][1]
        next_start = parsed_dates[i+1][0]

        # Calculate gap in months
        gap_months = (next_start.year - current_end.year) * 12 + (next_start.month - current_end.month)

        # Consider a gap significant if it's more than 36 months (3 years)
        if gap_months > 36:
            return False # Found a large gap
    return True # No large gaps found

# New function to verify claimed experience - NO LONGER USED FOR CALCULATION
def verify_experience(resume_text, extracted_years):
    """
    Compares explicitly stated experience (e.g., "10+ years") with extracted years.
    Returns True if consistent, False if a clear contradiction is found.
    """
    text_lower = resume_text.lower()
    
    # Look for explicit "X+ years experience" claims
    match = re.search(r'(\d+)\+\s*(?:year|yrs|years)\s*(?:of)?\s*experience', text_lower)
    if match:
        claimed_years = int(match.group(1))
        # If claimed_years is significantly higher than extracted_years
        if claimed_years > extracted_years + 3: # Allow for some discrepancy
            return False
    
    # Look for "fresh graduate" or "entry-level" vs high extracted experience
    if ("fresh graduate" in text_lower or "entry-level" in text_lower) and extracted_years >= 2:
        return False

    return True

# New function to get consistency score - NO LONGER USED FOR CALCULATION
def get_consistency_score(resume_text, extracted_years, work_history_raw):
    """
    Calculates a consistency score based on timeline gaps and claimed vs extracted experience.
    Score starts at 100 and deductions are made for inconsistencies.
    """
    score = 100

    if not check_timeline_consistency(work_history_raw):
        score -= 20 # Deduct for significant timeline gaps
    
    if not verify_experience(resume_text, extracted_years):
        score -= 30 # Deduct for contradiction in claimed vs extracted experience

    return max(0, score) # Ensure score doesn't go below 0

# Updated extract_resume_highlights as per user's latest prompt
# Modified to use existing extraction functions
def extract_resume_highlights(text, skill_library):
    highlights = {}
    text_lower = text.lower() # Convert to lowercase once for efficiency

    # 📘 Education - Use the dedicated extract_education function
    highlights["Education"] = extract_education(text)

    # 💼 Recent Role - Extract from work history
    work_history = extract_work_history(text)
    if work_history:
        highlights["Recent Role"] = work_history[0].get("Title", "Not Found")
    else:
        highlights["Recent Role"] = "Not Found"

    # 📊 Experience – Assume extracted earlier if you're using parser, or use the dedicated function
    highlights["Experience"] = extract_years_of_experience(text)

    # 🧠 Top Skills - Use the dedicated extract_skills_from_text function
    all_skills = extract_skills_from_text(text, skill_library)
    highlights["Skills"] = all_skills[:8] if all_skills else ["Not Found"]

    # 🏅 Certifications - Use the dedicated extract_certifications function
    certifications_list = extract_certifications(text)
    highlights["Certifications"] = certifications_list if certifications_list else ["Not Found"]

    # 🌐 Languages Known - Use the dedicated extract_languages function
    highlights["Languages"] = extract_languages(text)

    # 🕒 Availability
    highlights["Availability"] = "Immediate Joiner" if "immediate" in text_lower else "Not Mentioned"

    # 📍 Location - Use the dedicated extract_location function
    highlights["Location"] = extract_location(text)

    # 🛠 Tools Used
    ALL_TOOLS = [
        # Engineering/Dev
        "GitHub", "Bitbucket", "Jira", "Slack", "Postman", "Kubernetes", "Docker", "VSCode", "Eclipse", "Android Studio", "PyCharm",
        # Data / BI
        "Tableau", "Power BI", "MLflow", "Google Analytics", "BigQuery", "Looker", "Matplotlib", "Seaborn", "Snowflake",
        # Design / Creative
        "Figma", "Adobe XD", "Canva", "Photoshop", "Illustrator", "Premiere Pro",
        # Business / PM / Marketing
        "Salesforce", "Zoho CRM", "HubSpot", "MS Office", "Trello", "Asana", "ClickUp", "Notion", "SurveyMonkey",
        # Misc
        "Hadoop", "Spark", "Firebase", "Ansible", "Jupyter", "RStudio", "Notepad++"
    ]
    tools_found = set()
    for tool in ALL_TOOLS:
        if re.search(rf"\b{re.escape(tool.lower())}\b", text_lower):
            tools_found.add(tool)
    highlights["Tools"] = ", ".join(sorted(tools_found)) if tools_found else "Not Found"

    # 🏆 Achievements
    ACHIEVEMENT_TERMS = [
        "published", "presented", "awarded", "recognized", "top performer",
        "achievement", "mentor", "volunteer", "scholarship", "winner", "gold medal",
        "rank holder", "speaker", "conference", "hackathon", "competition", "olympiad"
    ]
    achievements = [term for term in ACHIEVEMENT_TERMS if re.search(rf"\b{re.escape(term)}\b", text_lower)]
    # Ensure all found achievements are displayed, or "Not Found" if none
    highlights["Achievements"] = ", ".join(sorted(set(achievements))).title() if achievements else "Not Found"

    # 💻 Portfolio / GitHub / Personal Site
    portfolio_match = re.search(r"(https?://(?:www\.)?(?:github|linkedin|portfolio|personal|behance|dribbble|notion|medium)\.[^\s]+)", text, re.I)
    highlights["Portfolio"] = portfolio_match.group(0) if portfolio_match else "Not Found"

    # 🌟 Soft Skills (Smart Matching)
    SOFT_SKILLS = [
        "communication", "leadership", "teamwork", "adaptability", "problem solving", "time management",
        "critical thinking", "creativity", "collaboration", "negotiation", "empathy", "emotional intelligence"
    ]
    soft_found = [s for s in SOFT_SKILLS if re.search(rf"\b{re.escape(s)}\b", text_lower)]
    highlights["Soft Skills"] = ", ".join(sorted(set(soft_found))).title() if soft_found else "Not Found"

    # 💡 Notable Projects Highlight (Smart Summary Placeholder)
    highlights["Notable Projects Highlight"] = "Found" if "project" in text_lower else "Not Found"

    # 📚 Publications
    if re.search(r"\b(published|journal|conference|doi|research|arxiv|whitepaper)\b", text_lower):
        highlights["Publications"] = "Found"
    else:
        highlights["Publications"] = "Not Found"

    return highlights

def preprocess_image_for_ocr(image):
    img_cv = np.array(image)
    img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
    img_processed = cv2.adaptiveThreshold(img_cv, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY, 11, 2)
    return Image.fromarray(img_processed)

def clean_text(text):
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    return text.strip().lower()

def extract_text_from_file(file_bytes_io, file_name, file_type):
    full_text = ""
    # Tesseract configuration for speed and common resume layout
    tesseract_config = "--oem 1 --psm 3" 

    # Ensure pytesseract.pytesseract.tesseract_cmd is set if tesseract is needed
    # This part should ideally be handled by the calling Streamlit app if it uses st.cache_resource
    # For a pure logic file, we assume tesseract is in PATH or configured externally.
    # If it's not, this will raise an error that needs to be caught by the caller.
    try:
        # Check if tesseract is available in PATH
        if shutil.which("tesseract") is None:
            print("WARNING: Tesseract OCR engine not found in system PATH. OCR may fail.")
            # You might want to raise an exception here if OCR is critical
            # raise FileNotFoundError("Tesseract OCR engine not found.")
    except Exception as e:
        print(f"WARNING: Error checking Tesseract path: {e}")


    if "pdf" in file_type:
        try:
            import pdfplumber # Import locally to avoid global dependency if not needed
            with pdfplumber.open(file_bytes_io) as pdf:
                pdf_text = ''.join(page.extract_text() or '' for page in pdf.pages)
            
            if len(pdf_text.strip()) < 50: # Heuristic for potentially scanned PDF
                from pdf2image import convert_from_bytes # Import locally
                images = convert_from_bytes(file_bytes_io.getvalue()) # Pass bytes directly
                for img in images:
                    processed_img = preprocess_image_for_ocr(img)
                    full_text += pytesseract.image_to_string(processed_img, lang='eng', config=tesseract_config) + "\n"
            else:
                full_text = pdf_text

        except Exception as e:
            # Fallback to OCR directly if pdfplumber fails or for any other PDF error
            try:
                from pdf2image import convert_from_bytes # Import locally
                images = convert_from_bytes(file_bytes_io.getvalue())
                for img in images:
                    processed_img = preprocess_image_for_ocr(img)
                    full_text += pytesseract.image_to_string(processed_img, lang='eng', config=tesseract_config) + "\n"
            except Exception as e_ocr:
                print(f"ERROR: Failed to extract text from PDF via OCR for {file_name}: {str(e_ocr)}")
                return f"[ERROR] Failed to extract text from PDF via OCR: {str(e_ocr)}"

    elif "image" in file_type:
        try:
            img = Image.open(file_bytes_io).convert("RGB")
            processed_img = preprocess_image_for_ocr(img)
            full_text = pytesseract.image_to_string(processed_img, lang='eng', config=tesseract_config)
        except Exception as e:
            print(f"ERROR: Failed to extract text from image for {file_name}: {str(e)}")
            return f"[ERROR] Failed to extract text from image: {str(e)}"
    else:
        print(f"ERROR: Unsupported file type for {file_name}: {file_type}")
        return f"[ERROR] Unsupported file type: {file_type}. Please upload a PDF or an image (JPG, PNG)."

    if not full_text.strip():
        print(f"ERROR: No readable text extracted from {file_name}. It might be a very low-quality scan or an empty document.")
        return "[ERROR] No readable text extracted from the file. It might be a very low-quality scan or an empty document."
    
    return full_text


def process_single_resume_logic(file_name, text, jd_text, 
                                jd_name_for_results,
                                skill_library,
                                max_experience,
                                summary_tone):
    """
    Processes a single resume (pre-extracted text) and returns a dictionary of results.
    This function contains the core screening logic and does NOT use Streamlit directly.
    """
    try:
        if text.startswith("[ERROR]"):
            return {
                "File Name": file_name,
                "Candidate Name": file_name.replace('.pdf', '').replace('.jpg', '').replace('.jpeg', '').replace('.png', '').replace('_', ' ').title(),
                "Score (%)": 0, "Years Experience": 0, "CGPA (4.0 Scale)": None,
                "Email": "Not Found", "Phone Number": "Not Found", "Location": "Not Found",
                "Languages Known": "Not Found", 
                "Education Details": "Not Found",
                "Work History": "Not Found", "Project Details": "Not Found",
                "Latest Education": "Not Found", 
                "Most Recent Job": "Not Found",  
                "Certifications": "Not Found",   
                "Resume Consistency Score": 0,
                "AI Suggestion": f"Error: {text.replace('[ERROR] ', '')}",
                "Detailed HR Assessment": f"Error processing resume: {text.replace('[ERROR] ', '')}",
                "Matched Keywords": "", "Missing Skills": "",
                "Semantic Similarity": 0.0,
                "Exact Match Score": 0.0,
                "Resume Raw Text": "",
                "Resume Word Count": 0,
                "JD Used": jd_name_for_results, "Date Screened": datetime.now().date(),
                "Certificate ID": str(uuid.uuid4()), "Certificate Rank": "Not Applicable",
                "Tag": "❌ Text Extraction Error",
                "Top Skills Highlight": "Not Found",
                "Availability": "Not Found",
                "Soft Skills": "Not Found",
                "Notable Projects Highlight": "Not Found",
                "Awards/Recognitions": "Not Found",
                "Tools Used Highlight": "Not Found",
                "Publications": "Not Found",
                "Portfolio/GitHub": "Not Found",
                "Manual Shortlist": False
            }

        exp = extract_years_of_experience(text)
        email = extract_email(text)
        phone = extract_phone_number(text)
        
        work_history_raw = extract_work_history(text)
        project_details_raw = extract_project_details(text, skill_library)
        
        education_details_formatted = extract_education(text)
        work_history_formatted = format_work_history(work_history_raw)
        project_details_formatted = format_project_details(project_details_raw)

        candidate_name = extract_name(text) or file_name.replace('.pdf', '').replace('.jpg', '').replace('.jpeg', '').replace('.png', '').replace('_', ' ').title()
        cgpa = extract_cgpa(text)
        
        resume_word_count = 0 # Not calculated for performance
        resume_consistency_score = 0 # Not calculated for performance

        highlights = extract_resume_highlights(text, skill_library)
        
        latest_education = highlights.get("Education", "Not Found")
        most_recent_job = highlights.get("Recent Role", "Not Found")
        
        certifications = highlights.get("Certifications", ["Not Found"])
        if isinstance(certifications, list):
            certifications = ", ".join(certifications) if certifications != ["Not Found"] else "Not Found"

        top_skills_highlight = highlights.get("Skills", ["Not Found"])
        if isinstance(top_skills_highlight, list):
            top_skills_highlight = ", ".join(top_skills_highlight) if top_skills_highlight != ["Not Found"] else "Not Found"
        
        availability = highlights.get("Availability", "Not Found")
        soft_skills = highlights.get("Soft Skills", "Not Found")
        notable_projects_highlight = highlights.get("Notable Projects Highlight", "Not Found")
        
        awards_recognitions = highlights.get("Achievements", "Not Found")
        tools_used_highlight = highlights.get("Tools", "Not Found")
        publications = highlights.get("Publications", "Not Found")
        portfolio_github = highlights.get("Portfolio", "Not Found")
        
        languages_known_highlight = highlights.get("Languages", "Not Found")
        location = highlights.get("Location", "Not Found")


        resume_skills = extract_skills_from_text(text, skill_library)
        jd_skills_local = extract_skills_from_text(jd_text, skill_library)

        matched_keywords = list(set(resume_skills).intersection(set(jd_skills_local)))
        missing_skills = list(set(jd_skills_local).difference(set(resume_skills)))
        
        final_score, semantic_similarity, exact_score = compute_production_match_score(
            jd_text, text, jd_skills_local, matched_keywords, global_sentence_model
        )
        
        job_domain = detect_job_domain(jd_name_for_results, jd_text)
        
        hr_summary = generate_llm_hr_summary(
            name=candidate_name,
            score=final_score,
            experience=exp,
            matched_skills=matched_keywords,
            missing_skills=missing_skills,
            cgpa=cgpa,
            job_domain=job_domain,
            tone=summary_tone
        )

        certificate_id = str(uuid.uuid4())
        certificate_rank = "⚪ Profile Reviewed"

        if final_score >= 90:
            certificate_rank = "🏅 Elite Match"
        elif final_score >= 80:
            certificate_rank = "⭐ Strong Match"
        elif final_score >= 75:
            certificate_rank = "✅ Good Fit"
        elif final_score >= 65:
            certificate_rank = "⚪ Low Fit"
        elif final_score >= 50:
            certificate_rank = "🟡 Basic Fit"
        
        tag = "❌ Limited Match"
        if final_score >= 90 and exp >= 5 and exp <= max_experience and semantic_similarity >= 0.85 and (cgpa is None or cgpa >= 3.5):
            tag = "👑 Exceptional Match"
        elif final_score >= 80 and exp >= 3 and exp <= max_experience and semantic_similarity >= 0.7 and (cgpa is None or cgpa >= 3.0):
            tag = "🔥 Strong Candidate"
        elif final_score >= 60 and exp >= 1 and exp <= max_experience and (cgpa is None or cgpa >= 2.5):
            tag = "✨ Promising Fit"
        elif final_score >= 40:
            tag = "⚠️ Needs Review"

        return {
            "File Name": file_name,
            "Candidate Name": candidate_name,
            "Score (%)": final_score,
            "Years Experience": exp,
            "CGPA (4.0 Scale)": cgpa,
            "Email": email or "Not Found",
            "Phone Number": phone or "Not Found",
            "Location": location or "Not Found",
            "Languages Known": languages_known_highlight,
            "Education Details": education_details_formatted,
            "Work History": work_history_formatted,
            "Project Details": project_details_formatted,
            "Latest Education": latest_education,
            "Most Recent Job": most_recent_job,
            "Certifications": certifications,
            "Resume Consistency Score": resume_consistency_score,
            "AI Suggestion": hr_summary,
            "Detailed HR Assessment": hr_summary,
            "Matched Keywords": ", ".join(matched_keywords),
            "Missing Skills": ", ".join(missing_skills),
            "Semantic Similarity": semantic_similarity,
            "Exact Match Score": exact_score,
            "Resume Raw Text": text,
            "Resume Word Count": resume_word_count,
            "JD Used": jd_name_for_results, "Date Screened": datetime.now().date(),
            "Certificate ID": certificate_id,
            "Certificate Rank": certificate_rank,
            "Tag": tag,
            "Top Skills Highlight": top_skills_highlight,
            "Availability": availability,
            "Soft Skills": soft_skills,
            "Notable Projects Highlight": notable_projects_highlight,
            "Awards/Recognitions": awards_recognitions,
            "Tools Used Highlight": tools_used_highlight,
            "Publications": publications,
            "Portfolio/GitHub": portfolio_github,
            "Manual Shortlist": False
        }
    except Exception as e:
        print(f"CRITICAL ERROR: Unhandled exception processing {file_name}: {e}")
        traceback.print_exc()
        return {
            "File Name": file_name,
            "Candidate Name": file_name.replace('.pdf', '').replace('.jpg', '').replace('.jpeg', '').replace('.png', '').replace('_', ' ').title(),
            "Score (%)": 0, "Years Experience": 0, "CGPA (4.0 Scale)": None,
            "Email": "Not Found", "Phone Number": "Not Found", "Location": "Not Found",
            "Languages Known": "Not Found", 
            "Education Details": "Not Found",
            "Work History": "Not Found", "Project Details": "Not Found",
            "Latest Education": "Not Found", 
            "Most Recent Job": "Not Found",  
            "Certifications": "Not Found",   
            "Resume Consistency Score": 0,
            "AI Suggestion": f"Critical Error: {e}",
            "Detailed HR Assessment": f"Critical Error processing resume: {e}",
            "Matched Keywords": "", "Missing Skills": "",
            "Semantic Similarity": 0.0,
            "Exact Match Score": 0.0,
            "Resume Raw Text": "",
            "Resume Word Count": 0,
            "JD Used": jd_name_for_results, "Date Screened": datetime.now().date(),
            "Certificate ID": str(uuid.uuid4()), "Certificate Rank": "Not Applicable",
            "Tag": "❌ Critical Processing Error",
            "Top Skills Highlight": "Not Found",
            "Availability": "Not Found",
            "Soft Skills": "Not Found",
            "Notable Projects Highlight": "Not Found",
            "Awards/Recognitions": "Not Found",
            "Tools Used Highlight": "Not Found",
            "Publications": "Not Found",
            "Portfolio/GitHub": "Not Found",
            "Manual Shortlist": False
        }
