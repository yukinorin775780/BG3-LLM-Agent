using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class KeyPickupFeedback : MonoBehaviour
    {
        [SerializeField] private Transform followTarget;
        [SerializeField] private Transform keyRoot;
        [SerializeField] private TextMesh label;
        [SerializeField] private bool keyVisible;

        private Material keyMaterial;

        public bool KeyVisible => keyVisible;

        public void Configure(Transform target)
        {
            followTarget = target;
            EnsureVisuals();
            ApplyVisibleState();
        }

        public void ShowKeyObtained()
        {
            keyVisible = true;
            EnsureVisuals();
            ApplyVisibleState();
            Debug.Log("BG3 key feedback shown: Heavy Iron Key Obtained.");
        }

        private void Awake()
        {
            EnsureVisuals();
            ApplyVisibleState();
        }

        private void LateUpdate()
        {
            if (!keyVisible)
            {
                return;
            }

            ResolveTarget();
            if (followTarget != null && keyRoot != null)
            {
                transform.position = followTarget.position + new Vector3(0.72f, 1.42f, -0.18f);
                keyRoot.localRotation = Quaternion.Euler(0f, Time.time * 120f, 90f);
            }

            FaceCamera(label);
        }

        private void ResolveTarget()
        {
            if (followTarget != null)
            {
                return;
            }

            var playerObject = GameObject.Find("Player");
            followTarget = playerObject == null ? null : playerObject.transform;
        }

        private void EnsureVisuals()
        {
            if (keyRoot == null)
            {
                var key = GameObject.CreatePrimitive(PrimitiveType.Cube);
                key.name = "HeavyIronKeyPickup";
                key.transform.SetParent(transform, false);
                key.transform.localScale = new Vector3(0.42f, 0.08f, 0.14f);
                keyRoot = key.transform;

                var collider = key.GetComponent<Collider>();
                if (collider != null)
                {
                    if (Application.isPlaying)
                    {
                        Destroy(collider);
                    }
                    else
                    {
                        DestroyImmediate(collider);
                    }
                }
            }

            if (label == null)
            {
                var labelObject = new GameObject("HeavyIronKeyLabel", typeof(TextMesh));
                labelObject.transform.SetParent(transform, false);
                labelObject.transform.localPosition = new Vector3(0f, 0.34f, 0f);
                label = labelObject.GetComponent<TextMesh>();
                label.text = "Heavy Iron Key Obtained";
                label.anchor = TextAnchor.MiddleCenter;
                label.alignment = TextAlignment.Center;
                label.characterSize = 0.12f;
                label.fontSize = 42;
                label.color = new Color(1f, 0.86f, 0.22f, 1f);

                var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf")
                    ?? Resources.GetBuiltinResource<Font>("Arial.ttf");
                if (font != null)
                {
                    label.font = font;
                    var renderer = labelObject.GetComponent<MeshRenderer>();
                    if (renderer != null)
                    {
                        renderer.sharedMaterial = font.material;
                    }
                }
            }

            if (keyMaterial == null)
            {
                keyMaterial = CreateMaterial(new Color(1f, 0.72f, 0.12f, 1f));
            }

            var keyRenderer = keyRoot.GetComponent<Renderer>();
            if (keyRenderer != null)
            {
                keyRenderer.sharedMaterial = keyMaterial;
            }
        }

        private void ApplyVisibleState()
        {
            if (keyRoot != null)
            {
                keyRoot.gameObject.SetActive(keyVisible);
            }

            if (label != null)
            {
                label.gameObject.SetActive(keyVisible);
            }
        }

        private static Material CreateMaterial(Color color)
        {
            var shader = Shader.Find("Universal Render Pipeline/Unlit")
                ?? Shader.Find("Unlit/Color")
                ?? Shader.Find("Universal Render Pipeline/Lit")
                ?? Shader.Find("Standard")
                ?? Shader.Find("Sprites/Default");
            if (shader == null)
            {
                return null;
            }

            var material = new Material(shader)
            {
                color = color
            };
            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }

            if (material.HasProperty("_Color"))
            {
                material.SetColor("_Color", color);
            }

            return material;
        }

        private static void FaceCamera(TextMesh textMesh)
        {
            if (textMesh == null || Camera.main == null)
            {
                return;
            }

            var labelTransform = textMesh.transform;
            var direction = labelTransform.position - Camera.main.transform.position;
            if (direction.sqrMagnitude > 0.001f)
            {
                labelTransform.rotation = Quaternion.LookRotation(direction.normalized, Vector3.up);
            }
        }
    }
}
