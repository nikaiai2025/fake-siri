import os
import contextlib
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from fake_siri.config import load_config
from fake_siri.voicevox_server import VoicevoxServer
from scripts import prepare_models
from scripts.check_publication import findings


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.patch = patch('scripts.prepare_models.ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def archive(self, entry):
        archive = self.root / 'fixture.zip'
        with zipfile.ZipFile(archive, 'w') as file:
            file.writestr(entry, b'model fixture')
        return archive

    def test_download_honors_custom_destination_and_is_repeatable(self):
        archive = self.archive(prepare_models.VOSK_MODEL + '/am/final.mdl')
        destination = self.root / 'custom Japanese model'
        with patch('urllib.request.urlretrieve', side_effect=lambda url, out: shutil.copyfile(archive, out)) as download:
            prepare_models.prepare_wake(destination)
            prepare_models.prepare_wake(destination)
        self.assertTrue((destination / 'am/final.mdl').is_file())
        download.assert_called_once()

    def test_download_cannot_escape_staging(self):
        archive = self.archive('../outside.txt')
        destination = self.root / 'model'
        with patch('urllib.request.urlretrieve', side_effect=lambda url, out: shutil.copyfile(archive, out)):
            with self.assertRaises(RuntimeError):
                prepare_models.prepare_wake(destination)
        self.assertFalse(destination.exists())
        self.assertFalse((self.root / 'trash/downloads/outside.txt').exists())

    def test_existing_incomplete_model_is_not_overwritten(self):
        destination = self.root / 'user model'
        destination.mkdir()
        with patch('urllib.request.urlretrieve') as download:
            with self.assertRaises(RuntimeError):
                prepare_models.prepare_wake(destination)
        download.assert_not_called()

    def test_existing_transcription_path_is_preserved(self):
        model = self.root / 'chosen model'
        model.mkdir()
        (model / 'model.bin').touch()
        config = load_config()
        config['transcription']['model_path'] = str(model)
        with patch('huggingface_hub.snapshot_download') as download, patch('scripts.prepare_models.save_config') as save:
            prepare_models.prepare_transcription(config)
        download.assert_not_called()
        save.assert_not_called()

    def test_new_transcription_model_uses_project_cache_and_relative_path(self):
        config = load_config()
        config['transcription']['model_path'] = ''
        target = self.root / 'trash/huggingface/example/snapshots/model'
        with patch('huggingface_hub.snapshot_download', return_value=str(target)) as download, \
             patch('scripts.prepare_models.save_config') as save:
            prepare_models.prepare_transcription(config)
        self.assertEqual(download.call_args.kwargs['cache_dir'], str(self.root / 'trash/huggingface'))
        self.assertEqual(config['transcription']['model_path'], 'trash/huggingface/example/snapshots/model')
        save.assert_called_once()

    def test_explicit_engine_path_resolves_from_project_not_working_directory(self):
        engine = self.root / 'custom/vv-engine/run.exe'
        engine.parent.mkdir(parents=True)
        engine.touch()
        config = load_config()['voicevox']
        config['engine_path'] = 'custom/vv-engine/run.exe'
        with patch('fake_siri.config.ROOT', self.root):
            self.assertEqual(VoicevoxServer(config, Mock()).find_engine(), engine)
        config['engine_path'] = 'missing/run.exe'
        with patch('fake_siri.config.ROOT', self.root):
            self.assertIsNone(VoicevoxServer(config, Mock()).find_engine())

    def test_standard_installer_directory_is_detected(self):
        engine = self.root / 'VOICEVOX/vv-engine/run.exe'
        engine.parent.mkdir(parents=True)
        engine.touch()
        config = load_config()['voicevox']
        config['engine_path'] = ''
        with patch.dict(os.environ, {'ProgramFiles': str(self.root)}, clear=True):
            self.assertEqual(VoicevoxServer(config, Mock()).find_engine(), engine)

    def test_publication_scan_checks_local_files_and_secrets_without_echoing_values(self):
        self.assertIn('local-only file', list(findings('config.local.json', b'{}')))
        token = 'sk-' + 'a' * 40
        self.assertEqual(list(findings('example.txt', token.encode())), ['API token'])
        private_path = 'C:' + '/Users/' + 'example/private'
        self.assertEqual(list(findings('example.txt', private_path.encode())), ['private user path'])
        self.assertEqual(list(findings('assets/cues/start.wav', b'RIFF\0')), [])
        self.assertIn('generated or private file', list(findings('recording.wav', b'RIFF\0')))

    def test_doctor_checks_voice_and_closes_services_without_generating(self):
        from fake_siri.__main__ import doctor
        config = load_config()
        config['voicevox']['speaker'] = 3
        model = self.root / 'fixture'
        (model / 'am').mkdir(parents=True)
        (model / 'am/final.mdl').touch()
        (model / 'model.bin').touch()
        config['wake']['model_path'] = str(model)
        config['transcription']['model_path'] = str(model)
        with patch('fake_siri.voicevox.Voicevox') as voice_type, \
             patch('fake_siri.codex_backend.CodexBackend') as backend_type, \
             patch('sounddevice.query_devices', return_value=[]), \
             contextlib.redirect_stdout(io.StringIO()):
            voice = voice_type.return_value
            voice.request.return_value = json.dumps([{'name': 'ずんだもん', 'styles': [{'id': 3, 'name': 'ノーマル'}]}]).encode()
            backend = backend_type.return_value
            backend.connect.return_value = 'ChatGPT'
            doctor(config)
            voice.ensure_ready.assert_called_once()
            voice.close.assert_called_once()
            backend.close.assert_called_once()
            backend.ask.assert_not_called()
            voice.speak.assert_not_called()

    def test_doctor_missing_voice_fails_and_still_cleans_up(self):
        from fake_siri.__main__ import doctor
        config = load_config()
        with patch('fake_siri.voicevox.Voicevox') as voice_type, \
             patch('fake_siri.codex_backend.CodexBackend') as backend_type, \
             patch('sounddevice.query_devices', return_value=[]), \
             contextlib.redirect_stdout(io.StringIO()):
            voice_type.return_value.request.return_value = b'[]'
            backend_type.return_value.connect.return_value = 'ChatGPT'
            with self.assertRaisesRegex(RuntimeError, 'VOICEVOX'):
                doctor(config)
            voice_type.return_value.close.assert_called_once()
            backend_type.return_value.close.assert_called_once()
