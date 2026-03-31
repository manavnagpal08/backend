from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import re
from collections import Counter

router = APIRouter()

class PortfolioRequest(BaseModel):
    github_url: str

# Copied/Adapted from portfolio_analyzer.py logic
# Note: In production, import this common logic instead of duplicating
GITHUB_API = "https://api.github.com"
FRONTEND_EXT = ["html", "css", "js", "ts", "jsx", "tsx"]
BACKEND_EXT = ["py", "java", "go", "php", "rb", "cs", "cpp", "c", "kt"]

def parse_github_url(url):
    url = url.strip().rstrip('/')
    if not url.startswith("https://github.com/"):
        return None, None
    parts = url.replace("https://github.com/", "").split("/")
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]

def fetch_repo_tree(owner, repo):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/main?recursive=1" # Defaulting to main
    # Add your GITHUB_TOKEN here if needed for higher rate limits
    response = requests.get(url) 
    if response.status_code != 200:
        # Try 'master' branch if main fails
        url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/master?recursive=1"
        response = requests.get(url)
    
    if response.status_code == 200:
        return response.json().get('tree', [])
    return []

@router.post("/analyze")
async def analyze_portfolio(request: PortfolioRequest):
    owner, repo = parse_github_url(request.github_url)
    if not owner:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")

    files = fetch_repo_tree(owner, repo)
    if not files:
        raise HTTPException(status_code=404, detail="Repository not found or empty")

    # Metrics Calculation
    paths = [f["path"] for f in files if f["type"] == "blob"]
    extensions = [p.split('.')[-1] for p in paths if '.' in p]
    ext_counts = Counter(extensions)
    
    frontend_count = sum(ext_counts[ext] for ext in FRONTEND_EXT if ext in ext_counts)
    backend_count = sum(ext_counts[ext] for ext in BACKEND_EXT if ext in ext_counts)
    
    total_code_files = frontend_count + backend_count
    
    # Simple Scoring (Adapt from portfolio_analyzer.py)
    score = 0
    if total_code_files > 50: score += 40
    elif total_code_files > 20: score += 20
    else: score += 10

    if backend_count > 5: score += 30
    if frontend_count > 5: score += 30
    
    # Analysis Summary
    analysis_text = f"## GitHub Audit: {owner}/{repo}\n\n"
    analysis_text += f"**Files Scanned:** {len(paths)}\n"
    analysis_text += f"**Backend Focus:** {backend_count} files\n"
    analysis_text += f"**Frontend Focus:** {frontend_count} files\n\n"
    analysis_text += "### Technologies Detected\n"
    for ext, count in ext_counts.most_common(5):
        analysis_text += f"- **.{ext}**: {count} files\n"

    return {
        "overall_score": min(score, 100),
        "code_quality": "High" if score > 80 else "Medium",
        "design_score": "N/A (Code Only)",
        "impact": "High" if total_code_files > 100 else "Moderate",
        "documentation": "README Found" if "README.md" in paths or "readme.md" in paths else "Missing",
        "analysis": analysis_text,
        "recommendation": "Great repository!" if score > 70 else "Add more documentation and tests."
    }
