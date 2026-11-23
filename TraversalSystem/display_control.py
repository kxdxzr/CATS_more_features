"""Experimental Windows hardware brightness control; never runs until explicitly enabled."""
import ctypes
from ctypes import wintypes
import json
import subprocess
import threading


class PhysicalMonitor(ctypes.Structure):
    _fields_ = [('handle', wintypes.HANDLE), ('description', wintypes.WCHAR * 128)]


class WindowsBrightness:
    def __init__(self):
        self.saved_ddc = []
        self.saved_wmi = []
        self.lock = threading.RLock()

    def _powershell(self, script):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=12,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('Windows brightness interface failed')
        return result.stdout

    def _monitors(self, operation):
        user32, dxva = ctypes.windll.user32, ctypes.windll.dxva2
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                          ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
        user32.EnumDisplayMonitors.restype = wintypes.BOOL
        dxva.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
        dxva.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PhysicalMonitor)]
        dxva.GetMonitorBrightness.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        dxva.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        dxva.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.POINTER(PhysicalMonitor)]
        failures = []
        @callback_type
        def callback(monitor, dc, rect, data):
            count = wintypes.DWORD()
            if not dxva.GetNumberOfPhysicalMonitorsFromHMONITOR(monitor, ctypes.byref(count)) or not count.value:
                failures.append('Could not enumerate physical display')
                return True
            handles = (PhysicalMonitor * count.value)()
            if not dxva.GetPhysicalMonitorsFromHMONITOR(monitor, count, handles):
                failures.append('Could not open physical display')
                return True
            try:
                for index, physical in enumerate(handles):
                    try:
                        operation(dxva, monitor, index, physical)
                    except Exception as error:
                        failures.append(str(error))
            finally:
                dxva.DestroyPhysicalMonitors(count, handles)
            return True
        if not user32.EnumDisplayMonitors(None, None, callback, 0):
            failures.append('Display enumeration failed')
        return failures

    def dim(self):
        with self.lock:
            if self.saved_ddc or self.saved_wmi:
                return
            # Save software-controlled internal displays before any DDC operation.
            try:
                raw = self._powershell("$ErrorActionPreference='Stop'; @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Where-Object Active | Select-Object InstanceName,CurrentBrightness,Level) | ConvertTo-Json -Compress -Depth 4")
                data = json.loads(raw) if raw.strip() else []
                self.saved_wmi = data if isinstance(data, list) else [data]
            except Exception as error:
                print('Brightness: internal display query unavailable: %s' % error, flush=True)
            def reduce_ddc(dxva, monitor, index, physical):
                low, current, high = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
                if not dxva.GetMonitorBrightness(physical.handle, ctypes.byref(low), ctypes.byref(current), ctypes.byref(high)):
                    print('Brightness: DDC/CI unavailable for %s' % physical.description, flush=True)
                    return
                self.saved_ddc.append((monitor, index, current.value))
                if not dxva.SetMonitorBrightness(physical.handle, low.value):
                    print('Brightness: could not dim %s' % physical.description, flush=True)
            for failure in self._monitors(reduce_ddc):
                print('Brightness: ' + failure, flush=True)
            for item in self.saved_wmi:
                try:
                    name = item['InstanceName'].replace("'", "''")
                    low = min(item['Level'])
                    self._powershell("$ErrorActionPreference='Stop'; $m=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Where-Object { $_.InstanceName -eq '%s' }; if (-not $m) { exit 1 }; Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{Timeout=[uint32]0;Brightness=[byte]%d} | Out-Null" % (name, low))
                except Exception as error:
                    print('Brightness: could not dim internal display: %s' % error, flush=True)
            print('Brightness: dim request complete; unsupported displays may remain unchanged.', flush=True)

    def restore(self):
        with self.lock:
            if not self.saved_ddc and not self.saved_wmi:
                return
            saved = {(monitor, index): value for monitor, index, value in self.saved_ddc}
            def restore_ddc(dxva, monitor, index, physical):
                key = (monitor, index)
                if key in saved:
                    if dxva.SetMonitorBrightness(physical.handle, saved[key]):
                        del saved[key]
                    else:
                        print('Brightness: could not restore %s' % physical.description, flush=True)
            for failure in self._monitors(restore_ddc):
                print('Brightness: ' + failure, flush=True)
            self.saved_ddc = [(monitor, index, value) for (monitor, index), value in saved.items()]
            remaining = []
            for item in self.saved_wmi:
                try:
                    name = item['InstanceName'].replace("'", "''")
                    self._powershell("$ErrorActionPreference='Stop'; $m=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Where-Object { $_.InstanceName -eq '%s' }; if (-not $m) { exit 1 }; Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{Timeout=[uint32]0;Brightness=[byte]%d} | Out-Null" % (name, item['CurrentBrightness']))
                except Exception as error:
                    remaining.append(item)
                    print('Brightness: could not restore internal display: %s' % error, flush=True)
            self.saved_wmi = remaining
            if self.saved_ddc or self.saved_wmi:
                print('WARNING: Some displays could not be restored. Restore brightness manually.', flush=True)
            else:
                print('Brightness: original values restored.', flush=True)
