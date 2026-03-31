from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import resume, portfolio, auth
import uvicorn
import nltk
import os

# Ensure NLTK data is downloaded
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

app = FastAPI(title="ScreenerPro AI Backend")

# Allow all CORS for Flutter development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resume.router, prefix="/resume", tags=["Resume"])
app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
app.include_router(auth.router, prefix="/auth", tags=["Auth"])

@app.get("/")
def read_root():
    return {"message": "ScreenerPro AI Backend is Running"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
