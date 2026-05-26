using UnityEngine;
using UnityEngine.UI;

namespace BG3UnityClient.UI
{
    public sealed class RewardToast : MonoBehaviour
    {
        [SerializeField] private CanvasGroup canvasGroup;
        [SerializeField] private Text messageText;
        [SerializeField] private float visibleSeconds = 2.65f;
        [SerializeField] private float fadeSeconds = 0.45f;

        private Coroutine toastRoutine;

        public static RewardToast FindOrCreate()
        {
            var existing = Object.FindAnyObjectByType<RewardToast>();
            if (existing != null)
            {
                return existing;
            }

            var canvasObject = new GameObject("RewardToastCanvas", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = canvasObject.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 30;

            var scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280f, 720f);
            scaler.matchWidthOrHeight = 0.5f;

            var root = CreateUiObject("RewardToast", canvasObject.transform);
            root.anchorMin = new Vector2(0.5f, 1f);
            root.anchorMax = new Vector2(0.5f, 1f);
            root.pivot = new Vector2(0.5f, 1f);
            root.anchoredPosition = new Vector2(0f, -82f);
            root.sizeDelta = new Vector2(326f, 50f);

            var group = root.gameObject.AddComponent<CanvasGroup>();
            group.alpha = 0f;
            group.blocksRaycasts = false;
            group.interactable = false;

            var background = root.gameObject.AddComponent<Image>();
            background.color = new Color(0.12f, 0.09f, 0.035f, 0.88f);
            background.raycastTarget = false;
            AddBorder(root, new Color(1f, 0.68f, 0.16f, 0.82f), 2f);

            var icon = CreateUiObject("GoldIcon", root);
            icon.anchorMin = new Vector2(0f, 0.5f);
            icon.anchorMax = new Vector2(0f, 0.5f);
            icon.pivot = new Vector2(0.5f, 0.5f);
            icon.anchoredPosition = new Vector2(29f, 0f);
            icon.sizeDelta = new Vector2(18f, 18f);
            icon.localRotation = Quaternion.Euler(0f, 0f, 45f);
            var iconImage = icon.gameObject.AddComponent<Image>();
            iconImage.color = new Color(1f, 0.72f, 0.16f, 1f);
            iconImage.raycastTarget = false;

            var message = CreateText("Message", root, "Heavy Iron Key Obtained", 16, FontStyle.Bold, TextAnchor.MiddleLeft, new Color(1f, 0.89f, 0.44f, 1f));
            message.horizontalOverflow = HorizontalWrapMode.Overflow;
            message.verticalOverflow = VerticalWrapMode.Truncate;
            SetStretch(message.rectTransform, new Vector2(54f, 8f), new Vector2(14f, 8f));

            var toast = root.gameObject.AddComponent<RewardToast>();
            toast.canvasGroup = group;
            toast.messageText = message;
            return toast;
        }

        public void Show(string message)
        {
            if (messageText != null)
            {
                messageText.text = string.IsNullOrEmpty(message) ? "Reward Obtained" : message;
            }

            if (toastRoutine != null)
            {
                StopCoroutine(toastRoutine);
            }

            toastRoutine = StartCoroutine(ShowRoutine());
        }

        private System.Collections.IEnumerator ShowRoutine()
        {
            if (canvasGroup != null)
            {
                canvasGroup.alpha = 1f;
            }

            yield return new WaitForSeconds(visibleSeconds);

            var elapsed = 0f;
            while (elapsed < fadeSeconds)
            {
                elapsed += Time.deltaTime;
                if (canvasGroup != null)
                {
                    canvasGroup.alpha = Mathf.Lerp(1f, 0f, Mathf.Clamp01(elapsed / fadeSeconds));
                }

                yield return null;
            }

            if (canvasGroup != null)
            {
                canvasGroup.alpha = 0f;
            }

            toastRoutine = null;
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

        private static void SetStretch(RectTransform rectTransform, Vector2 offsetMin, Vector2 offsetMax)
        {
            rectTransform.anchorMin = Vector2.zero;
            rectTransform.anchorMax = Vector2.one;
            rectTransform.pivot = new Vector2(0.5f, 0.5f);
            rectTransform.offsetMin = offsetMin;
            rectTransform.offsetMax = -offsetMax;
        }

        private static void AddBorder(RectTransform root, Color color, float thickness)
        {
            AddBorderSide("Top", root, color, new Vector2(0f, 1f), new Vector2(1f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, thickness));
            AddBorderSide("Bottom", root, color, new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, thickness));
            AddBorderSide("Left", root, color, new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(0f, 0.5f), new Vector2(thickness, 0f));
            AddBorderSide("Right", root, color, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(1f, 0.5f), new Vector2(thickness, 0f));
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

        private static Font GetDefaultFont()
        {
            return Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf")
                ?? Resources.GetBuiltinResource<Font>("Arial.ttf");
        }
    }
}
