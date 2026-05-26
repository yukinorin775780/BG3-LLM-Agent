using BG3UnityClient.UI;
using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class BossEncounterZone : MonoBehaviour
    {
        [SerializeField] private Transform player;
        [SerializeField] private BossEncounterMarker bossMarker;
        [SerializeField] private BackendDebugPanel debugPanel;
        [SerializeField] private float readyRange = 2.35f;
        [SerializeField] private bool encounterReady;

        public bool EncounterReady => encounterReady;

        public void Configure(Transform playerTransform, BossEncounterMarker marker, BackendDebugPanel panel, float range)
        {
            player = playerTransform;
            bossMarker = marker;
            debugPanel = panel;
            readyRange = range;
            EnsureTriggerCollider();
            debugPanel?.AttachBossZone(this);
        }

        public void AttachDebugPanel(BackendDebugPanel panel)
        {
            debugPanel = panel;
            debugPanel?.AttachBossZone(this);
        }

        private void Awake()
        {
            EnsureTriggerCollider();
        }

        private void Start()
        {
            ResolveReferences();
            debugPanel?.AttachBossZone(this);
        }

        private void Update()
        {
            if (encounterReady)
            {
                return;
            }

            ResolveReferences();
            if (player == null)
            {
                return;
            }

            var flatPlayer = new Vector3(player.position.x, transform.position.y, player.position.z);
            if (Vector3.Distance(flatPlayer, transform.position) <= readyRange)
            {
                SetEncounterReady();
            }
        }

        private void OnDrawGizmosSelected()
        {
            Gizmos.color = new Color(0.62f, 0.9f, 1f, 0.28f);
            Gizmos.DrawWireCube(transform.position + Vector3.up * 0.8f, new Vector3(readyRange * 2f, 1.6f, readyRange * 2f));
        }

        private void SetEncounterReady()
        {
            encounterReady = true;
            bossMarker?.SetBossReady(true);
            debugPanel?.SetBossEncounterReady(true);
            Debug.Log("BG3 boss encounter ready: player entered Gribbo zone.");
        }

        private void ResolveReferences()
        {
            if (player == null)
            {
                var playerObject = GameObject.Find("Player");
                player = playerObject == null ? null : playerObject.transform;
            }

            if (bossMarker == null)
            {
                bossMarker = UnityEngine.Object.FindAnyObjectByType<BossEncounterMarker>();
            }

            if (debugPanel == null)
            {
                debugPanel = UnityEngine.Object.FindAnyObjectByType<BackendDebugPanel>();
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
            trigger.center = new Vector3(0f, 0.8f, 0f);
            trigger.size = new Vector3(readyRange * 2f, 1.6f, readyRange * 2f);
        }
    }
}
