using BG3UnityClient.Api;
using UnityEngine;
using UnityEngine.UI;

namespace BG3UnityClient.UI
{
    public sealed class BarkPanel : MonoBehaviour
    {
        [SerializeField] private Text speakerText;
        [SerializeField] private Text bodyText;

        public void Configure(Text speaker, Text body)
        {
            speakerText = speaker;
            bodyText = body;
        }

        public void ShowResponse(ApiChatResponse response)
        {
            if (response == null)
            {
                ShowMessage("Backend", "No response returned.");
                return;
            }

            var speaker = ResolveSpeaker(response.FirstResponseSpeaker);
            var text = response.FirstResponseText;
            if (string.IsNullOrEmpty(text))
            {
                text = BuildFallbackText(response);
            }

            ShowMessage(speaker, text);
        }

        public void ShowResponses(ApiChatResponse response)
        {
            if (response == null || response.responses == null || response.responses.Length <= 1)
            {
                ShowResponse(response);
                return;
            }

            var lines = new System.Text.StringBuilder();
            for (var i = 0; i < response.responses.Length; i++)
            {
                var entry = response.responses[i];
                if (entry == null || string.IsNullOrEmpty(entry.text))
                {
                    continue;
                }

                if (lines.Length > 0)
                {
                    lines.AppendLine();
                }

                lines.Append($"{ResolveSpeaker(entry.speaker)}: {entry.text}");
            }

            ShowMessage("Party", lines.Length == 0 ? BuildFallbackText(response) : lines.ToString());
        }

        public void ShowLines(string speaker, params string[] lines)
        {
            if (lines == null || lines.Length == 0)
            {
                ShowMessage(speaker, string.Empty);
                return;
            }

            var builder = new System.Text.StringBuilder();
            for (var i = 0; i < lines.Length; i++)
            {
                if (string.IsNullOrEmpty(lines[i]))
                {
                    continue;
                }

                if (builder.Length > 0)
                {
                    builder.AppendLine();
                }

                builder.Append(lines[i]);
            }

            ShowMessage(speaker, builder.ToString());
        }

        public void ShowError(string error)
        {
            ShowMessage("Backend Error", error);
        }

        public void ShowMessage(string speaker, string text)
        {
            if (speakerText != null)
            {
                speakerText.text = string.IsNullOrEmpty(speaker) ? "Backend" : speaker;
            }

            if (bodyText != null)
            {
                bodyText.text = string.IsNullOrEmpty(text) ? "(no text)" : text;
            }
        }

        private static string BuildFallbackText(ApiChatResponse response)
        {
            if (response.journal_events != null && response.journal_events.Length > 0 && !string.IsNullOrEmpty(response.journal_events[0]))
            {
                return response.journal_events[0];
            }

            var location = response.ResolvedCurrentLocation;
            if (!string.IsNullOrEmpty(location))
            {
                return $"Location: {location}. Journal events: {response.JournalEventCount}";
            }

            return $"Journal events: {response.JournalEventCount}";
        }

        private static string ResolveSpeaker(string rawSpeaker)
        {
            if (string.IsNullOrEmpty(rawSpeaker))
            {
                return "Narrator";
            }

            var normalized = rawSpeaker.Trim().ToLowerInvariant().Replace("_", "").Replace("-", "").Replace("'", "");
            switch (normalized)
            {
                case "astarion":
                    return "Astarion";
                case "shadowheart":
                    return "Shadowheart";
                case "laezel":
                    return "Lae'zel";
                case "gribbo":
                    return "Gribbo";
                case "dm":
                case "narrator":
                    return "Narrator";
                default:
                    return rawSpeaker;
            }
        }
    }
}
