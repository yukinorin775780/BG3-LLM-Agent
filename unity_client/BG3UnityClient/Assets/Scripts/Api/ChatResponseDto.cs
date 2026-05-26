using System;

namespace BG3UnityClient.Api
{
    [Serializable]
    public sealed class ApiChatResponse
    {
        public ChatSpeakerResponse[] responses;
        public string[] journal_events;
        public string current_location;
        public ChatGameStateDto game_state;
        public ChatGameStateDto state;
        public ChatPlayerInventoryDto player_inventory;
        public ChatLatestRollDto latest_roll;
        public bool demo_cleared;

        [NonSerialized] public string raw_json;

        public int JournalEventCount => journal_events == null ? 0 : journal_events.Length;

        public string FirstResponseText
        {
            get
            {
                if (responses == null || responses.Length == 0 || responses[0] == null)
                {
                    return string.Empty;
                }

                return responses[0].text ?? string.Empty;
            }
        }

        public bool HasHeavyIronKey
        {
            get
            {
                if (player_inventory != null && player_inventory.heavy_iron_key > 0)
                {
                    return true;
                }

                return BackendClient.ExtractInventoryCount(raw_json, "player_inventory", "heavy_iron_key") > 0
                    || BackendClient.ExtractBooleanField(raw_json, "act4_heavy_iron_key_obtained");
            }
        }

        public string FirstResponseSpeaker
        {
            get
            {
                if (responses == null || responses.Length == 0 || responses[0] == null)
                {
                    return string.Empty;
                }

                return responses[0].speaker ?? string.Empty;
            }
        }

        public string ResolvedCurrentLocation
        {
            get
            {
                if (!string.IsNullOrEmpty(current_location))
                {
                    return current_location;
                }

                if (!string.IsNullOrEmpty(game_state?.current_location))
                {
                    return game_state.current_location;
                }

                return state?.current_location ?? string.Empty;
            }
        }

        public ChatLatestRollDto ResolvedLatestRoll
        {
            get
            {
                if (latest_roll != null)
                {
                    return latest_roll;
                }

                if (game_state?.latest_roll != null)
                {
                    return game_state.latest_roll;
                }

                return state?.latest_roll;
            }
        }

        public void ApplyFallbacks(string rawJson)
        {
            raw_json = rawJson;

            if (string.IsNullOrEmpty(current_location))
            {
                current_location = BackendClient.ExtractStringField(rawJson, "current_location");
            }

            if (responses == null || responses.Length == 0 || string.IsNullOrEmpty(responses[0]?.text))
            {
                var extractedResponses = BackendClient.ExtractSpeakerResponses(rawJson);
                if (extractedResponses.Length > 0)
                {
                    responses = extractedResponses;
                }
                else
                {
                    var text = BackendClient.ExtractFirstResponseField(rawJson, "text");
                    if (!string.IsNullOrEmpty(text))
                    {
                        responses = new[]
                        {
                            new ChatSpeakerResponse
                            {
                                speaker = BackendClient.ExtractFirstResponseField(rawJson, "speaker"),
                                text = text
                            }
                        };
                    }
                }
            }
            else
            {
                var extractedResponses = BackendClient.ExtractSpeakerResponses(rawJson);
                if (extractedResponses.Length > responses.Length)
                {
                    responses = extractedResponses;
                }
            }

            if (journal_events == null || journal_events.Length == 0)
            {
                journal_events = BackendClient.ExtractStringArrayField(rawJson, "journal_events");
            }
        }
    }

    [Serializable]
    public sealed class ChatSpeakerResponse
    {
        public string speaker;
        public string text;
    }

    [Serializable]
    public sealed class ChatGameStateDto
    {
        public string current_location;
        public string[] journal_events;
        public ChatLatestRollDto latest_roll;
    }

    [Serializable]
    public sealed class ChatPlayerInventoryDto
    {
        public int heavy_iron_key;
        public int lab_key;
        public int healing_potion;
    }

    [Serializable]
    public sealed class ChatLatestRollDto
    {
        public string intent;
        public string target;
        public string skill;
        public int dc;
        public int modifier;
        public ChatRollResultDto result;
    }

    [Serializable]
    public sealed class ChatRollResultDto
    {
        public bool is_success;
        public int raw_roll;
        public int total;
        public string result_type;
    }
}
