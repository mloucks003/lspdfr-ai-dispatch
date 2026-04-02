using System;
using System.Collections.Generic;
using LSPDFRDispatch.Models;

namespace LSPDFRDispatch
{
    /// <summary>
    /// Monitors game events for crimes in progress and generates 911 call payloads.
    /// Requirements: 8.1, 8.4
    /// </summary>
    public class CrimeEventDetector
    {
        private readonly IGameApi _gameApi;
        private readonly LocationResolver _locationResolver;
        private readonly float _detectionRadius;
        private readonly Random _random;

        // Track already-reported crime events to avoid duplicates
        private readonly HashSet<string> _reportedEvents = new HashSet<string>();

        private static readonly string[] CallerPrefixes = new[]
        {
            "Male caller reports",
            "Female caller reports",
            "Anonymous caller reports",
            "Store clerk reports",
            "Witness reports",
            "Bystander reports"
        };

        public CrimeEventDetector(IGameApi gameApi, LocationResolver locationResolver, float detectionRadius = 150f)
        {
            _gameApi = gameApi;
            _locationResolver = locationResolver;
            _detectionRadius = detectionRadius;
            _random = new Random();
        }

        /// <summary>
        /// Scans for new crime events and returns 911 call payloads for any
        /// that haven't been reported yet.
        /// </summary>
        public List<NineOneOneCall> DetectCrimes()
        {
            var calls = new List<NineOneOneCall>();
            var events = _gameApi.GetNearbyCrimeEvents(_detectionRadius);

            foreach (var crimeEvent in events)
            {
                string eventKey = BuildEventKey(crimeEvent);
                if (_reportedEvents.Contains(eventKey))
                    continue;

                _reportedEvents.Add(eventKey);
                calls.Add(BuildCall(crimeEvent));
            }

            return calls;
        }

        /// <summary>
        /// Resets the set of reported events (e.g., on a new patrol session).
        /// </summary>
        public void Reset()
        {
            _reportedEvents.Clear();
        }

        private NineOneOneCall BuildCall(CrimeEvent crimeEvent)
        {
            var location = _locationResolver.Resolve(crimeEvent.Position);

            var involvedPeds = new List<InvolvedPed>();
            if (crimeEvent.InvolvedPeds != null)
            {
                foreach (var ped in crimeEvent.InvolvedPeds)
                {
                    involvedPeds.Add(new InvolvedPed
                    {
                        Name = ped.Name ?? "Unknown",
                        Description = ped.Description ?? ""
                    });
                }
            }

            string callerPrefix = CallerPrefixes[_random.Next(CallerPrefixes.Length)];
            string crimeDescription = FormatCrimeDescription(crimeEvent.CrimeType);

            return new NineOneOneCall
            {
                CrimeType = crimeEvent.CrimeType ?? "Unknown",
                Location = new CallLocation
                {
                    Street = location.Street,
                    Landmark = location.Landmark,
                    X = crimeEvent.Position.X,
                    Y = crimeEvent.Position.Y,
                    Z = crimeEvent.Position.Z
                },
                InvolvedPeds = involvedPeds,
                CallerDescription = $"{callerPrefix} {crimeDescription} at {location.Street}"
            };
        }

        private string BuildEventKey(CrimeEvent crimeEvent)
        {
            // Key on crime type + approximate position (rounded to 10 units) to deduplicate
            int rx = (int)(crimeEvent.Position.X / 10) * 10;
            int ry = (int)(crimeEvent.Position.Y / 10) * 10;
            return $"{crimeEvent.CrimeType}_{rx}_{ry}";
        }

        private string FormatCrimeDescription(string crimeType)
        {
            if (string.IsNullOrEmpty(crimeType))
                return "suspicious activity";

            // Convert snake_case or PascalCase to readable text
            return crimeType
                .Replace("_", " ")
                .Replace("-", " ")
                .ToLowerInvariant();
        }
    }
}
