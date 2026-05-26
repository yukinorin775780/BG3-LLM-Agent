using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public enum TrapVisualState
    {
        Hidden,
        Revealed,
        Disabled,
        Triggered
    }

    public sealed class TrapMarker : MonoBehaviour
    {
        [SerializeField] private TrapVisualState state = TrapVisualState.Hidden;
        [SerializeField] private Transform markerRoot;
        [SerializeField] private Transform gasRoot;

        private Material markerMaterial;
        private Material gasMaterial;
        private Vector3 markerBaseScale = new Vector3(0.55f, 0.025f, 0.55f);
        private Vector3 gasBaseScale = new Vector3(1.65f, 0.035f, 1.65f);

        public TrapVisualState State => state;

        public void Configure(Vector3 worldPosition)
        {
            transform.position = worldPosition;
            EnsureVisuals();
            SetState(TrapVisualState.Hidden);
        }

        public void SetState(TrapVisualState nextState)
        {
            if (state == nextState && markerRoot != null && gasRoot != null)
            {
                ApplyState();
                return;
            }

            state = nextState;
            EnsureVisuals();
            ApplyState();
            Debug.Log($"BG3 trap marker state: {state}");
        }

        private void Awake()
        {
            EnsureVisuals();
            ApplyState();
        }

        private void Update()
        {
            if (markerRoot == null || !markerRoot.gameObject.activeSelf)
            {
                return;
            }

            if (state == TrapVisualState.Revealed)
            {
                var pulse = 1f + Mathf.Sin(Time.time * 4.5f) * 0.08f;
                markerRoot.localScale = markerBaseScale * pulse;
            }
            else
            {
                markerRoot.localScale = markerBaseScale;
            }
        }

        private void EnsureVisuals()
        {
            if (markerRoot == null)
            {
                markerRoot = CreateCylinder("AmberTrapMarker", markerBaseScale, new Vector3(0f, 0.045f, 0f)).transform;
                markerRoot.SetParent(transform, false);
            }

            if (gasRoot == null)
            {
                gasRoot = CreateCylinder("PoisonGasCloud", gasBaseScale, new Vector3(0f, 0.055f, 0f)).transform;
                gasRoot.SetParent(transform, false);
            }

            if (markerMaterial == null)
            {
                markerMaterial = CreateMaterial(new Color(1f, 0.58f, 0.08f, 0.88f), true);
            }

            if (gasMaterial == null)
            {
                gasMaterial = CreateMaterial(new Color(0.2f, 0.95f, 0.28f, 0.38f), true);
            }

            var markerRenderer = markerRoot.GetComponent<Renderer>();
            if (markerRenderer != null)
            {
                markerRenderer.sharedMaterial = markerMaterial;
            }

            var gasRenderer = gasRoot.GetComponent<Renderer>();
            if (gasRenderer != null)
            {
                gasRenderer.sharedMaterial = gasMaterial;
            }
        }

        private GameObject CreateCylinder(string objectName, Vector3 localScale, Vector3 localPosition)
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

        private void ApplyState()
        {
            if (markerRoot == null || gasRoot == null)
            {
                return;
            }

            markerRoot.gameObject.SetActive(state == TrapVisualState.Revealed || state == TrapVisualState.Disabled);
            gasRoot.gameObject.SetActive(state == TrapVisualState.Triggered);

            if (state == TrapVisualState.Revealed)
            {
                markerRoot.localScale = markerBaseScale;
                SetMaterialColor(markerMaterial, new Color(1f, 0.58f, 0.08f, 0.88f));
            }
            else if (state == TrapVisualState.Disabled)
            {
                markerRoot.localScale = markerBaseScale * 0.72f;
                SetMaterialColor(markerMaterial, new Color(0.58f, 0.62f, 0.64f, 0.72f));
            }
            else if (state == TrapVisualState.Triggered)
            {
                gasRoot.localScale = gasBaseScale;
                SetMaterialColor(gasMaterial, new Color(0.2f, 0.95f, 0.28f, 0.38f));
            }
        }

        private static Material CreateMaterial(Color color, bool transparent)
        {
            var shader = Shader.Find("Universal Render Pipeline/Unlit")
                ?? Shader.Find("Unlit/Color")
                ?? Shader.Find("Standard")
                ?? Shader.Find("Sprites/Default");
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
