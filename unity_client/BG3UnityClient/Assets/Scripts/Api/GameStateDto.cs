using System;

namespace BG3UnityClient.Api
{
    [Serializable]
    public sealed class ApiStateResponse
    {
        public string session_id;
        public string map_id;
        public MapDataDto map_data;
        public GameStateDto state;
        public GameStateDto game_state;
        public bool demo_cleared;

        public GameStateDto ResolvedState
        {
            get
            {
                if (state != null)
                {
                    return state;
                }

                if (game_state != null)
                {
                    return game_state;
                }

                return new GameStateDto
                {
                    map_data = map_data,
                    demo_cleared = demo_cleared
                };
            }
        }

        public void ApplyFallbacks(string rawJson, string fallbackSessionId)
        {
            if (string.IsNullOrEmpty(session_id))
            {
                session_id = fallbackSessionId;
            }

            if (string.IsNullOrEmpty(map_id))
            {
                map_id = BackendClient.ExtractStringField(rawJson, "map_id");
            }

            if (map_data == null)
            {
                map_data = new MapDataDto();
            }

            if (string.IsNullOrEmpty(map_data.id))
            {
                map_data.id = BackendClient.ExtractMapDataStringField(rawJson, "id");
            }

            if (string.IsNullOrEmpty(map_data.name))
            {
                map_data.name = BackendClient.ExtractMapDataStringField(rawJson, "name");
            }

            if (string.IsNullOrEmpty(map_data.id))
            {
                map_data.id = map_id;
            }

            if (string.IsNullOrEmpty(map_data.id) && rawJson.Contains("necromancer_lab"))
            {
                map_data.id = "necromancer_lab";
            }

            if (string.IsNullOrEmpty(map_data.name) && rawJson.Contains("死灵法师的废弃实验室"))
            {
                map_data.name = "死灵法师的废弃实验室";
            }
        }
    }

    [Serializable]
    public sealed class GameStateDto
    {
        public MapDataDto map_data;
        public bool demo_cleared;
    }

    [Serializable]
    public sealed class MapDataDto
    {
        public string id;
        public string name;
    }
}
