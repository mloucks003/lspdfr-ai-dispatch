using System.Collections.Generic;

namespace LSPDFRDispatch
{
    /// <summary>
    /// Abstraction over GTA V / RagePluginHook native function calls.
    /// Allows the plugin logic to be tested without the game running.
    /// </summary>
    public interface IGameApi
    {
        /// <summary>Returns peds within the specified radius of the player.</summary>
        IReadOnlyList<PedInfo> GetNearbyPeds(float radius);

        /// <summary>Returns vehicles within the specified radius of the player.</summary>
        IReadOnlyList<VehicleInfo> GetNearbyVehicles(float radius);

        /// <summary>Returns the player's current world position.</summary>
        Vector3 GetPlayerPosition();

        /// <summary>Translates world coordinates to the nearest GTA V street name.</summary>
        string GetStreetName(Vector3 position);

        /// <summary>Translates world coordinates to the nearest GTA V landmark, or null.</summary>
        string GetLandmark(Vector3 position);

        /// <summary>Returns the wanted level (0-5) of the specified ped.</summary>
        int GetWantedLevel(int pedHandle);

        /// <summary>Returns active crime events near the player.</summary>
        IReadOnlyList<CrimeEvent> GetNearbyCrimeEvents(float radius);
    }

    /// <summary>Minimal 3-component vector for world coordinates.</summary>
    public struct Vector3
    {
        public float X { get; set; }
        public float Y { get; set; }
        public float Z { get; set; }

        public Vector3(float x, float y, float z)
        {
            X = x;
            Y = y;
            Z = z;
        }

        public float DistanceTo(Vector3 other)
        {
            float dx = X - other.X;
            float dy = Y - other.Y;
            float dz = Z - other.Z;
            return (float)System.Math.Sqrt(dx * dx + dy * dy + dz * dz);
        }
    }
}
