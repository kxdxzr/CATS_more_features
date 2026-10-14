"""Package clean build outputs and repository defaults, never a live installation."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]

START_HERE = """CATS More Features {version} - Windows beta

THIS IS AN EXPERIMENTAL TEST BUILD AND MAY CONTAIN MANY BUGS.
Scheduled start has been tested in game. Full routes, refuelling, power saving,
cooldown recovery and real completion actions still need broader in-game testing.

Requirements: 64-bit Windows and .NET Framework 4.7.2 or newer.
Python does not need to be installed separately.

1. Extract the entire ZIP to a writable folder. Do not run from inside the ZIP.
2. Launch CATS-new.exe.
3. Configure Journal Dir and load a route (one destination per line).
4. Configure the tritium slot/refuelling mode, or disable automatic refuelling.
5. For a scheduled start, enable Scheduled start and choose the local date/time.
6. Choose Options > When route completes. The default keeps the game and CATS open.
7. Start with a supervised test. Stop halts CATS automation, not a jump already
   submitted in the game. Save your existing settings before updating installations.

Completion options: keep open, close game and CATS, or shut down the computer.
Game closure requests a normal exit, then terminates the game if necessary after
15 seconds. Windows shutdown has a 30-second countdown; cancel with shutdown /a.

This build does not include a Frontier API client ID. Journal-based traversal
works without it; Frontier API login requires your own registered client ID.
See building.md for configuration details, and README.md for limitations.

Reports: https://github.com/kxdxzr/CATS_more_features/issues
Source commit: {commit}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='v3.2.2-beta.1')
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'build/releases')
    args = parser.parse_args()
    if any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for char in args.version):
        raise ValueError('Invalid release version')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Commit intended changes before creating a release package')
    build = ROOT / 'MultiCarrierManager/bin/Release'
    files = {
        'CATS-new.exe': build / 'CATS-new.exe',
        'CATS-new.exe.config': build / 'CATS-new.exe.config',
        'CATS/pyinstaller/TraversalSystem/TraversalSystem-new.exe': ROOT.parent / 'build/TraversalSystem-new.exe',
        'settings/settings.ini': ROOT / 'MultiCarrierManager/settings.ini',
        'README.md': ROOT / 'README.md',
        'building.md': ROOT / 'building.md',
        'resolutions.md': ROOT / 'resolutions.md',
    }
    for dll in sorted(build.glob('*.dll')):
        files[dll.name] = dll
    if not any(name.endswith('.dll') for name in files):
        raise RuntimeError('Missing GUI dependencies; build Release output first')
    for name in ('settings.txt', 'res.csv', 'photos.txt'):
        files['CATS/' + name] = ROOT / 'TraversalSystem' / name
    for sequence in sorted((ROOT / 'TraversalSystem/sequences').rglob('*.txt')):
        files['CATS/sequences/' + sequence.relative_to(ROOT / 'TraversalSystem/sequences').as_posix()] = sequence
    for package in sorted((ROOT / 'packages').iterdir()):
        if not package.is_dir():
            continue
        for notice in sorted(package.iterdir()):
            if notice.is_file() and notice.name.upper().startswith(('LICENSE', 'THIRD-PARTY', 'NOTICE', 'COPYRIGHT')):
                files['third-party-notices/' + package.name + '/' + notice.name] = notice
    for name, file in files.items():
        if not file.is_file():
            raise FileNotFoundError('%s: %s' % (name, file))
    defaults = files['settings/settings.ini'].read_text(encoding='utf-8')
    assert 'completion-action=keep-open' in defaults
    assert 'shutdown-on-complete=False' in defaults
    assert 'scheduled-start=\n' in defaults
    assert 'webhook_url=\n' in files['CATS/settings.txt'].read_text(encoding='utf-8')
    generated = {
        'CATS/route.txt': b'',
        'START_HERE.txt': START_HERE.format(version=args.version, commit=commit).encode('utf-8'),
        'BUILD_INFO.txt': ('Version: %s\nSource commit: %s\nPlatform: Windows x64\n' % (args.version, commit)).encode('utf-8'),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / ('CATS-More-Features-%s-windows-x64.zip' % args.version)
    checksums = args.output / ('SHA256SUMS-%s.txt' % args.version)
    if archive.exists() or checksums.exists():
        raise FileExistsError('Release assets already exist; use a new version or output directory')
    hashes = []
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name in sorted(set(files) | set(generated)):
            content = generated[name] if name in generated else files[name].read_bytes()
            bundle.writestr(name, content)
            hashes.append(hashlib.sha256(content).hexdigest() + '  ' + name)
        bundle.writestr('SHA256SUMS.txt', '\n'.join(hashes) + '\n')
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError('Archive CRC verification failed')
        assert not any(name.startswith(('logs/', 'tokens/', 'carriers/')) for name in bundle.namelist())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksums.write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print(archive)
    print(checksums)
    print('ZIP SHA256: ' + digest)


if __name__ == '__main__':
    main()
