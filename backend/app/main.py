"""Mock backend for the Rohingya learning app.

Every endpoint returns made-up sample data shaped like the API spec so the
frontend can build against it. Nothing is persisted yet.
"""

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db
from app.mock_data import (
    AUDIO,
    CATEGORIES,
    DEFINITIONS,
    EXAMPLES,
    FORMS,
    IMAGES,
    SCRIPTS,
    SOURCES,
    WORD_INDEX,
    WORDS_BY_CATEGORY,
)

app = FastAPI(title="Rohingya Learning App API (mock)", version="0.1.0")

# Native Expo apps ignore CORS; this is only for Expo web / browser testing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CATEGORY_NAMES = {c["id"]: c["name"] for c in CATEGORIES}


def _word_or_404(word_id: str) -> tuple[str, dict]:
    if word_id not in WORD_INDEX:
        raise HTTPException(status_code=404, detail=f"Unknown word_id '{word_id}'")
    return WORD_INDEX[word_id]


# ---------------------------------------------------------------- health


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "database": "up" if db.ping() else "down"}


# ------------------------------------------------------------ categories


@app.get("/api/categories", tags=["categories"])
def get_categories():
    return {"categories": CATEGORIES}


@app.get("/api/categories/{category_id}/words", tags=["categories"])
def get_category_words(category_id: str):
    if category_id not in WORDS_BY_CATEGORY:
        raise HTTPException(status_code=404, detail=f"Unknown category_id '{category_id}'")
    return {"category_id": category_id, "words": WORDS_BY_CATEGORY[category_id]}


# ----------------------------------------------------------------- words


@app.get("/api/words", tags=["words"])
def list_words(
    category: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    items = [
        {**w, "category_id": cat_id}
        for cat_id, entries in WORDS_BY_CATEGORY.items()
        if category is None or cat_id == category
        for w in entries
    ]
    page = items[offset : offset + limit]
    next_offset = offset + limit if offset + limit < len(items) else None
    return {
        "words": page,
        "pagination": {"limit": limit, "offset": offset, "total": len(items),
                       "next_offset": next_offset},
    }


@app.get("/api/words/{word_id}", tags=["words"])
def get_word(word_id: str, script: str = "latn"):
    category_id, summary = _word_or_404(word_id)
    details = DEFINITIONS.get(word_id, {})
    return {
        "id": word_id,
        "english": {
            "term": summary["english"],
            "definition": details.get("definition"),
            "explanation": details.get("explanation"),
        },
        "rohingya": {
            "preferred_script": script,
            "text": None,
            "verified": False,
            "variants": [
                {"script": s["code"], "text": None, "type": s["type"], "verified": False}
                for s in SCRIPTS
            ],
        },
        "part_of_speech": details.get("part_of_speech"),
        "category": {"id": category_id, "name": CATEGORY_NAMES[category_id]},
        "related_topics": details.get("related_topics", []),
        "examples": EXAMPLES.get(word_id, [])[:1],
        "alternative_spellings": [],
        "word_forms": [],
        "media": {"audio": AUDIO.get(word_id, []), "images": IMAGES.get(word_id, [])},
        "sources": SOURCES if word_id in DEFINITIONS else [],
        "verification": {"status": "pending_review", "reviewed_by": None, "reviewed_at": None},
        "updated_at": "2026-10-21T00:00:00Z",
    }


@app.get("/api/words/{word_id}/scripts", tags=["words"])
def get_word_scripts(word_id: str):
    _word_or_404(word_id)
    return {
        "word_id": word_id,
        "available_scripts": [
            {"code": "latn", "label": "Latin transliteration", "available": True},
            {"code": "rohg", "label": "Hanifi Rohingya", "available": False},
        ],
        "preferred_script": "latn",
    }


@app.get("/api/words/{word_id}/examples", tags=["words"])
def get_word_examples(word_id: str):
    _word_or_404(word_id)
    return {"word_id": word_id, "examples": EXAMPLES.get(word_id, [])}


@app.get("/api/words/{word_id}/audio", tags=["words"])
def get_word_audio(word_id: str):
    _word_or_404(word_id)
    recordings = AUDIO.get(word_id, [])
    return {
        "word_id": word_id,
        "audio_url": recordings[0]["url"] if recordings else None,
        "language": "rhg",
        "speaker_type": "reviewed_reference" if recordings else None,
        "status": "available" if recordings else "unavailable",
        "audio": recordings,
    }


@app.get("/api/words/{word_id}/images", tags=["words"])
def get_word_images(word_id: str):
    _word_or_404(word_id)
    return {"word_id": word_id, "images": IMAGES.get(word_id, [])}


@app.get("/api/words/{word_id}/forms", tags=["words"])
def get_word_forms(word_id: str):
    _word_or_404(word_id)
    return {
        "word_id": word_id,
        "forms": FORMS.get(word_id, []),
        "examples": EXAMPLES.get(word_id, []),
    }


# ------------------------------------------------------------- translate


class TranslateRequest(BaseModel):
    text: str
    source_language: str = "en"
    target_language: str = "rhg"
    preferred_script: str = "Latin"


@app.post("/api/translate", tags=["translate"])
def translate(body: TranslateRequest):
    # No verified translations exist yet, so the answer is always "pending".
    return {
        "source_text": body.text,
        "translated_text": None,
        "target_language": body.target_language,
        "script": body.preferred_script,
        "status": "pending_translation",
        "verified": False,
        "audio_url": None,
    }


# --------------------------------------------------------- pronunciation


@app.post("/api/pronunciation/score", tags=["pronunciation"])
async def score_pronunciation(
    word_id: str = Form(...),
    language: str = Form("rhg"),
    reference_id: str | None = Form(None),
    audio: UploadFile = File(...),
):
    _word_or_404(word_id)
    await audio.read()  # accepted and discarded; nothing is stored
    return {
        "word_id": word_id,
        "score": 82,
        "max_score": 100,
        "feedback": "Good attempt. Practice the vowel sound.",
        "needs_improvement": [{"segment": "vowel_1", "issue": "Vowel differs from reference"}],
        "reference_audio_url": f"/audio/{word_id}.mp3",
        "status": "scored",
    }


# ---------------------------------------------------------------- lessons


@app.get("/api/lessons/{lesson_id}/next", tags=["lessons"])
def get_next_word(lesson_id: str):
    if lesson_id not in WORDS_BY_CATEGORY:
        raise HTTPException(status_code=404, detail=f"Unknown lesson_id '{lesson_id}'")
    return {
        "lesson_id": lesson_id,
        "next_word_id": "word_002",
        "english": "Hospital",
        "position": 2,
        "total": 12,
    }


# --------------------------------------------------------------- progress


class ProgressRequest(BaseModel):
    word_id: str
    completed: bool = True


@app.post("/api/progress", tags=["progress"])
def save_progress(body: ProgressRequest):
    _word_or_404(body.word_id)
    return {
        "success": True,
        "word_id": body.word_id,
        "completed": body.completed,
        "updated_progress_percent": 25,
    }


@app.get("/api/progress", tags=["progress"])
def get_progress():
    return {"completed_lessons": 2, "words_practiced": 18, "latest_pronunciation_score": 82}
