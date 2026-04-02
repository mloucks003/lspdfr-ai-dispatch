using System.Collections.Generic;
using LSPDFRDispatch.Models;

namespace LSPDFRDispatch
{
    /// <summary>
    /// Polls GTA V APIs (via IGameApi) for nearby peds, vehicles, and player position.
    /// Produces a GameState snapshot for transmission to the backend.
    /// Requirements: 7.1, 7.2, 7.3
    /// </summary>
    public class GameStateReader
    {
        private readonly IGameApi _gameApi;
        private readonly LocationResolver _locationResolver;
        private readonly float _scanRadius;

        /// <param name="gameApi">Abstraction over GTA V native calls.</param>
        /// <param name="locationResolver">Converts coordinates to street names.</param>
        /// <param name="scanRadius">Radius in game units to scan for peds/vehicles.</param>
        public GameStateReader(IGameApi gameApi, LocationResolver locationResolver, float scanRadius = 100f)
        {
            _gameApi = gameApi;
            _locationResolver = locationResolver;
            _scanRadius = scanRadius;
        }

        /// <summary>
        /// Reads the current game world and returns a GameState snapshot.
        /// </summary>
        public GameState ReadState()
        {
            var playerPos = _gameApi.GetPlayerPosition();
            var peds = _gameApi.GetNearbyPeds(_scanRadius);
            var vehicles = _gameApi.GetNearbyVehicles(_scanRadius);

            var state = new GameState
            {
                OfficerLocation = _locationResolver.Resolve(playerPos),
                NearbyPeds = BuildPedList(peds),
                NearbyVehicles = BuildVehicleList(vehicles)
            };

            return state;
        }

        private List<NearbyPed> BuildPedList(IReadOnlyList<PedInfo> peds)
        {
            var result = new List<NearbyPed>();
            foreach (var ped in peds)
            {
                result.Add(new NearbyPed
                {
                    Name = ped.Name ?? "Unknown",
                    Description = ped.Description ?? "",
                    WantedLevel = _gameApi.GetWantedLevel(ped.Handle)
                });
            }
            return result;
        }

        private List<NearbyVehicle> BuildVehicleList(IReadOnlyList<VehicleInfo> vehicles)
        {
            var result = new List<NearbyVehicle>();
            foreach (var vehicle in vehicles)
            {
                result.Add(new NearbyVehicle
                {
                    Plate = vehicle.Plate ?? "",
                    Make = vehicle.Make ?? "",
                    Model = vehicle.Model ?? "",
                    Color = vehicle.Color ?? ""
                });
            }
            return result;
        }
    }
}
