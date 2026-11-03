"""Mock backend for the Rohingya learning app.

Every endpoint returns made-up sample data shaped like the API spec so the
frontend can build against it. Nothing is persisted yet.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import db, ml_adapters
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    ml_adapters.warmup()
    yield


app = FastAPI(title="Rohingya Learning App API (mock)", version="0.1.0", lifespan=lifespan)

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
    return {
        "status": "ok",
        "database": "up" if db.ping() else "down",
        "ml": ml_adapters.status(),
    }


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


# ------------------------------------------------------------ transcribe


@app.post("/api/transcribe", tags=["transcribe"])
def transcribe(audio: UploadFile = File(...), language: str | None = Form(None)):
    try:
        result = ml_adapters.transcribe_audio(audio.file, language)
    except ValueError as exc:  # unsupported language code
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if result["status"] == "model_error":
        return JSONResponse(result, status_code=503)
    if result["status"] != "ok":  # empty, invalid, too short/long, no speech
        return JSONResponse(result, status_code=422)
    return result


# ------------------------------------------------------------- translate

DIRECTIONS = {("en", "rhg"): "en->roh", ("rhg", "en"): "roh->en"}


class TranslateRequest(BaseModel):
    text: str
    source_language: str = "en"
    target_language: str = "rhg"
    preferred_script: str = "Latin"


@app.post("/api/translate", tags=["translate"])
def translate(body: TranslateRequest):
    direction = DIRECTIONS.get((body.source_language, body.target_language))
    if direction is None:
        raise HTTPException(
            status_code=400,
            detail="Supported pairs: en -> rhg and rhg -> en",
        )
    result = ml_adapters.translate_text(body.text, direction)
    if result["status"] == "failed":
        raise HTTPException(status_code=422, detail="Could not translate empty or invalid text")
    translated = result["status"] == "ok"
    return {
        "source_text": body.text,
        "translated_text": result["translation"] if translated else None,
        "target_language": body.target_language,
        "script": body.preferred_script,
        "status": "translated" if translated else "pending_translation",
        "confidence": result["confidence"],
        "verified": False,
        "audio_url": None,
        "stub": result["stub"],
    }


# --------------------------------------------------------- pronunciation


@app.post("/api/pronunciation/score", tags=["pronunciation"])
def score_pronunciation(
    audio: UploadFile = File(...),
    target_text: str | None = Form(None),
    word_id: str | None = Form(None),
    language: str = Form("rhg"),
    reference_id: str | None = Form(None),
):
    if word_id:
        _, word = _word_or_404(word_id)
        target_text = target_text or word["english"]
    if not target_text:
        raise HTTPException(status_code=422, detail="Provide target_text or word_id")

    result = ml_adapters.score_audio(audio.file, target_text)
    scored = result.get("score") is not None
    return {
        "word_id": word_id,
        "target_text": target_text,
        "score": result.get("score"),
        "max_score": 100,
        "feedback": result.get("feedback", ""),
        "tips": result.get("tips", []),
        "status": "scored" if scored else "scoring_unavailable",
        "validated": False,
        "stub": result["stub"],
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
