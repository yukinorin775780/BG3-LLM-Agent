using UnityEngine;

namespace BG3UnityClient.Api
{
    [RequireComponent(typeof(BackendClient))]
    public sealed class UnityApiSmoke : MonoBehaviour
    {
        private BackendClient backendClient;

        private void Awake()
        {
            backendClient = GetComponent<BackendClient>();
        }

        private void Start()
        {
            Debug.Log($"BG3 Unity API smoke: requesting {backendClient.BaseUrl}/api/state");
            StartCoroutine(backendClient.GetState(OnStateLoaded, OnStateError));
        }

        private void OnStateLoaded(ApiStateResponse response)
        {
            var state = response.ResolvedState;
            var resolvedMapId = FirstNonEmpty(state?.map_data?.id, response.map_id, backendClient.MapId, "(unknown)");
            var resolvedMapName = FirstNonEmpty(state?.map_data?.name, "(unnamed)");
            var resolvedSessionId = string.IsNullOrEmpty(response.session_id) ? backendClient.SessionId : response.session_id;
            Debug.Log($"Connected to backend: {resolvedMapId} ({resolvedMapName}) session={resolvedSessionId}");
        }

        private void OnStateError(string error)
        {
            Debug.LogError($"BG3 Unity API smoke failed: {error}");
        }

        private static string FirstNonEmpty(params string[] values)
        {
            foreach (var value in values)
            {
                if (!string.IsNullOrEmpty(value))
                {
                    return value;
                }
            }

            return string.Empty;
        }
    }
}
