using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using Newtonsoft.Json;
using LSPDFRDispatch.Models;

namespace LSPDFRDispatch
{
    /// <summary>
    /// Sends game state and 911 calls to the backend via HTTP POST.
    /// Uses simple HttpWebRequest instead of WebSockets to avoid
    /// dependency issues in RPH's AppDomain.
    /// </summary>
    public class WebSocketTransport : IDisposable
    {
        private readonly string _baseUrl;
        private readonly string _apiKey;
        private readonly TimeSpan _rateLimitInterval;
        private DateTime _lastSendTime = DateTime.MinValue;
        private readonly ConcurrentQueue<string> _buffer = new ConcurrentQueue<string>();
        private bool _disposed;
        private bool _connected;

        public bool IsConnected { get { return _connected; } }
        public int BufferedMessageCount { get { return _buffer.Count; } }

        public WebSocketTransport(string serverUri, string apiKey,
            TimeSpan? rateLimitInterval = null, TimeSpan? reconnectDelay = null)
        {
            // Extract base URL (strip /ws/plugin?api_key=xxx)
            var uri = new Uri(serverUri);
            _baseUrl = "http://" + uri.Host + ":" + uri.Port;
            _apiKey = apiKey ?? "changeme";
            _rateLimitInterval = rateLimitInterval ?? TimeSpan.FromSeconds(1);
        }

        public void ConnectAsync(CancellationToken ct)
        {
            // Test connection with a health check
            try
            {
                var result = HttpPost("/health", "{}");
                _connected = result != null;
            }
            catch
            {
                _connected = false;
            }
        }

        public void SendGameStateAsync(GameState state)
        {
            var now = DateTime.UtcNow;
            if (now - _lastSendTime < _rateLimitInterval)
                return;

            var json = JsonConvert.SerializeObject(state);
            try
            {
                HttpPost("/api/plugin/gamestate", json);
                _lastSendTime = DateTime.UtcNow;
                _connected = true;
            }
            catch
            {
                _connected = false;
                _buffer.Enqueue("gs:" + json);
            }
        }

        public void SendNineOneOneCallAsync(NineOneOneCall call)
        {
            var json = JsonConvert.SerializeObject(call);
            try
            {
                HttpPost("/api/plugin/911call", json);
                _connected = true;
            }
            catch
            {
                _connected = false;
                _buffer.Enqueue("911:" + json);
            }
        }

        public void ReconnectLoopAsync(CancellationToken ct)
        {
            ConnectAsync(ct);
            if (_connected)
                DrainBuffer();
        }

        private void DrainBuffer()
        {
            string msg;
            while (_buffer.TryDequeue(out msg))
            {
                try
                {
                    if (msg.StartsWith("gs:"))
                        HttpPost("/api/plugin/gamestate", msg.Substring(3));
                    else if (msg.StartsWith("911:"))
                        HttpPost("/api/plugin/911call", msg.Substring(4));
                }
                catch { break; }
            }
        }

        private string HttpPost(string path, string jsonBody)
        {
            var request = (HttpWebRequest)WebRequest.Create(_baseUrl + path);
            request.Method = "POST";
            request.ContentType = "application/json";
            request.Headers.Add("X-API-Key", _apiKey);
            request.Timeout = 3000;

            var bytes = Encoding.UTF8.GetBytes(jsonBody);
            request.ContentLength = bytes.Length;
            using (var stream = request.GetRequestStream())
            {
                stream.Write(bytes, 0, bytes.Length);
            }

            using (var response = (HttpWebResponse)request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream()))
            {
                return reader.ReadToEnd();
            }
        }

        public void Dispose()
        {
            _disposed = true;
        }
    }
}
