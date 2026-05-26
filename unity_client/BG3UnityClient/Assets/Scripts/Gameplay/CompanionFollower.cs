using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class CompanionFollower : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private float followDistance = 1.4f;
        [SerializeField] private float sideOffset;
        [SerializeField] private float followSharpness = 7f;
        [SerializeField] private Vector2 roomBounds = new Vector2(5.35f, 5.35f);

        public void Configure(Transform followTarget, float distance, float lateralOffset, float halfWidth, float halfDepth)
        {
            target = followTarget;
            followDistance = distance;
            sideOffset = lateralOffset;
            roomBounds = new Vector2(halfWidth, halfDepth);
        }

        private void Update()
        {
            if (target == null)
            {
                return;
            }

            var desired = target.position - target.forward * followDistance + target.right * sideOffset;
            desired.x = Mathf.Clamp(desired.x, -roomBounds.x, roomBounds.x);
            desired.z = Mathf.Clamp(desired.z, -roomBounds.y, roomBounds.y);
            desired.y = transform.position.y;

            var t = 1f - Mathf.Exp(-followSharpness * Time.deltaTime);
            transform.position = Vector3.Lerp(transform.position, desired, t);

            var lookDirection = target.position - transform.position;
            lookDirection.y = 0f;
            if (lookDirection.sqrMagnitude > 0.01f)
            {
                transform.rotation = Quaternion.LookRotation(lookDirection.normalized, Vector3.up);
            }
        }
    }
}
