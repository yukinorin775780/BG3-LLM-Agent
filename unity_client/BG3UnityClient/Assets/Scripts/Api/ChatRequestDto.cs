using System;

namespace BG3UnityClient.Api
{
    [Serializable]
    public sealed class ApiChatRequest
    {
        public string session_id;
        public string map_id;
        public string user_input;
        public string intent;
        public string target;
        public string source;
        public ClientPlayerPositionDto client_player_position;

        public ApiChatRequest(string sessionId, string mapId, string userInput, string source)
        {
            session_id = sessionId;
            map_id = mapId;
            user_input = userInput;
            this.source = source;
        }
    }

    [Serializable]
    public sealed class ClientPlayerPositionDto
    {
        public int x;
        public int y;

        public ClientPlayerPositionDto(int x, int y)
        {
            this.x = x;
            this.y = y;
        }
    }
}
