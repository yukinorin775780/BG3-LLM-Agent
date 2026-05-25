using System.Text;
using BG3UnityClient.Api;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

namespace BG3UnityClient.UI
{
    public sealed class BackendDebugPanel : MonoBehaviour
    {
        private const string DefaultPrompt = "Is something wrong in the corridor?";

        [SerializeField] private BackendClient backendClient;
        [SerializeField] private Text statusText;
        [SerializeField] private InputField inputField;
        [SerializeField] private Button sendButton;
        [SerializeField] private Text outputText;

        private void Awake()
        {
            if (backendClient == null)
            {
                backendClient = FindObjectOfType<BackendClient>();
            }

            if (sendButton != null)
            {
                sendButton.onClick.AddListener(OnSendClicked);
            }

            if (statusText == null || inputField == null || sendButton == null || outputText == null)
            {
                CreateRuntimeUi();
            }
        }

        private void Start()
        {
            if (inputField != null && string.IsNullOrWhiteSpace(inputField.text))
            {
                inputField.text = DefaultPrompt;
            }

            SetStatus($"Connecting: {backendClient?.MapId ?? "(unknown)"}\nsession={backendClient?.SessionId ?? "(unknown)"}");
            SetOutput("Ready.");

            if (backendClient != null)
            {
                StartCoroutine(backendClient.GetState(OnStateLoaded, OnStateError));
            }
            else
            {
                SetStatus("BackendClient missing.");
                SetOutput("Error: BackendClient missing.");
            }
        }

        private void OnDestroy()
        {
            if (sendButton != null)
            {
                sendButton.onClick.RemoveListener(OnSendClicked);
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
            StartCoroutine(SendChat(userInput));
        }

        private System.Collections.IEnumerator SendChat(string userInput)
        {
            SetSendEnabled(false);
            SetOutput($"Sending...\n\n> {userInput}");

            yield return backendClient.PostChat(
                userInput,
                response => SetOutput(BuildChatSummary(userInput, response)),
                error => SetOutput($"Error: {error}"));

            SetSendEnabled(true);
        }

        private void OnStateLoaded(ApiStateResponse response)
        {
            var state = response.ResolvedState;
            var resolvedMapId = FirstNonEmpty(state?.map_data?.id, response.map_id, backendClient.MapId, "(unknown)");
            var resolvedSessionId = FirstNonEmpty(response.session_id, backendClient.SessionId, "(unknown)");
            SetStatus($"Connected: {resolvedMapId}\nsession={resolvedSessionId}");
        }

        private void OnStateError(string error)
        {
            SetStatus($"Connection failed: {error}");
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

        private void SetStatus(string value)
        {
            if (statusText != null)
            {
                statusText.text = value;
            }
        }

        private void SetOutput(string value)
        {
            if (outputText != null)
            {
                outputText.text = value;
            }
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

            var panel = CreateUiObject("BackendDebugPanel", canvasObject.transform);
            SetTopLeft(panel, new Vector2(32f, -32f), new Vector2(560f, 500f));
            var panelImage = panel.gameObject.AddComponent<Image>();
            panelImage.color = new Color(0.08f, 0.09f, 0.11f, 0.92f);
            panelImage.raycastTarget = false;

            var title = CreateText("Title", panel, "BG3 Unity Client", 24, FontStyle.Bold, TextAnchor.MiddleLeft, Color.white);
            SetTopLeft(title.rectTransform, new Vector2(20f, -18f), new Vector2(520f, 36f));

            statusText = CreateText("ConnectionStatus", panel, "Connecting...", 16, FontStyle.Normal, TextAnchor.UpperLeft, new Color(0.74f, 0.88f, 1f, 1f));
            SetTopLeft(statusText.rectTransform, new Vector2(20f, -62f), new Vector2(520f, 54f));

            inputField = CreateInputField("ChatInput", panel, DefaultPrompt);
            SetTopLeft(inputField.GetComponent<RectTransform>(), new Vector2(20f, -128f), new Vector2(390f, 44f));

            sendButton = CreateButton("SendButton", panel, "Send");
            SetTopLeft(sendButton.GetComponent<RectTransform>(), new Vector2(422f, -128f), new Vector2(118f, 44f));
            sendButton.onClick.AddListener(OnSendClicked);

            outputText = CreateText("OutputLog", panel, "Ready.", 15, FontStyle.Normal, TextAnchor.UpperLeft, new Color(0.92f, 0.94f, 0.95f, 1f));
            outputText.horizontalOverflow = HorizontalWrapMode.Wrap;
            outputText.verticalOverflow = VerticalWrapMode.Overflow;
            SetTopLeft(outputText.rectTransform, new Vector2(20f, -188f), new Vector2(520f, 282f));

            if (EventSystem.current == null)
            {
                var eventSystemObject = new GameObject("BackendDebugEventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
                eventSystemObject.GetComponent<InputSystemUIInputModule>().AssignDefaultActions();
            }
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
            image.color = new Color(0.95f, 0.96f, 0.98f, 1f);

            var placeholder = CreateText("Placeholder", root, value, 15, FontStyle.Italic, TextAnchor.MiddleLeft, new Color(0.46f, 0.48f, 0.52f, 0.75f));
            StretchWithPadding(placeholder.rectTransform, 12f, 8f);

            var text = CreateText("Text", root, value, 15, FontStyle.Normal, TextAnchor.MiddleLeft, new Color(0.08f, 0.09f, 0.11f, 1f));
            StretchWithPadding(text.rectTransform, 12f, 8f);

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
            image.color = new Color(0.24f, 0.48f, 0.82f, 1f);

            var text = CreateText("Text", root, label, 16, FontStyle.Bold, TextAnchor.MiddleCenter, Color.white);
            StretchWithPadding(text.rectTransform, 4f, 4f);

            var button = root.gameObject.AddComponent<Button>();
            button.targetGraphic = image;
            return button;
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
