using System.Collections.Generic;
using Newtonsoft.Json;

namespace LSPDFRDispatch.Models
{
    /// <summary>
    /// Snapshot of the current game world state sent to the backend.
    /// Matches the WebSocket message schema: { type: "game_state", data: GameState }
    /// </summary>
    public class GameState
    {
        [JsonProperty("nearby_peds")]
        public List<NearbyPed> NearbyPeds { get; set; } = new List<NearbyPed>();

        [JsonProperty("nearby_vehicles")]
        public List<NearbyVehicle> NearbyVehicles { get; set; } = new List<NearbyVehicle>();

        [JsonProperty("officer_location")]
        public OfficerLocation OfficerLocation { get; set; }
    }

    public class NearbyPed
    {
        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("description")]
        public string Description { get; set; }

        [JsonProperty("wanted_level")]
        public int WantedLevel { get; set; }
    }

    public class NearbyVehicle
    {
        [JsonProperty("plate")]
        public string Plate { get; set; }

        [JsonProperty("make")]
        public string Make { get; set; }

        [JsonProperty("model")]
        public string Model { get; set; }

        [JsonProperty("color")]
        public string Color { get; set; }
    }

    public class OfficerLocation
    {
        [JsonProperty("street")]
        public string Street { get; set; }

        [JsonProperty("landmark")]
        public string Landmark { get; set; }

        [JsonProperty("x")]
        public float X { get; set; }

        [JsonProperty("y")]
        public float Y { get; set; }

        [JsonProperty("z")]
        public float Z { get; set; }
    }
}
