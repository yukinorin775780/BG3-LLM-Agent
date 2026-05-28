using System;
using System.Text;
using System.Text.RegularExpressions;
using BG3UnityClient.Api;
using BG3UnityClient.UI;
using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class TrapZone : MonoBehaviour
    {
        private const string TrapId = "gas_trap_1";
        private const string PerceptionPrompt = "Is something wrong in the corridor?";
        private const string DisarmPrompt = "Astarion, disarm the trap.";

        [SerializeField] private BackendClient backendClient;
        [SerializeField] private TrapMarker trapMarker;
        [SerializeField] private BackendDebugPanel debugPanel;
        [SerializeField] private BarkPanel barkPanel;
        [SerializeField] private Transform player;
        [SerializeField] private Transform astarion;
        [SerializeField] private float proximityRange = 1.55f;
        [SerializeField] private Vector2Int backendApproachTile = new Vector2Int(5, 12);

        private bool perceptionRequested;
        private bool requestInFlight;
        private bool disarmInFlight;
        private Coroutine astarionMoveRoutine;

        public event Action<TrapVisualState> TrapStateChanged;

        public TrapVisualState State => trapMarker == null ? TrapVisualState.Hidden : trapMarker.State;

        public void Configure(
            BackendClient client,
            TrapMarker marker,
            Transform playerTransform,
            Transform astarionTransform,
            BackendDebugPanel panel,
            BarkPanel bark)
        {
            backendClient = client;
            trapMarker = marker;
            player = playerTransform;
            astarion = astarionTransform;
            debugPanel = panel;
            barkPanel = bark;
            EnsureTriggerCollider();
            debugPanel?.AttachTrapZone(this);
        }

        public void AttachDebugPanel(BackendDebugPanel panel)
        {
            debugPanel = panel;
            debugPanel?.AttachTrapZone(this);
        }

        public void AttachBarkPanel(BarkPanel panel)
        {
            barkPanel = panel;
        }

        public void RequestPerception()
        {
            if (perceptionRequested || requestInFlight || backendClient == null)
            {
                return;
            }

            perceptionRequested = true;
            requestInFlight = true;
            debugPanel?.ShowTrapOutput("Perception", "Sending trap proximity context to backend...");
            Debug.Log($"BG3 trap perception request sent: {TrapId} source=unity_trap_proximity");

            StartCoroutine(RunPerceptionSequence());
        }

        private System.Collections.IEnumerator RunPerceptionSequence()
        {
            yield return EnsureCorridorAccessForBackend();

            var payload = CreateTrapPayload(PerceptionPrompt, "unity_trap_proximity", null);
            yield return backendClient.PostChat(
                payload,
                response =>
                {
                    requestInFlight = false;
                    HandleTrapResponse("Perception", response, false);
                },
                error =>
                {
                    requestInFlight = false;
                    debugPanel?.ShowTrapOutput("Perception failed", error);
                    Debug.LogWarning($"BG3 trap perception request failed: {error}");
                });
        }

        public void AskAstarionToDisarm()
        {
            if (disarmInFlight || backendClient == null)
            {
                return;
            }

            disarmInFlight = true;
            debugPanel?.ShowTrapOutput("Disarm", "Asking Astarion to disarm gas_trap_1...");
            Debug.Log($"BG3 trap disarm request sent: {TrapId}");

            var payload = CreateTrapPayload(DisarmPrompt, "unity_disarm_button", null);
            StartCoroutine(backendClient.PostChat(
                payload,
                response =>
                {
                    disarmInFlight = false;
                    HandleTrapResponse("Disarm", response, true);
                },
                error =>
                {
                    disarmInFlight = false;
                    debugPanel?.ShowTrapOutput("Disarm failed", error);
                    Debug.LogWarning($"BG3 trap disarm request failed: {error}");
                }));
        }

        public void TriggerTrapDebug()
        {
            if (backendClient == null)
            {
                ApplyTrapState(TrapVisualState.Triggered, "Poison Gas Released (debug-only visual; backend unavailable).");
                return;
            }

            debugPanel?.ShowTrapOutput("Trigger Trap", "Sending debug trap trigger to backend...");
            Debug.Log($"BG3 trap trigger debug request sent: {TrapId}");

            var payload = CreateTrapPayload(string.Empty, "trap_trigger", "INTERACT");
            StartCoroutine(backendClient.PostChat(
                payload,
                response =>
                {
                    if (!HandleTrapResponse("Trigger Trap", response, false) && State != TrapVisualState.Disabled)
                    {
                        ApplyTrapState(TrapVisualState.Triggered, "Poison Gas Released (debug-only visual fallback).");
                    }
                },
                error =>
                {
                    if (State != TrapVisualState.Disabled)
                    {
                        ApplyTrapState(TrapVisualState.Triggered, $"Poison Gas Released (debug-only visual; backend error: {error}).");
                    }
                    else
                    {
                        debugPanel?.ShowTrapOutput("Trigger Trap skipped", $"Trap is already disabled. Backend error: {error}");
                    }
                }));
        }

        public bool HandleExternalChatResponse(ApiChatResponse response, string userInput)
        {
            var handled = HandleTrapResponse("Chat", response, LooksLikeDisarmCommand(userInput));
            return handled;
        }

        private void Awake()
        {
            EnsureTriggerCollider();
        }

        private void Start()
        {
            ResolveReferences();
            debugPanel?.AttachTrapZone(this);
        }

        private void Update()
        {
            if (perceptionRequested || requestInFlight || State != TrapVisualState.Hidden)
            {
                return;
            }

            ResolveReferences();
            if (player == null)
            {
                return;
            }

            var flatPlayer = new Vector3(player.position.x, transform.position.y, player.position.z);
            if (Vector3.Distance(flatPlayer, transform.position) <= proximityRange)
            {
                RequestPerception();
            }
        }

        private void OnDrawGizmosSelected()
        {
            Gizmos.color = new Color(1f, 0.58f, 0.08f, 0.32f);
            Gizmos.DrawWireCube(transform.position + Vector3.up * 0.6f, new Vector3(proximityRange * 2f, 1.2f, proximityRange * 2f));
        }

        private void ResolveReferences()
        {
            if (backendClient == null)
            {
                backendClient = UnityEngine.Object.FindAnyObjectByType<BackendClient>();
            }

            if (trapMarker == null)
            {
                trapMarker = UnityEngine.Object.FindAnyObjectByType<TrapMarker>();
            }

            if (debugPanel == null)
            {
                debugPanel = UnityEngine.Object.FindAnyObjectByType<BackendDebugPanel>();
            }

            if (barkPanel == null)
            {
                barkPanel = UnityEngine.Object.FindAnyObjectByType<BarkPanel>();
            }

            if (player == null)
            {
                var playerObject = GameObject.Find("Player");
                player = playerObject == null ? null : playerObject.transform;
            }

            if (astarion == null)
            {
                var astarionObject = GameObject.Find("Astarion");
                astarion = astarionObject == null ? null : astarionObject.transform;
            }
        }

        private void EnsureTriggerCollider()
        {
            var trigger = GetComponent<BoxCollider>();
            if (trigger == null)
            {
                trigger = gameObject.AddComponent<BoxCollider>();
            }

            trigger.isTrigger = true;
            trigger.center = new Vector3(0f, 0.65f, 0f);
            trigger.size = new Vector3(proximityRange * 2f, 1.3f, proximityRange * 2f);
        }

        private ApiChatRequest CreateTrapPayload(string userInput, string source, string intent)
        {
            var payload = new ApiChatRequest(backendClient.SessionId, backendClient.MapId, userInput, source)
            {
                intent = intent,
                target = TrapId,
                client_player_position = new ClientPlayerPositionDto(backendApproachTile.x, backendApproachTile.y)
            };
            return payload;
        }

        private ApiChatRequest CreateCorridorDoorPayload()
        {
            return new ApiChatRequest(backendClient.SessionId, backendClient.MapId, "Open the door to the poison corridor.", "unity_corridor_sync")
            {
                intent = "INTERACT",
                target = "door_a_to_b",
                client_player_position = new ClientPlayerPositionDto(2, 2)
            };
        }

        private System.Collections.IEnumerator EnsureCorridorAccessForBackend()
        {
            var doorKnownOpen = false;
            var stateFailed = false;

            yield return backendClient.GetState(
                response => doorKnownOpen = IsCorridorDoorOpen(response.raw_json),
                error =>
                {
                    stateFailed = true;
                    Debug.LogWarning($"BG3 trap corridor state check failed: {error}");
                });

            if (doorKnownOpen || stateFailed)
            {
                yield break;
            }

            Debug.Log("BG3 trap corridor sync request sent: door_a_to_b");
            yield return backendClient.PostChat(
                CreateCorridorDoorPayload(),
                response => Debug.Log("BG3 trap corridor sync completed."),
                error => Debug.LogWarning($"BG3 trap corridor sync failed: {error}"));
        }

        private bool HandleTrapResponse(string label, ApiChatResponse response, bool animateDisarm)
        {
            barkPanel?.ShowResponse(response);
            var summary = BuildTrapResponseSummary(label, response);
            debugPanel?.ShowTrapOutput(label, summary);

            if (!TryResolveTrapState(response, out var resolvedState))
            {
                Debug.Log($"BG3 trap backend response did not change state: {label}");
                return false;
            }

            if (!animateDisarm && label == "Perception" && resolvedState == TrapVisualState.Disabled)
            {
                resolvedState = TrapVisualState.Revealed;
            }

            ApplyTrapState(resolvedState, $"{label}: backend inferred {resolvedState}.");
            if (animateDisarm && resolvedState == TrapVisualState.Disabled)
            {
                MoveAstarionToTrap();
            }

            return true;
        }

        private void ApplyTrapState(TrapVisualState nextState, string detail)
        {
            trapMarker?.SetState(nextState);
            debugPanel?.SetTrapState(nextState);
            TrapStateChanged?.Invoke(nextState);
            if (!string.IsNullOrEmpty(detail))
            {
                debugPanel?.ShowTrapOutput($"Trap: {nextState}", detail);
            }

            Debug.Log($"BG3 trap state applied: {nextState}");
        }

        private void MoveAstarionToTrap()
        {
            ResolveReferences();
            if (astarion == null || trapMarker == null)
            {
                return;
            }

            if (astarionMoveRoutine != null)
            {
                StopCoroutine(astarionMoveRoutine);
            }

            astarionMoveRoutine = StartCoroutine(MoveAstarionRoutine());
        }

        private System.Collections.IEnumerator MoveAstarionRoutine()
        {
            var follower = astarion.GetComponent<CompanionFollower>();
            if (follower != null)
            {
                follower.enabled = false;
            }

            var start = astarion.position;
            var end = trapMarker.transform.position + new Vector3(-0.8f, 1f, -0.7f);
            var elapsed = 0f;
            const float duration = 0.55f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                var t = Mathf.Clamp01(elapsed / duration);
                astarion.position = Vector3.Lerp(start, end, t);
                yield return null;
            }

            yield return new WaitForSeconds(0.35f);

            if (follower != null)
            {
                follower.enabled = true;
            }

            astarionMoveRoutine = null;
        }

        public static bool TryResolveTrapState(ApiChatResponse response, out TrapVisualState resolvedState)
        {
            resolvedState = TrapVisualState.Hidden;
            var haystack = BuildTrapHaystack(response);
            if (string.IsNullOrEmpty(haystack) || !haystack.Contains(TrapId))
            {
                return false;
            }

            if (ContainsAny(haystack, "necromancer_lab_poison_trap_disarmed", "[陷阱解除]", "\"status\":\"disabled\"", "\"status\": \"disabled\"", "disarmed"))
            {
                resolvedState = TrapVisualState.Disabled;
                return true;
            }

            if (ContainsAny(haystack, "necromancer_lab_poison_trap_triggered", "[毒气陷阱]", "\"status\":\"triggered\"", "\"status\": \"triggered\"", "poison gas released"))
            {
                resolvedState = TrapVisualState.Triggered;
                return true;
            }

            if (ContainsAny(haystack, "astarion_detected_gas_trap", "necromancer_lab_poison_trap_revealed", "[陷阱感知]", "毒气压力板", "\"is_hidden\":false", "\"is_hidden\": false"))
            {
                resolvedState = TrapVisualState.Revealed;
                return true;
            }

            return false;
        }

        public static string BuildTrapResponseSummary(string label, ApiChatResponse response)
        {
            var builder = new StringBuilder();
            builder.AppendLine(label);

            if (response == null)
            {
                builder.AppendLine("No backend response.");
                return builder.ToString();
            }

            if (!string.IsNullOrEmpty(response.FirstResponseText))
            {
                var speaker = string.IsNullOrEmpty(response.FirstResponseSpeaker) ? "backend" : response.FirstResponseSpeaker;
                builder.AppendLine($"{speaker}: {response.FirstResponseText}");
            }

            if (TryResolveTrapState(response, out var resolvedState))
            {
                builder.AppendLine($"Trap: {resolvedState}");
            }
            else
            {
                builder.AppendLine("Trap: no state change detected");
            }

            if (response.journal_events != null)
            {
                var limit = Mathf.Min(3, response.journal_events.Length);
                for (var i = 0; i < limit; i++)
                {
                    if (!string.IsNullOrEmpty(response.journal_events[i]))
                    {
                        builder.AppendLine($"- {response.journal_events[i]}");
                    }
                }
            }

            return builder.ToString();
        }

        private static bool LooksLikeDisarmCommand(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return false;
            }

            var normalized = value.ToLowerInvariant();
            return normalized.Contains("astarion")
                && (normalized.Contains("disarm") || normalized.Contains("disable") || normalized.Contains("解除") || normalized.Contains("拆"));
        }

        private static string BuildTrapHaystack(ApiChatResponse response)
        {
            if (response == null)
            {
                return string.Empty;
            }

            var builder = new StringBuilder();
            builder.Append(response.raw_json);
            builder.Append('\n');
            builder.Append(response.FirstResponseSpeaker);
            builder.Append('\n');
            builder.Append(response.FirstResponseText);
            if (response.journal_events != null)
            {
                for (var i = 0; i < response.journal_events.Length; i++)
                {
                    builder.Append('\n');
                    builder.Append(response.journal_events[i]);
                }
            }

            return builder.ToString().ToLowerInvariant();
        }

        private static bool ContainsAny(string value, params string[] markers)
        {
            for (var i = 0; i < markers.Length; i++)
            {
                if (value.Contains(markers[i].ToLowerInvariant()))
                {
                    return true;
                }
            }

            return false;
        }

        private static bool IsCorridorDoorOpen(string rawJson)
        {
            if (string.IsNullOrEmpty(rawJson))
            {
                return false;
            }

            return Regex.IsMatch(
                rawJson,
                "\"door_a_to_b\"\\s*:\\s*\\{.*?(\"is_open\"\\s*:\\s*true|\"status\"\\s*:\\s*\"open\")",
                RegexOptions.Singleline);
        }
    }
}
