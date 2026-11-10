"""Scan Git publication candidates/history without printing potential secrets."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    'private user path': re.compile(r'(?i)[A-Z]:[/\\]+Users[/\\]+[^/\\\s]+'),
    'API token': re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'JWT token': re.compile(r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}'),
}
PRIVATE_DIRS = {'trash', '.venv', '.codex', '.claude', '__pycache__', 'models'}
PRIVATE_NAMES = {'config.local.json', 'config.local.json.tmp', 'auth.json', '.env'}
ASSETS = {'assets/chappy.ico', 'assets/cues/start.wav', 'assets/cues/end.wav'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def findings(path, data):
    file = Path(path)
    if any(part in PRIVATE_DIRS for part in file.parts) or file.name in PRIVATE_NAMES or (
        file.name.startswith('.env.') and file.name != '.env.example'
    ):
        yield 'local-only file'
    if file.suffix.lower() in {'.exe', '.dll', '.zip', '.7z', '.pem', '.key', '.log', '.wav', '.mp3', '.m4a', '.flac'} and path not in ASSETS:
        yield 'generated or private file'
    if path in ASSETS:
        return
    if b'\0' in data:
        yield 'unexpected binary'
        return
    text = data.decode('utf-8-sig', errors='replace')
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            yield label


def main():
    problems = []
    paths = set(git('ls-files', '-z', '--cached', '--others', '--exclude-standard').decode('utf-8').split('\0')) - {''}
    for path in sorted(paths):
        file = ROOT / path
        if file.is_file():
            problems.extend(f'{path}: {finding}' for finding in findings(path, file.read_bytes()))
    history = git('rev-list', '--objects', '--all').decode('utf-8').splitlines()
    blobs = 0
    for entry in history:
        oid, _, path = entry.partition(' ')
        if path and git('cat-file', '-t', oid).strip() == b'blob':
            blobs += 1
            problems.extend(f'history {oid[:8]} {path}: {finding}' for finding in findings(path, git('cat-file', 'blob', oid)))
    for problem in problems:
        print('CHECK:', problem)
    print(f'Scanned {len(paths)} publication candidates and {blobs} historical blobs; findings={len(problems)}')
    emails = git('log', '--all', '--format=%ae%n%ce').decode('utf-8').splitlines()
    if any(email and not email.endswith('@users.noreply.github.com') for email in emails):
        print('NOTICE: Git history includes a non-noreply author/committer email. Review locally before publishing.')
    return bool(problems)


if __name__ == '__main__':
    raise SystemExit(main())
