"""Dummy data copied from the API spec.

Everything here is made up. All Rohingya text is intentionally null —
do not add translations here unless they come from a verified source.
"""

CATEGORIES = [
    {"id": "healthcare", "name": "Healthcare",
     "description": "Words and phrases for hospitals, clinics, and appointments"},
    {"id": "education", "name": "Education",
     "description": "School registration, teachers, and classroom communication"},
    {"id": "housing", "name": "Housing",
     "description": "Finding a home, asking about rent, and repairs"},
    {"id": "daily_life", "name": "Daily Life",
     "description": "Greetings, shopping, and common requests"},
    {"id": "transportation", "name": "Transportation",
     "description": "Bus routes, tickets, and directions"},
    {"id": "employment", "name": "Employment",
     "description": "Job applications, schedules, and workplace questions"},
]

# Healthcare words from the spec, plus the expanded sentence bank as phrases.
_SENTENCE_BANK = {
    "healthcare": [
        "I need help finding a family doctor.",
        "I do not understand this prescription.",
        "Can you tell me when my appointment starts?",
        "Where can I get medicine?",
        "I need an interpreter for my appointment.",
    ],
    "education": [
        "How do I register my child for school?",
        "Where can I find the school office?",
        "Can you explain this homework?",
        "When does the school day finish?",
        "Is there someone who can help translate this letter?",
    ],
    "housing": [
        "I am looking for a place to rent.",
        "How much is the monthly rent?",
        "Are utilities included in the rent?",
        "The heater in my apartment is not working.",
        "Who should I contact about a repair?",
    ],
    "daily_life": [
        "Could you please repeat that?",
        "I am still learning English.",
        "How much does this cost?",
        "Where can I find the nearest grocery store?",
        "Thank you for helping me.",
    ],
    "transportation": [
        "Which bus goes to the Welcome Centre?",
        "Where do I buy a bus ticket?",
        "What time does the next bus leave?",
        "Is this the correct stop for the hospital?",
        "Could you show me the way to the station?",
    ],
    "employment": [
        "Where can I find job postings?",
        "Can someone help me write a resume?",
        "What documents do I need to apply?",
        "What time does my shift start?",
        "Can you explain the workplace safety instructions?",
    ],
}


def _build_words() -> dict[str, list[dict]]:
    words: dict[str, list[dict]] = {
        "healthcare": [
            {"id": "word_001", "english": "Doctor", "type": "word", "translation_available": True},
            {"id": "word_002", "english": "Hospital", "type": "word", "translation_available": True},
            {"id": "phrase_003", "english": "I need to see a doctor.", "type": "phrase",
             "translation_available": False},
            {"id": "phrase_004", "english": "Where is the nearest clinic?", "type": "phrase",
             "translation_available": False},
            {"id": "phrase_005", "english": "I have an appointment tomorrow.", "type": "phrase",
             "translation_available": False},
        ]
    }
    counter = 6
    for category_id, sentences in _SENTENCE_BANK.items():
        entries = words.setdefault(category_id, [])
        for sentence in sentences:
            entries.append({
                "id": f"phrase_{counter:03d}",
                "english": sentence,
                "type": "phrase",
                "translation_available": False,
            })
            counter += 1
    return words


WORDS_BY_CATEGORY = _build_words()

# word_id -> (category_id, summary)
WORD_INDEX = {
    w["id"]: (cat_id, w)
    for cat_id, entries in WORDS_BY_CATEGORY.items()
    for w in entries
}

EXAMPLES = {
    "word_001": [
        {"id": "example_001", "english": "I need to see a doctor.", "rohingya": None, "verified": False},
        {"id": "example_002", "english": "Can I make an appointment with a doctor?",
         "rohingya": None, "verified": False},
        {"id": "example_003", "english": "Is there a doctor who can help me today?",
         "rohingya": None, "verified": False},
    ],
}

FORMS = {
    "word_001": [
        {"type": "related_phrase", "english": "Doctor's appointment", "rohingya": None,
         "script": "latn", "verified": False},
    ],
}

AUDIO = {
    "word_001": [
        {"id": "audio_001", "url": "/media/audio/word_001_reference.mp3", "format": "audio/mpeg",
         "speaker_variety": "unspecified", "verified": False, "duration_seconds": 2.1},
    ],
}

IMAGES = {
    "word_001": [
        {"id": "image_001", "url": "/media/images/doctor-illustration.webp",
         "alt_text": "Illustration of a doctor speaking with a patient",
         "license": "rights_to_be_confirmed"},
    ],
}

DEFINITIONS = {
    "word_001": {
        "definition": "A medical professional who diagnoses and treats health conditions.",
        "explanation": "Use this word when asking for medical help.",
        "part_of_speech": "noun",
        "related_topics": ["appointments", "clinic visits"],
    },
}

SCRIPTS = [
    {"code": "latn", "label": "Latin transliteration", "type": "transliteration"},
    {"code": "rohg", "label": "Hanifi Rohingya", "type": "native_script"},
]

SOURCES = [
    {
        "source_id": "source_001",
        "type": "community_review",
        "name": "Welcome Centre language review",
        "reference_url": None,
        "notes": "Confirm reviewer attribution and consent before publication",
        "verification": {"status": "pending_review", "reviewed_at": None},
    }
]
