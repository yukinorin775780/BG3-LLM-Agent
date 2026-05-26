using UnityEngine;
using UnityEngine.UI;

namespace BG3UnityClient.UI
{
    public sealed class ActObjectiveHud : MonoBehaviour
    {
        [SerializeField] private Text actTitleText;
        [SerializeField] private Text objectiveText;

        public void Configure(Text actTitle, Text objective)
        {
            actTitleText = actTitle;
            objectiveText = objective;
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
    }
}
