using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

class FixtureBackend
{
    static void Main(string[] args)
    {
        if (args.Length > 0)
        {
            while (true) { File.AppendAllText("ticks-" + args[1], "."); Thread.Sleep(50); }
        }
        string mode = File.ReadAllText("mode.txt");
        var child = Process.Start(new ProcessStartInfo(Process.GetCurrentProcess().MainModule.FileName, "--child " + mode)
        { UseShellExecute = false, CreateNoWindow = true });
        File.WriteAllText("pid-" + mode, child.Id.ToString());
        Console.WriteLine("Fixture phase: " + mode);
        if (mode == "cooperative")
        {
            Console.ReadLine();
            Environment.Exit(3);
        }
        while (true) { Console.WriteLine("Fixture running " + mode); Thread.Sleep(100); }
    }
}
