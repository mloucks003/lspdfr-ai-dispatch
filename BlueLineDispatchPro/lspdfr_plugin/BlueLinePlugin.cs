using System;
using System.IO;
using System.Text;
using Rage;
using LSPD_First_Response.Mod.API;
using LSPD_First_Response.Engine.Scripting.Entities;

[assembly: Rage.Attributes.Plugin("BlueLineDispatch",
    Description = "BlueLineDispatchPro plate query bridge",
    Author = "BlueLinePro",
    PrefersSingleInstance = true)]

public class Main : Rage.Plugin
{
    private static readonly string SharedDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "BlueLineDispatch");

    private static string QueryFile    { get { return Path.Combine(SharedDir, "plate_query.txt"); } }
    private static string ResponseFile { get { return Path.Combine(SharedDir, "plate_response.json"); } }

    public override void Initialize()
    {
        Functions.OnOnDutyStateChanged += OnDutyChanged;
        Game.LogTrivial("[BlueLineDispatch] Plugin initialized.");
    }

    private void OnDutyChanged(bool onDuty)
    {
        if (onDuty)
        {
            GameFiber.StartNew(MainLoop);
            Game.DisplayNotification("~b~BlueLineDispatch~w~ plate bridge ~g~active");
        }
    }

    private void MainLoop()
    {
        Directory.CreateDirectory(SharedDir);
        Game.LogTrivial("[BlueLineDispatch] Watching: " + SharedDir);
        while (true)
        {
            GameFiber.Sleep(300);
            if (!File.Exists(QueryFile)) continue;
            try
            {
                string plate = File.ReadAllText(QueryFile).Trim().ToUpper();
                File.Delete(QueryFile);
                Game.LogTrivial("[BlueLineDispatch] Query: " + plate);
                string response = LookupPlate(plate);
                File.WriteAllText(ResponseFile, response, Encoding.UTF8);
                Game.LogTrivial("[BlueLineDispatch] Response written.");
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[BlueLineDispatch] Error: " + ex.Message);
            }
        }
    }

    private string LookupPlate(string plate)
    {
        string clean = plate.Replace(" ", "").Replace("-", "").ToUpper();
        Vehicle found = null;
        foreach (Vehicle v in World.GetAllVehicles())
        {
            if (!v.IsValid() || !v.Exists()) continue;
            string vp = (v.LicensePlate ?? "").Replace(" ", "").Replace("-", "").ToUpper();
            if (vp == clean || vp.Contains(clean) || clean.Contains(vp))
            { found = v; break; }
        }

        if (found == null || !found.IsValid())
            return "{\"found\":false,\"plate\":\"" + plate + "\"}";

        bool   stolen    = Functions.IsVehicleStolen(found);
        string model     = found.Model.Name ?? "UNKNOWN";
        string color     = GetColorName(found.PrimaryColor);
        string ownerName = "UNKNOWN";
        bool   wanted    = false;
        bool   licValid  = true;
        string dob       = "01/01/1990";
        string regStatus = "Valid";

        Ped driver = found.Driver;
        if (driver != null && driver.IsValid() && driver.Exists())
        {
            Persona p = Functions.GetPersonaForPed(driver);
            ownerName = p.FullName ?? "UNKNOWN";
            wanted    = p.Wanted;
            licValid  = p.ELicenseState == ELicenseState.Valid;
            dob       = string.Format("{0:D2}/{1:D2}/{2}", p.BirthMonth, p.BirthDay, p.BirthYear);
            regStatus = (p.ELicenseState == ELicenseState.Suspended) ? "Suspended" : "Valid";
        }

        return "{"
            + "\"found\":true,"
            + "\"plate\":\"" + plate + "\","
            + "\"model\":\"" + model + "\","
            + "\"color\":\"" + color + "\","
            + "\"stolen\":" + stolen.ToString().ToLower() + ","
            + "\"owner\":\"" + ownerName + "\","
            + "\"wanted\":" + wanted.ToString().ToLower() + ","
            + "\"license_valid\":" + licValid.ToString().ToLower() + ","
            + "\"registration\":\"" + regStatus + "\","
            + "\"dob\":\"" + dob + "\""
            + "}";
    }

    private string GetColorName(System.Drawing.Color c)
    {
        int r = c.R, g = c.G, b = c.B;
        if (r > 200 && g > 200 && b > 200) return "White";
        if (r < 50  && g < 50  && b < 50)  return "Black";
        if (r > 160 && g < 80  && b < 80)  return "Red";
        if (r < 80  && g < 80  && b > 160) return "Blue";
        if (r < 80  && g > 160 && b < 80)  return "Green";
        if (r > 160 && g > 160 && b < 80)  return "Yellow";
        if (r > 200 && g > 110 && b < 80)  return "Orange";
        if (r > 140 && g > 120 && b > 120) return "Silver";
        if (r > 100 && g > 70  && b < 50)  return "Brown";
        if (r > 140 && g < 80  && b > 140) return "Purple";
        return "Dark";
    }

    public override void Finally() { Game.LogTrivial("[BlueLineDispatch] Unloaded."); }
}
