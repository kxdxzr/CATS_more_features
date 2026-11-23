using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace MultiCarrierManager.CATS
{
    public class CatSitter
    {
        private readonly TextBox output;
        private readonly CATSForm form;
        private readonly Label countdownLabel, etaLabel;
        private Process process;
        private ProcessJob job;
        private bool stopping, closeOnSuccess;
        public bool isRunning { get; set; }
        public string finalSystem { get; set; }
        private string nextSystem;

        public CatSitter(TextBox output, CATSForm form, Label countdownLabel, Label etaLabel)
        {
            this.output = output;
            this.form = form;
            this.countdownLabel = countdownLabel;
            this.etaLabel = etaLabel;
        }

        private void OnUi(Action action)
        {
            if (form.IsDisposed || !form.IsHandleCreated) return;
            try { form.BeginInvoke(action); }
            catch (InvalidOperationException) { }
        }

        public void run_cmd(bool refuelTest = false, bool completionTest = false)
        {
            if (process != null) throw new InvalidOperationException("Previous traversal has not stopped.");
            output.Clear();
            stopping = closeOnSuccess = false;
            var running = new Process();
            var runJob = new ProcessJob();
            process = running;
            job = runJob;
            running.StartInfo = new ProcessStartInfo
            {
                FileName = Path.GetFullPath("CATS\\pyinstaller\\TraversalSystem\\TraversalSystem-new.exe"),
                Arguments = refuelTest ? "--refuel-test" : completionTest ? "--completion-test-real-pause" : "",
                WorkingDirectory = Path.GetFullPath("CATS"),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = System.Text.Encoding.UTF8,
                StandardErrorEncoding = System.Text.Encoding.UTF8
            };
            running.StartInfo.EnvironmentVariables["CATS_CONTROL_STDIN"] = "1";
            DataReceivedEventHandler received = (sender, e) =>
            {
                if (e.Data == null) return;
                OnUi(() =>
                {
                    if (process != running || stopping) return;
                    HandleOutput(e.Data);
                });
            };
            running.OutputDataReceived += received;
            running.ErrorDataReceived += received;
            try
            {
                running.Start();
                runJob.Add(running);
                running.BeginOutputReadLine();
                running.BeginErrorReadLine();
                isRunning = true;
                Program.logger.Log("TraversalPID=" + running.Id);
                Task.Run(() =>
                {
                    // WaitForExit also drains redirected output before posting completion.
                    running.WaitForExit();
                    int code = running.ExitCode;
                    OnUi(() =>
                    {
                        if (process != running) { running.Dispose(); runJob.Dispose(); return; }
                        bool exitApplication = !stopping && code == 0 && closeOnSuccess;
                        Program.logger.Log("TraversalExitCode=" + code);
                        if (!runJob.Stop()) { Program.logger.LogError("Traversal descendants have not exited"); return; }
                        runJob.Dispose();
                        running.Dispose();
                        process = null;
                        job = null;
                        isRunning = false;
                        form.TraversalFinished();
                        if (exitApplication)
                        {
                            if (Program.settings.ScreenOffOnClose) ScheduleDisplaysOff();
                            Application.Exit();
                        }
                    });
                });
            }
            catch
            {
                runJob.Dispose();
                try { if (!running.HasExited) running.Kill(); } catch (InvalidOperationException) { }
                running.Dispose();
                process = null;
                job = null;
                isRunning = false;
                throw;
            }
        }

        private void HandleOutput(string line)
        {
            const string countdownPrefix = "CATS_COUNTDOWN:";
            if (line.StartsWith(countdownPrefix, StringComparison.Ordinal))
            {
                countdownLabel.Text = line.Substring(countdownPrefix.Length);
                return;
            }
            int remaining;
            if (int.TryParse(line, out remaining))
            {
                countdownLabel.Text = "Current jump: " + TimeSpan.FromSeconds(remaining).ToString(@"hh\:mm\:ss");
                return;
            }
            output.AppendText(line + Environment.NewLine);
            if (!line.StartsWith("journal_directory=")) Program.logger.LogCats(line);
            if (line == "CATS_COMPLETION_CLOSE") closeOnSuccess = true;
            if (line.StartsWith("Next stop: ")) nextSystem = line.Substring(11);
            if (line.StartsWith("ETA:")) etaLabel.Text = line;
            if (line.StartsWith("Waiting for carrier")) countdownLabel.Text = line;
            if (line.StartsWith("alert:")) { MessageBox.Show(line.Substring(6), "Alert"); return; }
            string stage = null;
            if (line == "Beginning in 5...") stage = "Starting up...";
            if (line == "Beginning navigation.") stage = "Navigating menus...";
            if (line.StartsWith("Navigation complete")) stage = "Counting down...";
            if (line == "Jumping!") stage = "In hyperspace...";
            if (line == "Jump complete!" || line == "Refuel process completed.") stage = "Cooling down...";
            if (line == "Restocking tritium...") stage = "Restocking tritium...";
            if (stage != null) form.Text = $"CATS | En route to {finalSystem} | Next stop: {nextSystem} | {stage}";
        }

        private static void ScheduleDisplaysOff()
        {
            // Delay until the GUI exits; SC_MONITORPOWER only requests display power off,
            // not system sleep. User activity or Windows can wake displays again.
            string script = "Start-Sleep -Seconds 2; Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class DisplayPower { [DllImport(\"user32.dll\", SetLastError=true)] public static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, IntPtr l, uint f, uint t, out IntPtr r); }'; $r=[IntPtr]::Zero; [DisplayPower]::SendMessageTimeout([IntPtr]0xffff,0x112,[IntPtr]0xf170,[IntPtr]2,2,1000,[ref]$r) | Out-Null";
            try
            {
                Process.Start(new ProcessStartInfo("powershell.exe", "-NoProfile -NonInteractive -EncodedCommand " + Convert.ToBase64String(System.Text.Encoding.Unicode.GetBytes(script)))
                { UseShellExecute = false, CreateNoWindow = true });
                Program.logger.Log("Display power-off requested after CATS exit");
            }
            catch (Exception error) { Program.logger.LogError("Display power-off request failed: " + error.Message); }
        }

        public bool close()
        {
            var running = process;
            if (running == null) return true;
            stopping = true;
            closeOnSuccess = false;
            try
            {
                if (!running.HasExited)
                {
                    try { running.StandardInput.WriteLine("stop"); running.StandardInput.Flush(); }
                    catch (IOException) { }
                    if (!running.WaitForExit(Program.settings.DimDuringJump ? 30000 : 1500))
                    {
                        Program.logger.Log("TraversalStop: terminating process job");
                        if (!job.Stop()) return false;
                    }
                    if (!running.WaitForExit(5000)) return false;
                }
                if (!job.Stop()) return false;
                job.Dispose();
                Program.logger.Log("TraversalStoppedConfirmed PID=" + running.Id + " ExitCode=" + running.ExitCode);
                process = null; // queued callbacks from this run are now obsolete
                job = null;
                isRunning = false;
                return true;
            }
            catch (Exception e)
            {
                Program.logger.LogError("TraversalStop failed: " + e.Message);
                return false;
            }
        }
    }
}
