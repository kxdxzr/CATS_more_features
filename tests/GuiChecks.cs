using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using MultiCarrierManager;
using MultiCarrierManager.CATS;

class GuiChecks
{
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static void Pump(int milliseconds)
    {
        var timer = Stopwatch.StartNew();
        while (timer.ElapsedMilliseconds < milliseconds) { Application.DoEvents(); Thread.Sleep(10); }
    }
    static object Invoke(object instance, string name, params object[] args)
    {
        return instance.GetType().GetMethod(name, BindingFlags.NonPublic | BindingFlags.Instance).Invoke(instance, args);
    }
    [STAThread]
    static int Main()
    {
        try
        {
            var settings = new SettingsManager("settings/settings.ini");
            Check(settings.CompletionAction == "shutdown", "Legacy shutdown migration failed");
            var program = typeof(CATSForm).Assembly.GetType("MultiCarrierManager.Program");
            program.GetField("settings").SetValue(null, settings);
            program.GetField("logger").SetValue(null, new Logger());
            using (var form = new CATSForm())
            {
                var handle = form.Handle;
                Invoke(form, "LoadSchedule");
                var date = (DateTimePicker)form.Controls.Find("scheduleDate", true)[0];
                var time = (DateTimePicker)form.Controls.Find("scheduleTime", true)[0];
                var enabled = (CheckBox)form.Controls.Find("scheduleEnabled", true)[0];
                Check(date.Value.ToString("yyyy-MM-dd") == "2026-10-15" && time.Value.Hour == 21, "Old schedule load failed");
                Invoke(form.Controls.Find("scheduleTenMinutes", true)[0], "OnClick", EventArgs.Empty);
                DateTime parsed = DateTime.Parse(settings.ScheduledStart);
                Check(Math.Abs((parsed - DateTime.Now.AddMinutes(10)).TotalSeconds) < 3, "Quick time button failed");
                enabled.Checked = false;
                Check(settings.ScheduledStart == "", "Disabling schedule failed");
                ((TextBox)form.Controls.Find("textBox2", true)[0]).Text = "First\r\nSecond\r\nThird";
                File.WriteAllText("CATS/save.txt", "2");
                form.TraversalFinished();
                Check(((ComboBox)form.Controls.Find("comboBox1", true)[0]).SelectedIndex == 2,
                      "Stopped progress would be overwritten on next Run");
                foreach (string action in new [] { "keep-open", "close-apps", "shutdown" })
                {
                    settings.SetCompletionAction(action);
                    var loaded = new SettingsManager("settings/settings.ini");
                    Check(loaded.CompletionAction == action, "Completion action roundtrip failed");
                    using (var options = new OptionsForm())
                    {
                        Invoke(options, "OptionsForm_Load", null, EventArgs.Empty);
                        var choices = (ComboBox)options.Controls.Find("completionAction", true)[0];
                        Check(choices.SelectedIndex == Array.IndexOf(new[] { "keep-open", "close-apps", "shutdown" }, action), "Options selection failed");
                    }
                }
                var output = (TextBox)form.Controls.Find("textBox1", true)[0];
                var cats = new CatSitter(output, form, new Label(), new Label());
                foreach (string phase in new [] { "navigation", "countdown", "scheduled", "cooperative" })
                {
                    File.WriteAllText("CATS/mode.txt", phase);
                    cats.run_cmd();
                    var deadline = Stopwatch.StartNew();
                    while ((!File.Exists("CATS/pid-" + phase) || !File.Exists("CATS/ticks-" + phase)) && deadline.ElapsedMilliseconds < 10000) Pump(20);
                    Check(File.Exists("CATS/pid-" + phase), "Fixture failed to start");
                    int childPid = int.Parse(File.ReadAllText("CATS/pid-" + phase));
                    Check(cats.close() && !cats.isRunning, "Stop did not confirm exit");
                    bool alive;
                    try { alive = !Process.GetProcessById(childPid).HasExited; }
                    catch (ArgumentException) { alive = false; }
                    Check(!alive, "Onefile-like child survived Stop");
                    long size = new FileInfo("CATS/ticks-" + phase).Length;
                    // Restart before pumping the old run's callbacks.
                    if (phase == "navigation")
                    {
                        File.WriteAllText("CATS/mode.txt", "restart");
                        cats.run_cmd();
                        Pump(300);
                        Check(cats.isRunning, "Old exit callback stopped the new run");
                        Check(cats.close(), "Immediate restart could not stop");
                    }
                    Pump(250);
                    Check(new FileInfo("CATS/ticks-" + phase).Length == size, "Output continued after Stop");
                }
            }
            Console.WriteLine("PASS: picker/quick-button/settings and Stop/restart process-tree checks");
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
