"""Experimental visual LeiGod pause; refuses uncertain windows and never toggles white."""
import base64
import ctypes
import subprocess
import time


SCRIPT = r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class LeiUi {
 [StructLayout(LayoutKind.Sequential)] public struct R { public int L,T,Ri,B; }
 [StructLayout(LayoutKind.Sequential)] public struct P { public int X,Y; }
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
 [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a,uint b,bool c);
 [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h,int c);
 [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out R r);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(P p);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint d,UIntPtr e);
}
'@
function ReadButton($hwnd,$pidExpected) {
 if ([LeiUi]::GetForegroundWindow() -ne $hwnd) { return 'unknown' }
 $r=New-Object LeiUi+R
 if (-not [LeiUi]::GetWindowRect($hwnd,[ref]$r)) { return 'unknown' }
 $w=$r.Ri-$r.L; $h=$r.B-$r.T
 # Only the layout actually observed during the supervised test is accepted.
 if ($w -lt 1000 -or $w -gt 1040 -or $h -lt 615 -or $h -gt 660) { return 'unknown' }
 $x=[int]($r.L+$w*0.778); $y=[int]($r.T+$h*0.014)
 $cw=[int]($w*0.068); $ch=[int]($h*0.039)
 foreach ($dx in @(2,[int]($cw/2),($cw-3))) {
  foreach ($dy in @(2,[int]($ch/2),($ch-3))) {
   $pt=New-Object LeiUi+P; $pt.X=$x+$dx; $pt.Y=$y+$dy
   $owner=[uint32]0; [void][LeiUi]::GetWindowThreadProcessId([LeiUi]::WindowFromPoint($pt),[ref]$owner)
   if ($owner -ne $pidExpected) { return 'unknown' }
  }
 }
 $bmp=[System.Drawing.Bitmap]::new($cw,$ch); $g=[System.Drawing.Graphics]::FromImage($bmp)
 try {
  $g.CopyFromScreen($x,$y,0,0,$bmp.Size); $red=0; $white=0
  for($i=0;$i -lt $cw;$i++){for($j=0;$j -lt $ch;$j++){
   $c=$bmp.GetPixel($i,$j)
   if($c.R -gt 150 -and $c.R -gt 1.5*$c.G -and $c.R -gt 1.3*$c.B){$red++}
   if($c.R -gt 200 -and $c.G -gt 200 -and $c.B -gt 200){$white++}
  }}
  if($red -gt $cw*$ch*0.65){return 'red'}
  if($white -gt $cw*$ch*0.65){return 'white'}
  return 'unknown'
 } finally { $g.Dispose(); $bmp.Dispose() }
}
try {
 $windows=@(Get-Process -Name leigod -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0})
 if($windows.Count -ne 1){throw 'Expected exactly one LeiGod window'}
 $app=$windows[0]; $hwnd=$app.MainWindowHandle; $pidExpected=[uint32]$app.Id
 $dummy=[uint32]0; $other=[LeiUi]::GetWindowThreadProcessId([LeiUi]::GetForegroundWindow(),[ref]$dummy)
 $self=[LeiUi]::GetCurrentThreadId(); $attached=$false
 try {
  if($other -and $other -ne $self){$attached=[LeiUi]::AttachThreadInput($self,$other,$true)}
  [void][LeiUi]::ShowWindowAsync($hwnd,9); [void][LeiUi]::BringWindowToTop($hwnd)
  [void][LeiUi]::SetForegroundWindow($hwnd)
 } finally { if($attached){[void][LeiUi]::AttachThreadInput($self,$other,$false)} }
 Start-Sleep -Milliseconds 800
 $s=ReadButton $hwnd $pidExpected
 if($s -eq 'white'){Write-Output 'VISUALLY_ALREADY_PAUSED'; exit 0}
 if($s -ne 'red'){throw 'Foreground, layout, visibility or button colour not confirmed'}
 Start-Sleep -Milliseconds 300
 if((ReadButton $hwnd $pidExpected) -ne 'red'){throw 'Button state changed before click'}
 $r=New-Object LeiUi+R; [void][LeiUi]::GetWindowRect($hwnd,[ref]$r)
 $x=[int]($r.L+($r.Ri-$r.L)*0.812); $y=[int]($r.T+($r.B-$r.T)*0.033)
 if([LeiUi]::GetForegroundWindow() -ne $hwnd){throw 'Foreground changed before click'}
 [void][LeiUi]::SetCursorPos($x,$y)
 [LeiUi]::mouse_event(2,0,0,0,[UIntPtr]::Zero); [LeiUi]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
 for($i=0;$i -lt 20;$i++){
  Start-Sleep -Milliseconds 500
  if((ReadButton $hwnd $pidExpected) -eq 'white'){Write-Output 'VISUALLY_PAUSED'; exit 0}
 }
 throw 'Pause was clicked once, but confirmation was not seen'
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
"""


def pause(control, dry_run=False):
    if dry_run:
        print("TEST: would attempt LeiGod pause; no focus change, click or network request.", flush=True)
        return True
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("WARNING: LeiGod pause skipped: start CATS as administrator.", flush=True)
        return False
    command = base64.b64encode(SCRIPT.encode('utf-16le')).decode('ascii')
    process = None
    try:
        with control.lock:
            control.check()
            process = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive',
                                        '-EncodedCommand', command], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            control.cancel_external = lambda: process.kill() if process.poll() is None else None
        deadline = time.monotonic() + 20
        while process.poll() is None and time.monotonic() < deadline:
            control.sleep(0.1)
        if process.poll() is None:
            process.kill()
            process.communicate()
            print("WARNING: LeiGod pause timed out; status not confirmed.", flush=True)
            return False
        out, err = process.communicate()
        result = out.decode('utf-8', errors='replace').strip()
        if process.returncode == 0 and result in ('VISUALLY_PAUSED', 'VISUALLY_ALREADY_PAUSED'):
            print("LeiGod: visually paused; server billing not independently verified.", flush=True)
            return True
        print("WARNING: LeiGod pause not confirmed: %s" %
              (err.decode('utf-8', errors='replace').strip() or result or 'unknown error'), flush=True)
        return False
    except (OSError, subprocess.SubprocessError) as error:
        print("WARNING: LeiGod pause failed: %s" % error, flush=True)
        return False
    finally:
        with control.lock:
            control.cancel_external = lambda: None
