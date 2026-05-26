using UnityEngine;
using BG3UnityClient.UI;

namespace BG3UnityClient.Gameplay
{
    public sealed class KeyPickupFeedback : MonoBehaviour
    {
        [SerializeField] private Transform followTarget;
        [SerializeField] private RewardToast rewardToast;
        [SerializeField] private bool keyVisible;

        public bool KeyVisible => keyVisible;

        public void Configure(Transform target)
        {
            followTarget = target;
        }

        public void ShowKeyObtained()
        {
            keyVisible = true;
            EnsureToast();
            rewardToast?.Show("Heavy Iron Key Obtained");
            Debug.Log("BG3 key feedback shown: Heavy Iron Key Obtained.");
        }

        private void Awake()
        {
            EnsureToast();
        }

        private void EnsureToast()
        {
            if (rewardToast == null)
            {
                rewardToast = RewardToast.FindOrCreate();
            }
        }
    }
}
