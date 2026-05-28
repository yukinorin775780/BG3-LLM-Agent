using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class ObjectiveMarker : MonoBehaviour
    {
        [SerializeField] private string markerLabel = "Objective";
        [SerializeField] private Color markerColor = new Color(0.58f, 0.82f, 1f, 0.86f);
        [SerializeField] private Vector3 ringBaseScale = new Vector3(0.88f, 0.024f, 0.88f);
        [SerializeField] private Transform ringRoot;
        [SerializeField] private Transform beaconRoot;
        [SerializeField] private WorldBillboardLabel label;

        private Material ringMaterial;
        private Material beaconMaterial;
        private readonly Vector3 beaconBaseScale = new Vector3(0.08f, 0.32f, 0.08f);

        public void Configure(string labelText, Vector3 worldPosition, Color color, Vector3 ringScale)
        {
            markerLabel = string.IsNullOrEmpty(labelText) ? "Objective" : labelText;
            markerColor = color;
            ringBaseScale = ringScale;
            transform.position = worldPosition;
            EnsureVisuals();
            ApplyColor();
        }

        private void Awake()
        {
            EnsureVisuals();
            ApplyColor();
        }

        private void Update()
        {
            if (ringRoot != null)
            {
                var pulse = 1f + Mathf.Sin(Time.time * 4.2f) * 0.09f;
                ringRoot.localScale = ringBaseScale * pulse;
            }

            if (beaconRoot != null)
            {
                var hover = Mathf.Sin(Time.time * 3.2f) * 0.08f;
                beaconRoot.localPosition = new Vector3(0f, 0.72f + hover, 0f);
            }
        }

        private void EnsureVisuals()
        {
            if (ringRoot == null)
            {
                ringRoot = CreateCylinder("ObjectiveRing", ringBaseScale, new Vector3(0f, 0.052f, 0f)).transform;
                ringRoot.SetParent(transform, false);
            }

            if (beaconRoot == null)
            {
                beaconRoot = CreateCylinder("ObjectiveBeacon", beaconBaseScale, new Vector3(0f, 0.72f, 0f)).transform;
                beaconRoot.SetParent(transform, false);
            }

            if (label == null)
            {
                var labelObject = new GameObject("ObjectiveLabel", typeof(WorldBillboardLabel));
                labelObject.transform.SetParent(transform, false);
                label = labelObject.GetComponent<WorldBillboardLabel>();
            }

            if (ringMaterial == null)
            {
                ringMaterial = CreateMaterial(markerColor, true);
            }

            if (beaconMaterial == null)
            {
                beaconMaterial = CreateMaterial(new Color(markerColor.r, markerColor.g, markerColor.b, 0.58f), true);
            }

            SetRendererMaterial(ringRoot, ringMaterial);
            SetRendererMaterial(beaconRoot, beaconMaterial);

            if (label != null)
            {
                var width = Mathf.Clamp(markerLabel.Length * 0.06f, 0.58f, 1.32f);
                label.Configure(
                    markerLabel,
                    transform.position + new Vector3(0f, 1.12f, 0f),
                    new Color(markerColor.r, markerColor.g, markerColor.b, 1f),
                    new Color(0.018f, 0.022f, 0.028f, 0.8f),
                    new Vector2(width, 0.17f));
            }
        }

        private void ApplyColor()
        {
            SetMaterialColor(ringMaterial, markerColor);
            SetMaterialColor(beaconMaterial, new Color(markerColor.r, markerColor.g, markerColor.b, 0.58f));
            if (label != null)
            {
                label.SetText(markerLabel);
            }
        }

        private static GameObject CreateCylinder(string objectName, Vector3 localScale, Vector3 localPosition)
        {
            var visual = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            visual.name = objectName;
            visual.transform.localPosition = localPosition;
            visual.transform.localScale = localScale;

            var collider = visual.GetComponent<Collider>();
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

            return visual;
        }

        private static Material CreateMaterial(Color color, bool transparent)
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

            var material = new Material(shader);
            if (transparent)
            {
                material.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
                SetFloatIfPresent(material, "_Surface", 1f);
                SetFloatIfPresent(material, "_Blend", 0f);
                SetIntIfPresent(material, "_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
                SetIntIfPresent(material, "_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
                SetIntIfPresent(material, "_ZWrite", 0);
                material.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            }

            SetMaterialColor(material, color);
            return material;
        }

        private static void SetRendererMaterial(Transform target, Material material)
        {
            var renderer = target == null ? null : target.GetComponent<Renderer>();
            if (renderer != null && material != null)
            {
                renderer.sharedMaterial = material;
            }
        }

        private static void SetMaterialColor(Material material, Color color)
        {
            if (material == null)
            {
                return;
            }

            material.color = color;
            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }

            if (material.HasProperty("_Color"))
            {
                material.SetColor("_Color", color);
            }
        }

        private static void SetFloatIfPresent(Material material, string propertyName, float value)
        {
            if (material != null && material.HasProperty(propertyName))
            {
                material.SetFloat(propertyName, value);
            }
        }

        private static void SetIntIfPresent(Material material, string propertyName, int value)
        {
            if (material != null && material.HasProperty(propertyName))
            {
                material.SetInt(propertyName, value);
            }
        }
    }
}
