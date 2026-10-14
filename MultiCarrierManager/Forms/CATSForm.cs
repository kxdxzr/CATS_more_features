using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security;
using System.Windows.Forms;
using System.Windows.Forms.VisualStyles;
using MultiCarrierManager.CATS;

namespace MultiCarrierManager
{
    public partial class CATSForm : Form
    {
        private CatSitter cats;
        private bool DisableSave = false;
        private bool loadingSchedule;
        private CheckBox scheduleEnabled;
        private DateTimePicker scheduleDate, scheduleTime;
        private Button scheduleNow, scheduleTenMinutes, scheduleHour;
        public CATSForm()
        {
            InitializeComponent();
            InitializeScheduling();
            this.Shown += new System.EventHandler(this.CATSForm_Shown);
            this.Closed += new System.EventHandler(this.CATSForm_Closed);
        }

        private void CATSForm_Shown(object sender, EventArgs e)
        {
            cats = new CatSitter(textBox1, this, label1, label4);
            loadFromRouteFile();
            loadSettingsFile();
            updateSettings(sender, e);
            Program.logger.Log("TraversalFormLoaded");
        }


        private void CATSForm_Closed(object sender, EventArgs e)
        {
            if (cats != null) cats.close();
        }

        private void label6_Click(object sender, EventArgs e)
        {

        }

        private void label7_Click(object sender, EventArgs e)
        {

        }

        private void populateComboBox(object sender, EventArgs e)
        {
            DisableSave = true;
            ComboBox box = comboBox1;
            box.Items.Clear();

            box.Items.Add("Before first system in route");
            foreach (string line in textBox2.Text.Split(Environment.NewLine.ToCharArray()))
            {
                if (line == "" || line == Environment.NewLine) continue;
                box.Items.Add(line);
            }

            box.SelectedIndex = 0;

            if (File.Exists("CATS\\save.txt"))
            {
                try
                {
                    int index = Convert.ToInt32(File.ReadAllText("CATS\\save.txt"));
                    if (index == 0) File.Delete("CATS\\save.txt");
                    else box.SelectedIndex = index;
                }
                catch (Exception)
                {
                    File.Delete("CATS\\save.txt");
                    box.SelectedIndex = 0;
                }
            }
            DisableSave = false;
        }

        private void updateSettings(object sender, EventArgs e)
        {
            string journal = textBox5.Text;
            string slot = textBox3.Text;
            string route = textBox2.Text;
            int index = comboBox1.SelectedIndex;
            if (index < 0) index = 0;

            string[] oldLines = File.ReadAllLines("CATS\\settings.txt");
            foreach (string line in oldLines)
            {
                if (line.StartsWith("webhook_url"))
                {
                    webhook = line.Replace("webhook_url=", "");
                }
            }

            if (journal.Contains("~"))
            {
                journal = journal.Replace("~", Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
                textBox5.Text = journal;
            }
            
            if (!journal.EndsWith("\\")) {
                journal += "\\";
                textBox5.Text = journal;
            }

            string[] lines = new[] { "webhook_url=" + webhook, "journal_directory=" + journal, "tritium_slot=" + slot, "route_file=route.txt" };
            File.WriteAllLines("CATS\\settings.txt", lines);
            File.WriteAllText("CATS\\route.txt", route);
            File.WriteAllText("CATS\\save.txt", Convert.ToString(index));
            SaveSchedule();

            populateComboBox(sender, e);
        }

        private void runButton_Click(object sender, EventArgs e)
        {
            if (Program.settings.AutoPlot && !Program.settings.DisableRefuel)
            {
                int slot;
                if (!int.TryParse(textBox3.Text, out slot) || slot < 0)
                {
                    MessageBox.Show("Enter a non-negative Tritium slot, or disable automatic refuelling in Options.", "CATS");
                    return;
                }
            }
            updateSettings(sender, e);
            if (comboBox1.Items.Count <= 1)
            {
                MessageBox.Show("Please load a non-empty route before starting.", "CATS");
                return;
            }
            if (!cats.isRunning)
            {
                Program.logger.Log("TraversalRunning");
                cats.finalSystem = (string)comboBox1.Items[comboBox1.Items.Count - 1];
                Program.logger.Log("Destination:" + cats.finalSystem);

                stopButton.Enabled = true;
                runButton.Enabled = false;
                loadButton.Enabled = false;
                importButton.Enabled = false;
                button2.Enabled = false;
                button3.Enabled = false;
                SetRunSettingsEnabled(false);
                try { cats.run_cmd(); }
                catch (Exception error)
                {
                    TraversalFinished();
                    MessageBox.Show("Cannot start traversal: " + error.Message, "CATS");
                }
            }
        }

        public void stopButton_Click(object sender, EventArgs e)
        {
            if (cats.isRunning)
            {
                stopButton.Enabled = false;
                Program.logger.Log("TraversalStopRequested");
                if (cats.close()) TraversalFinished();
                else
                {
                    stopButton.Enabled = true;
                    MessageBox.Show("Traversal has not stopped. Run remains disabled; try Stop again.", "CATS");
                }
            }
        }

        public void TraversalFinished()
        {
            // Reload the backend's saved position before Run can write settings again.
            populateComboBox(this, EventArgs.Empty);
            stopButton.Enabled = false;
            runButton.Enabled = loadButton.Enabled = importButton.Enabled = true;
            button2.Enabled = button3.Enabled = true;
            SetRunSettingsEnabled(true);
            label1.Text = "Current jump: stopped";
            Text = "Carrier Administration and Traversal System (CATS)";
        }

        private void SetRunSettingsEnabled(bool enabled)
        {
            OptionsButton.Enabled = textBox2.Enabled = textBox3.Enabled = textBox5.Enabled = comboBox1.Enabled = enabled;
            scheduleEnabled.Enabled = scheduleNow.Enabled = scheduleTenMinutes.Enabled = scheduleHour.Enabled = enabled;
            scheduleDate.Enabled = scheduleTime.Enabled = enabled && scheduleEnabled.Checked;
        }

        private void loadFromRouteFile()
        {
            TextBox box = textBox2;
            textBox2.Text = "";
            string[] lines = File.ReadAllLines("CATS\\route.txt");

            foreach (string l in lines)
            {
                box.Text = box.Text + l + Environment.NewLine;
            }
            
            Program.logger.Log("RouteLoaded");
        }

        private string webhook;

        private void loadSettingsFile()
        {
            string[] lines = File.ReadAllLines("CATS\\settings.txt");
            textBox3.Text = "";
            textBox5.Text = "";
            LoadSchedule();

            foreach (string line in lines)
            {
                if (line.StartsWith("webhook_url"))
                {
                    webhook = line.Replace("webhook_url=", "");
                }
                else if (line.StartsWith("journal_directory"))
                {
                    textBox5.Text = line.Replace("journal_directory=", "");
                }
                else if (line.StartsWith("tritium_slot"))
                {
                    textBox3.Text = line.Replace("tritium_slot=", "");
                }
            }

            Program.logger.Log("TraversalSettingsLoaded");
        }

        private void loadButton_Click(object sender, EventArgs e)
        {
            OpenFileDialog dialog = new OpenFileDialog();
            if (dialog.ShowDialog() == DialogResult.OK)
            {
                try
                {
                    var filePath = dialog.FileName;
                    string[] lines = System.IO.File.ReadAllLines(filePath);
                    File.WriteAllLines("CATS\\route.txt", lines);
                    loadFromRouteFile();
                    updateSettings(sender, e);
                }
                catch (SecurityException ex)
                {
                    MessageBox.Show($"Security error.\n\nError message: {ex.Message}\n\n" +
                                    $"Details:\n\n{ex.StackTrace}");
                }
            }
        }

        private void importButton_Click(object sender, EventArgs e)
        {
            OpenFileDialog dialog = new OpenFileDialog()
            {
                Filter = "CSV Files (*.csv)|*.csv"
            };
            if (dialog.ShowDialog() == DialogResult.OK)
            {
                try
                {
                    var filePath = dialog.FileName;
                    string[] lines = System.IO.File.ReadAllLines(filePath);
                    List<string> systems = new List<string>();

                    int i = 0;

                    foreach (string line in lines)
                    {
                        i++;
                        if (i < 3) continue;
                        systems.Add(line.Split('"')[1]);
                    }


                    File.WriteAllLines("CATS\\route.txt", systems.ToArray());

                    loadFromRouteFile();
                    
                    updateSettings(sender, e);
                }
                catch (SecurityException ex)
                {
                    MessageBox.Show($"Security error.\n\nError message: {ex.Message}\n\n" +
                                    $"Details:\n\n{ex.StackTrace}");
                }
            }
        }

        private void button2_Click(object sender, EventArgs e)
        {
            if (!SpanshRouteForm.isOpen)
            {
                Hide();
                SpanshRouteForm.isOpen = true;
                SpanshRouteForm form = new SpanshRouteForm();
                form.ShowDialog();
                Close();
            }
        }

        private void button3_Click(object sender, EventArgs e)
        {
            Hide();
            Form1 form = new Form1();
            form.ShowDialog();
            Close();
        }

        private void CATSForm_FormClosing(object sender, FormClosingEventArgs e)
        {
            if (cats != null && cats.isRunning && !cats.close())
            {
                e.Cancel = true;
                MessageBox.Show("Could not stop traversal. Please try Stop again before closing.", "CATS");
                return;
            }
            if (e.CloseReason == CloseReason.UserClosing)
            {
                Program.logger.Log("End");
                Program.logger.Upload();
            }
        }

        private void OptionsButton_Click(object sender, EventArgs e)
        {
            OptionsForm form = new OptionsForm();
            form.ShowDialog();
        }

        private void button4_Click(object sender, EventArgs e)
        {
            AboutForm form = new AboutForm();
            form.ShowDialog();
        }

        private void CATSForm_Load(object sender, EventArgs e)
        {

        }

        private void button5_Click(object sender, EventArgs e)
        {
            DiscordForm form = new DiscordForm();
            form.ShowDialog();
        }

        private void comboBox1_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (!DisableSave) updateSettings(sender, e);
        }

        private void comboBox1_Click(object sender, EventArgs e)
        {
            updateSettings(sender, e);
        }

        private void textBox3_Leave(object sender, EventArgs e)
        {
            updateSettings(sender, e);
        }

        private void textBox5_Leave(object sender, EventArgs e)
        {
            updateSettings(sender, e);
        }

        private void InitializeScheduling()
        {
            scheduleEnabled = new CheckBox { Name = "scheduleEnabled", Text = "Scheduled start", Location = new System.Drawing.Point(12, 478), Size = new System.Drawing.Size(110, 24) };
            scheduleDate = new DateTimePicker { Name = "scheduleDate", Format = DateTimePickerFormat.Custom, CustomFormat = "yyyy-MM-dd", Location = new System.Drawing.Point(125, 480), Size = new System.Drawing.Size(132, 20) };
            scheduleTime = new DateTimePicker { Name = "scheduleTime", Format = DateTimePickerFormat.Custom, CustomFormat = "HH:mm:ss", ShowUpDown = true, Location = new System.Drawing.Point(265, 480), Size = new System.Drawing.Size(110, 20) };
            scheduleNow = new Button { Name = "scheduleNow", Text = "Now", Location = new System.Drawing.Point(385, 477), Size = new System.Drawing.Size(80, 25) };
            scheduleTenMinutes = new Button { Name = "scheduleTenMinutes", Text = "+10 min", Location = new System.Drawing.Point(475, 477), Size = new System.Drawing.Size(85, 25) };
            scheduleHour = new Button { Name = "scheduleHour", Text = "+1 hour", Location = new System.Drawing.Point(570, 477), Size = new System.Drawing.Size(90, 25) };
            Controls.AddRange(new Control[] { scheduleEnabled, scheduleDate, scheduleTime, scheduleNow, scheduleTenMinutes, scheduleHour });
            scheduleEnabled.CheckedChanged += (s, e) => { scheduleDate.Enabled = scheduleTime.Enabled = scheduleEnabled.Checked; SaveSchedule(); };
            scheduleDate.ValueChanged += (s, e) => SaveSchedule();
            scheduleTime.ValueChanged += (s, e) => SaveSchedule();
            scheduleNow.Click += (s, e) => SetSchedule(DateTime.Now);
            scheduleTenMinutes.Click += (s, e) => SetSchedule(DateTime.Now.AddMinutes(10));
            scheduleHour.Click += (s, e) => SetSchedule(DateTime.Now.AddHours(1));
        }

        private void SetSchedule(DateTime value)
        {
            loadingSchedule = true;
            scheduleDate.Value = scheduleTime.Value = value;
            scheduleEnabled.Checked = true;
            loadingSchedule = false;
            SaveSchedule();
        }

        private void LoadSchedule()
        {
            loadingSchedule = true;
            DateTime value;
            bool enabled = DateTime.TryParseExact(Program.settings.ScheduledStart,
                new[] { "yyyy-MM-dd HH:mm", "yyyy-MM-dd HH:mm:ss" },
                System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out value);
            scheduleDate.Value = scheduleTime.Value = enabled ? value : DateTime.Now;
            scheduleEnabled.Checked = enabled;
            scheduleDate.Enabled = scheduleTime.Enabled = enabled;
            loadingSchedule = false;
        }

        private void SaveSchedule()
        {
            if (loadingSchedule || Program.settings == null) return;
            DateTime value = scheduleDate.Value.Date.Add(scheduleTime.Value.TimeOfDay);
            Program.settings.SetScheduledStart(scheduleEnabled.Checked
                ? value.ToString("yyyy-MM-dd HH:mm:ss", System.Globalization.CultureInfo.InvariantCulture) : "");
        }
    }
}
