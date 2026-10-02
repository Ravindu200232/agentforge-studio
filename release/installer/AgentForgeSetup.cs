// AgentForgeSetup.exe: the one-click online installer.
//
// It reads manifest.json (the latest GitHub release's, unless /manifest= names another), then downloads and installs
// every component it lists into %LOCALAPPDATA%\Programs\AgentForge: the app itself and each command line tool a blank
// Windows computer is missing. Four files download side by side, each is installed as soon as it arrives, and the npm
// tools start the moment Node.js is in place. One progress bar, weighted by size, goes from 0 to 100%; every download
// is checked against its sha256. It needs no administrator rights, adds Desktop and Start-menu shortcuts and an entry in
// "Installed apps", and run again it repairs or updates (an unchanged component is not downloaded again).
//
//   AgentForgeSetup.exe                         install or update
//   AgentForgeSetup.exe /uninstall              remove the app (the user's projects and settings stay)
//   AgentForgeSetup.exe /manifest=<url|path>    install from another manifest (a local build, a test)
//   AgentForgeSetup.exe /dir=<folder>           install somewhere else
//   AgentForgeSetup.exe /noshortcuts            no Desktop or Start-menu shortcut (tests)
//   AgentForgeSetup.exe /auto                   start at once, close when done (exit code 0 = installed)
//
// Built with the C# compiler every Windows has (release/build.ps1), so it is written for C# 5.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace AgentForge.Setup
{
    class Options
    {
        public static readonly string DefaultDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", Config.AppName);
        const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\";

        public string Manifest = Config.ManifestUrl;
        public string InstallDir;
        public bool Uninstall;
        public bool Shortcuts = true;           // the Start-menu entry, and the Desktop one unless it is unticked
        public bool DesktopShortcut = true;
        public bool Auto;

        public static Options Parse(string[] args)
        {
            var options = new Options();
            foreach (var arg in args)
            {
                var lower = arg.ToLowerInvariant();
                if (lower == "/uninstall") options.Uninstall = true;
                else if (lower == "/noshortcuts") options.Shortcuts = false;
                else if (lower == "/auto") options.Auto = true;
                else if (lower.StartsWith("/manifest=")) options.Manifest = arg.Substring("/manifest=".Length).Trim('"');
                else if (lower.StartsWith("/dir=")) options.InstallDir = arg.Substring("/dir=".Length).Trim('"');
            }
            // An update or a removal goes where AgentForge already is; a first install to the default place.
            if (string.IsNullOrEmpty(options.InstallDir))
                options.InstallDir = (options.Uninstall ? InstalledHere() : null) ?? Previous() ?? DefaultDir;
            return options;
        }

        /// <summary>Where AgentForge was installed last time (its "Installed apps" entry), if it is still there.</summary>
        public static string Previous()
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(UninstallKey + Config.AppName))
                {
                    var place = key == null ? null : key.GetValue("InstallLocation") as string;
                    return !string.IsNullOrEmpty(place) && IsInstallation(place) ? place : null;
                }
            }
            catch { return null; }
        }

        /// <summary>The folder this exe runs from, when it is the copy inside an installation.</summary>
        static string InstalledHere()
        {
            var here = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            return IsInstallation(here) ? here : null;
        }

        /// <summary>Whether a folder is an AgentForge installation, the only kind setup replaces or removes.</summary>
        public static bool IsInstallation(string folder)
        {
            return Directory.Exists(folder) && (File.Exists(Path.Combine(folder, "installed.json")) || File.Exists(Path.Combine(folder, Config.AppName + ".exe")));
        }
    }

    class Component
    {
        public string Id, Title, Url, Sha256, Type, Target, Version;
        public long Size, Weight;
        public int Strip;
        public List<string> Packages = new List<string>();
        public List<string> Command = new List<string>();
        public Dictionary<string, string> Env = new Dictionary<string, string>();

        /// <summary>How much of the bar this component is: its download and its installation.</summary>
        public long Work { get { return Weight > 0 ? Weight : Math.Max(1, Size) + Math.Max(1, Size) / 3; } }

        /// <summary>What an installed copy is recorded as, so an unchanged one is not installed again.</summary>
        public string Stamp { get { return (Sha256 ?? "") + "|" + string.Join(",", Packages) + "|" + string.Join(" ", Command) + "|" + (Version ?? ""); } }
    }

    class Manifest
    {
        public string Version = "";
        public List<Component> Components = new List<Component>();

        public static Manifest Parse(string json)
        {
            var data = (Dictionary<string, object>)new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.DeserializeObject(json);
            var manifest = new Manifest { Version = Text(data, "version") };
            foreach (var raw in (object[])data["components"])
            {
                var row = (Dictionary<string, object>)raw;
                var component = new Component
                {
                    Id = Text(row, "id"), Title = Text(row, "title"), Url = Text(row, "url"), Sha256 = Text(row, "sha256").ToLowerInvariant(),
                    Type = Text(row, "type"), Target = Text(row, "target"), Version = Text(row, "version"),
                    Size = Number(row, "size"), Weight = Number(row, "weight"), Strip = (int)Number(row, "strip"),
                };
                if (row.ContainsKey("packages")) foreach (var item in (object[])row["packages"]) component.Packages.Add(Convert.ToString(item));
                if (row.ContainsKey("command")) foreach (var item in (object[])row["command"]) component.Command.Add(Convert.ToString(item));
                if (row.ContainsKey("env")) foreach (var pair in (Dictionary<string, object>)row["env"]) component.Env[pair.Key] = Convert.ToString(pair.Value);
                manifest.Components.Add(component);
            }
            return manifest;
        }

        static string Text(Dictionary<string, object> row, string key)
        {
            object value;
            return row.TryGetValue(key, out value) && value != null ? Convert.ToString(value) : "";
        }

        static long Number(Dictionary<string, object> row, string key)
        {
            object value;
            return row.TryGetValue(key, out value) && value != null ? Convert.ToInt64(value) : 0;
        }
    }

    class Cancelled : Exception { }

    /// <summary>The work itself, run on background threads; the form only draws what it reports.</summary>
    class Installer
    {
        /// <summary>How many files download side by side.</summary>
        const int ParallelDownloads = 4;
        const string NodeFolder = "tools/node";
        static readonly string[] Kinds = { "zip", "msi-extract", "npm-global", "npm-exec" };

        readonly Options options;
        readonly Action<double, string> report;
        readonly Func<bool> cancelled;
        readonly object sync = new object();
        long done, total;                                   // units of the bar
        long received, toReceive;                           // what the downloads have brought, out of all of them
        int downloading;                                    // files downloading right now
        readonly List<string> installing = new List<string>();
        readonly Stopwatch drawn = Stopwatch.StartNew();
        Exception failure;                                  // the first thing that went wrong: everything else stops for it
        Dictionary<string, string> installed;
        readonly string downloads = Path.Combine(Path.GetTempPath(), "AgentForgeSetup");
        static readonly string LogFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AgentForge", "install.log");

        public Installer(Options options, Action<double, string> report, Func<bool> cancelled)
        {
            this.options = options;
            this.report = report;
            this.cancelled = cancelled;
        }

        static readonly object LogLock = new object();

        public static void Log(string line)
        {
            try
            {
                lock (LogLock)       // several installs write at once: one at a time, or a line is lost to a sharing error
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(LogFile));
                    File.AppendAllText(LogFile, string.Format("{0:yyyy-MM-dd HH:mm:ss}  {1}{2}", DateTime.Now, line, Environment.NewLine));
                }
            }
            catch { }
        }

        bool Stopping { get { lock (sync) return failure != null || cancelled(); } }

        /// <summary>Moves the bar on by `units`, `bytes` of them downloaded ones.</summary>
        void Advance(long units, long bytes)
        {
            lock (sync) { done += units; received += bytes; }
            if (Stopping) throw new Cancelled();
            Draw(false);
        }

        /// <summary>Tells the form how far it is: at most ten times a second, unless `now` (something started or ended).</summary>
        void Draw(bool now)
        {
            double fraction;
            string text;
            lock (sync)
            {
                if (!now && drawn.ElapsedMilliseconds < 100) return;
                drawn.Restart();
                fraction = total > 0 ? Math.Min(1.0, (double)done / total) : 0;
                var lines = new List<string>();
                if (installing.Count > 0)
                    lines.Add("Installing " + installing[0] + (installing.Count > 1 ? string.Format(" and {0} more", installing.Count - 1) : "") + "…");
                if (downloading > 0)
                    lines.Add(string.Format("Downloading {0} · {1:0} of {2:0} MB", downloading == 1 ? "1 file" : downloading + " files",
                                            received / 1048576.0, Math.Max(received, toReceive) / 1048576.0));
                text = lines.Count > 0 ? string.Join("\n", lines) : "Getting ready…";
            }
            report(fraction, text);
        }

        string Tools(string relative) { return Path.Combine(options.InstallDir, relative.Replace('/', '\\')); }

        static bool HasFile(Component component) { return component.Type == "zip" || component.Type == "msi-extract"; }

        public string Run()
        {
            ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072 | (SecurityProtocolType)12288;   // TLS 1.2 and 1.3
            ServicePointManager.DefaultConnectionLimit = 16;     // .NET Framework allows two connections to one host otherwise
            ServicePointManager.Expect100Continue = false;
            Directory.CreateDirectory(options.InstallDir);
            Directory.CreateDirectory(downloads);
            Log("install into " + options.InstallDir + " from " + options.Manifest);

            installed = ReadInstalled();
            WriteInstalled(installed);              // marks the folder as AgentForge's from the start, so a retry or a removal knows it
            report(0, "Reading what to install…");
            var manifest = Manifest.Parse(ReadText(options.Manifest));
            var todo = manifest.Components.Where(c => !installed.ContainsKey(c.Id) || installed[c.Id] != c.Stamp || !Directory.Exists(Tools(c.Target))).ToList();
            var unknown = todo.FirstOrDefault(c => !Kinds.Contains(c.Type));
            if (unknown != null) throw new InvalidOperationException("The manifest names an unknown component type: " + unknown.Type);
            total = todo.Sum(c => c.Work);
            toReceive = todo.Where(HasFile).Sum(c => c.Size);
            Log(string.Format("version {0}: {1} of {2} components to install", manifest.Version, todo.Count, manifest.Components.Count));

            // Everything at once: a few files download side by side, each is installed the moment it is here, and the
            // npm tools start as soon as Node.js is in place.
            var gate = new SemaphoreSlim(ParallelDownloads);
            var work = new List<Task>();
            Task node = null;
            foreach (var component in todo.Where(HasFile))
            {
                var c = component;
                var task = Background(delegate
                {
                    gate.Wait();
                    string file;
                    try { file = Download(c); }
                    finally { gate.Release(); }
                    Install(c, file);
                });
                if (c.Target == NodeFolder) node = task;
                work.Add(task);
            }
            foreach (var component in todo.Where(c => !HasFile(c)))
            {
                var c = component;
                work.Add(Background(delegate
                {
                    if (node != null)
                        try { node.Wait(); } catch (AggregateException) { throw new Cancelled(); }
                    Install(c, null);
                }));
            }
            while (work.Count > 0)
            {
                var index = Task.WaitAny(work.ToArray());
                var ended = work[index];
                work.RemoveAt(index);
                if (!ended.IsFaulted) continue;
                // Something went wrong: the rest notice and stop, then the user sees the first real error.
                try { Task.WaitAll(work.ToArray(), 60000); } catch (AggregateException) { }
                Exception first;
                lock (sync) first = failure;
                if (first == null || cancelled()) throw new Cancelled();
                ExceptionDispatchInfo.Capture(first).Throw();
            }

            report(1, "Finishing…");
            var exe = Path.Combine(options.InstallDir, Config.AppName + ".exe");
            CopySelf();
            Register(manifest.Version, exe);
            if (options.Shortcuts) Shortcuts.Create(exe, options.InstallDir, options.DesktopShortcut);
            Log("installed " + manifest.Version);
            try { Directory.Delete(downloads, true); } catch { }
            return exe;
        }

        /// <summary>Runs `work` on its own thread; the first real error it hits is recorded, and stops everything else.</summary>
        Task Background(Action work)
        {
            return Task.Factory.StartNew(delegate
            {
                try { work(); }
                catch (Cancelled) { throw; }
                catch (Exception error)
                {
                    lock (sync) if (failure == null) failure = error;
                    throw;
                }
            }, CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        }

        void Install(Component component, string file)
        {
            if (Stopping) throw new Cancelled();
            Log("install " + component.Id);
            lock (sync) installing.Add(component.Title);
            Draw(true);
            try
            {
                if (component.Type == "zip") InstallZip(component, file);
                else if (component.Type == "msi-extract") InstallMsi(component, file);
                else if (component.Type == "npm-global") InstallNpm(component);
                else RunNpmExec(component);
            }
            finally
            {
                lock (sync) installing.Remove(component.Title);
            }
            lock (sync)
            {
                installed[component.Id] = component.Stamp;
                WriteInstalled(installed);
            }
            Log("installed " + component.Id);
            Draw(true);
        }

        // ---- downloading ---------------------------------------------------------------------------------------

        static string ReadText(string where)
        {
            if (File.Exists(where)) return File.ReadAllText(where, Encoding.UTF8);
            using (var client = new WebClient())
            {
                client.Headers[HttpRequestHeader.UserAgent] = "AgentForgeSetup";
                client.Encoding = Encoding.UTF8;
                try { return client.DownloadString(where); }
                catch (WebException error)
                {
                    var response = error.Response as HttpWebResponse;
                    if (response != null && response.StatusCode == HttpStatusCode.NotFound)
                        throw new InvalidOperationException("No AgentForge release is published yet, so there is nothing to install. Try again once it is out.", error);
                    if (response == null)
                        throw new InvalidOperationException("Setup could not reach GitHub to see what to install. Check the internet connection and press Try again.", error);
                    throw;
                }
            }
        }

        /// <summary>The component's file, downloaded (or resumed) and checked against its sha256.</summary>
        string Download(Component component)
        {
            if (Stopping) throw new Cancelled();
            var name = component.Id + Path.GetExtension(new Uri(component.Url, UriKind.RelativeOrAbsolute).IsAbsoluteUri
                ? new Uri(component.Url).AbsolutePath : component.Url);
            var file = Path.Combine(downloads, name);
            var counted = new Counted();
            if (File.Exists(file) && Sha256(file) == component.Sha256) { CountTo(component, counted, component.Size); return file; }
            lock (sync) downloading++;
            Draw(true);
            try
            {
                if (File.Exists(component.Url))
                {
                    File.Copy(component.Url, file, true);     // a local manifest's own file
                }
                else
                {
                    Exception last = null;
                    for (int attempt = 1; attempt <= 4; attempt++)
                    {
                        try { Fetch(component, file, counted); last = null; break; }
                        catch (Cancelled) { throw; }
                        catch (Exception error)
                        {
                            last = error;
                            Log(string.Format("download {0} attempt {1} failed: {2}", component.Id, attempt, error.Message));
                            var web = error as WebException;
                            var response = web == null ? null : web.Response as HttpWebResponse;
                            if (response != null && (int)response.StatusCode == 416) File.Delete(file);   // a whole, but wrong, file: start over
                            if (Stopping) throw new Cancelled();
                            Thread.Sleep(1500 * attempt);
                        }
                    }
                    if (last != null) throw new InvalidOperationException(string.Format("{0} could not be downloaded: {1}", component.Title, last.Message));
                }
            }
            finally
            {
                lock (sync) downloading--;
            }
            CountTo(component, counted, component.Size);
            if (!string.IsNullOrEmpty(component.Sha256) && Sha256(file) != component.Sha256)
            {
                File.Delete(file);
                throw new InvalidOperationException(component.Title + " did not download correctly (its checksum does not match). Run the setup again.");
            }
            return file;
        }

        /// <summary>How much of the bar one download has moved, so a retry never counts the same bytes twice.</summary>
        class Counted { public long Units; }

        /// <summary>Brings a download's share of the bar up to `units` (its share is its size).</summary>
        void CountTo(Component component, Counted counted, long units)
        {
            units = Math.Min(units, component.Size);
            if (units > counted.Units)
            {
                var more = units - counted.Units;
                counted.Units = units;
                Advance(more, more);
            }
            else if (Stopping) throw new Cancelled();
        }

        void Fetch(Component component, string file, Counted counted)
        {
            long have = File.Exists(file) ? new FileInfo(file).Length : 0;
            var request = (HttpWebRequest)WebRequest.Create(component.Url);
            request.UserAgent = "AgentForgeSetup";
            request.Timeout = 60000;
            request.ReadWriteTimeout = 120000;
            if (have > 0) request.AddRange(have);
            using (var response = (HttpWebResponse)request.GetResponse())
            {
                bool resumed = response.StatusCode == HttpStatusCode.PartialContent;
                if (!resumed) have = 0;
                long length = response.ContentLength > 0 ? response.ContentLength + have : component.Size;
                Func<long, long> share = bytes => length > 0 ? (long)((double)bytes / length * component.Size) : 0;
                CountTo(component, counted, share(have));
                using (var input = response.GetResponseStream())
                using (var output = new FileStream(file, resumed ? FileMode.Append : FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20))
                {
                    var buffer = new byte[1 << 18];
                    long got = have;
                    int read;
                    while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        output.Write(buffer, 0, read);
                        got += read;
                        CountTo(component, counted, share(got));
                    }
                }
            }
        }

        static string Sha256(string file)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(file))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        // ---- installing ----------------------------------------------------------------------------------------

        void InstallZip(Component component, string file)
        {
            var target = Tools(component.Target);
            if (component.Id == "app")
            {
                WaitForAppToClose();
                // The app's own files are all in the archive: last version's leftovers would only confuse it.
                var resources = Path.Combine(target, "resources");
                if (Directory.Exists(resources)) Directory.Delete(resources, true);
            }
            else if (Directory.Exists(target))
            {
                Directory.Delete(target, true);
            }
            Directory.CreateDirectory(target);
            var root = Path.GetFullPath(target).TrimEnd('\\') + "\\";
            using (var archive = ZipFile.OpenRead(file))
            {
                long all = Math.Max(1, archive.Entries.Sum(e => e.Length));
                long budget = component.Work - component.Size, reported = 0, seen = 0;
                foreach (var entry in archive.Entries)
                {
                    var parts = entry.FullName.Replace('\\', '/').Split('/').Skip(component.Strip).ToArray();
                    var relative = string.Join("\\", parts);
                    if (relative.Length == 0) continue;
                    var destination = Path.GetFullPath(Path.Combine(target, relative));
                    if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;      // never outside the target
                    if (entry.FullName.EndsWith("/") || entry.FullName.EndsWith("\\")) { Directory.CreateDirectory(destination); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    entry.ExtractToFile(destination, true);
                    seen += entry.Length;
                    long now = (long)((double)seen / all * budget);
                    Advance(now - reported, 0);
                    reported = now;
                }
                if (reported < budget) Advance(budget - reported, 0);
            }
        }

        void InstallMsi(Component component, string file)
        {
            var target = Tools(component.Target);
            if (Directory.Exists(target)) Directory.Delete(target, true);
            Directory.CreateDirectory(target);
            // An administrative install only unpacks the package, so it needs no administrator rights.
            var code = Execute("msiexec.exe", string.Format("/a \"{0}\" /qn TARGETDIR=\"{1}\"", file, target.TrimEnd('\\')), null, 1800);
            if (code != 0) throw new InvalidOperationException(string.Format("{0} could not be unpacked (msiexec exit {1}).", component.Title, code));
            Advance(component.Work - component.Size, 0);
        }

        string Node { get { return Tools(NodeFolder + "/node.exe"); } }
        string Npm { get { return Tools(NodeFolder + "/node_modules/npm/bin/npm-cli.js"); } }

        Dictionary<string, string> ToolEnv(Component component)
        {
            var env = new Dictionary<string, string>();
            env["PATH"] = string.Join(";", new[] { Tools("tools/node"), Tools("tools/npm"), Tools("tools/git/cmd"), Environment.GetEnvironmentVariable("PATH") ?? "" });
            env["npm_config_update_notifier"] = "false";
            env["npm_config_fund"] = "false";
            env["npm_config_audit"] = "false";
            foreach (var pair in component.Env) env[pair.Key] = pair.Value.Replace("{install}", options.InstallDir);
            return env;
        }

        void InstallNpm(Component component)
        {
            if (!File.Exists(Node)) throw new InvalidOperationException("Node.js has to be installed before " + component.Title + ".");
            var target = Tools(component.Target);
            Directory.CreateDirectory(target);
            var args = string.Format("\"{0}\" install -g --prefix \"{1}\" {2}", Npm, target.TrimEnd('\\'), string.Join(" ", component.Packages.Select(p => "\"" + p + "\"")));
            var code = Execute(Node, args, ToolEnv(component), 3600);
            if (code != 0) throw new InvalidOperationException(string.Format("{0} could not be installed (npm exit {1}). See {2}.", component.Title, code, LogFile));
            Advance(component.Work, 0);
        }

        void RunNpmExec(Component component)
        {
            if (!File.Exists(Node)) throw new InvalidOperationException("Node.js has to be installed before " + component.Title + ".");
            Directory.CreateDirectory(Tools(component.Target));
            var args = string.Format("\"{0}\" exec --yes -- {1}", Npm, string.Join(" ", component.Command.Select(p => "\"" + p + "\"")));
            var code = Execute(Node, args, ToolEnv(component), 3600);
            if (code != 0) throw new InvalidOperationException(string.Format("{0} could not be installed (exit {1}). See {2}.", component.Title, code, LogFile));
            Advance(component.Work, 0);
        }

        int Execute(string exe, string args, Dictionary<string, string> env, int seconds)
        {
            Log("run " + exe + " " + args);
            var start = new ProcessStartInfo(exe, args)
            {
                UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,   // what node writes
                WorkingDirectory = options.InstallDir,
            };
            if (env != null) foreach (var pair in env) start.EnvironmentVariables[pair.Key] = pair.Value;
            using (var process = Process.Start(start))
            {
                process.OutputDataReceived += (s, e) => { if (e.Data != null) Log("  " + e.Data); };
                process.ErrorDataReceived += (s, e) => { if (e.Data != null) Log("  " + e.Data); };
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                var deadline = DateTime.Now.AddSeconds(seconds);
                while (!process.WaitForExit(500))
                {
                    if (Stopping || DateTime.Now > deadline)
                    {
                        try { Process.Start(new ProcessStartInfo("taskkill", "/PID " + process.Id + " /T /F") { CreateNoWindow = true, UseShellExecute = false }).WaitForExit(); } catch { }
                        if (Stopping) throw new Cancelled();
                        return -1;
                    }
                    Draw(false);
                }
                process.WaitForExit();
                return process.ExitCode;
            }
        }

        void WaitForAppToClose()
        {
            while (Process.GetProcessesByName(Config.AppName).Any(p => { try { return p.MainModule.FileName.StartsWith(options.InstallDir, StringComparison.OrdinalIgnoreCase); } catch { return true; } }))
            {
                var answer = MessageBox.Show("AgentForge is open. Close it, then press Retry to carry on.", "AgentForge Setup",
                                             MessageBoxButtons.RetryCancel, MessageBoxIcon.Information);
                if (answer == DialogResult.Cancel) throw new Cancelled();
            }
        }

        // ---- the record of what is installed, and Windows' own records ---------------------------------------------

        string InstalledFile { get { return Path.Combine(options.InstallDir, "installed.json"); } }

        Dictionary<string, string> ReadInstalled()
        {
            try
            {
                var data = new JavaScriptSerializer().Deserialize<Dictionary<string, string>>(File.ReadAllText(InstalledFile));
                return data ?? new Dictionary<string, string>();
            }
            catch { return new Dictionary<string, string>(); }
        }

        void WriteInstalled(Dictionary<string, string> installed)
        {
            File.WriteAllText(InstalledFile, new JavaScriptSerializer().Serialize(installed));
        }

        void CopySelf()
        {
            var self = Assembly.GetExecutingAssembly().Location;
            var copy = Path.Combine(options.InstallDir, "AgentForgeSetup.exe");
            if (!string.Equals(Path.GetFullPath(self), Path.GetFullPath(copy), StringComparison.OrdinalIgnoreCase))
                File.Copy(self, copy, true);
        }

        void Register(string version, string exe)
        {
            using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + Config.AppName))
            {
                var setup = Path.Combine(options.InstallDir, "AgentForgeSetup.exe");
                key.SetValue("DisplayName", Config.AppName);
                key.SetValue("DisplayVersion", version);
                key.SetValue("Publisher", Config.Publisher);
                key.SetValue("DisplayIcon", exe);
                key.SetValue("InstallLocation", options.InstallDir);
                key.SetValue("UninstallString", string.Format("\"{0}\" /uninstall", setup));
                key.SetValue("ModifyPath", string.Format("\"{0}\"", setup));
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                key.SetValue("EstimatedSize", (int)(FolderSize(options.InstallDir) / 1024), RegistryValueKind.DWord);
            }
        }

        static long FolderSize(string folder)
        {
            try { return new DirectoryInfo(folder).EnumerateFiles("*", SearchOption.AllDirectories).Sum(f => f.Length); }
            catch { return 0; }
        }

        // ---- removing ------------------------------------------------------------------------------------------

        public static void Uninstall(Options options)
        {
            Log("uninstall " + options.InstallDir);
            if (!Options.IsInstallation(options.InstallDir))
                throw new InvalidOperationException(options.InstallDir + " is not an AgentForge installation, so nothing was removed.");
            foreach (var process in Process.GetProcessesByName(Config.AppName))
            {
                try { process.CloseMainWindow(); process.WaitForExit(5000); if (!process.HasExited) process.Kill(); } catch { }
            }
            Shortcuts.Remove();
            Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + Config.AppName, false);
            // This exe may be the one inside the folder: the folder goes once it has exited.
            var command = string.Format("/c ping 127.0.0.1 -n 3 > nul & rmdir /s /q \"{0}\"", options.InstallDir);
            Process.Start(new ProcessStartInfo("cmd.exe", command) { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden });
        }
    }

    static class Shortcuts
    {
        static string Desktop { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), Config.AppName + ".lnk"); } }
        static string StartMenu { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), Config.AppName + ".lnk"); } }

        public static void Create(string exe, string folder, bool desktop)
        {
            if (!desktop) try { if (File.Exists(Desktop)) File.Delete(Desktop); } catch { }
            foreach (var place in desktop ? new[] { Desktop, StartMenu } : new[] { StartMenu })
            {
                var shellType = Type.GetTypeFromProgID("WScript.Shell");
                var shell = Activator.CreateInstance(shellType);
                var link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { place });
                var linkType = link.GetType();
                linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { exe });
                linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { folder });
                linkType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, link, new object[] { exe + ",0" });
                linkType.InvokeMember("Description", BindingFlags.SetProperty, null, link, new object[] { "AgentForge — build, test and deploy apps with AI agents" });
                linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
            }
        }

        public static void Remove()
        {
            foreach (var place in new[] { Desktop, StartMenu })
                try { if (File.Exists(place)) File.Delete(place); } catch { }
        }
    }

    /// <summary>One window: what will happen, one progress bar, and OK to open the app.</summary>
    class SetupForm : Form
    {
        static readonly Color Accent = Color.FromArgb(139, 132, 243);
        static readonly Color Ink = Color.FromArgb(22, 24, 29);
        static readonly Color Muted = Color.FromArgb(104, 108, 120);

        readonly Options options;
        readonly Label title = new Label(), detail = new Label(), status = new Label(), percent = new Label(), placeLabel = new Label();
        readonly TextBox place = new TextBox();
        readonly Button change = new Button();
        readonly CheckBox desktop = new CheckBox();
        readonly Bar bar = new Bar();
        readonly Button primary = new Button(), secondary = new Button();
        volatile bool stop;
        bool working, finished;
        string appExe;

        public SetupForm(Options options)
        {
            this.options = options;
            Text = options.Uninstall ? "Remove AgentForge" : "AgentForge Setup";
            AutoScaleMode = AutoScaleMode.Dpi;
            AutoScaleDimensions = new SizeF(96F, 96F);
            ClientSize = new Size(560, 350);
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.White;
            Font = new Font("Segoe UI", 9.75F);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            var logo = new PictureBox { Location = new Point(32, 30), Size = new Size(56, 56), SizeMode = PictureBoxSizeMode.Zoom };
            try { logo.Image = Icon.ExtractAssociatedIcon(Application.ExecutablePath).ToBitmap(); } catch { }
            Controls.Add(logo);

            title.SetBounds(104, 30, 420, 34);
            title.Font = new Font("Segoe UI Semibold", 17F);
            title.ForeColor = Ink;
            title.Text = "AgentForge";
            Controls.Add(title);

            detail.SetBounds(104, 66, 420, 112);
            detail.ForeColor = Muted;
            detail.Text = options.Uninstall
                ? "Removes AgentForge and the tools it installed from " + options.InstallDir + ".\n\nYour projects (Documents\\AgentForge) and settings stay, so a later install picks up where you left off."
                : "Plan, build, test and deploy apps with AI agents.\n\nSetup downloads AgentForge and everything it needs (Python, Node.js, Git and the GitHub, AWS, Azure, Vercel, Netlify and Supabase command line tools), about 1 GB. No administrator rights are needed.";
            Controls.Add(detail);

            // Where to install, and whether to put AgentForge on the Desktop: chosen before anything is downloaded.
            placeLabel.SetBounds(32, 186, 496, 20);
            placeLabel.ForeColor = Ink;
            placeLabel.Text = "Install location";
            Controls.Add(placeLabel);

            place.SetBounds(32, 208, 384, 26);
            place.ReadOnly = true;
            place.BackColor = Color.FromArgb(246, 247, 250);
            place.Text = options.InstallDir;
            Controls.Add(place);

            Style(change, false);
            change.SetBounds(426, 206, 102, 30);
            change.Text = "Change…";
            change.Click += delegate { OnChange(); };
            Controls.Add(change);

            desktop.SetBounds(32, 244, 300, 24);
            desktop.Text = "Add AgentForge to the Desktop";
            desktop.Checked = options.DesktopShortcut;
            desktop.ForeColor = Ink;
            desktop.CheckedChanged += delegate { options.DesktopShortcut = desktop.Checked; };
            Controls.Add(desktop);

            foreach (Control control in new Control[] { placeLabel, place, change })
                control.Visible = !options.Uninstall;
            desktop.Visible = !options.Uninstall && options.Shortcuts;

            bar.SetBounds(32, 200, 496, 8);
            bar.Visible = false;
            Controls.Add(bar);

            status.SetBounds(32, 216, 420, 40);
            status.ForeColor = Muted;
            Controls.Add(status);

            percent.SetBounds(452, 216, 76, 20);
            percent.TextAlign = ContentAlignment.TopRight;
            percent.ForeColor = Ink;
            percent.Font = new Font("Segoe UI Semibold", 9.75F);
            Controls.Add(percent);

            Style(primary, true);
            primary.SetBounds(408, 292, 120, 36);
            primary.Text = options.Uninstall ? "Uninstall" : "Install";
            primary.Click += delegate { OnPrimary(); };
            Controls.Add(primary);

            Style(secondary, false);
            secondary.SetBounds(280, 292, 120, 36);
            secondary.Text = "Cancel";
            secondary.Click += delegate { OnSecondary(); };
            Controls.Add(secondary);
            AcceptButton = primary;
            if (options.Auto && !options.Uninstall) Shown += delegate { OnPrimary(); };
        }

        /// <summary>What /auto exits with: 0 installed, 1 failed, 2 cancelled.</summary>
        public int ExitCode = 2;

        static void Style(Button button, bool filled)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = filled ? 0 : 1;
            button.FlatAppearance.BorderColor = Color.FromArgb(220, 222, 228);
            button.BackColor = filled ? Accent : Color.White;
            button.ForeColor = Ink;
            button.Font = new Font("Segoe UI Semibold", 9.75F);
            button.Cursor = Cursors.Hand;
        }

        void OnSecondary()
        {
            if (working) { stop = true; secondary.Enabled = false; status.Text = "Stopping…"; return; }
            Close();
        }

        /// <summary>About what an installation takes on disk, tools and browser included.</summary>
        const long NeededBytes = 3500L * 1024 * 1024;

        void OnChange()
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "Choose where to install AgentForge. Setup makes an AgentForge folder inside the one you pick.";
                dialog.ShowNewFolderButton = true;
                var start = options.InstallDir;
                while (!string.IsNullOrEmpty(start) && !Directory.Exists(start)) start = Path.GetDirectoryName(start);
                if (!string.IsNullOrEmpty(start)) dialog.SelectedPath = start;
                if (dialog.ShowDialog(this) != DialogResult.OK || string.IsNullOrEmpty(dialog.SelectedPath)) return;

                var chosen = dialog.SelectedPath;
                // Its own folder, never the chosen one itself: removing AgentForge later removes only what setup made.
                var name = Path.GetFileName(chosen.TrimEnd('\\'));
                if (!Options.IsInstallation(chosen) && !string.Equals(name, Config.AppName, StringComparison.OrdinalIgnoreCase))
                    chosen = Path.Combine(chosen, Config.AppName);
                var why = CannotInstallIn(chosen);
                if (why != null) { MessageBox.Show(this, why, "AgentForge Setup", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
                options.InstallDir = chosen;
                place.Text = chosen;
            }
        }

        /// <summary>Why AgentForge cannot go in `folder` (no room, or no right to write there without an administrator), or null.</summary>
        static string CannotInstallIn(string folder)
        {
            try
            {
                var full = Path.GetFullPath(folder);
                if (Directory.Exists(full) && Directory.EnumerateFileSystemEntries(full).Any() && !Options.IsInstallation(full))
                    return full + " already has other files in it. Choose an empty folder, or one with AgentForge in it.";
                var drive = new DriveInfo(Path.GetPathRoot(full));
                if (drive.IsReady && drive.AvailableFreeSpace < NeededBytes)
                    return string.Format("{0} has {1:0.0} GB free. AgentForge and its tools need about {2:0.0} GB: choose another drive or free some space.",
                                         drive.Name, drive.AvailableFreeSpace / 1073741824.0, NeededBytes / 1073741824.0);
                var existing = full;
                while (!Directory.Exists(existing)) existing = Path.GetDirectoryName(existing);
                var probe = Path.Combine(existing, ".agentforge-setup-" + Guid.NewGuid().ToString("N"));
                File.WriteAllText(probe, "");
                File.Delete(probe);
                return null;
            }
            catch (UnauthorizedAccessException)
            {
                return "Setup cannot write to " + folder + " without administrator rights. Choose a folder in your user folder or on another drive.";
            }
            catch (Exception error)
            {
                return "Setup cannot use " + folder + ": " + error.Message;
            }
        }

        void OnPrimary()
        {
            if (finished)
            {
                if (appExe != null && File.Exists(appExe)) Process.Start(new ProcessStartInfo(appExe) { UseShellExecute = true, WorkingDirectory = Path.GetDirectoryName(appExe) });
                Close();
                return;
            }
            if (options.Uninstall) { RunUninstall(); return; }
            var why = CannotInstallIn(options.InstallDir);
            if (why != null)
            {
                if (options.Auto) { Installer.Log("failed: " + why); ExitCode = 1; Close(); return; }
                MessageBox.Show(this, why, "AgentForge Setup", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            working = true;
            primary.Enabled = false;
            foreach (Control control in new Control[] { placeLabel, place, change, desktop }) control.Visible = false;
            bar.Visible = true;
            detail.Text = "Installing AgentForge and its tools. You can keep using your computer; this window shows how far it is.";
            new Thread(Work) { IsBackground = true }.Start();
        }

        void Work()
        {
            try
            {
                var installer = new Installer(options, Report, () => stop);
                appExe = installer.Run();
                Ui(delegate
                {
                    working = false;
                    finished = true;
                    bar.Value = 1;
                    percent.Text = "100%";
                    title.Text = "AgentForge is installed ✓";
                    detail.Text = "Everything is in place." +
                                  (!options.Shortcuts ? "" : options.DesktopShortcut ? " AgentForge is on your Desktop and in the Start menu." : " AgentForge is in the Start menu.") +
                                  "\n\nPress OK to open it.";
                    status.Text = "";
                    primary.Text = "OK";
                    primary.Enabled = true;
                    secondary.Text = "Close";
                    secondary.Enabled = true;
                    ExitCode = 0;
                    if (options.Auto) Close();
                });
            }
            catch (Cancelled)
            {
                Installer.Log("cancelled");
                ExitCode = 2;
                Ui(delegate { working = false; status.Text = "Setup was cancelled. Run it again to finish; what was downloaded is kept."; primary.Text = "Install"; primary.Enabled = true; secondary.Text = "Close"; secondary.Enabled = true; stop = false; });
            }
            catch (Exception error)
            {
                Installer.Log("failed: " + error);
                ExitCode = 1;
                Ui(delegate
                {
                    if (options.Auto) { working = false; Close(); return; }
                    working = false;
                    status.ForeColor = Color.FromArgb(200, 40, 40);
                    status.Text = error.Message;
                    primary.Text = "Try again";
                    primary.Enabled = true;
                    secondary.Text = "Close";
                    secondary.Enabled = true;
                });
            }
        }

        void Report(double fraction, string text)
        {
            Ui(delegate
            {
                bar.Value = fraction;
                percent.Text = string.Format("{0:0}%", Math.Floor(fraction * 100));
                status.Text = text ?? "";
            });
        }

        void RunUninstall()
        {
            if (MessageBox.Show("Remove AgentForge from this computer? Your projects and settings are kept.", "Remove AgentForge",
                                MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            try
            {
                Installer.Uninstall(options);
                title.Text = "AgentForge was removed";
                detail.Text = "Your projects in Documents\\AgentForge and your settings were kept.";
                primary.Visible = false;
                secondary.Text = "Close";
            }
            catch (Exception error)
            {
                status.Text = error.Message;
            }
        }

        void Ui(MethodInvoker work)
        {
            if (IsDisposed) return;
            try { if (InvokeRequired) BeginInvoke(work); else work(); } catch (ObjectDisposedException) { } catch (InvalidOperationException) { }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (working)
            {
                if (MessageBox.Show("Stop installing AgentForge?", "AgentForge Setup", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                { e.Cancel = true; return; }
                stop = true;
            }
            base.OnFormClosing(e);
        }
    }

    /// <summary>A flat progress bar in the app's own colour.</summary>
    class Bar : Control
    {
        double value;
        public double Value { get { return value; } set { this.value = Math.Max(0, Math.Min(1, value)); Invalidate(); } }

        public Bar() { DoubleBuffered = true; }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(Color.FromArgb(236, 237, 242));
            using (var brush = new SolidBrush(Color.FromArgb(139, 132, 243)))
                e.Graphics.FillRectangle(brush, 0, 0, (int)(Width * value), Height);
        }
    }

    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            var form = new SetupForm(Options.Parse(args));
            Application.Run(form);
            return form.ExitCode;
        }
    }
}
