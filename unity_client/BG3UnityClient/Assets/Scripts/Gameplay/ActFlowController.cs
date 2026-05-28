using System;
using System.Text;
using BG3UnityClient.Api;
using BG3UnityClient.UI;
using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public enum ActFlowStage
    {
        Act1SafeRoom = 1,
        Act2PoisonCorridor = 2,
        Act3SecretStudy = 3,
        Act4GribboLab = 4
    }

    public sealed class ActFlowController : MonoBehaviour
    {
        private const string StrategyPrompt = "我们怎么处理他？队友们有什么建议，怎么拿钥匙？";
        private const string DiaryTruthPrompt = "I know what the potion did to you. You are not a guard. You are an experiment. Give me the key and we will get you out.";

        private static readonly string[] BossSetupCommands =
        {
            "/flag necromancer_lab_diary_decoded true",
            "/flag act3_diary_decoded true",
            "/flag act3_gribbo_potion_truth_known true",
            "/flag act4_gribbo_confrontation_started true",
            "/flag act4_diary_truth_available true",
            "/flag necromancer_lab_force_truth_negotiation_success true"
        };

        [SerializeField] private ActFlowStage currentAct = ActFlowStage.Act1SafeRoom;
        [SerializeField] private BackendClient backendClient;
        [SerializeField] private BackendDebugPanel debugPanel;
        [SerializeField] private BarkPanel barkPanel;
        [SerializeField] private TrapZone trapZone;
        [SerializeField] private BossEncounterMarker bossEncounter;
        [SerializeField] private BossEncounterZone bossZone;
        [SerializeField] private KeyPickupFeedback keyFeedback;
        [SerializeField] private Transform player;
        [SerializeField] private Transform secretStudyRoot;
        [SerializeField] private Transform gribboLabRoot;
        [SerializeField] private ObjectiveMarker blueDoorObjectiveMarker;
        [SerializeField] private ObjectiveMarker trapObjectiveMarker;
        [SerializeField] private ObjectiveMarker studyObjectiveMarker;
        [SerializeField] private ObjectiveMarker gribboObjectiveMarker;
        [SerializeField] private Vector3 safeRoomAnchor = new Vector3(0f, 1f, -3.55f);
        [SerializeField] private Vector3 poisonCorridorAnchor = new Vector3(0.3f, 1f, 0.35f);
        [SerializeField] private Vector3 secretStudyAnchor = new Vector3(-3.75f, 1f, 0.85f);
        [SerializeField] private Vector3 gribboLabAnchor = new Vector3(-0.65f, 1f, 2.85f);

        private bool chemicalNotesRead;
        private bool diaryTruthKnown;
        private bool keyObtained;
        private bool requestInFlight;
        private bool act3AdvanceStarted;
        private TrapZone subscribedTrapZone;

        public ActFlowStage CurrentAct => currentAct;
        public string CurrentActTitle => GetActTitle(currentAct);
        public string CurrentObjective => GetObjective(currentAct);
        public string CurrentControlHint => GetControlHint(currentAct);
        public bool ChemicalNotesRead => chemicalNotesRead;
        public bool DiaryTruthKnown => diaryTruthKnown;
        public bool KeyObtained => keyObtained;
        public bool RequestInFlight => requestInFlight;

        public void Configure(
            BackendClient client,
            BackendDebugPanel panel,
            BarkPanel bark,
            TrapZone trap,
            BossEncounterMarker bossMarker,
            BossEncounterZone bossEncounterZone,
            KeyPickupFeedback feedback,
            Transform playerTransform,
            Transform studyRoot,
            Transform labRoot,
            ObjectiveMarker blueDoorMarker,
            ObjectiveMarker trapMarker,
            ObjectiveMarker studyMarker,
            ObjectiveMarker gribboMarker)
        {
            backendClient = client;
            debugPanel = panel;
            barkPanel = bark;
            BindTrapZone(trap);
            bossEncounter = bossMarker;
            bossZone = bossEncounterZone;
            keyFeedback = feedback;
            player = playerTransform;
            secretStudyRoot = studyRoot;
            gribboLabRoot = labRoot;
            blueDoorObjectiveMarker = blueDoorMarker;
            trapObjectiveMarker = trapMarker;
            studyObjectiveMarker = studyMarker;
            gribboObjectiveMarker = gribboMarker;
            debugPanel?.AttachActFlow(this);
            ApplyPresentation();
        }

        public void AttachDebugPanel(BackendDebugPanel panel, BarkPanel bark)
        {
            debugPanel = panel;
            if (bark != null)
            {
                barkPanel = bark;
            }

            debugPanel?.AttachActFlow(this);
            RefreshDebugUi();
        }

        public void HandleTrigger(ActFlowStage targetAct)
        {
            if (targetAct == ActFlowStage.Act2PoisonCorridor && currentAct == ActFlowStage.Act1SafeRoom && !requestInFlight)
            {
                StartCoroutine(AdvanceToAct2FromCorridorTrigger());
            }
        }

        public void RequestTrapDisarm()
        {
            if (currentAct != ActFlowStage.Act2PoisonCorridor)
            {
                debugPanel?.ShowActOutput("Act Flow", "Trap disarm is only part of Act2 Poison Corridor.");
                return;
            }

            trapZone?.AskAstarionToDisarm();
        }

        public void ReadChemicalNotes()
        {
            if (!CanUseAct3ReadButtons())
            {
                debugPanel?.ShowActOutput("Act3 Secret Study", "Chemical notes are available after the Act2 route unlock.");
                return;
            }

            if (backendClient == null)
            {
                debugPanel?.ShowActOutput("Read Chemical Notes", "Error: BackendClient missing.");
                return;
            }

            StartCoroutine(RunAct3Read(
                "Read Chemical Notes",
                CreateReadPayload("Read chemical_notes.", "chemical_notes", new ClientPlayerPositionDto(15, 4)),
                response =>
                {
                    chemicalNotesRead = chemicalNotesRead || TryResolveChemicalContext(response);
                    barkPanel?.ShowResponses(response);
                    debugPanel?.ShowActOutput(
                        "Read Chemical Notes",
                        BuildActResponseSummary("Read Chemical Notes", response, chemicalNotesRead ? "Diary context confirmed." : "Diary context not confirmed."));
                    RefreshDebugUi();
                }));
        }

        public void ReadNecromancerDiary()
        {
            if (!CanUseAct3ReadButtons())
            {
                debugPanel?.ShowActOutput("Act3 Secret Study", "The diary is available after the Act2 route unlock.");
                return;
            }

            if (backendClient == null)
            {
                debugPanel?.ShowActOutput("Read Necromancer Diary", "Error: BackendClient missing.");
                return;
            }

            StartCoroutine(RunAct3Read(
                "Read Necromancer Diary",
                CreateReadPayload("Read necromancer_diary with Arcana.", "necromancer_diary", new ClientPlayerPositionDto(15, 3)),
                response =>
                {
                    diaryTruthKnown = diaryTruthKnown || TryResolveDiaryTruth(response);
                    barkPanel?.ShowResponses(response);
                    debugPanel?.ShowActOutput(
                        "Read Necromancer Diary",
                        BuildActResponseSummary("Read Necromancer Diary", response, diaryTruthKnown ? "Diary truth confirmed. Advancing to Act4." : "Diary truth not confirmed. Read Chemical Notes, then try the diary again."));

                    if (diaryTruthKnown)
                    {
                        SetAct(ActFlowStage.Act4GribboLab);
                    }

                    RefreshDebugUi();
                }));
        }

        public void AskPartyStrategy()
        {
            if (currentAct != ActFlowStage.Act4GribboLab)
            {
                debugPanel?.ShowActOutput("Act4 Gribbo Lab", "Ask Party Strategy is available in Act4.");
                return;
            }

            if (backendClient == null)
            {
                debugPanel?.ShowActOutput("Ask Party Strategy", "Error: BackendClient missing.");
                return;
            }

            var payload = CreateBossPayload(StrategyPrompt, "boss_strategy_button", null);
            StartCoroutine(RunBossRequest(
                "Ask Party Strategy",
                payload,
                response =>
                {
                    ApplyBossReady();
                    var strategyLines = BackendDebugPanel.BuildStrategyLines(response);
                    if (strategyLines.Length > 0)
                    {
                        barkPanel?.ShowLines("Party Strategy", strategyLines);
                    }
                    else
                    {
                        barkPanel?.ShowResponses(response);
                    }

                    debugPanel?.ShowActOutput("Ask Party Strategy", BuildActResponseSummary("Ask Party Strategy", response, "Three-party bark queue requested."));
                    Debug.Log("BG3 act flow boss strategy response received.");
                }));
        }

        public void UseDiaryTruth()
        {
            if (currentAct != ActFlowStage.Act4GribboLab)
            {
                debugPanel?.ShowActOutput("Act4 Gribbo Lab", "Use Diary Truth is available in Act4.");
                return;
            }

            if (backendClient == null)
            {
                debugPanel?.ShowActOutput("Use Diary Truth", "Error: BackendClient missing.");
                return;
            }

            var payload = CreateBossPayload(DiaryTruthPrompt, "boss_diary_truth", null);
            StartCoroutine(RunBossRequest(
                "Use Diary Truth",
                payload,
                response =>
                {
                    ApplyBossReady();
                    if (BackendDebugPanel.TryResolveKeyObtained(response))
                    {
                        ApplyKeyObtained();
                    }

                    barkPanel?.ShowResponses(response);
                    debugPanel?.ShowActOutput("Use Diary Truth", BuildActResponseSummary("Use Diary Truth", response, keyObtained ? "Heavy Iron Key obtained." : "Key not confirmed by backend."));
                    Debug.Log($"BG3 act flow diary truth response received: keyObtained={keyObtained}");
                }));
        }

        public void PrepareBossContextDebugOnly()
        {
            if (requestInFlight)
            {
                return;
            }

            StartCoroutine(SetupBossContextDebugOnly());
        }

        private void Awake()
        {
            ResolveReferences();
        }

        private void Start()
        {
            ResolveReferences();
            MovePartyTo(safeRoomAnchor, Vector3.forward);
            ApplyPresentation();
            RefreshDebugUi();
            ShowActTransitionFeedback();
            barkPanel?.ShowMessage("Narrator", "The safe room is clear. Move to the blue door.");
        }

        private void Update()
        {
            TryStartAct3AdvanceAfterTrapDisabled();
        }

        private void OnDestroy()
        {
            if (subscribedTrapZone != null)
            {
                subscribedTrapZone.TrapStateChanged -= OnTrapStateChanged;
            }
        }

        private System.Collections.IEnumerator AdvanceToAct2FromCorridorTrigger()
        {
            SetRequestInFlight(true);
            debugPanel?.ShowActOutput("Act1 -> Act2", "Opening door_a_to_b through /api/chat before entering the poison corridor.");

            if (backendClient != null)
            {
                yield return backendClient.PostChat(
                    CreateAct1DoorPayload(),
                    response =>
                    {
                        barkPanel?.ShowResponses(response);
                        debugPanel?.ShowActOutput("Act1 -> Act2", BuildActResponseSummary("Open Corridor Door", response, "door_a_to_b interaction sent."));
                    },
                    error =>
                    {
                        debugPanel?.ShowActOutput("Act1 -> Act2", $"door_a_to_b backend action failed.\n{error}");
                        barkPanel?.ShowError(error);
                    });
            }

            SetAct(ActFlowStage.Act2PoisonCorridor);
            SetRequestInFlight(false);
        }

        private System.Collections.IEnumerator AdvanceToAct3AfterTrapDisarm()
        {
            SetRequestInFlight(true);
            debugPanel?.ShowActOutput("Act2 -> Act3", "Trap disabled. Inspecting the blocked lab route, then revealing the secret study path.");

            yield return PostActFlowChat(
                "Inspect Lab Door",
                CreateRouteUnlockPayload(),
                "door_b_to_d inspected; secret study route hint requested.");

            yield return PostActFlowChat(
                "Find Secret Study",
                CreateSecretStudyEntryPayload(),
                "Secret study entry requested.");

            SetAct(ActFlowStage.Act3SecretStudy);
            SetRequestInFlight(false);
        }

        private System.Collections.IEnumerator RunAct3Read(string label, ApiChatRequest payload, Action<ApiChatResponse> onSuccess)
        {
            if (requestInFlight)
            {
                yield break;
            }

            SetRequestInFlight(true);
            debugPanel?.ShowActOutput(label, "Sending Act3 READ request to /api/chat...");

            if (backendClient == null)
            {
                debugPanel?.ShowActOutput(label, "Error: BackendClient missing.");
                SetRequestInFlight(false);
                yield break;
            }

            yield return backendClient.PostChat(
                payload,
                response => onSuccess?.Invoke(response),
                error =>
                {
                    debugPanel?.ShowActOutput(label, $"Error: {error}");
                    barkPanel?.ShowError(error);
                });

            SetRequestInFlight(false);
        }

        private System.Collections.IEnumerator RunBossRequest(string label, ApiChatRequest payload, Action<ApiChatResponse> onSuccess)
        {
            if (requestInFlight)
            {
                yield break;
            }

            SetRequestInFlight(true);
            debugPanel?.ShowActOutput(label, "Sending Act4 boss request to /api/chat...");
            Debug.Log($"BG3 act flow boss request sent: {label} target={payload.target} source={payload.source}");

            if (backendClient == null)
            {
                debugPanel?.ShowActOutput(label, "Error: BackendClient missing.");
                SetRequestInFlight(false);
                yield break;
            }

            yield return backendClient.PostChat(
                payload,
                response => onSuccess?.Invoke(response),
                error =>
                {
                    debugPanel?.ShowActOutput(label, $"Error: {error}");
                    barkPanel?.ShowError(error);
                    Debug.LogWarning($"BG3 act flow boss request failed: {label}: {error}");
                });

            SetRequestInFlight(false);
        }

        private System.Collections.IEnumerator SetupBossContextDebugOnly()
        {
            SetRequestInFlight(true);
            debugPanel?.ShowActOutput("Prepare Boss Context (Debug)", "Debug-only setup for Unity spike: seeding Act4 truth flags through /api/chat commands.");

            if (backendClient == null)
            {
                debugPanel?.ShowActOutput("Prepare Boss Context (Debug)", "Error: BackendClient missing.");
                SetRequestInFlight(false);
                yield break;
            }

            ApiChatResponse lastResponse = null;
            string lastError = null;
            for (var i = 0; i < BossSetupCommands.Length; i++)
            {
                var command = BossSetupCommands[i];
                var payload = new ApiChatRequest(backendClient.SessionId, backendClient.MapId, command, "unity_boss_setup_debug_only");
                yield return backendClient.PostChat(
                    payload,
                    response =>
                    {
                        lastResponse = response;
                        lastError = null;
                    },
                    error => lastError = error);

                if (!string.IsNullOrEmpty(lastError))
                {
                    debugPanel?.ShowActOutput("Prepare Boss Context (Debug)", $"Failed on `{command}`\n{lastError}");
                    barkPanel?.ShowError(lastError);
                    SetRequestInFlight(false);
                    yield break;
                }
            }

            diaryTruthKnown = true;
            SetAct(ActFlowStage.Act4GribboLab);
            ApplyBossReady();
            debugPanel?.ShowActOutput("Prepare Boss Context (Debug)", BuildActResponseSummary("Prepare Boss Context (Debug)", lastResponse, "Debug-only setup complete. This is not the natural Act1-Act3 route."));
            barkPanel?.ShowMessage("Boss Context", "Debug-only setup complete. Ask the party for strategy.");
            Debug.Log("BG3 act flow debug-only boss context setup completed.");
            SetRequestInFlight(false);
        }

        private System.Collections.IEnumerator PostActFlowChat(string label, ApiChatRequest payload, string headline)
        {
            if (backendClient == null)
            {
                debugPanel?.ShowActOutput(label, "Error: BackendClient missing.");
                yield break;
            }

            yield return backendClient.PostChat(
                payload,
                response =>
                {
                    barkPanel?.ShowResponses(response);
                    debugPanel?.ShowActOutput(label, BuildActResponseSummary(label, response, headline));
                },
                error =>
                {
                    debugPanel?.ShowActOutput(label, $"Error: {error}");
                    barkPanel?.ShowError(error);
                });
        }

        private void SetAct(ActFlowStage nextAct)
        {
            if (currentAct == nextAct)
            {
                ApplyPresentation();
                RefreshDebugUi();
                return;
            }

            currentAct = nextAct;
            ApplyPresentation();
            RefreshDebugUi();
            ShowActTransitionFeedback();
            Debug.Log($"BG3 act flow advanced: {currentAct}");
        }

        private void ApplyPresentation()
        {
            ResolveReferences();

            if (secretStudyRoot != null)
            {
                secretStudyRoot.gameObject.SetActive(currentAct >= ActFlowStage.Act3SecretStudy);
            }

            if (gribboLabRoot != null)
            {
                gribboLabRoot.gameObject.SetActive(currentAct >= ActFlowStage.Act4GribboLab);
            }

            if (bossEncounter != null)
            {
                bossEncounter.gameObject.SetActive(currentAct >= ActFlowStage.Act4GribboLab);
            }

            if (bossZone != null)
            {
                bossZone.enabled = currentAct >= ActFlowStage.Act4GribboLab;
            }

            if (trapZone != null)
            {
                trapZone.enabled = currentAct == ActFlowStage.Act2PoisonCorridor;
            }

            SetMarkerActive(blueDoorObjectiveMarker, currentAct == ActFlowStage.Act1SafeRoom);
            SetMarkerActive(
                trapObjectiveMarker,
                currentAct == ActFlowStage.Act2PoisonCorridor
                && (trapZone == null || trapZone.State != TrapVisualState.Disabled));
            SetMarkerActive(studyObjectiveMarker, currentAct == ActFlowStage.Act3SecretStudy);
            SetMarkerActive(gribboObjectiveMarker, currentAct == ActFlowStage.Act4GribboLab && !keyObtained);

            if (currentAct == ActFlowStage.Act2PoisonCorridor)
            {
                MovePartyTo(poisonCorridorAnchor, new Vector3(0.82f, 0f, 0.58f));
            }
            else if (currentAct == ActFlowStage.Act3SecretStudy)
            {
                MovePartyTo(secretStudyAnchor, Vector3.forward);
            }

            if (currentAct == ActFlowStage.Act4GribboLab)
            {
                MovePartyTo(gribboLabAnchor, Vector3.forward);
                ApplyBossReady();
            }

            FrameCurrentAct(true);
        }

        private void MovePartyTo(Vector3 playerPosition, Vector3 forward)
        {
            ResolveReferences();
            SetActorPosition(player, playerPosition, forward);
            SetActorPosition(FindActor("Astarion"), playerPosition + new Vector3(-0.82f, 0f, -0.82f), forward);
            SetActorPosition(FindActor("Shadowheart"), playerPosition + new Vector3(0.82f, 0f, -0.92f), forward);
            SetActorPosition(FindActor("Lae'zel"), playerPosition + new Vector3(0f, 0f, -1.48f), forward);
        }

        private static void SetActorPosition(Transform actor, Vector3 position, Vector3 forward)
        {
            if (actor == null)
            {
                return;
            }

            actor.position = position;
            if (forward.sqrMagnitude > 0.001f)
            {
                actor.rotation = Quaternion.LookRotation(forward.normalized, Vector3.up);
            }
        }

        private static Transform FindActor(string actorName)
        {
            var actorObject = GameObject.Find(actorName);
            return actorObject == null ? null : actorObject.transform;
        }

        private void ApplyBossReady()
        {
            bossEncounter?.SetBossReady(true);
            debugPanel?.ApplyActBossReady();
            RefreshDebugUi();
        }

        private void ApplyKeyObtained()
        {
            keyObtained = true;
            bossEncounter?.SetKeyObtained(true);
            SetMarkerActive(gribboObjectiveMarker, false);
            if (debugPanel != null)
            {
                debugPanel.ApplyActKeyObtained();
            }
            else
            {
                keyFeedback?.ShowKeyObtained();
            }

            RefreshDebugUi();
        }

        private void SetRequestInFlight(bool inFlight)
        {
            requestInFlight = inFlight;
            RefreshDebugUi();
        }

        private bool CanUseAct3ReadButtons()
        {
            return currentAct == ActFlowStage.Act3SecretStudy && !requestInFlight;
        }

        private ApiChatRequest CreateAct1DoorPayload()
        {
            return new ApiChatRequest(backendClient.SessionId, backendClient.MapId, "Open the door to the poison corridor.", "unity_act1_corridor_trigger")
            {
                intent = "INTERACT",
                target = "door_a_to_b",
                client_player_position = new ClientPlayerPositionDto(2, 2)
            };
        }

        private ApiChatRequest CreateRouteUnlockPayload()
        {
            return new ApiChatRequest(backendClient.SessionId, backendClient.MapId, "Inspect door_b_to_d; do not lockpick.", "unity_act2_route_unlock")
            {
                intent = "INTERACT",
                target = "door_b_to_d",
                client_player_position = new ClientPlayerPositionDto(5, 8)
            };
        }

        private ApiChatRequest CreateSecretStudyEntryPayload()
        {
            return new ApiChatRequest(backendClient.SessionId, backendClient.MapId, "Search the cracked_wall for the secret study.", "unity_act3_secret_study_entry")
            {
                intent = "INTERACT",
                target = "cracked_wall",
                client_player_position = new ClientPlayerPositionDto(8, 7)
            };
        }

        private ApiChatRequest CreateReadPayload(string userInput, string target, ClientPlayerPositionDto position)
        {
            return new ApiChatRequest(backendClient.SessionId, backendClient.MapId, userInput, "act3_study_context")
            {
                intent = "READ",
                target = target,
                client_player_position = position
            };
        }

        private ApiChatRequest CreateBossPayload(string userInput, string source, string intent)
        {
            return new ApiChatRequest(backendClient.SessionId, backendClient.MapId, userInput, source)
            {
                intent = intent,
                target = "gribbo",
                client_player_position = new ClientPlayerPositionDto(4, 9)
            };
        }

        private void ResolveReferences()
        {
            if (backendClient == null)
            {
                backendClient = UnityEngine.Object.FindAnyObjectByType<BackendClient>();
            }

            if (debugPanel == null)
            {
                debugPanel = UnityEngine.Object.FindAnyObjectByType<BackendDebugPanel>();
                debugPanel?.AttachActFlow(this);
            }

            if (barkPanel == null)
            {
                barkPanel = UnityEngine.Object.FindAnyObjectByType<BarkPanel>();
            }

            if (trapZone == null)
            {
                BindTrapZone(UnityEngine.Object.FindAnyObjectByType<TrapZone>());
            }
            else
            {
                BindTrapZone(trapZone);
            }

            if (bossEncounter == null)
            {
                bossEncounter = UnityEngine.Object.FindAnyObjectByType<BossEncounterMarker>();
            }

            if (bossZone == null)
            {
                bossZone = UnityEngine.Object.FindAnyObjectByType<BossEncounterZone>();
            }

            if (keyFeedback == null)
            {
                keyFeedback = UnityEngine.Object.FindAnyObjectByType<KeyPickupFeedback>();
            }

            if (player == null)
            {
                var playerObject = GameObject.Find("Player");
                player = playerObject == null ? null : playerObject.transform;
            }

            if (blueDoorObjectiveMarker == null)
            {
                blueDoorObjectiveMarker = ResolveMarker("BlueDoorObjectiveMarker");
            }

            if (trapObjectiveMarker == null)
            {
                trapObjectiveMarker = ResolveMarker("TrapObjectiveMarker");
            }

            if (studyObjectiveMarker == null)
            {
                studyObjectiveMarker = ResolveMarker("StudyObjectiveMarker");
            }

            if (gribboObjectiveMarker == null)
            {
                gribboObjectiveMarker = ResolveMarker("GribboObjectiveMarker");
            }
        }

        private void RefreshDebugUi()
        {
            var huds = UnityEngine.Object.FindObjectsByType<ActObjectiveHud>(FindObjectsSortMode.None);
            for (var i = 0; i < huds.Length; i++)
            {
                huds[i].SetAct(CurrentActTitle, CurrentObjective);
                huds[i].SetProgress((int)currentAct);
                huds[i].SetControlHint(CurrentControlHint);
            }

            debugPanel?.AttachActFlow(this);
        }

        private void BindTrapZone(TrapZone zone)
        {
            if (subscribedTrapZone == zone)
            {
                trapZone = zone;
                return;
            }

            if (subscribedTrapZone != null)
            {
                subscribedTrapZone.TrapStateChanged -= OnTrapStateChanged;
            }

            trapZone = zone;
            subscribedTrapZone = zone;

            if (subscribedTrapZone != null)
            {
                subscribedTrapZone.TrapStateChanged += OnTrapStateChanged;
            }
        }

        private void OnTrapStateChanged(TrapVisualState state)
        {
            if (state == TrapVisualState.Disabled)
            {
                TryStartAct3AdvanceAfterTrapDisabled();
                return;
            }

            RefreshDebugUi();
        }

        private void TryStartAct3AdvanceAfterTrapDisabled()
        {
            if (currentAct != ActFlowStage.Act2PoisonCorridor || act3AdvanceStarted || trapZone == null || trapZone.State != TrapVisualState.Disabled)
            {
                return;
            }

            act3AdvanceStarted = true;
            Debug.Log("BG3 act flow trap disabled observed; advancing to Act3.");
            StartCoroutine(AdvanceToAct3AfterTrapDisarm());
        }

        private void ShowActTransitionFeedback()
        {
            debugPanel?.ShowActToast(CurrentActTitle);
        }

        private void FrameCurrentAct(bool snap)
        {
            var camera = Camera.main;
            if (camera == null)
            {
                return;
            }

            var follow = camera.GetComponent<TopDownCameraFollow>();
            if (follow == null)
            {
                return;
            }

            switch (currentAct)
            {
                case ActFlowStage.Act1SafeRoom:
                    follow.SetFraming(new Vector3(0f, 10.2f, -8.8f), new Vector3(0f, 0.8f, 2.65f), 50f);
                    break;
                case ActFlowStage.Act2PoisonCorridor:
                    follow.SetFraming(new Vector3(0f, 9.2f, -7.2f), new Vector3(1.2f, 0.8f, 1.15f), 49f);
                    break;
                case ActFlowStage.Act3SecretStudy:
                    follow.SetFraming(new Vector3(0f, 8.7f, -6.8f), new Vector3(-0.25f, 0.8f, 0.45f), 48f);
                    break;
                case ActFlowStage.Act4GribboLab:
                    follow.SetFraming(new Vector3(0f, 9.2f, -7.2f), new Vector3(-1.35f, 0.8f, 0.7f), 48f);
                    break;
            }

            if (snap)
            {
                follow.SnapToTarget();
            }
        }

        private static void SetMarkerActive(ObjectiveMarker marker, bool active)
        {
            if (marker != null)
            {
                marker.gameObject.SetActive(active);
            }
        }

        private static ObjectiveMarker ResolveMarker(string objectName)
        {
            var markerObject = GameObject.Find(objectName);
            return markerObject == null ? null : markerObject.GetComponent<ObjectiveMarker>();
        }

        private static string GetActTitle(ActFlowStage act)
        {
            switch (act)
            {
                case ActFlowStage.Act1SafeRoom:
                    return "Act 1 — Safe Room";
                case ActFlowStage.Act2PoisonCorridor:
                    return "Act 2 — Poison Corridor";
                case ActFlowStage.Act3SecretStudy:
                    return "Act 3 — Secret Study";
                case ActFlowStage.Act4GribboLab:
                    return "Act 4 — Gribbo Lab";
                default:
                    return "Act Flow";
            }
        }

        private string GetObjective(ActFlowStage act)
        {
            switch (act)
            {
                case ActFlowStage.Act1SafeRoom:
                    return "Move to the blue door to enter the poison corridor.";
                case ActFlowStage.Act2PoisonCorridor:
                    if (trapZone != null && trapZone.State == TrapVisualState.Disabled)
                    {
                        return "Trap disabled. Follow the revealed route into the secret study.";
                    }

                    if (trapZone != null && trapZone.State == TrapVisualState.Revealed)
                    {
                        return "Astarion spotted the trap. Ask him to disarm it.";
                    }

                    return "Approach the amber trap marker.";
                case ActFlowStage.Act3SecretStudy:
                    if (!chemicalNotesRead)
                    {
                        return "Read Chemical Notes, then Read Necromancer Diary.";
                    }

                    return diaryTruthKnown ? "Diary truth confirmed. Move into Gribbo Lab." : "Read Necromancer Diary to learn Gribbo's truth.";
                case ActFlowStage.Act4GribboLab:
                    return keyObtained ? "Heavy Iron Key obtained." : "Ask Party Strategy, then Use Diary Truth.";
                default:
                    return string.Empty;
            }
        }

        private string GetControlHint(ActFlowStage act)
        {
            switch (act)
            {
                case ActFlowStage.Act1SafeRoom:
                    return "WASD: move to the blue door trigger.";
                case ActFlowStage.Act2PoisonCorridor:
                    if (trapZone != null && trapZone.State == TrapVisualState.Disabled)
                    {
                        return "Trap disabled. Act 3 opens automatically.";
                    }

                    if (trapZone != null && trapZone.State == TrapVisualState.Revealed)
                    {
                        return "Press 1/R or click Ask Astarion to Disarm.";
                    }

                    return "WASD: approach the amber marker to trigger perception.";
                case ActFlowStage.Act3SecretStudy:
                    return chemicalNotesRead ? "Press 2/T or click Read Necromancer Diary." : "Press 1/R or click Read Chemical Notes.";
                case ActFlowStage.Act4GribboLab:
                    return keyObtained ? "Heavy Iron Key obtained. Demo beat complete." : "1/R Ask Party Strategy; 2/T Use Diary Truth.";
                default:
                    return "WASD move | click action buttons or use shortcuts.";
            }
        }

        private static bool TryResolveChemicalContext(ApiChatResponse response)
        {
            if (response == null)
            {
                return false;
            }

            return BackendClient.ExtractBooleanField(response.raw_json, "act3_chemical_notes_seen")
                || BackendClient.ExtractBooleanField(response.raw_json, "act3_diary_context_gathered")
                || ContainsAny(BuildHaystack(response), "[线索整合] chemical_notes -> diary_context", "diary_context");
        }

        private static bool TryResolveDiaryTruth(ApiChatResponse response)
        {
            if (response == null)
            {
                return false;
            }

            var haystack = BuildHaystack(response);
            return BackendClient.ExtractBooleanField(response.raw_json, "act3_diary_decoded")
                || BackendClient.ExtractBooleanField(response.raw_json, "necromancer_lab_diary_decoded")
                || BackendClient.ExtractBooleanField(response.raw_json, "act3_gribbo_potion_truth_known")
                || BackendClient.ExtractBooleanField(response.raw_json, "act3_party_knows_gribbo_truth")
                || ContainsAll(haystack, "gribbo", "heavy_iron_key")
                || ContainsAll(haystack, "gribbo", "potion", "truth")
                || ContainsAll(haystack, "gribbo", "毒气", "heavy_iron_key");
        }

        private static string BuildActResponseSummary(string label, ApiChatResponse response, string headline)
        {
            var builder = new StringBuilder();
            builder.AppendLine(label);
            if (!string.IsNullOrEmpty(headline))
            {
                builder.AppendLine(headline);
            }

            if (response == null)
            {
                builder.AppendLine("No backend response.");
                return builder.ToString();
            }

            if (!string.IsNullOrEmpty(response.FirstResponseText))
            {
                var speaker = string.IsNullOrEmpty(response.FirstResponseSpeaker) ? "Backend" : response.FirstResponseSpeaker;
                builder.AppendLine($"{speaker}: {response.FirstResponseText}");
            }

            if (response.journal_events != null)
            {
                var limit = Mathf.Min(5, response.journal_events.Length);
                builder.AppendLine($"Journal events: {response.JournalEventCount}");
                for (var i = 0; i < limit; i++)
                {
                    if (!string.IsNullOrEmpty(response.journal_events[i]))
                    {
                        builder.AppendLine($"- {response.journal_events[i]}");
                    }
                }
            }

            if (BackendDebugPanel.TryResolveKeyObtained(response))
            {
                builder.AppendLine("Key: Heavy Iron Key Obtained");
            }

            return builder.ToString();
        }

        private static string BuildHaystack(ApiChatResponse response)
        {
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
            if (string.IsNullOrEmpty(value))
            {
                return false;
            }

            var normalized = value.ToLowerInvariant();
            for (var i = 0; i < markers.Length; i++)
            {
                var marker = markers[i];
                if (!string.IsNullOrEmpty(marker) && normalized.Contains(marker.ToLowerInvariant()))
                {
                    return true;
                }
            }

            return false;
        }

        private static bool ContainsAll(string value, params string[] markers)
        {
            if (string.IsNullOrEmpty(value))
            {
                return false;
            }

            var normalized = value.ToLowerInvariant();
            for (var i = 0; i < markers.Length; i++)
            {
                var marker = markers[i];
                if (!string.IsNullOrEmpty(marker) && !normalized.Contains(marker.ToLowerInvariant()))
                {
                    return false;
                }
            }

            return true;
        }
    }
}
