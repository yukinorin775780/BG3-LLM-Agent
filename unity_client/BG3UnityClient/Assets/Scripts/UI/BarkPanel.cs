using BG3UnityClient.Api;
using UnityEngine;
using UnityEngine.UI;

namespace BG3UnityClient.UI
{
    public sealed class BarkPanel : MonoBehaviour
    {
        [SerializeField] private float queuedLineSeconds = 1.35f;
        [SerializeField] private Text speakerText;
        [SerializeField] private Text bodyText;

        private Coroutine queueRoutine;

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

            var entries = new BarkEntry[response.responses.Length];
            var count = 0;
            for (var i = 0; i < response.responses.Length; i++)
            {
                var entry = response.responses[i];
                if (entry == null || string.IsNullOrEmpty(entry.text))
                {
                    continue;
                }

                entries[count] = new BarkEntry(ResolveSpeaker(entry.speaker), entry.text);
                count++;
            }

            if (count == 0)
            {
                ShowMessage("Party", BuildFallbackText(response));
                return;
            }

            QueueEntries(entries, count);
        }

        public void ShowLines(string speaker, params string[] lines)
        {
            if (lines == null || lines.Length == 0)
            {
                ShowMessage(speaker, string.Empty);
                return;
            }

            var entries = new BarkEntry[lines.Length];
            var count = 0;
            for (var i = 0; i < lines.Length; i++)
            {
                if (string.IsNullOrEmpty(lines[i]))
                {
                    continue;
                }

                var parsedSpeaker = speaker;
                var text = lines[i];
                var separatorIndex = lines[i].IndexOf(':');
                if (separatorIndex > 0 && separatorIndex + 1 < lines[i].Length)
                {
                    parsedSpeaker = ResolveSpeaker(lines[i].Substring(0, separatorIndex));
                    text = lines[i].Substring(separatorIndex + 1).Trim();
                }

                entries[count] = new BarkEntry(parsedSpeaker, text);
                count++;
            }

            if (count == 0)
            {
                ShowMessage(speaker, string.Empty);
                return;
            }

            QueueEntries(entries, count);
        }

        public void ShowError(string error)
        {
            ShowMessage("Backend Error", error);
        }

        public void ShowMessage(string speaker, string text)
        {
            StopQueue();
            if (speakerText != null)
            {
                speakerText.text = string.IsNullOrEmpty(speaker) ? "Backend" : speaker;
            }

            if (bodyText != null)
            {
                bodyText.text = string.IsNullOrEmpty(text) ? "(no text)" : text;
            }
        }

        private void QueueEntries(BarkEntry[] entries, int count)
        {
            StopQueue();
            queueRoutine = StartCoroutine(ShowQueue(entries, count));
        }

        private System.Collections.IEnumerator ShowQueue(BarkEntry[] entries, int count)
        {
            for (var i = 0; i < count; i++)
            {
                SetMessage(entries[i].speaker, entries[i].text);
                yield return new WaitForSeconds(queuedLineSeconds);
            }

            queueRoutine = null;
        }

        private void StopQueue()
        {
            if (queueRoutine != null)
            {
                StopCoroutine(queueRoutine);
                queueRoutine = null;
            }
        }

        private void SetMessage(string speaker, string text)
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

            var normalized = rawSpeaker.Trim().ToLowerInvariant().Replace("_", "").Replace("-", "").Replace("'", "").Replace("’", "");
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

        private readonly struct BarkEntry
        {
            public readonly string speaker;
            public readonly string text;

            public BarkEntry(string speaker, string text)
            {
                this.speaker = speaker;
                this.text = text;
            }
        }
    }
}
