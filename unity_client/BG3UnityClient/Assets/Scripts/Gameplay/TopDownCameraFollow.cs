using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class TopDownCameraFollow : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private Vector3 offset = new Vector3(0f, 8.5f, -7.5f);
        [SerializeField] private Vector3 lookAtOffset = new Vector3(0f, 0.8f, 0f);
        [SerializeField] private float followSharpness = 8f;

        public void Configure(Transform followTarget)
        {
            target = followTarget;
        }

        public void SetFraming(Vector3 nextOffset, Vector3 nextLookAtOffset, float fieldOfView)
        {
            offset = nextOffset;
            lookAtOffset = nextLookAtOffset;

            var camera = GetComponent<Camera>();
            if (camera != null)
            {
                camera.fieldOfView = fieldOfView;
            }
        }

        public void SnapToTarget()
        {
            if (target == null)
            {
                return;
            }

            transform.position = target.position + offset;
            transform.LookAt(target.position + lookAtOffset, Vector3.up);
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
            transform.LookAt(target.position + lookAtOffset, Vector3.up);
        }
    }
}
