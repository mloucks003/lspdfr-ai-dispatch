using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using LSPDFRDispatch.Models;

namespace LSPDFRDispatch
{
    /// <summary>
    /// WebSocket client that connects to the backend /ws/plugin endpoint.
    /// Sends game state updates and 911 call events with:
    ///   - Rate limiting: max 1 update per second (Req 7.6)
    ///   - Buffering: queues messages on disconnect, drains in order on reconnect (Req 7.5)
    ///   - API key authentication (Req 13.5)
    /// Requirements: 7.4, 7.5, 7.6
    /// </summary>
    public class WebSocketTransport : IDisposable
    {
        private readonly string _serverUri;
        private readonly string _apiKey;
        private readonly TimeSpan _rateLimitInterval;
        private readonly TimeSpan _reconnectDelay;

        private ClientWebSocket _socket;
        private readonly ConcurrentQueue<string> _messageBuffer = new ConcurrentQueue<string>();
        private DateTime _lastSendTime = DateTime.MinValue;
        private CancellationTokenSource _cts;
        private bool _disposed;

        /// <summary>True when the WebSocket connection is open.</summary>
        public bool IsConnected =>
            _socket?.State == WebSocketState.Open;

        /// <summary>Number of messages currently buffered (waiting for reconnect).</summary>
        public int BufferedMessageCount => _messageBuffer.Count;

        /// <param name="serverUri">Backend WebSocket URI, e.g. ws://localhost:8000/ws/plugin</param>
        /// <param name="apiKey">Shared API key for authentication.</param>
        /// <param name="rateLimitInterval">Minimum interval between sends. Default 1 second.</param>
        /// <param name="reconnectDelay">Delay between reconnection attempts. Default 5 seconds.</param>
        public WebSocketTransport(
            string serverUri,
            string apiKey,
            TimeSpan? rateLimitInterval = null,
            TimeSpan? reconnectDelay = null)
        {
            _serverUri = serverUri ?? throw new ArgumentNullException(nameof(serverUri));
            _apiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
            _rateLimitInterval = rateLimitInterval ?? TimeSpan.FromSeconds(1);
            _reconnectDelay = reconnectDelay ?? TimeSpan.FromSeconds(5);
        }

        /// <summary>
        /// Opens the WebSocket connection to the backend with API key auth.
        /// </summary>
        public async Task ConnectAsync(CancellationToken cancellationToken = default)
        {
            _cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            _socket = new ClientWebSocket();
            _socket.Options.SetRequestHeader("X-API-Key", _apiKey);

            await _socket.ConnectAsync(new Uri(_serverUri), _cts.Token).ConfigureAwait(false);

            // Drain any buffered messages in order
            await DrainBufferAsync().ConfigureAwait(false);
        }

        /// <summary>
        /// Sends a game state update, subject to rate limiting.
        /// If disconnected, the message is buffered for later transmission.
        /// </summary>
        public async Task SendGameStateAsync(GameState state)
        {
            var envelope = new { type = "game_state", data = state };
            string json = JsonConvert.SerializeObject(envelope);
            await SendWithRateLimitAsync(json).ConfigureAwait(false);
        }

        /// <summary>
        /// Sends a 911 call event immediately (not rate-limited — these are high priority).
        /// If disconnected, the message is buffered for later transmission.
        /// </summary>
        public async Task SendNineOneOneCallAsync(NineOneOneCall call)
        {
            var envelope = new { type = "911_call", data = call };
            string json = JsonConvert.SerializeObject(envelope);
            await SendOrBufferAsync(json).ConfigureAwait(false);
        }

        /// <summary>
        /// Attempts to reconnect to the backend. Drains the buffer on success.
        /// </summary>
        public async Task ReconnectAsync(CancellationToken cancellationToken = default)
        {
            // Dispose old socket
            if (_socket != null)
            {
                try { _socket.Dispose(); } catch { /* ignore */ }
            }

            _socket = new ClientWebSocket();
            _socket.Options.SetRequestHeader("X-API-Key", _apiKey);

            await _socket.ConnectAsync(new Uri(_serverUri), cancellationToken).ConfigureAwait(false);

            // Drain buffered messages in order
            await DrainBufferAsync().ConfigureAwait(false);
        }

        /// <summary>
        /// Runs a reconnection loop that keeps trying until connected.
        /// </summary>
        public async Task ReconnectLoopAsync(CancellationToken cancellationToken = default)
        {
            while (!cancellationToken.IsCancellationRequested && !IsConnected)
            {
                try
                {
                    await ReconnectAsync(cancellationToken).ConfigureAwait(false);
                    if (IsConnected) return;
                }
                catch (Exception)
                {
                    // Connection failed — wait and retry
                }

                await Task.Delay(_reconnectDelay, cancellationToken).ConfigureAwait(false);
            }
        }

        /// <summary>
        /// Listens for incoming messages (e.g., ack) from the backend.
        /// </summary>
        public async Task<string> ReceiveAsync(CancellationToken cancellationToken = default)
        {
            var buffer = new byte[4096];
            var sb = new StringBuilder();

            WebSocketReceiveResult result;
            do
            {
                result = await _socket.ReceiveAsync(
                    new ArraySegment<byte>(buffer), cancellationToken).ConfigureAwait(false);

                if (result.MessageType == WebSocketMessageType.Close)
                    return null;

                sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
            }
            while (!result.EndOfMessage);

            return sb.ToString();
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            _cts?.Cancel();
            _cts?.Dispose();
            try { _socket?.Dispose(); } catch { /* ignore */ }
        }

        // ── Private helpers ──────────────────────────────────────────

        private async Task SendWithRateLimitAsync(string json)
        {
            var now = DateTime.UtcNow;
            if (now - _lastSendTime < _rateLimitInterval)
            {
                // Rate limited — skip this update (latest state will be sent next cycle)
                return;
            }

            await SendOrBufferAsync(json).ConfigureAwait(false);
        }

        private async Task SendOrBufferAsync(string json)
        {
            if (!IsConnected)
            {
                _messageBuffer.Enqueue(json);
                return;
            }

            try
            {
                await SendRawAsync(json).ConfigureAwait(false);
                _lastSendTime = DateTime.UtcNow;
            }
            catch (WebSocketException)
            {
                // Connection lost — buffer the message
                _messageBuffer.Enqueue(json);
            }
        }

        private async Task SendRawAsync(string json)
        {
            var bytes = Encoding.UTF8.GetBytes(json);
            await _socket.SendAsync(
                new ArraySegment<byte>(bytes),
                WebSocketMessageType.Text,
                endOfMessage: true,
                cancellationToken: _cts?.Token ?? CancellationToken.None
            ).ConfigureAwait(false);
        }

        private async Task DrainBufferAsync()
        {
            while (_messageBuffer.TryDequeue(out string message))
            {
                await SendRawAsync(message).ConfigureAwait(false);
            }
        }
    }
}
