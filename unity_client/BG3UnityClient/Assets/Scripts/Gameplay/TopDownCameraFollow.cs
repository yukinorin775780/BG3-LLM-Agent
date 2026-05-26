using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class TopDownCameraFollow : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private Vector3 offset = new Vector3(0f, 8.5f, -7.5f);
        [SerializeField] private float followSharpness = 8f;
        [SerializeField] private float lookAtHeight = 0.8f;

        public void Configure(Transform followTarget)
        {
            target = followTarget;
        }

        private void LateUpdate()
        {
            if (target == null)
            {
                return;
            }

            var desiredPosition = target.position + offset;
            var t = 1f - Mathf.Exp(-followSharpness * Time.deltaTime);
            transform.position = Vector3.Lerp(transform.position, desiredPosition, t);
            transform.LookAt(target.position + Vector3.up * lookAtHeight, Vector3.up);
        }
    }
}
