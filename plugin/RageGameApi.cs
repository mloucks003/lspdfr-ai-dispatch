using System;
using System.Collections.Generic;
using System.Linq;
using Rage;
using Rage.Native;

namespace LSPDFRDispatch
{
    public class RageGameApi : IGameApi
    {
        private static readonly string[] VehicleColors = {
            "Black", "White", "Silver", "Gray", "Red", "Blue", "Green",
            "Yellow", "Orange", "Brown", "Beige", "Gold", "Dark Blue",
            "Dark Red", "Dark Green", "Light Blue", "Matte Black"
        };

        private static readonly string[] PedDescFallback = {
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
                var entities = World.GetEntities(
                    player.Position, radius, GetEntitiesFlags.ConsiderHumanPeds);

                foreach (var entity in entities)
                {
                    var ped = entity as Ped;
                    if (ped == null || !ped.IsValid() || !ped.IsAlive || ped == player) continue;
                    if (result.Count >= 20) break;

                    result.Add(new PedInfo
                    {
                        Handle = (int)ped.Handle.Value,
                        Name = GetPedName(ped),
                        Description = GetPedDescription(ped),
                        Position = ToVec(ped.Position)
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
                var entities = World.GetEntities(
                    player.Position, radius, GetEntitiesFlags.ConsiderGroundVehicles);

                foreach (var entity in entities)
                {
                    var veh = entity as Vehicle;
                    if (veh == null || !veh.IsValid()) continue;
                    if (result.Count >= 15) break;

                    result.Add(new VehicleInfo
                    {
                        Handle = (int)veh.Handle.Value,
                        Plate = veh.LicensePlate ?? "UNKNOWN",
                        Make = GetVehicleMake(veh),
                        Model = veh.Model.Name ?? "Unknown",
                        Color = GetVehicleColor(veh),
                        Position = ToVec(veh.Position)
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
            catch { return new Vector3(0, 0, 0); }
        }

        public string GetStreetName(Vector3 position)
        {
            try
            {
                uint streetHash = 0, crossingHash = 0;
                NativeFunction.Natives.GET_STREET_NAME_AT_COORD(
                    position.X, position.Y, position.Z, out streetHash, out crossingHash);

                string street = World.GetStreetName(
                    new Rage.Vector3(position.X, position.Y, position.Z));
                return !string.IsNullOrEmpty(street) ? street : "Unknown Street";
            }
            catch { return "Unknown Street"; }
        }

        public string GetLandmark(Vector3 position)
        {
            try
            {
                string zone = World.GetZoneName(
                    new Rage.Vector3(position.X, position.Y, position.Z));
                return (!string.IsNullOrEmpty(zone) && zone != "UNK") ? zone : null;
            }
            catch { return null; }
        }

        public int GetWantedLevel(int pedHandle)
        {
            try
            {
                if ((uint)pedHandle == Game.LocalPlayer.Character.Handle.Value)
                    return Game.LocalPlayer.WantedLevel;
                return 0;
            }
            catch { return 0; }
        }

        public IReadOnlyList<CrimeEvent> GetNearbyCrimeEvents(float radius)
        {
            var events = new List<CrimeEvent>();
            try
            {
                var player = Game.LocalPlayer.Character;
                var entities = World.GetEntities(
                    player.Position, radius, GetEntitiesFlags.ConsiderHumanPeds);

                foreach (var entity in entities)
                {
                    var ped = entity as Ped;
                    if (ped == null || !ped.IsValid() || !ped.IsAlive || ped == player) continue;

                    string crimeType = DetectCrimeType(ped);
                    if (crimeType != null)
                    {
                        events.Add(new CrimeEvent
                        {
                            CrimeType = crimeType,
                            Position = ToVec(ped.Position),
                            InvolvedPeds = new[] {
                                new PedInfo {
                                    Handle = (int)ped.Handle.Value,
                                    Name = GetPedName(ped),
                                    Description = GetPedDescription(ped),
                                    Position = ToVec(ped.Position)
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

        private string DetectCrimeType(Ped ped)
        {
            try
            {
                if (ped.IsShooting) return "shooting";
                if (ped.IsInMeleeCombat) return "assault";
                if (ped.IsFleeing) return "suspicious_person";
                return null;
            }
            catch { return null; }
        }

        private string GetPedName(Ped ped)
        {
            try
            {
                var persona = LSPD_First_Response.Mod.API.Functions.GetPersonaForPed(ped);
                if (persona != null)
                    return $"{persona.Forename} {persona.Surname}";
            }
            catch { }
            return $"Unknown_{(int)ped.Handle.Value}";
        }

        private string GetPedDescription(Ped ped)
        {
            try
            {
                string gender = ped.IsMale ? "male" : "female";
                return $"{gender}, {ped.Model.Name}";
            }
            catch { return PedDescFallback[_rng.Next(PedDescFallback.Length)]; }
        }

        private string GetVehicleMake(Vehicle veh)
        {
            try
            {
                // Use model name prefix as make fallback
                string name = veh.Model.Name;
                if (!string.IsNullOrEmpty(name))
                    return name.Split('_').FirstOrDefault() ?? "Unknown";
            }
            catch { }
            return "Unknown";
        }

        private string GetVehicleColor(Vehicle veh)
        {
            try
            {
                // Use primary color index
                int color = veh.PrimaryColor.R > 200 ? 4 :  // Red
                            veh.PrimaryColor.B > 200 ? 5 :  // Blue
                            veh.PrimaryColor.G > 200 ? 6 :  // Green
                            veh.PrimaryColor.R + veh.PrimaryColor.G + veh.PrimaryColor.B > 600 ? 1 : // White
                            0; // Black
                return VehicleColors[color];
            }
            catch { return "Unknown"; }
        }

        private static Vector3 ToVec(Rage.Vector3 v) => new Vector3(v.X, v.Y, v.Z);
    }
}
