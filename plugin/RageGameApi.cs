using System;
using System.Collections.Generic;
using System.Linq;
using Rage;
using Rage.Native;

namespace LSPDFRDispatch
{
    /// <summary>
    /// Real implementation of IGameApi using RagePluginHook natives.
    /// Reads peds, vehicles, player position, street names, wanted levels,
    /// and crime events from the live GTA V game world.
    /// </summary>
    public class RageGameApi : IGameApi
    {
        private static readonly string[] VehicleMakes = {
            "Albany", "Annis", "Benefactor", "BF", "Bollokan", "Bravado",
            "Brute", "Buckingham", "Canis", "Cheval", "Coil", "Declasse",
            "Dewbauchee", "Dinka", "Dundreary", "Emperor", "Enus", "Fathom",
            "Gallivanter", "Grotti", "HVY", "Imponte", "Invetero", "Jacksheepe",
            "Jobuilt", "Karin", "Lampadati", "Maibatsu", "Mammoth", "MTL",
            "Obey", "Ocelot", "Overflod", "Pegassi", "Pfister", "Principe",
            "Progen", "Schyster", "Shitzu", "Truffade", "Ubermacht", "Vapid",
            "Vulcar", "Weeny", "Western", "Willard", "Zirconium"
        };

        private static readonly string[] VehicleColors = {
            "Black", "White", "Silver", "Gray", "Red", "Blue", "Green",
            "Yellow", "Orange", "Brown", "Beige", "Gold", "Dark Blue",
            "Dark Red", "Dark Green", "Light Blue", "Matte Black"
        };

        private static readonly string[] PedDescriptions = {
            "White male", "White female", "Black male", "Black female",
            "Hispanic male", "Hispanic female", "Asian male", "Asian female"
        };

        private readonly Random _rng = new Random();

        public IReadOnlyList<PedInfo> GetNearbyPeds(float radius)
        {
            var result = new List<PedInfo>();
            try
            {
                var player = Game.LocalPlayer.Character;
                var peds = World.GetEntities(
                    player.Position, radius, GetEntitiesFlags.ConsiderHumanPeds
                ).OfType<Ped>().Where(p => p.IsValid() && p.IsAlive && p != player);

                foreach (var ped in peds.Take(20)) // Cap at 20 to avoid perf issues
                {
                    result.Add(new PedInfo
                    {
                        Handle = ped.Handle.Value,
                        Name = GetPedName(ped),
                        Description = GetPedDescription(ped),
                        Position = ToVector3(ped.Position)
                    });
                }
            }
            catch (Exception ex)
            {
                Game.LogTrivial($"[LSPDFRDispatch] GetNearbyPeds error: {ex.Message}");
            }
            return result;
        }

        public IReadOnlyList<VehicleInfo> GetNearbyVehicles(float radius)
        {
            var result = new List<VehicleInfo>();
            try
            {
                var player = Game.LocalPlayer.Character;
                var vehicles = World.GetEntities(
                    player.Position, radius, GetEntitiesFlags.ConsiderGroundVehicles
                ).OfType<Vehicle>().Where(v => v.IsValid());

                foreach (var veh in vehicles.Take(15))
                {
                    result.Add(new VehicleInfo
                    {
                        Handle = veh.Handle.Value,
                        Plate = veh.LicensePlate ?? "UNKNOWN",
                        Make = GetVehicleMake(veh),
                        Model = veh.Model.Name ?? "Unknown",
                        Color = GetVehicleColor(veh),
                        Position = ToVector3(veh.Position)
                    });
                }
            }
            catch (Exception ex)
            {
                Game.LogTrivial($"[LSPDFRDispatch] GetNearbyVehicles error: {ex.Message}");
            }
            return result;
        }

        public Vector3 GetPlayerPosition()
        {
            try
            {
                var pos = Game.LocalPlayer.Character.Position;
                return new Vector3(pos.X, pos.Y, pos.Z);
            }
            catch
            {
                return new Vector3(0, 0, 0);
            }
        }

        public string GetStreetName(Vector3 position)
        {
            try
            {
                var pos = new Rage.Vector3(position.X, position.Y, position.Z);
                uint streetHash = 0, crossingHash = 0;
                NativeFunction.Natives.GET_STREET_NAME_AT_COORD(
                    pos.X, pos.Y, pos.Z, out streetHash, out crossingHash);

                string street = NativeFunction.Natives.GET_STREET_NAME_FROM_HASH_KEY<string>(streetHash);
                if (!string.IsNullOrEmpty(street))
                {
                    string crossing = NativeFunction.Natives.GET_STREET_NAME_FROM_HASH_KEY<string>(crossingHash);
                    if (!string.IsNullOrEmpty(crossing))
                        return $"{street} / {crossing}";
                    return street;
                }
                return "Unknown Street";
            }
            catch
            {
                return "Unknown Street";
            }
        }

        public string GetLandmark(Vector3 position)
        {
            try
            {
                var pos = new Rage.Vector3(position.X, position.Y, position.Z);
                uint zoneHash = NativeFunction.Natives.GET_HASH_OF_MAP_AREA_AT_COORDS<uint>(pos.X, pos.Y, pos.Z);
                string zone = NativeFunction.Natives.GET_NAME_OF_ZONE<string>(pos.X, pos.Y, pos.Z);
                if (!string.IsNullOrEmpty(zone) && zone != "UNK")
                    return zone;
                return null;
            }
            catch
            {
                return null;
            }
        }

        public int GetWantedLevel(int pedHandle)
        {
            try
            {
                // For the player, use the actual wanted level
                if (pedHandle == Game.LocalPlayer.Character.Handle.Value)
                    return Game.LocalPlayer.WantedLevel;
                // For other peds, check if they're flagged
                return 0;
            }
            catch
            {
                return 0;
            }
        }

        public IReadOnlyList<CrimeEvent> GetNearbyCrimeEvents(float radius)
        {
            var events = new List<CrimeEvent>();
            try
            {
                var player = Game.LocalPlayer.Character;
                var peds = World.GetEntities(
                    player.Position, radius, GetEntitiesFlags.ConsiderHumanPeds
                ).OfType<Ped>().Where(p => p.IsValid() && p.IsAlive && p != player);

                foreach (var ped in peds)
                {
                    string crimeType = DetectCrimeType(ped);
                    if (crimeType != null)
                    {
                        events.Add(new CrimeEvent
                        {
                            CrimeType = crimeType,
                            Position = ToVector3(ped.Position),
                            InvolvedPeds = new[] {
                                new PedInfo {
                                    Handle = ped.Handle.Value,
                                    Name = GetPedName(ped),
                                    Description = GetPedDescription(ped),
                                    Position = ToVector3(ped.Position)
                                }
                            }
                        });
                    }
                }
            }
            catch (Exception ex)
            {
                Game.LogTrivial($"[LSPDFRDispatch] GetNearbyCrimeEvents error: {ex.Message}");
            }
            return events;
        }

        // ── Helpers ──────────────────────────────────────────────────

        private string DetectCrimeType(Ped ped)
        {
            try
            {
                if (ped.IsShooting) return "shooting";
                if (ped.IsInMeleeCombat) return "assault";
                if (ped.IsFleeing) return "suspicious_person";
                if (NativeFunction.Natives.IS_PED_IN_COMBAT<bool>(ped, 0)) return "disturbance";
                return null;
            }
            catch
            {
                return null;
            }
        }

        private string GetPedName(Ped ped)
        {
            try
            {
                // LSPDFR provides persona data for peds
                var persona = LSPD_First_Response.Mod.API.Functions.GetPersonaForPed(ped);
                if (persona != null)
                    return $"{persona.Forename} {persona.Surname}";
            }
            catch { /* LSPDFR API not available or ped has no persona */ }

            return $"Unknown_{ped.Handle.Value}";
        }

        private string GetPedDescription(Ped ped)
        {
            try
            {
                bool isMale = ped.IsMale;
                string gender = isMale ? "male" : "female";
                return $"{gender}, {ped.Model.Name}";
            }
            catch
            {
                return PedDescriptions[_rng.Next(PedDescriptions.Length)];
            }
        }

        private string GetVehicleMake(Vehicle veh)
        {
            try
            {
                string makeName = NativeFunction.Natives.GET_MAKE_NAME_FROM_VEHICLE_MODEL<string>(veh.Model.Hash);
                if (!string.IsNullOrEmpty(makeName))
                    return makeName;
            }
            catch { }
            return veh.Model.Name?.Split('_').FirstOrDefault() ?? "Unknown";
        }

        private string GetVehicleColor(Vehicle veh)
        {
            try
            {
                int primaryColor = 0, secondaryColor = 0;
                NativeFunction.Natives.GET_VEHICLE_COLOURS(veh, out primaryColor, out secondaryColor);
                if (primaryColor >= 0 && primaryColor < VehicleColors.Length)
                    return VehicleColors[primaryColor];
            }
            catch { }
            return "Unknown";
        }

        private static Vector3 ToVector3(Rage.Vector3 v) => new Vector3(v.X, v.Y, v.Z);
    }
}
