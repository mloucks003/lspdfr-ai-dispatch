namespace LSPDFRDispatch
{
    /// <summary>
    /// Converts world coordinates to GTA V street names and landmarks
    /// using the IGameApi abstraction over native functions.
    /// Requirements: 7.2
    /// </summary>
    public class LocationResolver
    {
        private readonly IGameApi _gameApi;

        public LocationResolver(IGameApi gameApi)
        {
            _gameApi = gameApi;
        }

        /// <summary>
        /// Resolves the given world position to a street name.
        /// </summary>
        public string GetStreetName(Vector3 position)
        {
            return _gameApi.GetStreetName(position);
        }

        /// <summary>
        /// Resolves the given world position to a landmark name, or null if none nearby.
        /// </summary>
        public string GetLandmark(Vector3 position)
        {
            return _gameApi.GetLandmark(position);
        }

        /// <summary>
        /// Builds a full location model from world coordinates.
        /// </summary>
        public Models.OfficerLocation Resolve(Vector3 position)
        {
            return new Models.OfficerLocation
            {
                Street = GetStreetName(position) ?? "Unknown",
                Landmark = GetLandmark(position),
                X = position.X,
                Y = position.Y,
                Z = position.Z
            };
        }
    }
}
