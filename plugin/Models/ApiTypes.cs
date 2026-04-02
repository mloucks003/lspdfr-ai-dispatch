namespace LSPDFRDispatch
{
    /// <summary>
    /// Information about a ped returned by IGameApi.GetNearbyPeds.
    /// </summary>
    public class PedInfo
    {
        public int Handle { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public Vector3 Position { get; set; }
    }

    /// <summary>
    /// Information about a vehicle returned by IGameApi.GetNearbyVehicles.
    /// </summary>
    public class VehicleInfo
    {
        public int Handle { get; set; }
        public string Plate { get; set; }
        public string Make { get; set; }
        public string Model { get; set; }
        public string Color { get; set; }
        public Vector3 Position { get; set; }
    }

    /// <summary>
    /// A crime event detected by the game engine.
    /// </summary>
    public class CrimeEvent
    {
        public string CrimeType { get; set; }
        public Vector3 Position { get; set; }
        public PedInfo[] InvolvedPeds { get; set; }
    }
}
