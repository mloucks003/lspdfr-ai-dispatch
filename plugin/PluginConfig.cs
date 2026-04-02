using System;
using System.IO;
using Rage;

namespace LSPDFRDispatch
{
    /// <summary>
    /// Plugin configuration loaded from an INI file in the GTA V directory.
    /// File: Plugins/LSPDFRDispatch.ini
    /// </summary>
    public class PluginConfig
    {
        public string BackendUrl { get; set; } = "ws://localhost:8000";
        public string ApiKey { get; set; } = "changeme";
        public float ScanRadius { get; set; } = 100f;
        public float CrimeDetectionRadius { get; set; } = 150f;
        public string OfficerCallsign { get; set; } = "1-Adam-12";

        private const string INI_PATH = "Plugins/LSPDFRDispatch.ini";

        public static PluginConfig Load()
        {
            var config = new PluginConfig();

            try
            {
                if (File.Exists(INI_PATH))
                {
                    var ini = new InitializationFile(INI_PATH);
                    config.BackendUrl = ini.ReadString("General", "BackendUrl", config.BackendUrl);
                    config.ApiKey = ini.ReadString("General", "ApiKey", config.ApiKey);
                    config.ScanRadius = ini.ReadSingle("General", "ScanRadius", config.ScanRadius);
                    config.CrimeDetectionRadius = ini.ReadSingle("General", "CrimeDetectionRadius", config.CrimeDetectionRadius);
                    config.OfficerCallsign = ini.ReadString("General", "OfficerCallsign", config.OfficerCallsign);
                    Game.LogTrivial("[LSPDFRDispatch] Config loaded from " + INI_PATH);
                }
                else
                {
                    // Create default config file
                    SaveDefault();
                    Game.LogTrivial("[LSPDFRDispatch] Default config created at " + INI_PATH);
                }
            }
            catch (Exception ex)
            {
                Game.LogTrivial($"[LSPDFRDispatch] Config load error: {ex.Message}. Using defaults.");
            }

            return config;
        }

        private static void SaveDefault()
        {
            try
            {
                var lines = new[]
                {
                    "[General]",
                    "BackendUrl=ws://localhost:8000",
                    "ApiKey=changeme",
                    "ScanRadius=100",
                    "CrimeDetectionRadius=150",
                    "OfficerCallsign=1-Adam-12"
                };
                File.WriteAllLines(INI_PATH, lines);
            }
            catch { /* ignore write errors */ }
        }
    }
}
