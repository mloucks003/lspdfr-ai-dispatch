using System;
using System.Threading;
using System.Threading.Tasks;
using LSPD_First_Response.Mod.API;
using Rage;

namespace LSPDFRDispatch
{
    /// <summary>
    /// LSPDFR plugin entry point. Initializes all components and runs
    /// the main game state polling + crime detection loop.
    /// </summary>
    public class EntryPoint : Plugin
    {
        private WebSocketTransport _transport;
        private GameStateReader _stateReader;
        private CrimeEventDetector _crimeDetector;
        private CancellationTokenSource _cts;
        private Vector3 _lastPosition;
        private const float POSITION_CHANGE_THRESHOLD = 50f;

        public override void Initialize()
        {
            Functions.OnOnDutyStateChanged += OnDutyStateChanged;
            Game.LogTrivial("[LSPDFRDispatch] Plugin initialized. Waiting for on-duty.");
        }

        public override void Finally()
        {
            _cts?.Cancel();
            _transport?.Dispose();
            Game.LogTrivial("[LSPDFRDispatch] Plugin shut down.");
        }

        private void OnDutyStateChanged(bool onDuty)
        {
            if (onDuty)
            {
                Game.LogTrivial("[LSPDFRDispatch] Officer on duty — starting dispatch system.");
                StartDispatchSystem();
            }
            else
            {
                Game.LogTrivial("[LSPDFRDispatch] Officer off duty — stopping dispatch system.");
                _cts?.Cancel();
                _transport?.Dispose();
            }
        }

        private void StartDispatchSystem()
        {
            var config = PluginConfig.Load();

            var gameApi = new RageGameApi();
            var locationResolver = new LocationResolver(gameApi);

            _stateReader = new GameStateReader(gameApi, locationResolver, config.ScanRadius);
            _crimeDetector = new CrimeEventDetector(gameApi, locationResolver, config.CrimeDetectionRadius);

            _transport = new WebSocketTransport(
                $"{config.BackendUrl}/ws/plugin?api_key={config.ApiKey}",
                config.ApiKey
            );

            _cts = new CancellationTokenSource();
            _lastPosition = gameApi.GetPlayerPosition();

            // Connect and start the main loop on a background fiber
            GameFiber.StartNew(() => MainLoopFiber());
        }

        private void MainLoopFiber()
        {
            // Connect to backend
            try
            {
                Task.Run(async () => await _transport.ConnectAsync(_cts.Token)).Wait();
                Game.LogTrivial("[LSPDFRDispatch] Connected to backend.");
            }
            catch (Exception ex)
            {
                Game.LogTrivial($"[LSPDFRDispatch] Initial connection failed: {ex.Message}. Will retry.");
            }

            Game.DisplayNotification("~b~LSPDFR Dispatch~w~ system active. Backend: connected.");

            while (!_cts.IsCancellationRequested)
            {
                try
                {
                    // Ensure connection
                    if (!_transport.IsConnected)
                    {
                        Task.Run(async () => await _transport.ReconnectLoopAsync(_cts.Token)).Wait(5000);
                    }

                    // Read game state
                    var state = _stateReader.ReadState();

                    // Check if position changed enough to send update
                    var currentPos = new Vector3(
                        state.OfficerLocation.X,
                        state.OfficerLocation.Y,
                        state.OfficerLocation.Z
                    );

                    bool positionChanged = _lastPosition.DistanceTo(currentPos) > POSITION_CHANGE_THRESHOLD;
                    bool hasPeds = state.NearbyPeds.Count > 0;
                    bool hasVehicles = state.NearbyVehicles.Count > 0;

                    if (positionChanged || hasPeds || hasVehicles)
                    {
                        Task.Run(async () => await _transport.SendGameStateAsync(state)).Wait(2000);
                        _lastPosition = currentPos;
                    }

                    // Detect crimes and send 911 calls
                    var calls = _crimeDetector.DetectCrimes();
                    foreach (var call in calls)
                    {
                        Task.Run(async () => await _transport.SendNineOneOneCallAsync(call)).Wait(2000);
                        Game.LogTrivial($"[LSPDFRDispatch] 911 call sent: {call.CrimeType} at {call.Location.Street}");
                    }
                }
                catch (Exception ex)
                {
                    Game.LogTrivial($"[LSPDFRDispatch] Loop error: {ex.Message}");
                }

                // Wait ~1 second before next tick (rate limiting built into transport too)
                GameFiber.Sleep(1000);
            }
        }
    }
}
