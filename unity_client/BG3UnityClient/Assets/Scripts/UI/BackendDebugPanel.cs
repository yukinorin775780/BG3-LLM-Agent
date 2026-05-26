using System;
using System.Text;
using BG3UnityClient.Api;
using BG3UnityClient.Gameplay;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

namespace BG3UnityClient.UI
{
    public sealed class BackendDebugPanel : MonoBehaviour
    {
        private const string DefaultPrompt = "Is something wrong in the corridor?";
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

        [SerializeField] private BackendClient backendClient;
        [SerializeField] private Text statusText;
        [SerializeField] private InputField inputField;
        [SerializeField] private Button sendButton;
        [SerializeField] private Button disarmButton;
        [SerializeField] private Button triggerTrapButton;
        [SerializeField] private Button readChemicalNotesButton;
        [SerializeField] private Button readDiaryButton;
        [SerializeField] private Button setupBossButton;
        [SerializeField] private Button askStrategyButton;
        [SerializeField] private Button useDiaryTruthButton;
        [SerializeField] private Button outputToggleButton;
        [SerializeField] private Text outputText;
        [SerializeField] private Text outputPreviewText;
        [SerializeField] private RectTransform debugPanelRoot;
        [SerializeField] private RectTransform outputContainer;
        [SerializeField] private BarkPanel barkPanel;
        [SerializeField] private ActObjectiveHud actHud;
        [SerializeField] private TrapZone trapZone;
        [SerializeField] private ActFlowController actFlow;
        [SerializeField] private BossEncounterMarker bossEncounter;
        [SerializeField] private BossEncounterZone bossZone;
        [SerializeField] private KeyPickupFeedback keyFeedback;

        private string connectionStatusLine = "Connecting...";
        private string sessionStatusLine = "session=(unknown)";
        private TrapVisualState trapState = TrapVisualState.Hidden;
        private bool bossReady;
        private bool keyObtained;
        private bool bossRequestInFlight;
        private bool outputExpanded;

        private void Awake()
        {
            EnsureGameplayShell();

            if (backendClient == null)
            {
                backendClient = UnityEngine.Object.FindAnyObjectByType<BackendClient>();
            }

            if (sendButton != null)
            {
                sendButton.onClick.AddListener(OnSendClicked);
            }

            if (statusText == null || inputField == null || sendButton == null || outputText == null)
            {
                CreateRuntimeUi();
            }

            if (barkPanel == null)
            {
                barkPanel = UnityEngine.Object.FindAnyObjectByType<BarkPanel>();
            }

            if (actHud == null)
            {
                actHud = UnityEngine.Object.FindAnyObjectByType<ActObjectiveHud>();
            }

            if (trapZone == null)
            {
                trapZone = UnityEngine.Object.FindAnyObjectByType<TrapZone>();
                trapZone?.AttachDebugPanel(this);
                trapZone?.AttachBarkPanel(barkPanel);
            }

            if (bossEncounter == null)
            {
                bossEncounter = UnityEngine.Object.FindAnyObjectByType<BossEncounterMarker>();
                SyncBossStateFromMarker();
            }

            if (bossZone == null)
            {
                bossZone = UnityEngine.Object.FindAnyObjectByType<BossEncounterZone>();
                bossZone?.AttachDebugPanel(this);
            }

            if (keyFeedback == null)
            {
                keyFeedback = UnityEngine.Object.FindAnyObjectByType<KeyPickupFeedback>();
            }

            if (actFlow == null)
            {
                actFlow = UnityEngine.Object.FindAnyObjectByType<ActFlowController>();
            }

            actFlow?.AttachDebugPanel(this, barkPanel);
        }

        private static void EnsureGameplayShell()
        {
            SceneBootstrap.EnsureShellExists();
        }

        private void Start()
        {
            if (inputField != null && string.IsNullOrWhiteSpace(inputField.text))
            {
                inputField.text = DefaultPrompt;
            }

            SetConnectionStatus($"Connecting: {backendClient?.MapId ?? "(unknown)"}", $"session={backendClient?.SessionId ?? "(unknown)"}");
            RefreshActFlowUi();
            SetOutput("Ready.");

            if (backendClient != null)
            {
                StartCoroutine(backendClient.GetState(OnStateLoaded, OnStateError));
            }
            else
            {
                SetConnectionStatus("BackendClient missing.", sessionStatusLine);
                SetOutput("Error: BackendClient missing.");
            }
        }

        private void OnDestroy()
        {
            if (sendButton != null)
            {
                sendButton.onClick.RemoveListener(OnSendClicked);
            }

            if (disarmButton != null)
            {
                disarmButton.onClick.RemoveListener(OnDisarmClicked);
            }

            if (triggerTrapButton != null)
            {
                triggerTrapButton.onClick.RemoveListener(OnTriggerTrapClicked);
            }

            if (readChemicalNotesButton != null)
            {
                readChemicalNotesButton.onClick.RemoveListener(OnReadChemicalNotesClicked);
            }

            if (readDiaryButton != null)
            {
                readDiaryButton.onClick.RemoveListener(OnReadDiaryClicked);
            }

            if (setupBossButton != null)
            {
                setupBossButton.onClick.RemoveListener(OnSetupBossContextClicked);
            }

            if (askStrategyButton != null)
            {
                askStrategyButton.onClick.RemoveListener(OnAskStrategyClicked);
            }

            if (useDiaryTruthButton != null)
            {
                useDiaryTruthButton.onClick.RemoveListener(OnUseDiaryTruthClicked);
            }

            if (outputToggleButton != null)
            {
                outputToggleButton.onClick.RemoveListener(OnToggleOutputClicked);
            }
        }

        private void OnSendClicked()
        {
            if (backendClient == null)
            {
                SetOutput("Error: BackendClient missing.");
                return;
            }

            var userInput = inputField == null ? string.Empty : inputField.text;
            if (EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(null);
            }

            StartCoroutine(SendChat(userInput));
        }

        private System.Collections.IEnumerator SendChat(string userInput)
        {
            SetSendEnabled(false);
            SetOutput($"Sending...\n\n> {userInput}");

            yield return backendClient.PostChat(
                userInput,
                response =>
                {
                    trapZone?.HandleExternalChatResponse(response, userInput);
                    SetOutput(BuildChatSummary(userInput, response));
                    barkPanel?.ShowResponses(response);
                },
                error =>
                {
                    SetOutput($"Error: {error}");
                    barkPanel?.ShowError(error);
                });

            SetSendEnabled(true);
        }

        private void OnStateLoaded(ApiStateResponse response)
        {
            var state = response.ResolvedState;
            var resolvedMapId = FirstNonEmpty(state?.map_data?.id, response.map_id, backendClient.MapId, "(unknown)");
            var resolvedSessionId = FirstNonEmpty(response.session_id, backendClient.SessionId, "(unknown)");
            SetConnectionStatus($"Connected: {resolvedMapId}", $"session={resolvedSessionId}");
        }

        private void OnStateError(string error)
        {
            SetConnectionStatus($"Connection failed: {error}", sessionStatusLine);
        }

        private string BuildChatSummary(string userInput, ApiChatResponse response)
        {
            var builder = new StringBuilder();
            builder.AppendLine($"> {userInput}");
            builder.AppendLine();

            var speaker = FirstNonEmpty(response.FirstResponseSpeaker, "backend");
            var text = response.FirstResponseText;
            if (!string.IsNullOrEmpty(text))
            {
                builder.AppendLine($"{speaker}: {text}");
            }
            else
            {
                builder.AppendLine("No response text returned.");
            }

            var location = response.ResolvedCurrentLocation;
            if (!string.IsNullOrEmpty(location))
            {
                builder.AppendLine($"Location: {location}");
            }

            AppendJournalSummary(builder, response);
            AppendRollSummary(builder, response.ResolvedLatestRoll);
            if (TrapZone.TryResolveTrapState(response, out var resolvedTrapState))
            {
                builder.AppendLine($"Trap: {resolvedTrapState}");
            }

            AppendBossSummary(builder, response);

            return builder.ToString();
        }

        private static void AppendJournalSummary(StringBuilder builder, ApiChatResponse response)
        {
            var count = response.JournalEventCount;
            builder.AppendLine($"Journal events: {count}");

            if (response.journal_events == null)
            {
                return;
            }

            var limit = Mathf.Min(3, response.journal_events.Length);
            for (var i = 0; i < limit; i++)
            {
                if (!string.IsNullOrEmpty(response.journal_events[i]))
                {
                    builder.AppendLine($"- {response.journal_events[i]}");
                }
            }
        }

        private static void AppendRollSummary(StringBuilder builder, ChatLatestRollDto roll)
        {
            if (roll == null || IsEmptyRoll(roll))
            {
                return;
            }

            var skill = FirstNonEmpty(roll.skill, roll.intent, "roll");
            if (roll.result != null)
            {
                builder.AppendLine($"Roll: {skill} total={roll.result.total} dc={roll.dc} success={roll.result.is_success}");
                return;
            }

            builder.AppendLine($"Roll: {skill} dc={roll.dc}");
        }

        private static bool IsEmptyRoll(ChatLatestRollDto roll)
        {
            return string.IsNullOrEmpty(roll.intent)
                && string.IsNullOrEmpty(roll.target)
                && string.IsNullOrEmpty(roll.skill)
                && roll.dc == 0
                && roll.modifier == 0
                && roll.result == null;
        }

        private void SetSendEnabled(bool enabled)
        {
            if (sendButton != null)
            {
                sendButton.interactable = enabled;
            }
        }

        public void AttachTrapZone(TrapZone zone)
        {
            trapZone = zone;
            SetTrapState(zone == null ? TrapVisualState.Hidden : zone.State);
        }

        public void SetTrapState(TrapVisualState value)
        {
            trapState = value;
            RefreshStatusText();
            RefreshTrapButtons();
            RefreshActFlowUi();
        }

        public void ShowTrapOutput(string title, string value)
        {
            SetOutput($"{title}\n\n{value}");
        }

        public void AttachActFlow(ActFlowController flow)
        {
            actFlow = flow;
            RefreshActFlowUi();
        }

        public void RefreshActFlowUi()
        {
            if (actFlow != null)
            {
                SetAct(actFlow.CurrentActTitle, actFlow.CurrentObjective);
            }
            else
            {
                SetAct("Act 1 - Safe Room", "Open the door / move toward corridor.");
            }

            RefreshTrapButtons();
            RefreshBossButtons();
            RefreshActButtons();
        }

        public void ShowActOutput(string title, string value)
        {
            SetOutput($"{title}\n\n{value}");
        }

        public void ApplyActBossReady()
        {
            ApplyBossReady();
        }

        public void ApplyActKeyObtained()
        {
            ApplyKeyObtained();
        }

        public void AttachBossZone(BossEncounterZone zone)
        {
            bossZone = zone;
            if (zone != null && zone.EncounterReady)
            {
                SetBossEncounterReady(true);
            }
            else
            {
                RefreshBossButtons();
            }
        }

        public void SetBossEncounterReady(bool ready)
        {
            if (!ready)
            {
                return;
            }

            var wasReady = bossReady;
            bossReady = true;
            if (bossEncounter == null)
            {
                bossEncounter = UnityEngine.Object.FindAnyObjectByType<BossEncounterMarker>();
            }

            bossEncounter?.SetBossReady(true);
            RefreshStatusText();
            RefreshBossButtons();

            if (!wasReady)
            {
                SetOutput("Boss Encounter Ready\n\nGribbo, the poison tank, and the final exit are in view. Prepare context if needed, then ask the party for strategy.");
                barkPanel?.ShowMessage("Boss Encounter Ready", "Gribbo is close. Ask the party how to handle him.");
                if (actFlow != null)
                {
                    RefreshActFlowUi();
                }
                else
                {
                    SetAct("Act 4 - Gribbo Lab", "Convince Gribbo to surrender the key.");
                }

                Debug.Log("BG3 boss encounter ready UI applied.");
            }
        }

        private void SetConnectionStatus(string connectionLine, string sessionLine)
        {
            connectionStatusLine = connectionLine;
            sessionStatusLine = sessionLine;
            RefreshStatusText();
        }

        private void RefreshStatusText()
        {
            if (statusText != null)
            {
                statusText.text = $"{connectionStatusLine}\n{sessionStatusLine}\nTrap: {trapState}\nBoss: {(bossReady ? "Encounter Ready" : "Approach Gribbo")}\nKey: {(keyObtained ? "Heavy Iron Key Obtained" : "Missing")}";
            }
        }

        private void SetOutput(string value)
        {
            if (outputText != null)
            {
                outputText.text = value;
            }

            if (outputPreviewText != null)
            {
                outputPreviewText.text = FirstLine(value);
            }
        }

        public void SetAct(string title, string objective)
        {
            if (actHud == null)
            {
                actHud = UnityEngine.Object.FindAnyObjectByType<ActObjectiveHud>();
            }

            actHud?.SetAct(title, objective);
        }

        private static string FirstLine(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "Ready.";
            }

            var newline = value.IndexOf('\n');
            return newline < 0 ? value : value.Substring(0, newline);
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

        private void CreateRuntimeUi()
        {
            var canvasObject = new GameObject("BackendDebugCanvas", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = canvasObject.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 10;

            var scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280f, 720f);
            scaler.matchWidthOrHeight = 0.5f;

            actHud = CreateActObjectiveHud(canvasObject.transform);

            debugPanelRoot = CreateUiObject("BackendDebugPanel", canvasObject.transform);
            SetTopLeft(debugPanelRoot, new Vector2(18f, -104f), new Vector2(318f, 336f));
            var panelImage = debugPanelRoot.gameObject.AddComponent<Image>();
            panelImage.color = new Color(0.08f, 0.09f, 0.11f, 0.92f);
            panelImage.raycastTarget = false;
            AddBorder(debugPanelRoot, new Color(0.46f, 0.56f, 0.62f, 0.36f), 1f);

            var title = CreateText("Title", debugPanelRoot, "DEV", 14, FontStyle.Bold, TextAnchor.MiddleLeft, new Color(0.78f, 0.9f, 1f, 1f));
            SetTopLeft(title.rectTransform, new Vector2(12f, -10f), new Vector2(76f, 22f));

            outputToggleButton = CreateButton("OutputToggleButton", debugPanelRoot, "Log");
            SetTopLeft(outputToggleButton.GetComponent<RectTransform>(), new Vector2(244f, -10f), new Vector2(62f, 24f));
            outputToggleButton.onClick.AddListener(OnToggleOutputClicked);

            statusText = CreateText("ConnectionStatus", debugPanelRoot, "Connecting...", 11, FontStyle.Normal, TextAnchor.UpperLeft, new Color(0.74f, 0.88f, 1f, 1f));
            statusText.horizontalOverflow = HorizontalWrapMode.Wrap;
            statusText.verticalOverflow = VerticalWrapMode.Truncate;
            SetTopLeft(statusText.rectTransform, new Vector2(12f, -38f), new Vector2(294f, 70f));

            inputField = CreateInputField("ChatInput", debugPanelRoot, DefaultPrompt);
            SetTopLeft(inputField.GetComponent<RectTransform>(), new Vector2(12f, -118f), new Vector2(232f, 31f));

            sendButton = CreateButton("SendButton", debugPanelRoot, "Send");
            SetTopLeft(sendButton.GetComponent<RectTransform>(), new Vector2(252f, -118f), new Vector2(54f, 31f));
            sendButton.onClick.AddListener(OnSendClicked);

            disarmButton = CreateButton("DisarmButton", debugPanelRoot, "Disarm");
            SetTopLeft(disarmButton.GetComponent<RectTransform>(), new Vector2(12f, -160f), new Vector2(142f, 28f));
            disarmButton.onClick.AddListener(OnDisarmClicked);

            triggerTrapButton = CreateButton("TriggerTrapButton", debugPanelRoot, "Trigger");
            SetTopLeft(triggerTrapButton.GetComponent<RectTransform>(), new Vector2(164f, -160f), new Vector2(142f, 28f));
            triggerTrapButton.onClick.AddListener(OnTriggerTrapClicked);

            readChemicalNotesButton = CreateButton("ReadChemicalNotesButton", debugPanelRoot, "Chem Notes");
            SetTopLeft(readChemicalNotesButton.GetComponent<RectTransform>(), new Vector2(12f, -194f), new Vector2(142f, 28f));
            readChemicalNotesButton.onClick.AddListener(OnReadChemicalNotesClicked);

            readDiaryButton = CreateButton("ReadDiaryButton", debugPanelRoot, "Diary");
            SetTopLeft(readDiaryButton.GetComponent<RectTransform>(), new Vector2(164f, -194f), new Vector2(142f, 28f));
            readDiaryButton.onClick.AddListener(OnReadDiaryClicked);

            setupBossButton = CreateButton("SetupBossButton", debugPanelRoot, "Prep Debug");
            SetTopLeft(setupBossButton.GetComponent<RectTransform>(), new Vector2(12f, -228f), new Vector2(142f, 28f));
            setupBossButton.onClick.AddListener(OnSetupBossContextClicked);

            askStrategyButton = CreateButton("AskStrategyButton", debugPanelRoot, "Strategy");
            SetTopLeft(askStrategyButton.GetComponent<RectTransform>(), new Vector2(164f, -228f), new Vector2(142f, 28f));
            askStrategyButton.onClick.AddListener(OnAskStrategyClicked);

            useDiaryTruthButton = CreateButton("UseDiaryTruthButton", debugPanelRoot, "Truth");
            SetTopLeft(useDiaryTruthButton.GetComponent<RectTransform>(), new Vector2(12f, -262f), new Vector2(294f, 28f));
            useDiaryTruthButton.onClick.AddListener(OnUseDiaryTruthClicked);

            outputPreviewText = CreateText("OutputPreview", debugPanelRoot, "Ready.", 11, FontStyle.Normal, TextAnchor.MiddleLeft, new Color(0.82f, 0.86f, 0.88f, 0.92f));
            outputPreviewText.horizontalOverflow = HorizontalWrapMode.Wrap;
            outputPreviewText.verticalOverflow = VerticalWrapMode.Truncate;
            SetTopLeft(outputPreviewText.rectTransform, new Vector2(12f, -301f), new Vector2(294f, 22f));

            outputContainer = CreateUiObject("OutputContainer", debugPanelRoot);
            SetTopLeft(outputContainer, new Vector2(12f, -334f), new Vector2(294f, 98f));
            var outputBackground = outputContainer.gameObject.AddComponent<Image>();
            outputBackground.color = new Color(0.015f, 0.018f, 0.022f, 0.7f);
            outputBackground.raycastTarget = false;
            AddBorder(outputContainer, new Color(0.42f, 0.48f, 0.52f, 0.32f), 1f);

            outputText = CreateText("OutputLog", outputContainer, "Ready.", 11, FontStyle.Normal, TextAnchor.UpperLeft, new Color(0.92f, 0.94f, 0.95f, 1f));
            outputText.horizontalOverflow = HorizontalWrapMode.Wrap;
            outputText.verticalOverflow = VerticalWrapMode.Truncate;
            StretchWithPadding(outputText.rectTransform, 8f, 7f);
            RefreshDebugPanelLayout();

            barkPanel = CreateBarkPanel(canvasObject.transform);
            barkPanel.ShowMessage("Narrator", "The corridor falls quiet.");

            if (EventSystem.current == null)
            {
                var eventSystemObject = new GameObject("BackendDebugEventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
                eventSystemObject.GetComponent<InputSystemUIInputModule>().AssignDefaultActions();
            }

            RefreshStatusText();
            RefreshTrapButtons();
            RefreshBossButtons();
            RefreshActButtons();
        }

        private void OnToggleOutputClicked()
        {
            outputExpanded = !outputExpanded;
            RefreshDebugPanelLayout();
            ClearSelectedUi();
        }

        private void RefreshDebugPanelLayout()
        {
            if (debugPanelRoot != null)
            {
                debugPanelRoot.sizeDelta = new Vector2(318f, outputExpanded ? 444f : 336f);
            }

            if (outputContainer != null)
            {
                outputContainer.gameObject.SetActive(outputExpanded);
            }

            if (outputPreviewText != null)
            {
                outputPreviewText.gameObject.SetActive(!outputExpanded);
            }

            SetButtonLabel(outputToggleButton, outputExpanded ? "Hide" : "Log");
        }

        private void OnDisarmClicked()
        {
            ClearSelectedUi();

            if (actFlow != null)
            {
                actFlow.RequestTrapDisarm();
                return;
            }

            trapZone?.AskAstarionToDisarm();
        }

        private void OnTriggerTrapClicked()
        {
            ClearSelectedUi();

            trapZone?.TriggerTrapDebug();
        }

        private void OnReadChemicalNotesClicked()
        {
            ClearSelectedUi();

            if (actFlow == null)
            {
                SetOutput("Read Chemical Notes\n\nError: ActFlowController missing.");
                return;
            }

            actFlow.ReadChemicalNotes();
        }

        private void OnReadDiaryClicked()
        {
            ClearSelectedUi();

            if (actFlow == null)
            {
                SetOutput("Read Necromancer Diary\n\nError: ActFlowController missing.");
                return;
            }

            actFlow.ReadNecromancerDiary();
        }

        private void OnSetupBossContextClicked()
        {
            ClearSelectedUi();
            if (actFlow != null)
            {
                actFlow.PrepareBossContextDebugOnly();
                return;
            }

            if (backendClient == null)
            {
                SetOutput("Setup Boss Context\n\nError: BackendClient missing.");
                return;
            }

            if (!bossRequestInFlight)
            {
                StartCoroutine(SetupBossContext());
            }
        }

        private void OnAskStrategyClicked()
        {
            ClearSelectedUi();
            if (actFlow != null)
            {
                actFlow.AskPartyStrategy();
                return;
            }

            if (backendClient == null)
            {
                SetOutput("Ask Party Strategy\n\nError: BackendClient missing.");
                return;
            }

            var payload = CreateBossPayload(StrategyPrompt, "boss_strategy_button", null);
            StartCoroutine(RunBossRequest(
                "Ask Party Strategy",
                payload,
                response =>
                {
                    ApplyBossReady();
                    var strategyLines = BuildStrategyLines(response);
                    if (strategyLines.Length > 0)
                    {
                        barkPanel?.ShowLines("Party Strategy", strategyLines);
                    }
                    else
                    {
                        barkPanel?.ShowResponses(response);
                    }

                    SetOutput(BuildBossActionSummary("Ask Party Strategy", response, "Boss: Ready"));
                    Debug.Log("BG3 boss strategy response received.");
                }));
        }

        private void OnUseDiaryTruthClicked()
        {
            ClearSelectedUi();
            if (actFlow != null)
            {
                actFlow.UseDiaryTruth();
                return;
            }

            if (backendClient == null)
            {
                SetOutput("Use Diary Truth\n\nError: BackendClient missing.");
                return;
            }

            var payload = CreateBossPayload(DiaryTruthPrompt, "boss_diary_truth", null);
            StartCoroutine(RunBossRequest(
                "Use Diary Truth",
                payload,
                response =>
                {
                    ApplyBossReady();
                    if (TryResolveKeyObtained(response))
                    {
                        ApplyKeyObtained();
                    }

                    barkPanel?.ShowResponses(response);
                    SetOutput(BuildBossActionSummary("Use Diary Truth", response, keyObtained ? "Key Obtained" : "Key not confirmed"));
                    Debug.Log($"BG3 boss diary truth response received: keyObtained={keyObtained}");
                }));
        }

        private System.Collections.IEnumerator SetupBossContext()
        {
            SetBossRequestInFlight(true);
            SetOutput("Prepare Boss Context\n\nDebug-only for Unity spike: seeding Act4 boss flags through the existing chat command path.");

            ApiChatResponse lastResponse = null;
            string lastError = null;
            for (var i = 0; i < BossSetupCommands.Length; i++)
            {
                var command = BossSetupCommands[i];
                var payload = new ApiChatRequest(backendClient.SessionId, backendClient.MapId, command, "unity_boss_setup");
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
                    SetOutput($"Prepare Boss Context\n\nFailed on `{command}`\n{lastError}");
                    barkPanel?.ShowError(lastError);
                    SetBossRequestInFlight(false);
                    yield break;
                }
            }

            ApplyBossReady();
            SetOutput(BuildBossActionSummary("Prepare Boss Context", lastResponse, "Debug-only setup complete. Diary truth route is seeded for this Unity prototype."));
            barkPanel?.ShowMessage("Boss Context", "Debug-only setup complete. Ask the party for strategy.");
            Debug.Log("BG3 boss context setup completed through debug-only Unity spike flags.");
            SetBossRequestInFlight(false);
        }

        private System.Collections.IEnumerator RunBossRequest(string label, ApiChatRequest payload, Action<ApiChatResponse> onSuccess)
        {
            if (bossRequestInFlight)
            {
                yield break;
            }

            SetBossRequestInFlight(true);
            SetOutput($"{label}\n\nSending boss request...");
            Debug.Log($"BG3 boss request sent: {label} target={payload.target} source={payload.source}");

            yield return backendClient.PostChat(
                payload,
                response =>
                {
                    onSuccess?.Invoke(response);
                    SetBossRequestInFlight(false);
                },
                error =>
                {
                    SetOutput($"{label}\n\nError: {error}");
                    barkPanel?.ShowError(error);
                    Debug.LogWarning($"BG3 boss request failed: {label}: {error}");
                    SetBossRequestInFlight(false);
                });
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

        private void RefreshTrapButtons()
        {
            var flowInFlight = actFlow != null && actFlow.RequestInFlight;
            var flowAllowsTrap = actFlow == null || actFlow.CurrentAct == ActFlowStage.Act2PoisonCorridor;
            if (disarmButton != null)
            {
                disarmButton.interactable = trapZone != null && trapState == TrapVisualState.Revealed && flowAllowsTrap && !flowInFlight;
            }

            if (triggerTrapButton != null)
            {
                triggerTrapButton.interactable = trapZone != null && trapState != TrapVisualState.Disabled && trapState != TrapVisualState.Triggered && !flowInFlight;
            }
        }

        private void RefreshBossButtons()
        {
            var flowInFlight = actFlow != null && actFlow.RequestInFlight;
            var flowAllowsBoss = actFlow == null || actFlow.CurrentAct == ActFlowStage.Act4GribboLab;
            if (setupBossButton != null)
            {
                setupBossButton.interactable = backendClient != null && !bossRequestInFlight && !flowInFlight;
            }

            if (askStrategyButton != null)
            {
                askStrategyButton.interactable = backendClient != null && bossReady && !bossRequestInFlight && !flowInFlight && flowAllowsBoss;
            }

            if (useDiaryTruthButton != null)
            {
                useDiaryTruthButton.interactable = backendClient != null && bossReady && !keyObtained && !bossRequestInFlight && !flowInFlight && flowAllowsBoss;
            }

        }

        private void RefreshActButtons()
        {
            var canRead = actFlow != null
                && actFlow.CurrentAct == ActFlowStage.Act3SecretStudy
                && backendClient != null
                && !actFlow.RequestInFlight;

            if (readChemicalNotesButton != null)
            {
                readChemicalNotesButton.interactable = canRead;
            }

            if (readDiaryButton != null)
            {
                readDiaryButton.interactable = canRead;
            }
        }

        private void SetBossRequestInFlight(bool inFlight)
        {
            bossRequestInFlight = inFlight;
            RefreshBossButtons();
            RefreshActButtons();
        }

        private void SyncBossStateFromMarker()
        {
            if (bossEncounter == null)
            {
                RefreshStatusText();
                RefreshBossButtons();
                return;
            }

            bossReady = bossEncounter.BossReady;
            keyObtained = bossEncounter.KeyObtained;
            RefreshStatusText();
            RefreshBossButtons();
        }

        private void ApplyBossReady()
        {
            bossReady = true;
            bossEncounter?.SetBossReady(true);
            if (actFlow == null)
            {
                SetAct("Act 4 - Gribbo Lab", "Convince Gribbo to surrender the key.");
            }
            else
            {
                RefreshActFlowUi();
            }

            RefreshStatusText();
            RefreshBossButtons();
        }

        private void ApplyKeyObtained()
        {
            bossReady = true;
            keyObtained = true;
            bossEncounter?.SetBossReady(true);
            bossEncounter?.SetKeyObtained(true);
            if (keyFeedback == null)
            {
                keyFeedback = UnityEngine.Object.FindAnyObjectByType<KeyPickupFeedback>();
            }

            keyFeedback?.ShowKeyObtained();
            if (actFlow == null)
            {
                SetAct("Act 4 - Gribbo Lab", "Heavy Iron Key obtained.");
            }
            else
            {
                RefreshActFlowUi();
            }

            RefreshStatusText();
            RefreshBossButtons();
        }

        private static void ClearSelectedUi()
        {
            if (EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(null);
            }
        }

        private static void AppendBossSummary(StringBuilder builder, ApiChatResponse response)
        {
            if (response == null)
            {
                return;
            }

            var strategyLines = BuildStrategyLines(response);
            if (strategyLines.Length > 0)
            {
                builder.AppendLine("Boss strategy:");
                for (var i = 0; i < strategyLines.Length; i++)
                {
                    builder.AppendLine(strategyLines[i]);
                }
            }

            if (TryResolveKeyObtained(response))
            {
                builder.AppendLine("Key: Heavy Iron Key Obtained");
                builder.AppendLine("heavy_iron_key");
                builder.AppendLine("key_surrendered");
                builder.AppendLine("gribbo -> player");
            }
        }

        private static string BuildBossActionSummary(string label, ApiChatResponse response, string headline)
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

            if (response.responses != null)
            {
                var limit = Mathf.Min(3, response.responses.Length);
                for (var i = 0; i < limit; i++)
                {
                    var entry = response.responses[i];
                    if (entry != null && !string.IsNullOrEmpty(entry.text))
                    {
                        builder.AppendLine($"{NormalizeSpeakerLabel(entry.speaker)}: {entry.text}");
                    }
                }
            }

            AppendBossSummary(builder, response);

            if (response.journal_events != null)
            {
                builder.AppendLine($"Journal events: {response.JournalEventCount}");
                var limit = Mathf.Min(5, response.journal_events.Length);
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

        public static string[] BuildStrategyLines(ApiChatResponse response)
        {
            var lines = new string[3];
            FillStrategyFromResponses(response, lines);
            FillStrategyFromJournal(response, lines);

            var count = 0;
            for (var i = 0; i < lines.Length; i++)
            {
                if (!string.IsNullOrEmpty(lines[i]))
                {
                    count++;
                }
            }

            if (count == 0)
            {
                return Array.Empty<string>();
            }

            var compact = new string[count];
            var writeIndex = 0;
            for (var i = 0; i < lines.Length; i++)
            {
                if (!string.IsNullOrEmpty(lines[i]))
                {
                    compact[writeIndex] = lines[i];
                    writeIndex++;
                }
            }

            return compact;
        }

        private static void FillStrategyFromResponses(ApiChatResponse response, string[] lines)
        {
            if (response?.responses == null)
            {
                return;
            }

            for (var i = 0; i < response.responses.Length; i++)
            {
                var entry = response.responses[i];
                if (entry == null || string.IsNullOrEmpty(entry.text))
                {
                    continue;
                }

                var index = SpeakerIndex(entry.speaker);
                if (index >= 0 && string.IsNullOrEmpty(lines[index]))
                {
                    lines[index] = $"{NormalizeSpeakerLabel(entry.speaker)}: {entry.text}";
                }
            }
        }

        private static void FillStrategyFromJournal(ApiChatResponse response, string[] lines)
        {
            if (response?.journal_events == null)
            {
                return;
            }

            for (var i = 0; i < response.journal_events.Length; i++)
            {
                var value = response.journal_events[i];
                if (string.IsNullOrEmpty(value) || !value.Contains("[Boss方案]"))
                {
                    continue;
                }

                var normalized = value.ToLowerInvariant();
                SetJournalStrategyLine(lines, normalized, "astarion", "Astarion");
                SetJournalStrategyLine(lines, normalized, "shadowheart", "Shadowheart");
                SetJournalStrategyLine(lines, normalized, "laezel", "Lae'zel");
            }
        }

        private static void SetJournalStrategyLine(string[] lines, string normalizedJournal, string speakerId, string speakerLabel)
        {
            var index = SpeakerIndex(speakerId);
            if (index < 0 || !string.IsNullOrEmpty(lines[index]) || !normalizedJournal.Contains(speakerId))
            {
                return;
            }

            var stance = "strategy";
            if (normalizedJournal.Contains("steal_key"))
            {
                stance = "steal_key";
            }
            else if (normalizedJournal.Contains("contain_corruption"))
            {
                stance = "contain_corruption";
            }
            else if (normalizedJournal.Contains("execute"))
            {
                stance = "execute";
            }

            lines[index] = $"{speakerLabel}: {stance}";
        }

        public static bool TryResolveKeyObtained(ApiChatResponse response)
        {
            if (response == null)
            {
                return false;
            }

            if (response.HasHeavyIronKey)
            {
                return true;
            }

            var haystack = BuildBossHaystack(response);
            if (BackendClient.ExtractBooleanField(response.raw_json, "act4_heavy_iron_key_obtained"))
            {
                return true;
            }

            return ContainsAny(
                haystack,
                "[boss解决] negotiation -> key_surrendered",
                "[物品转移] gribbo -> player heavy_iron_key",
                "key_surrendered");
        }

        private static string BuildBossHaystack(ApiChatResponse response)
        {
            var builder = new StringBuilder();
            builder.Append(response.raw_json);
            builder.Append('\n');
            builder.Append(response.FirstResponseSpeaker);
            builder.Append('\n');
            builder.Append(response.FirstResponseText);

            if (response.responses != null)
            {
                for (var i = 0; i < response.responses.Length; i++)
                {
                    builder.Append('\n');
                    builder.Append(response.responses[i]?.speaker);
                    builder.Append(':');
                    builder.Append(response.responses[i]?.text);
                }
            }

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

        private static int SpeakerIndex(string speaker)
        {
            var normalized = NormalizeSpeakerId(speaker);
            if (normalized == "astarion")
            {
                return 0;
            }

            if (normalized == "shadowheart")
            {
                return 1;
            }

            return normalized == "laezel" ? 2 : -1;
        }

        private static string NormalizeSpeakerId(string speaker)
        {
            return string.IsNullOrEmpty(speaker)
                ? string.Empty
                : speaker.Trim().ToLowerInvariant().Replace("_", string.Empty).Replace("-", string.Empty).Replace("'", string.Empty).Replace("’", string.Empty);
        }

        private static string NormalizeSpeakerLabel(string speaker)
        {
            var normalized = NormalizeSpeakerId(speaker);
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
                default:
                    return string.IsNullOrEmpty(speaker) ? "Backend" : speaker;
            }
        }

        private static bool ContainsAny(string value, params string[] markers)
        {
            if (string.IsNullOrEmpty(value))
            {
                return false;
            }

            for (var i = 0; i < markers.Length; i++)
            {
                if (!string.IsNullOrEmpty(markers[i]) && value.Contains(markers[i].ToLowerInvariant()))
                {
                    return true;
                }
            }

            return false;
        }

        private static RectTransform CreateUiObject(string name, Transform parent)
        {
            var gameObject = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer));
            var rectTransform = gameObject.GetComponent<RectTransform>();
            rectTransform.SetParent(parent, false);
            return rectTransform;
        }

        private static Text CreateText(string name, RectTransform parent, string value, int fontSize, FontStyle style, TextAnchor alignment, Color color)
        {
            var rectTransform = CreateUiObject(name, parent);
            var text = rectTransform.gameObject.AddComponent<Text>();
            text.font = GetDefaultFont();
            text.text = value;
            text.fontSize = fontSize;
            text.fontStyle = style;
            text.alignment = alignment;
            text.color = color;
            text.raycastTarget = false;
            return text;
        }

        private static InputField CreateInputField(string name, RectTransform parent, string value)
        {
            var root = CreateUiObject(name, parent);
            var image = root.gameObject.AddComponent<Image>();
            image.color = new Color(0.9f, 0.93f, 0.94f, 0.96f);

            var placeholder = CreateText("Placeholder", root, value, 12, FontStyle.Italic, TextAnchor.MiddleLeft, new Color(0.46f, 0.48f, 0.52f, 0.75f));
            StretchWithPadding(placeholder.rectTransform, 8f, 5f);

            var text = CreateText("Text", root, value, 12, FontStyle.Normal, TextAnchor.MiddleLeft, new Color(0.08f, 0.09f, 0.11f, 1f));
            StretchWithPadding(text.rectTransform, 8f, 5f);

            var input = root.gameObject.AddComponent<InputField>();
            input.targetGraphic = image;
            input.textComponent = text;
            input.placeholder = placeholder;
            input.text = value;
            input.lineType = InputField.LineType.SingleLine;
            return input;
        }

        private static Button CreateButton(string name, RectTransform parent, string label)
        {
            var root = CreateUiObject(name, parent);
            var image = root.gameObject.AddComponent<Image>();
            image.color = new Color(0.16f, 0.34f, 0.48f, 0.96f);

            var text = CreateText("Text", root, label, 12, FontStyle.Bold, TextAnchor.MiddleCenter, Color.white);
            text.resizeTextForBestFit = true;
            text.resizeTextMinSize = 9;
            text.resizeTextMaxSize = 12;
            StretchWithPadding(text.rectTransform, 4f, 4f);

            var button = root.gameObject.AddComponent<Button>();
            button.targetGraphic = image;
            return button;
        }

        private static ActObjectiveHud CreateActObjectiveHud(Transform canvasTransform)
        {
            var root = CreateUiObject("ActObjectiveHud", canvasTransform);
            SetTopLeft(root, new Vector2(18f, -18f), new Vector2(420f, 68f));

            var image = root.gameObject.AddComponent<Image>();
            image.color = new Color(0.025f, 0.032f, 0.04f, 0.76f);
            image.raycastTarget = false;
            AddBorder(root, new Color(0.78f, 0.66f, 0.44f, 0.58f), 1.5f);

            var accent = CreateUiObject("Accent", root);
            accent.anchorMin = new Vector2(0f, 0f);
            accent.anchorMax = new Vector2(0f, 1f);
            accent.pivot = new Vector2(0f, 0.5f);
            accent.anchoredPosition = Vector2.zero;
            accent.sizeDelta = new Vector2(4f, 0f);
            var accentImage = accent.gameObject.AddComponent<Image>();
            accentImage.color = new Color(1f, 0.64f, 0.2f, 0.92f);
            accentImage.raycastTarget = false;

            var title = CreateText("ActTitle", root, "Act 1 - Safe Room", 17, FontStyle.Bold, TextAnchor.UpperLeft, new Color(1f, 0.86f, 0.54f, 1f));
            SetTopLeft(title.rectTransform, new Vector2(16f, -10f), new Vector2(388f, 24f));

            var objective = CreateText("Objective", root, "Open the door / move toward corridor.", 14, FontStyle.Normal, TextAnchor.UpperLeft, new Color(0.88f, 0.93f, 0.94f, 0.95f));
            objective.horizontalOverflow = HorizontalWrapMode.Wrap;
            objective.verticalOverflow = VerticalWrapMode.Truncate;
            SetTopLeft(objective.rectTransform, new Vector2(16f, -36f), new Vector2(388f, 24f));

            var hud = root.gameObject.AddComponent<ActObjectiveHud>();
            hud.Configure(title, objective);
            return hud;
        }

        private static BarkPanel CreateBarkPanel(Transform canvasTransform)
        {
            var root = CreateUiObject("BarkPanel", canvasTransform);
            root.anchorMin = new Vector2(0.5f, 0f);
            root.anchorMax = new Vector2(0.5f, 0f);
            root.pivot = new Vector2(0.5f, 0f);
            root.anchoredPosition = new Vector2(0f, 26f);
            root.sizeDelta = new Vector2(780f, 126f);

            var image = root.gameObject.AddComponent<Image>();
            image.color = new Color(0.025f, 0.028f, 0.034f, 0.9f);
            image.raycastTarget = false;
            AddBorder(root, new Color(0.8f, 0.62f, 0.38f, 0.62f), 2f);

            var group = root.gameObject.AddComponent<CanvasGroup>();
            group.alpha = 1f;
            group.blocksRaycasts = false;
            group.interactable = false;

            var speakerPlate = CreateUiObject("SpeakerPlate", root);
            SetTopLeft(speakerPlate, new Vector2(18f, -14f), new Vector2(184f, 28f));
            var plateImage = speakerPlate.gameObject.AddComponent<Image>();
            plateImage.color = new Color(0.18f, 0.12f, 0.06f, 0.92f);
            plateImage.raycastTarget = false;

            var speaker = CreateText("Speaker", speakerPlate, "Narrator", 16, FontStyle.Bold, TextAnchor.MiddleLeft, new Color(1f, 0.78f, 0.44f, 1f));
            StretchWithPadding(speaker.rectTransform, 10f, 4f);

            var queue = CreateText("Queue", root, string.Empty, 13, FontStyle.Bold, TextAnchor.MiddleRight, new Color(0.82f, 0.74f, 0.62f, 0.9f));
            SetTopLeft(queue.rectTransform, new Vector2(692f, -16f), new Vector2(70f, 24f));

            var body = CreateText("Body", root, "The corridor falls quiet.", 18, FontStyle.Normal, TextAnchor.UpperLeft, new Color(0.96f, 0.97f, 0.98f, 1f));
            body.horizontalOverflow = HorizontalWrapMode.Wrap;
            body.verticalOverflow = VerticalWrapMode.Truncate;
            body.lineSpacing = 1.05f;
            SetTopLeft(body.rectTransform, new Vector2(24f, -52f), new Vector2(732f, 58f));

            var panel = root.gameObject.AddComponent<BarkPanel>();
            panel.Configure(speaker, body, queue, group);
            return panel;
        }

        private static void AddBorder(RectTransform root, Color color, float thickness)
        {
            AddBorderSide("BorderTop", root, color, new Vector2(0f, 1f), new Vector2(1f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, thickness));
            AddBorderSide("BorderBottom", root, color, new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, thickness));
            AddBorderSide("BorderLeft", root, color, new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(0f, 0.5f), new Vector2(thickness, 0f));
            AddBorderSide("BorderRight", root, color, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(1f, 0.5f), new Vector2(thickness, 0f));
        }

        private static void AddBorderSide(string name, RectTransform root, Color color, Vector2 anchorMin, Vector2 anchorMax, Vector2 pivot, Vector2 sizeDelta)
        {
            var side = CreateUiObject(name, root);
            side.anchorMin = anchorMin;
            side.anchorMax = anchorMax;
            side.pivot = pivot;
            side.anchoredPosition = Vector2.zero;
            side.sizeDelta = sizeDelta;
            var image = side.gameObject.AddComponent<Image>();
            image.color = color;
            image.raycastTarget = false;
        }

        private static void SetButtonLabel(Button button, string label)
        {
            var text = button == null ? null : button.GetComponentInChildren<Text>();
            if (text != null)
            {
                text.text = label;
            }
        }

        private static void SetTopLeft(RectTransform rectTransform, Vector2 anchoredPosition, Vector2 size)
        {
            rectTransform.anchorMin = new Vector2(0f, 1f);
            rectTransform.anchorMax = new Vector2(0f, 1f);
            rectTransform.pivot = new Vector2(0f, 1f);
            rectTransform.anchoredPosition = anchoredPosition;
            rectTransform.sizeDelta = size;
        }

        private static void StretchWithPadding(RectTransform rectTransform, float horizontalPadding, float verticalPadding)
        {
            rectTransform.anchorMin = Vector2.zero;
            rectTransform.anchorMax = Vector2.one;
            rectTransform.pivot = new Vector2(0.5f, 0.5f);
            rectTransform.offsetMin = new Vector2(horizontalPadding, verticalPadding);
            rectTransform.offsetMax = new Vector2(-horizontalPadding, -verticalPadding);
        }

        private static Font GetDefaultFont()
        {
            return Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf")
                ?? Resources.GetBuiltinResource<Font>("Arial.ttf");
        }
    }
}
