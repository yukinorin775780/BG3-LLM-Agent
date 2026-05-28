using UnityEngine;
using UnityEngine.UI;

namespace BG3UnityClient.UI
{
    public sealed class ActObjectiveHud : MonoBehaviour
    {
        [SerializeField] private Text actTitleText;
        [SerializeField] private Text objectiveText;
        [SerializeField] private Text progressText;
        [SerializeField] private Text controlHintText;
        [SerializeField] private CanvasGroup actToastGroup;
        [SerializeField] private Text actToastText;
        [SerializeField] private float toastVisibleSeconds = 1.45f;
        [SerializeField] private float toastFadeSeconds = 0.28f;

        private Coroutine toastRoutine;

        public void Configure(Text actTitle, Text objective)
        {
            Configure(actTitle, objective, null, null);
        }

        public void Configure(Text actTitle, Text objective, CanvasGroup toastGroup, Text toastText)
        {
            Configure(actTitle, objective, null, null, toastGroup, toastText);
        }

        public void Configure(Text actTitle, Text objective, Text progress, Text controlHint, CanvasGroup toastGroup, Text toastText)
        {
            actTitleText = actTitle;
            objectiveText = objective;
            progressText = progress;
            controlHintText = controlHint;
            actToastGroup = toastGroup;
            actToastText = toastText;
        }

        public void SetAct(string title, string objective)
        {
            if (actTitleText != null)
            {
                actTitleText.text = string.IsNullOrEmpty(title) ? "Current Act" : title;
            }

            if (objectiveText != null)
            {
                objectiveText.text = string.IsNullOrEmpty(objective) ? "Objective pending." : objective;
            }
        }

        public void SetProgress(int actNumber)
        {
            if (progressText == null)
            {
                return;
            }

            var clamped = Mathf.Clamp(actNumber, 1, 4);
            progressText.text = FormatStep(1, "Safe Room", clamped)
                + " -> "
                + FormatStep(2, "Corridor", clamped)
                + " -> "
                + FormatStep(3, "Study", clamped)
                + " -> "
                + FormatStep(4, "Gribbo", clamped);
        }

        public void SetControlHint(string hint)
        {
            if (controlHintText != null)
            {
                controlHintText.text = string.IsNullOrEmpty(hint) ? "WASD move | click visible buttons or press 1/R, 2/T." : hint;
            }
        }

        public void ShowActToast(string title)
        {
            if (actToastGroup == null || actToastText == null)
            {
                return;
            }

            actToastText.text = string.IsNullOrEmpty(title) ? "Act Updated" : title;
            if (toastRoutine != null)
            {
                StopCoroutine(toastRoutine);
            }

            toastRoutine = StartCoroutine(ShowToastRoutine());
        }

        private System.Collections.IEnumerator ShowToastRoutine()
        {
            actToastGroup.alpha = 1f;
            yield return new WaitForSeconds(toastVisibleSeconds);

            var elapsed = 0f;
            while (elapsed < toastFadeSeconds)
            {
                elapsed += Time.deltaTime;
                actToastGroup.alpha = Mathf.Lerp(1f, 0f, Mathf.Clamp01(elapsed / toastFadeSeconds));
                yield return null;
            }

            actToastGroup.alpha = 0f;
            toastRoutine = null;
        }

        private static string FormatStep(int step, string label, int current)
        {
            if (step == current)
            {
                return $"[Act{step} {label}]";
            }

            return $"Act{step} {label}";
        }
    }
}
