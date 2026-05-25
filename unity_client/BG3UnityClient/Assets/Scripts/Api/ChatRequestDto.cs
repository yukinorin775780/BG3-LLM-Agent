using System;

namespace BG3UnityClient.Api
{
    [Serializable]
    public sealed class ApiChatRequest
    {
        public string session_id;
        public string map_id;
        public string user_input;
        public string source;

        public ApiChatRequest(string sessionId, string mapId, string userInput, string source)
        {
            session_id = sessionId;
            map_id = mapId;
            user_input = userInput;
            this.source = source;
        }
    }
}
