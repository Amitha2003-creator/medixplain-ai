"""Text-to-speech for the voice assistant (English and Malayalam).

Uses gTTS, which sends the text to Google Translate's speech service and returns
an MP3. It needs an internet connection. Only the answer text is sent.
"""

import io
import re

GTTS_LANG = {"en": "en", "ml": "ml"}
MAX_SPEECH_CHARS = 1500  # long answers are cut so playback stays short


class VoiceError(RuntimeError):
    """Raised when speech cannot be created. The message is safe to show users."""


def clean_for_speech(text: str) -> str:
    """Remove things that sound odd when read aloud: [1] citations, markdown, links."""
    text = re.sub(r"\[\d+\]", "", text or "")                    # [1], [2]
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)         # [label](url) -> label
    text = re.sub(r"https?://\S+", "", text)                     # bare links
    text = re.sub(r"[*_`#>]+", "", text)                         # markdown symbols
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)  # bullet marks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)                  # "calcium ." -> "calcium."
    text = re.sub(r"\n{2,}", "\n", text).strip()
    if len(text) > MAX_SPEECH_CHARS:
        cut = text[:MAX_SPEECH_CHARS]
        last_sentence_end = cut.rfind(". ")
        text = cut[: last_sentence_end + 1] if last_sentence_end > 200 else cut
    return text


def text_to_speech(text: str, language: str = "en") -> bytes:
    """Return MP3 audio of the text in English or Malayalam."""
    from gtts import gTTS
    from gtts.tts import gTTSError

    spoken = clean_for_speech(text)
    if not spoken:
        raise VoiceError("There is no text to read aloud.")
    try:
        buffer = io.BytesIO()
        gTTS(spoken, lang=GTTS_LANG.get(language, "en")).write_to_fp(buffer)
    except gTTSError as exc:
        raise VoiceError(f"Could not create the spoken answer: {exc}") from exc
    return buffer.getvalue()