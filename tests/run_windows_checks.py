"""Safe Windows integration tests: synthetic backend and real exe in waiting states only."""
import datetime as dt
import ctypes
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
VSWHERE = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
compilers = subprocess.check_output([str(VSWHERE), '-latest', '-products', '*',
                                    '-requires', 'Microsoft.Component.MSBuild', '-find',
                                    r'MSBuild\**\Bin\Roslyn\csc.exe'], text=True).splitlines()
if not compilers:
    raise RuntimeError('Visual Studio C# compiler not found; install .NET desktop development tools')
CSC = Path(compilers[0])
TEMP = Path(tempfile.gettempdir()) / 'opencode'
TEMP.mkdir(exist_ok=True)


def check_frozen_stop(sandbox, phase):
    run = sandbox / 'CATS'
    (run / 'save.txt').unlink(missing_ok=True)
    journals = sandbox / 'journals'
    journals.mkdir(exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    events = [dict(event='CarrierStats', timestamp=now.isoformat(), CarrierID=42, FuelLevel=1000),
              dict(event='CarrierJump', timestamp=(now - dt.timedelta(seconds=30)).isoformat(),
                   MarketID=42, Docked=True, StationType='FleetCarrier', StarSystem='Previous')]
    (journals / 'Journal.1.log').write_text(''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')
    (run / 'settings.txt').write_text('webhook_url=\njournal_directory=' + str(journals) + '\ntritium_slot=\nroute_file=route.txt\n', encoding='utf-8')
    (run / 'route.txt').write_text('Target\n', encoding='utf-8')
    target = (dt.datetime.now() + dt.timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S') if phase == 'schedule' else ''
    (sandbox / 'settings/settings.ini').write_text('auto-plot-jumps=True\ndisable-refuel=True\nscheduled-start=' + target + '\nshutdown-on-complete=True\n', encoding='utf-8')
    for filename in ('res.csv', 'photos.txt'):
        shutil.copy2(ROOT / 'TraversalSystem' / filename, run / filename)
    # Remote/headless desktops may expose an unsupported size. This test never
    # navigates: use dummy coordinates in the disposable fixture only.
    width = ctypes.windll.user32.GetSystemMetrics(0)
    height = ctypes.windll.user32.GetSystemMetrics(1)
    res = run / 'res.csv'
    res.write_text(res.read_text(encoding='utf-8').rstrip() + '\n%d,%d,1,1,1,1,1\n' % (width, height), encoding='utf-8')
    env = dict(os.environ, CATS_CONTROL_STDIN='1')
    process = subprocess.Popen([str(ROOT.parent / 'build/TraversalSystem-new.exe')], cwd=run, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               encoding='utf-8', bufsize=1)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
    try:
        expected = 'Waiting...' if phase == 'schedule' else 'Waiting for carrier cooldown'
        output = ''
        while expected not in output:
            try:
                output += lines.get(timeout=30)
            except queue.Empty:
                raise AssertionError('Exe did not enter ' + phase + '; exit=' + str(process.poll()) + '\n' + output)
        process.stdin.write('stop\n')
        process.stdin.flush()
        assert process.wait(timeout=10) == 3
        while not lines.empty():
            output += lines.get_nowait()
        assert 'Beginning navigation.' not in output
        assert 'Shutting down system' not in output
        print('PASS: real onefile exe Stop during ' + phase + ' (empty slot with refuel disabled)')
    finally:
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        process.stdin.close()


with tempfile.TemporaryDirectory(dir=TEMP) as temporary:
    sandbox = Path(temporary)
    backend_dir = sandbox / 'CATS/pyinstaller/TraversalSystem'
    backend_dir.mkdir(parents=True)
    (sandbox / 'settings').mkdir()
    (sandbox / 'settings/settings.ini').write_text('auto-plot-jumps=True\nopen-to-traversal=True\nget-tritium=False\ndisable-refuel=True\npower-saving=False\nrefuel-mode=0\nsingle-discord-message=False\nscheduled-start=2026-10-15 21:30\nshutdown-on-complete=True\n', encoding='utf-8')
    built = ROOT / 'MultiCarrierManager/bin/Release'
    for file in built.iterdir():
        if file.is_file() and file.suffix in ('.exe', '.dll', '.config'):
            shutil.copy2(file, sandbox / file.name)
    fixture = backend_dir / 'TraversalSystem-new.exe'
    subprocess.run([str(CSC), '/nologo', '/target:exe', '/out:' + str(fixture), str(ROOT / 'tests/FixtureBackend.cs')], check=True)
    runner = sandbox / 'GuiChecks.exe'
    subprocess.run([str(CSC), '/nologo', '/target:exe', '/out:' + str(runner),
                    '/r:' + str(sandbox / 'CATS-new.exe'), '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
                    str(ROOT / 'tests/GuiChecks.cs')], check=True)
    subprocess.run([str(runner)], cwd=sandbox, check=True, timeout=90)
    check_frozen_stop(sandbox, 'schedule')
    check_frozen_stop(sandbox, 'cooldown')
