from typing import Dict, Any, List
from app.db.database import db

# Privacy guarantee (Section 65 & 66):
# Do NOT store raw audio. Only process recognized text transcripts and log structured events.


class VoiceService:
    def __init__(self):
        self.suggested_commands: List[str] = [
            "Find wireless headphones under $80",
            "Find me a wireless keyboard under $70 with large keys",
            "Show cheaper options",
            "Compare the first two",
            "Add it to my cart",
            "What's in my cart?",
            "What's my total?",
            "Prepare checkout",
            "Confirm $59.36 purchase",
            "Cancel"
        ]

    def get_suggested_commands(self) -> List[str]:
        return self.suggested_commands

    def format_speech_for_screenreader(self, text: str) -> str:
        """Sanitizes text for clean synthesized output."""
        return text.replace("$", "dollars ").replace("/", " per ")


voice_service = VoiceService()
