using System;
using System.Threading;
using LSPD_First_Response.Mod.API;
using Rage;

namespace LSPDFRDispatch
{
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
                Game.LogTrivial("[LSPDFRDispatch] Officer off duty — stopping.");
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
                config.BackendUrl + "/ws/plugin?api_key=" + config.ApiKey,
                config.ApiKey
            );

            _cts = new CancellationTokenSource();
            _lastPosition = gameApi.GetPlayerPosition();

            GameFiber.StartNew(MainLoopFiber);
        }

        private void MainLoopFiber()
        {
            try
            {
                _transport.ConnectAsync(_cts.Token);
                if (_transport.IsConnected)
                    Game.LogTrivial("[LSPDFRDispatch] Connected to backend.");
                else
                    Game.LogTrivial("[LSPDFRDispatch] Backend not available. Will retry.");
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[LSPDFRDispatch] Connection failed: " + ex.Message);
            }

            Game.DisplayNotification("~b~LSPDFR Dispatch~w~ system active.");

            while (!_cts.IsCancellationRequested)
            {
                try
                {
                    if (!_transport.IsConnected)
                        _transport.ReconnectLoopAsync(_cts.Token);

                    var state = _stateReader.ReadState();
                    var currentPos = new Vector3(
                        state.OfficerLocation.X,
                        state.OfficerLocation.Y,
                        state.OfficerLocation.Z);

                    bool posChanged = _lastPosition.DistanceTo(currentPos) > POSITION_CHANGE_THRESHOLD;
                    if (posChanged || state.NearbyPeds.Count > 0 || state.NearbyVehicles.Count > 0)
                    {
                        _transport.SendGameStateAsync(state);
                        _lastPosition = currentPos;
                    }

                    var calls = _crimeDetector.DetectCrimes();
                    foreach (var call in calls)
                    {
                        _transport.SendNineOneOneCallAsync(call);
                        Game.LogTrivial("[LSPDFRDispatch] 911 call: " + call.CrimeType + " at " + call.Location.Street);
                    }
                }
                catch (Exception ex)
                {
                    Game.LogTrivial("[LSPDFRDispatch] Loop error: " + ex.Message);
                }

                GameFiber.Sleep(1000);
            }
        }
    }
}
