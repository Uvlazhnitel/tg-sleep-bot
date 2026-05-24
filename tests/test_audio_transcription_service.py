import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.core.exceptions import UpstreamServiceError
from app.services.audio_transcription_service import AudioTranscriptionService


class FakeTranscriptionsAPI:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self.response


class FakeAudioAPI:
    def __init__(self, response) -> None:
        self.transcriptions = FakeTranscriptionsAPI(response)


class FakeOpenAIClient:
    def __init__(self, response) -> None:
        self.audio = FakeAudioAPI(response)


class RecordingTranscriptionsAPI(FakeTranscriptionsAPI):
    def __init__(self, response) -> None:
        super().__init__(response)
        self.file_names: list[str] = []

    def create(self, **kwargs):
        file_obj = kwargs["file"]
        self.file_names.append(Path(file_obj.name).name)
        return super().create(**kwargs)


class RecordingAudioAPI:
    def __init__(self, response) -> None:
        self.transcriptions = RecordingTranscriptionsAPI(response)


class RecordingOpenAIClient:
    def __init__(self, response) -> None:
        self.audio = RecordingAudioAPI(response)


def test_transcribe_file_returns_text(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"fake audio")
    client = FakeOpenAIClient(SimpleNamespace(text="  Привет, это голосовое.  "))

    service = AudioTranscriptionService(settings, client=client)

    result = service.transcribe_file(audio_path)

    assert result == "Привет, это голосовое."
    assert client.audio.transcriptions.calls == 1


def test_transcribe_file_raises_for_empty_response(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"fake audio")
    client = FakeOpenAIClient(SimpleNamespace(text="   "))

    service = AudioTranscriptionService(settings, client=client)

    with pytest.raises(UpstreamServiceError):
        service.transcribe_file(audio_path)


def test_transcribe_file_converts_oga_before_transcribing(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    audio_path = tmp_path / "sample.oga"
    audio_path.write_bytes(b"fake audio")
    client = RecordingOpenAIClient(SimpleNamespace(text="Привет"))
    converted_paths: list[Path] = []

    def fake_run(command, check, stdout, stderr, text):
        assert command[0] == "ffmpeg"
        destination = Path(command[-1])
        converted_paths.append(destination)
        destination.write_bytes(b"converted audio")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.services.audio_transcription_service.subprocess.run", fake_run)

    service = AudioTranscriptionService(settings, client=client)

    result = service.transcribe_file(audio_path)

    assert result == "Привет"
    assert client.audio.transcriptions.file_names == [converted_paths[0].name]
    assert converted_paths[0].suffix == ".mp3"
    assert not converted_paths[0].exists()


def test_transcribe_file_skips_conversion_for_supported_input(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"fake audio")
    client = RecordingOpenAIClient(SimpleNamespace(text="Привет"))

    def fail_run(*args, **kwargs):
        raise AssertionError("ffmpeg should not be called for mp3 input")

    monkeypatch.setattr("app.services.audio_transcription_service.subprocess.run", fail_run)

    service = AudioTranscriptionService(settings, client=client)

    result = service.transcribe_file(audio_path)

    assert result == "Привет"
    assert client.audio.transcriptions.file_names == ["sample.mp3"]


def test_transcribe_file_raises_when_ffmpeg_is_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    audio_path = tmp_path / "sample.oga"
    audio_path.write_bytes(b"fake audio")
    client = RecordingOpenAIClient(SimpleNamespace(text="unused"))

    def missing_ffmpeg(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(
        "app.services.audio_transcription_service.subprocess.run", missing_ffmpeg
    )

    service = AudioTranscriptionService(settings, client=client)

    with pytest.raises(UpstreamServiceError, match="Audio transcription request failed."):
        service.transcribe_file(audio_path)


def test_transcribe_file_raises_when_conversion_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    audio_path = tmp_path / "sample.oga"
    audio_path.write_bytes(b"fake audio")
    client = RecordingOpenAIClient(SimpleNamespace(text="unused"))
    converted_paths: list[Path] = []

    def failed_conversion(command, check, stdout, stderr, text):
        destination = Path(command[-1])
        converted_paths.append(destination)
        destination.write_bytes(b"partial output")
        raise subprocess.CalledProcessError(1, command, stderr="boom")

    monkeypatch.setattr(
        "app.services.audio_transcription_service.subprocess.run", failed_conversion
    )

    service = AudioTranscriptionService(settings, client=client)

    with pytest.raises(UpstreamServiceError, match="Audio transcription request failed."):
        service.transcribe_file(audio_path)

    assert converted_paths
    assert not converted_paths[0].exists()
