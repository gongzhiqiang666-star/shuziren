"""Argument-array adapter for the confirmed v122 runtime bridge."""

from pathlib import Path


class V122Adapter:
    def __init__(self, runtime_root, bridge_path, environment="env"):
        self.runtime_root = Path(runtime_root)
        self.bridge_path = Path(bridge_path)
        self.python = self.runtime_root / "_internal" / environment / "python.exe"

    def _command(self, action, *arguments):
        return [str(self.python), str(self.bridge_path), action] + [str(value) for value in arguments]

    def avatar_preprocess(self, video_path, model_name, model_id):
        return self._command("avatar-preprocess", video_path, model_name, model_id)

    def voice_create(self, audio_path, transcript, voice_name, voice_id):
        return self._command("voice-create", audio_path, transcript, voice_name, voice_id)

    def speech_generate(self, voice_id, transcript, text, output_path):
        return self._command("speech-generate", voice_id, transcript, text, output_path)

    def avatar_drive(self, model_id, audio_path, output_path):
        return self._command("avatar-drive", model_id, audio_path, output_path)
