import logging
import os

logger = logging.getLogger(__name__)


class SpeechService:
    """Google Cloud Speech-to-Text（設定時）または将来のサーバー側STT用"""

    def __init__(self):
        self.client = None
        creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds:
            logger.info("GOOGLE_APPLICATION_CREDENTIALS not set; server-side STT disabled")
            return
        try:
            from google.cloud import speech_v1p1beta1 as speech

            self.client = speech.SpeechClient()
            logger.info("Google Cloud Speech-to-Text client initialized")
        except Exception as exc:
            logger.error("Failed to initialize Speech client: %s", exc)

    def transcribe(self, audio_file_path: str, language_code: str = "ja-JP"):
        if not self.client:
            raise RuntimeError("Speech client not initialized")

        from google.cloud import speech_v1p1beta1 as speech

        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=language_code,
            enable_automatic_punctuation=True,
            model="default",
        )

        response = self.client.recognize(config=config, audio=audio)
        if response.results:
            result = response.results[0].alternatives[0]
            return result.transcript, result.confidence
        return "", 0.0
