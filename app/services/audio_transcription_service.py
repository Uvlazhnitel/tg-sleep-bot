import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import UpstreamServiceError


class AudioTranscriptionService:
    _CONVERSION_SUFFIXES = {".oga", ".ogg"}

    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        settings.require_openai_api_key()
        self.settings = settings
        self.client = client or OpenAI(api_key=settings.openai_api_key)

    def transcribe_file(self, audio_path: str | Path) -> str:
        path = Path(audio_path)
        try:
            with self._prepared_audio_path(path) as prepared_path:
                with prepared_path.open("rb") as audio_file:
                    response = self.client.audio.transcriptions.create(
                        model=self.settings.openai_transcription_model,
                        file=audio_file,
                    )
        except Exception as exc:  # pragma: no cover
            raise UpstreamServiceError("Audio transcription request failed.") from exc

        transcript = self._extract_text(response)
        if not transcript:
            raise UpstreamServiceError("Audio transcription returned an empty response.")
        return transcript

    @contextmanager
    def _prepared_audio_path(self, path: Path) -> Iterator[Path]:
        if path.suffix.lower() not in self._CONVERSION_SUFFIXES:
            yield path
            return

        converted_path = self._convert_to_mp3(path)
        try:
            yield converted_path
        finally:
            if converted_path.exists():
                converted_path.unlink()

    def _convert_to_mp3(self, source_path: Path) -> Path:
        file_descriptor, destination = tempfile.mkstemp(suffix=".mp3")
        os.close(file_descriptor)
        destination_path = Path(destination)
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-acodec",
            "mp3",
            str(destination_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            if destination_path.exists():
                destination_path.unlink()
            raise UpstreamServiceError(
                "Audio conversion requires ffmpeg, but it is not installed."
            ) from exc
        except subprocess.CalledProcessError as exc:
            if destination_path.exists():
                destination_path.unlink()
            raise UpstreamServiceError(
                "Audio conversion failed before transcription."
            ) from exc
        return destination_path

    @staticmethod
    def _extract_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text.strip()
        return ""
