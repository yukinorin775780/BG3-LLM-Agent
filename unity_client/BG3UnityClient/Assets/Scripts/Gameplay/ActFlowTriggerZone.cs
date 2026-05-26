using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class ActFlowTriggerZone : MonoBehaviour
    {
        [SerializeField] private ActFlowController flowController;
        [SerializeField] private Transform player;
        [SerializeField] private ActFlowStage targetAct = ActFlowStage.Act2PoisonCorridor;
        [SerializeField] private float triggerRange = 1.35f;
        [SerializeField] private bool consumed;

        public void Configure(ActFlowController controller, Transform playerTransform, ActFlowStage act, float range)
        {
            flowController = controller;
            player = playerTransform;
            targetAct = act;
            triggerRange = range;
            EnsureTriggerCollider();
        }

        private void Awake()
        {
            EnsureTriggerCollider();
        }

        private void Update()
        {
            if (consumed)
            {
                return;
            }

            ResolveReferences();
            if (flowController == null || player == null)
            {
                return;
            }

            var flatPlayer = new Vector3(player.position.x, transform.position.y, player.position.z);
            if (Vector3.Distance(flatPlayer, transform.position) > triggerRange)
            {
                return;
            }

            consumed = true;
            flowController.HandleTrigger(targetAct);
            Debug.Log($"BG3 act flow trigger consumed: {targetAct}");
        }

        private void OnDrawGizmosSelected()
        {
            Gizmos.color = new Color(0.38f, 0.72f, 1f, 0.26f);
            Gizmos.DrawWireCube(transform.position + Vector3.up * 0.45f, new Vector3(triggerRange * 2f, 0.9f, triggerRange * 2f));
        }

        private void ResolveReferences()
        {
            if (flowController == null)
            {
                flowController = UnityEngine.Object.FindAnyObjectByType<ActFlowController>();
            }

            if (player == null)
            {
                var playerObject = GameObject.Find("Player");
                player = playerObject == null ? null : playerObject.transform;
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
            trigger.center = new Vector3(0f, 0.45f, 0f);
            trigger.size = new Vector3(triggerRange * 2f, 0.9f, triggerRange * 2f);
        }
    }
}
