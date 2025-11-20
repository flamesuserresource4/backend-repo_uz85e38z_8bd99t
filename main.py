import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any

from database import create_document
from schemas import QuizAnswer, QuizResult

app = FastAPI(title="Attachment Style Quiz API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Attachment Style Quiz Backend Running"}

# Research-grounded question bank based on the Experiences in Close Relationships (ECR-R) dimensions
# We avoid naming styles directly to keep it blind. Items map to anxiety and avoidance factors.
QUESTIONS: List[Dict[str, Any]] = [
    # Avoidance items (sampled and adapted from ECR-R; worded neutrally)
    {"id": "A1", "text": "I prefer not to show a partner how I feel deep down.", "factor": "avoidance"},
    {"id": "A2", "text": "I find it difficult to depend on close others.", "factor": "avoidance"},
    {"id": "A3", "text": "I don't feel comfortable opening up to romantic partners.", "factor": "avoidance"},
    {"id": "A4", "text": "I prefer not to be too close to others.", "factor": "avoidance"},
    {"id": "A5", "text": "It's important for me to feel independent from others.", "factor": "avoidance"},
    {"id": "A6", "text": "I want to get close, but I keep people at arm’s length.", "factor": "avoidance"},
    # Anxiety items
    {"id": "X1", "text": "I worry about being abandoned.", "factor": "anxiety"},
    {"id": "X2", "text": "I often worry my partner doesn't really love me.", "factor": "anxiety"},
    {"id": "X3", "text": "I need a lot of reassurance from close others.", "factor": "anxiety"},
    {"id": "X4", "text": "I worry that romantic partners won’t care as much as I do.", "factor": "anxiety"},
    {"id": "X5", "text": "I get frustrated if I don't get the closeness I want.", "factor": "anxiety"},
    {"id": "X6", "text": "I fear being alone more than most people.", "factor": "anxiety"},
]

SCALE_INFO = {
    "min": 1,
    "max": 7,
    "labels": {
        1: "Strongly disagree",
        4: "Neutral",
        7: "Strongly agree"
    },
    "citation": {
        "name": "ECR-R (Experiences in Close Relationships – Revised)",
        "authors": "Fraley, Waller, & Brennan",
        "year": 2000,
        "link": "https://labs.psychology.illinois.edu/~rcfraley/measures/ecrr.htm"
    }
}

class SubmitPayload(BaseModel):
    answers: List[QuizAnswer]
    meta: Dict[str, Any] = {}

@app.get("/api/questions")
def get_questions():
    return {"questions": [{"id": q["id"], "text": q["text"]} for q in QUESTIONS], "scale": SCALE_INFO}


def compute_scores(answers: List[QuizAnswer]):
    # Build maps
    factor_scores = {"anxiety": [], "avoidance": []}
    qmap = {q["id"]: q for q in QUESTIONS}
    for ans in answers:
        if ans.question_id not in qmap:
            raise HTTPException(status_code=400, detail=f"Unknown question id: {ans.question_id}")
        factor = qmap[ans.question_id]["factor"]
        factor_scores[factor].append(ans.score)
    # Mean scores on 1-7 scale
    anxiety = sum(factor_scores["anxiety"]) / max(1, len(factor_scores["anxiety"]))
    avoidance = sum(factor_scores["avoidance"]) / max(1, len(factor_scores["avoidance"]))
    return anxiety, avoidance


def classify_style(anxiety: float, avoidance: float):
    # Midpoint threshold (4) split; can be refined later
    thr = 4.0
    if anxiety < thr and avoidance < thr:
        style = "Secure"
        prevalence = "~50% of adults in community samples"
        recs = [
            "Maintain open communication and healthy boundaries.",
            "Continue investing in supportive relationships.",
            "Practice self-reflection to keep patterns secure under stress.",
        ]
    elif anxiety >= thr and avoidance < thr:
        style = "Anxious (Preoccupied)"
        prevalence = "~20%"
        recs = [
            "Build self-soothing routines (breathing, grounding).",
            "Communicate needs clearly without protest behaviors.",
            "Seek consistent, responsive partners or therapists.",
        ]
    elif anxiety < thr and avoidance >= thr:
        style = "Avoidant (Dismissive)"
        prevalence = "~25%"
        recs = [
            "Practice expressing needs and accepting help.",
            "Experiment with gradual intimacy and repair attempts.",
            "Reflect on autonomy vs. connection to find balance.",
        ]
    else:
        style = "Fearful-Avoidant (Disorganized)"
        prevalence = "~5–10%"
        recs = [
            "Work on trauma-informed stabilization with a professional.",
            "Develop consistent routines for safety and connection.",
            "Use titrated exposure to intimacy with trusted others.",
        ]
    return style, prevalence, recs


@app.post("/api/submit")
def submit_quiz(payload: SubmitPayload):
    anxiety, avoidance = compute_scores(payload.answers)
    style, prevalence, recs = classify_style(anxiety, avoidance)
    result = QuizResult(
        answers=payload.answers,
        anxiety_score=anxiety,
        avoidance_score=avoidance,
        style=style,
        prevalence=prevalence,
        recommendations=recs,
        meta=payload.meta or {}
    )

    # Persist result
    try:
        create_document("quizresult", result)
    except Exception:
        # If DB not configured, continue without failing the quiz
        pass

    return {
        "style": style,
        "anxiety_score": round(anxiety, 2),
        "avoidance_score": round(avoidance, 2),
        "prevalence": prevalence,
        "recommendations": recs,
        "explanation": "Scores are computed on two dimensions (anxiety and avoidance) derived from the validated ECR-R measure."
    }

@app.get("/api/research")
def research_info():
    return {
        "sources": [
            {
                "title": "Experiences in Close Relationships – Revised (ECR-R)",
                "authors": "Fraley, Waller, & Brennan",
                "year": 2000,
                "url": "https://labs.psychology.illinois.edu/~rcfraley/measures/ecrr.htm",
                "note": "Widely used measure for adult attachment, providing anxiety and avoidance dimensions."
            },
            {
                "title": "Adult attachment orientations and their relations to romantic relationship functioning",
                "authors": "Mikulincer & Shaver",
                "year": 2007,
                "url": "https://doi.org/10.1037/0003-066X.61.2.167",
                "note": "Review summarizing prevalence and behavioral correlates of attachment styles."
            }
        ],
        "disclaimer": "This quiz is informational and not a clinical diagnosis. Questions are adapted from research items to keep the experience brief and blind."
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
