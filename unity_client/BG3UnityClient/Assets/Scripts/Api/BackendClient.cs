using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.Networking;

namespace BG3UnityClient.Api
{
    public sealed class BackendClient : MonoBehaviour
    {
        [SerializeField] private string baseUrl = "http://127.0.0.1:8000";
        [SerializeField] private string sessionId = "unity_spike_001";
        [SerializeField] private string mapId = "necromancer_lab";

        public string BaseUrl => baseUrl;
        public string SessionId => sessionId;
        public string MapId => mapId;

        public IEnumerator PostChat(string userInput, Action<ApiChatResponse> onSuccess, Action<string> onError)
        {
            var payload = new ApiChatRequest(sessionId, mapId, userInput, "unity_client");
            yield return PostChat(payload, onSuccess, onError);
        }

        public IEnumerator PostChat(ApiChatRequest payload, Action<ApiChatResponse> onSuccess, Action<string> onError)
        {
            var url = $"{baseUrl.TrimEnd('/')}/api/chat";
            var body = Encoding.UTF8.GetBytes(JsonUtility.ToJson(payload));

            using (var request = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
            {
                request.uploadHandler = new UploadHandlerRaw(body);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.SetRequestHeader("Accept", "application/json");

                yield return request.SendWebRequest();

                if (request.result != UnityWebRequest.Result.Success)
                {
                    var detail = request.downloadHandler != null ? request.downloadHandler.text : string.Empty;
                    onError?.Invoke(string.IsNullOrEmpty(detail)
                        ? $"{request.responseCode} {request.error}"
                        : $"{request.responseCode} {request.error}: {detail}");
                    yield break;
                }

                try
                {
                    var rawJson = request.downloadHandler.text;
                    var response = JsonUtility.FromJson<ApiChatResponse>(rawJson);
                    if (response == null)
                    {
                        onError?.Invoke("Backend returned empty chat response.");
                        yield break;
                    }

                    response.ApplyFallbacks(rawJson);
                    onSuccess?.Invoke(response);
                }
                catch (Exception ex)
                {
                    onError?.Invoke($"Failed to parse backend chat JSON: {ex.Message}");
                }
            }
        }

        public IEnumerator GetState(Action<ApiStateResponse> onSuccess, Action<string> onError)
        {
            var url = $"{baseUrl.TrimEnd('/')}/api/state?session_id={UnityWebRequest.EscapeURL(sessionId)}&map_id={UnityWebRequest.EscapeURL(mapId)}";
            using (var request = UnityWebRequest.Get(url))
            {
                yield return request.SendWebRequest();

                if (request.result != UnityWebRequest.Result.Success)
                {
                    onError?.Invoke($"{request.responseCode} {request.error}");
                    yield break;
                }

                try
                {
                    var rawJson = request.downloadHandler.text;
                    var response = JsonUtility.FromJson<ApiStateResponse>(rawJson);
                    if (response == null)
                    {
                        onError?.Invoke("Backend returned empty state response.");
                        yield break;
                    }

                    response.ApplyFallbacks(rawJson, sessionId);
                    onSuccess?.Invoke(response);
                }
                catch (Exception ex)
                {
                    onError?.Invoke($"Failed to parse backend state JSON: {ex.Message}");
                }
            }
        }

        public static string ExtractStringField(string json, string fieldName)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(fieldName))
            {
                return string.Empty;
            }

            var match = Regex.Match(json, $"\"{Regex.Escape(fieldName)}\"\\s*:\\s*\"([^\"]*)\"");
            return match.Success ? DecodeJsonString(match.Groups[1].Value) : string.Empty;
        }

        public static string[] ExtractStringArrayField(string json, string fieldName)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(fieldName))
            {
                return Array.Empty<string>();
            }

            var arrayMatch = Regex.Match(
                json,
                $"\"{Regex.Escape(fieldName)}\"\\s*:\\s*\\[(.*?)\\]",
                RegexOptions.Singleline);
            if (!arrayMatch.Success)
            {
                return Array.Empty<string>();
            }

            var values = new List<string>();
            foreach (Match itemMatch in Regex.Matches(arrayMatch.Groups[1].Value, "\"((?:\\\\.|[^\"])*)\""))
            {
                values.Add(DecodeJsonString(itemMatch.Groups[1].Value));
            }

            return values.ToArray();
        }

        public static string ExtractFirstResponseField(string json, string fieldName)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(fieldName))
            {
                return string.Empty;
            }

            var responsesIndex = json.IndexOf("\"responses\"", StringComparison.Ordinal);
            if (responsesIndex < 0)
            {
                return string.Empty;
            }

            var searchLength = Math.Min(2000, json.Length - responsesIndex);
            var responsesSlice = json.Substring(responsesIndex, searchLength);
            var match = Regex.Match(
                responsesSlice,
                $"\"{Regex.Escape(fieldName)}\"\\s*:\\s*\"((?:\\\\.|[^\"])*)\"",
                RegexOptions.Singleline);
            return match.Success ? DecodeJsonString(match.Groups[1].Value) : string.Empty;
        }

        public static ChatSpeakerResponse[] ExtractSpeakerResponses(string json)
        {
            if (string.IsNullOrEmpty(json))
            {
                return Array.Empty<ChatSpeakerResponse>();
            }

            var arraySlice = ExtractArraySlice(json, "responses");
            if (string.IsNullOrEmpty(arraySlice))
            {
                return Array.Empty<ChatSpeakerResponse>();
            }

            var responses = new List<ChatSpeakerResponse>();
            foreach (Match objectMatch in Regex.Matches(arraySlice, "\\{(.*?)\\}", RegexOptions.Singleline))
            {
                var objectJson = objectMatch.Groups[1].Value;
                var speaker = ExtractStringFieldFromSlice(objectJson, "speaker");
                var text = ExtractStringFieldFromSlice(objectJson, "text");
                if (!string.IsNullOrEmpty(text))
                {
                    responses.Add(new ChatSpeakerResponse
                    {
                        speaker = speaker,
                        text = text
                    });
                }
            }

            return responses.ToArray();
        }

        public static string ExtractMapDataStringField(string json, string fieldName)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(fieldName))
            {
                return string.Empty;
            }

            var mapDataIndex = json.IndexOf("\"map_data\"", StringComparison.Ordinal);
            if (mapDataIndex < 0)
            {
                return string.Empty;
            }

            var searchStart = mapDataIndex;
            var searchLength = Math.Min(1500, json.Length - searchStart);
            var mapDataSlice = json.Substring(searchStart, searchLength);
            var match = Regex.Match(mapDataSlice, $"\"{Regex.Escape(fieldName)}\"\\s*:\\s*\"([^\"]*)\"");
            return match.Success ? DecodeJsonString(match.Groups[1].Value) : string.Empty;
        }

        public static bool ExtractBooleanField(string json, string fieldName)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(fieldName))
            {
                return false;
            }

            return Regex.IsMatch(
                json,
                $"\"{Regex.Escape(fieldName)}\"\\s*:\\s*true",
                RegexOptions.IgnoreCase);
        }

        public static int ExtractInventoryCount(string json, string objectName, string itemId)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(objectName) || string.IsNullOrEmpty(itemId))
            {
                return 0;
            }

            var objectIndex = json.IndexOf($"\"{objectName}\"", StringComparison.Ordinal);
            if (objectIndex < 0)
            {
                return 0;
            }

            var searchLength = Math.Min(1200, json.Length - objectIndex);
            var objectSlice = json.Substring(objectIndex, searchLength);
            var match = Regex.Match(objectSlice, $"\"{Regex.Escape(itemId)}\"\\s*:\\s*(\\d+)");
            if (!match.Success || !int.TryParse(match.Groups[1].Value, out var count))
            {
                return 0;
            }

            return count;
        }

        private static string ExtractArraySlice(string json, string fieldName)
        {
            var fieldIndex = json.IndexOf($"\"{fieldName}\"", StringComparison.Ordinal);
            if (fieldIndex < 0)
            {
                return string.Empty;
            }

            var arrayStart = json.IndexOf('[', fieldIndex);
            if (arrayStart < 0)
            {
                return string.Empty;
            }

            var depth = 0;
            var inString = false;
            var escaping = false;
            for (var i = arrayStart; i < json.Length; i++)
            {
                var c = json[i];
                if (inString)
                {
                    if (escaping)
                    {
                        escaping = false;
                    }
                    else if (c == '\\')
                    {
                        escaping = true;
                    }
                    else if (c == '"')
                    {
                        inString = false;
                    }

                    continue;
                }

                if (c == '"')
                {
                    inString = true;
                }
                else if (c == '[')
                {
                    depth++;
                }
                else if (c == ']')
                {
                    depth--;
                    if (depth == 0)
                    {
                        return json.Substring(arrayStart + 1, i - arrayStart - 1);
                    }
                }
            }

            return string.Empty;
        }

        private static string ExtractStringFieldFromSlice(string json, string fieldName)
        {
            var match = Regex.Match(
                json,
                $"\"{Regex.Escape(fieldName)}\"\\s*:\\s*\"((?:\\\\.|[^\"])*)\"",
                RegexOptions.Singleline);
            return match.Success ? DecodeJsonString(match.Groups[1].Value) : string.Empty;
        }

        private static string DecodeJsonString(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return string.Empty;
            }

            try
            {
                return Regex.Unescape(value);
            }
            catch (ArgumentException)
            {
                return value;
            }
        }
    }
}
