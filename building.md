# Building and testing this experimental fork

This is a testing build, not a stable release. Build **both** the GUI and Python backend: the new GUI
starts `CATS/pyinstaller/TraversalSystem/TraversalSystem-new.exe`, rather than the upstream backend name.

## Requirements

- Windows with Visual Studio's .NET desktop development tools, MSBuild and the .NET Framework 4.7.2 targeting pack.
- Python and pip. The current build has been tested with Python 3.13.9 in an isolated virtual environment.
- The NuGet dependencies under `packages/` from the repository.

Run the following commands from the repository root in PowerShell.

## 1. Build the Python backend

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\pyinstaller.exe TraversalSystem\main.py --onefile --name TraversalSystem-new --distpath ..\build --workpath ..\build\tmp --specpath ..\build --python-option u --noconfirm
```

The executable is written to `../build/TraversalSystem-new.exe`. The unused `zstd` dependency has been
removed to avoid its native compilation requirement; the existing `zstandard` dependency is retained.

## 2. Build the Windows Forms GUI

Locate MSBuild using Visual Studio Installer's `vswhere`:

```powershell
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$msbuild = & $vswhere -latest -products '*' -requires Microsoft.Component.MSBuild -find 'MSBuild\**\Bin\MSBuild.exe'
& $msbuild MultiCarrierManager.sln /t:Build /p:Configuration=Release /p:AssemblyName=CATS-new /p:PostBuildEvent= /verbosity:minimal /nologo
```

Output: `MultiCarrierManager/bin/Release/CATS-new.exe`, its `.config`, and dependency DLLs.
Disabling `PostBuildEvent` avoids the upstream packaging step copying default settings over a deployment.

### Frontier API configuration

When a private `MultiCarrierManager/ApiTools/OAuth2.cs` exists, the project uses it. Otherwise it compiles
`OAuth2.cs.template` automatically. A real Frontier client ID is **not required to compile or use journal-based
traversal, scheduling and refuelling**. Frontier API login in the admin interface requires your own registered ID.

For the template implementation, set either the environment variable `CATS_FRONTIER_CLIENT_ID`, or the
`FrontierClientId` appSettings entry in `CATS-new.exe.config`:

```xml
<appSettings>
  <add key="FrontierClientId" value="YOUR_REGISTERED_CLIENT_ID" />
</appSettings>
```

Add this section inside the existing `<configuration>` element; keep the other configuration sections.
Do not commit private OAuth source files, tokens, webhook URLs or local account settings.

## 3. Deploy the test build

Use a separate test installation, or back up the executables in an existing installation before replacing them.
Copy the new GUI, its `.config` and dependency DLLs from the Release output, and the new backend from `../build`.
The runtime directory must have this layout:

```text
<installation>/
  CATS-new.exe
  CATS-new.exe.config
  <dependency DLLs>
  settings/
    settings.ini
  CATS/
    settings.txt
    route.txt
    res.csv
    photos.txt
    sequences/
    pyinstaller/
      TraversalSystem/
        TraversalSystem-new.exe
```

For a fresh installation, copy `MultiCarrierManager/settings.ini` to `settings/settings.ini`, the files
`TraversalSystem/{settings.txt,res.csv,photos.txt}` into `CATS/`, and the complete `TraversalSystem/sequences/`
directory into `CATS/sequences/`. Create `CATS/route.txt` with one destination per line. Configure your actual
journal directory and tritium slot in the GUI before running. Preserve existing route, settings, tokens and account data
when updating an installation; do not replace those with repository defaults.

Start `CATS-new.exe`. It sets its working directory to the installation directory automatically.
To run the backend directly, the working directory must be `<installation>/CATS`, because settings, sequences
and other resources are resolved relative to that directory. GUI-managed Stop and auto-closing the CATS GUI require
starting the backend through the new GUI.

The old `build_TraversalSystem.sh` and Inno Setup scripts describe the upstream packaging layout. They have not
been updated or validated as installers for this fork; use the commands and manual layout above for this test build.

## 4. Run safe automated checks

After building both executables:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\venv\Scripts\python.exe tests\run_windows_checks.py
```

The Windows checks discover the C# compiler with `vswhere` and use temporary test directories. They build a synthetic
backend to verify process-tree Stop and immediate restart, inspect GUI controls/settings, and cancel the real onefile
backend while it is waiting for a scheduled start or carrier cooldown. They do not send game input, close a real game
or shut down the computer. Completion actions and game-process handling are mocked in the unit tests.

These checks do **not** establish reliable behaviour across every game state. Full routes, refuelling modes,
power saving, live cooldown transitions and real completion actions still need further in-game testing.

## Runtime details

- Stop requests cancellation and saves progress, with a Windows Job Object fallback that terminates backend descendants.
  It does not cancel a jump already submitted in the game. Logs include the backend PID and confirmed stop result.
- Restart reads recent journals and waits for pending jumps/cooldown. Cooldown is conservatively five minutes after an arrival
  event, or a five-minute startup wait if no arrival record or pending request can be recovered.
- `completion-action` is `keep-open`, `close-apps` or `shutdown`. If absent, legacy `shutdown-on-complete` is used.
- `close-apps` requests normal game exit, waits up to 15 seconds, then terminates the game if necessary. CATS exits only after
  successful route completion and successful game closure. Failure keeps the GUI open to show the error.
- `shutdown` schedules `shutdown /s /t 30` after route completion. Use `shutdown /a` to cancel the Windows countdown.
