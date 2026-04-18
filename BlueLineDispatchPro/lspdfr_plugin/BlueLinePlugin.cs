// BlueLineDispatch -- SHVDN3 bridge script
// Compiles against ScriptHookVDotNet3.dll only (no RPH SDK needed).
// At runtime uses reflection to call LSPDFR's persona engine for real
// owner name / DOB / wanted status from the actual driver ped.
using System;
using System.Collections;
using System.IO;
using System.Reflection;
using System.Text;
using GTA;
using GTA.Native;

public class BlueLinePlugin : Script
{
    private readonly string _dir;
    private readonly string _qFile;
    private readonly string _rFile;

    public BlueLinePlugin()
    {
        _dir   = Path.Combine(Environment.GetFolderPath(
                     Environment.SpecialFolder.LocalApplicationData), "BlueLineDispatch");
        _qFile = Path.Combine(_dir, "plate_query.txt");
        _rFile = Path.Combine(_dir, "plate_response.json");
        Directory.CreateDirectory(_dir);
        Tick     += OnTick;
        Interval  = 300;
        GTA.UI.Notification.Show("~b~BlueLineDispatch~w~ bridge ~g~active");
    }

    private void OnTick(object sender, EventArgs e)
    {
        if (!File.Exists(_qFile)) return;
        try
        {
            string plate = File.ReadAllText(_qFile).Trim().ToUpper();
            File.Delete(_qFile);
            File.WriteAllText(_rFile, BuildResponse(plate), Encoding.UTF8);
        }
        catch { }
    }

    private string BuildResponse(string plate)
    {
        string clean = plate.Replace(" ", "").Replace("-", "").ToUpper();
        Vehicle found = null;
        foreach (Vehicle v in World.GetAllVehicles())
        {
            if (!v.Exists()) continue;
            string vp = (v.Mods.LicensePlate != null ? v.Mods.LicensePlate : "")
                        .Replace(" ", "").Replace("-", "").ToUpper();
            if (vp == clean || vp.Contains(clean) || clean.Contains(vp))
            { found = v; break; }
        }

        if (found == null || !found.Exists())
            return "{\"found\":false,\"plate\":\"" + Esc(plate) + "\"}";

        // ── Real vehicle data (SHVDN) ─────────────────────────────────────────
        string model = GetModelName(found);
        string color = GetColorName(found.Mods.PrimaryColor);

        // ── Real LSPDFR persona (reflection) ─────────────────────────────────
        string owner = ""; string dob = "";
        bool wanted = false; bool licValid = true;
        string reg = "Valid"; bool stolen = false;
        bool gotPersona = false;

        Ped driver = found.Driver;
        if (driver != null && driver.Exists())
            gotPersona = TryGetPersona(driver.Handle,
                ref owner, ref dob, ref wanted, ref licValid, ref reg);

        TryGetStolen(found.Handle, ref stolen);

        string src = gotPersona ? "lspdfr" : "shvdn";

        string j = "{\"found\":true"
            + ",\"plate\":\""  + Esc(plate) + "\""
            + ",\"model\":\""  + Esc(model) + "\""
            + ",\"color\":\""  + Esc(color) + "\""
            + ",\"stolen\":"   + stolen.ToString().ToLower()
            + ",\"source\":\"" + src + "\"";

        if (gotPersona)
            j += ",\"owner\":\""         + Esc(owner)  + "\""
               + ",\"dob\":\""           + Esc(dob)    + "\""
               + ",\"wanted\":"          + wanted.ToString().ToLower()
               + ",\"license_valid\":"   + licValid.ToString().ToLower()
               + ",\"registration\":\"" + Esc(reg) + "\"";

        return j + "}";
    }

    // ── Reflection helpers ────────────────────────────────────────────────────

    private static bool TryGetPersona(int pedHandle,
        ref string name, ref string dob, ref bool wanted,
        ref bool licValid, ref string reg)
    {
        try
        {
            Assembly rph = null; Assembly lspdfr = null;
            foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
            {
                string n = a.GetName().Name;
                if (n == "RagePluginHook")    rph    = a;
                if (n == "LSPD First Response") lspdfr = a;
            }
            if (rph == null || lspdfr == null) return false;

            // Find matching Rage.Ped by native handle
            object ragePed = FindRageEntityByHandle(rph, "Rage.World", "GetAllPeds", pedHandle);
            if (ragePed == null) return false;

            // Call Functions.GetPersonaForPed
            Type funcs = lspdfr.GetType("LSPD_First_Response.Mod.API.Functions");
            if (funcs == null) return false;
            MethodInfo gp = funcs.GetMethod("GetPersonaForPed");
            if (gp == null) return false;
            object persona = gp.Invoke(null, new object[] { ragePed });
            if (persona == null) return false;

            Type pt = persona.GetType();
            name    = StrProp(persona, pt, "FullName");
            wanted  = BoolProp(persona, pt, "Wanted");
            int bm  = IntProp(persona, pt, "BirthMonth");
            int bd  = IntProp(persona, pt, "BirthDay");
            int by  = IntProp(persona, pt, "BirthYear");
            dob     = string.Format("{0:D2}/{1:D2}/{2}", bm, bd, by);
            object lic = ObjProp(persona, pt, "ELicenseState");
            if (lic != null)
            {
                string ls = lic.ToString();
                licValid = (ls == "Valid");
                reg = (ls == "Suspended") ? "Suspended" : "Valid";
            }
            return !string.IsNullOrEmpty(name);
        }
        catch { return false; }
    }

    private static void TryGetStolen(int vehHandle, ref bool stolen)
    {
        try
        {
            Assembly rph = null; Assembly lspdfr = null;
            foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
            {
                string n = a.GetName().Name;
                if (n == "RagePluginHook")    rph    = a;
                if (n == "LSPD First Response") lspdfr = a;
            }
            if (rph == null || lspdfr == null) return;
            object rageVeh = FindRageEntityByHandle(rph, "Rage.World", "GetAllVehicles", vehHandle);
            if (rageVeh == null) return;
            Type funcs = lspdfr.GetType("LSPD_First_Response.Mod.API.Functions");
            if (funcs == null) return;
            MethodInfo m = funcs.GetMethod("IsVehicleStolen");
            if (m != null) stolen = (bool)m.Invoke(null, new object[] { rageVeh });
        }
        catch { }
    }

    private static object FindRageEntityByHandle(Assembly rph, string worldClass, string method, int handle)
    {
        Type world = rph.GetType(worldClass);
        if (world == null) return null;
        MethodInfo mi = world.GetMethod(method,
            BindingFlags.Public | BindingFlags.Static, null, new Type[0], null);
        if (mi == null) return null;
        IEnumerable items = mi.Invoke(null, null) as IEnumerable;
        if (items == null) return null;
        foreach (object item in items)
        {
            PropertyInfo hp = item.GetType().GetProperty("Handle");
            if (hp == null) continue;
            object h = hp.GetValue(item, null);
            if (h != null && Convert.ToInt32(h) == handle) return item;
        }
        return null;
    }

    private static string StrProp(object o, Type t, string n)
    {
        try { PropertyInfo p = t.GetProperty(n); return p != null ? (p.GetValue(o,null) ?? "").ToString() : ""; }
        catch { return ""; }
    }
    private static bool BoolProp(object o, Type t, string n)
    {
        try { PropertyInfo p = t.GetProperty(n); return p != null && (bool)p.GetValue(o,null); }
        catch { return false; }
    }
    private static int IntProp(object o, Type t, string n)
    {
        try { PropertyInfo p = t.GetProperty(n); return p != null ? Convert.ToInt32(p.GetValue(o,null)) : 0; }
        catch { return 0; }
    }
    private static object ObjProp(object o, Type t, string n)
    {
        try { PropertyInfo p = t.GetProperty(n); return p != null ? p.GetValue(o,null) : null; }
        catch { return null; }
    }

    // ── Model / color helpers ─────────────────────────────────────────────────

    private static string GetModelName(Vehicle v)
    {
        try
        {
            string key = Function.Call<string>(
                (GTA.Native.Hash)0xB215AAC32D25D015, v.Model.Hash); // GET_DISPLAY_NAME_FROM_VEHICLE_MODEL
            string loc = Function.Call<string>(
                (GTA.Native.Hash)0x7B5280EBA9840C72, key, false);   // _GET_LABEL_TEXT
            if (!string.IsNullOrEmpty(loc) && loc != "NULL") return loc;
        }
        catch { }
        return v.Model.ToString();
    }

    private static string GetColorName(VehicleColor c)
    {
        string s = c.ToString()
            .Replace("Metallic","").Replace("Matte","")
            .Replace("Util","").Replace("Worn","").Trim();
        if (s.Contains("Black"))  return "Black";
        if (s.Contains("White"))  return "White";
        if (s.Contains("Red"))    return "Red";
        if (s.Contains("Blue"))   return "Blue";
        if (s.Contains("Green"))  return "Green";
        if (s.Contains("Yellow")) return "Yellow";
        if (s.Contains("Orange")) return "Orange";
        if (s.Contains("Silver") || s.Contains("Grey") || s.Contains("Gray")) return "Silver";
        if (s.Contains("Brown"))  return "Brown";
        if (s.Contains("Purple")) return "Purple";
        if (s.Contains("Gold"))   return "Gold";
        if (s.Contains("Pink"))   return "Pink";
        if (s.Contains("Beige"))  return "Beige";
        return s.Length > 0 ? s : c.ToString();
    }

    private static string Esc(string s)
    {
        if (s == null) return "";
        return s.Replace("\\","\\\\").Replace("\"","\\\"");
    }
}
