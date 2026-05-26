using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public sealed class WorldBillboardLabel : MonoBehaviour
    {
        [SerializeField] private TextMesh textMesh;
        [SerializeField] private Transform backingRoot;
        [SerializeField] private Vector2 backingSize = new Vector2(0.58f, 0.18f);

        private Material backingMaterial;

        public void Configure(string label, Vector3 worldPosition, Color textColor, Color backingColor, Vector2 size)
        {
            transform.position = worldPosition;
            backingSize = size;
            EnsureVisuals(label, textColor, backingColor);
        }

        public void SetText(string label)
        {
            if (textMesh != null)
            {
                textMesh.text = label;
                return;
            }

            EnsureVisuals(label, Color.white, new Color(0.03f, 0.035f, 0.045f, 0.72f));
        }

        private void LateUpdate()
        {
            if (Camera.main == null)
            {
                return;
            }

            var direction = transform.position - Camera.main.transform.position;
            if (direction.sqrMagnitude > 0.001f)
            {
                transform.rotation = Quaternion.LookRotation(direction.normalized, Camera.main.transform.up);
            }
        }

        private void EnsureVisuals(string label, Color textColor, Color backingColor)
        {
            if (backingRoot == null)
            {
                var backing = GameObject.CreatePrimitive(PrimitiveType.Cube);
                backing.name = "TagBacking";
                backing.transform.SetParent(transform, false);
                backing.transform.localPosition = new Vector3(0f, 0f, 0.018f);
                backing.transform.localScale = new Vector3(backingSize.x, backingSize.y, 0.018f);
                backingRoot = backing.transform;

                var collider = backing.GetComponent<Collider>();
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

            if (textMesh == null)
            {
                var textObject = new GameObject("TagText", typeof(TextMesh));
                textObject.transform.SetParent(transform, false);
                textObject.transform.localPosition = new Vector3(0f, -0.006f, -0.018f);
                textMesh = textObject.GetComponent<TextMesh>();
                textMesh.anchor = TextAnchor.MiddleCenter;
                textMesh.alignment = TextAlignment.Center;
                textMesh.characterSize = 0.052f;
                textMesh.fontSize = 36;

                var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf")
                    ?? Resources.GetBuiltinResource<Font>("Arial.ttf");
                if (font != null)
                {
                    textMesh.font = font;
                    var renderer = textObject.GetComponent<MeshRenderer>();
                    if (renderer != null)
                    {
                        renderer.sharedMaterial = font.material;
                        renderer.sortingOrder = 12;
                    }
                }
            }

            if (backingMaterial == null)
            {
                backingMaterial = CreateMaterial(backingColor, true);
            }

            if (backingRoot != null)
            {
                backingRoot.localScale = new Vector3(backingSize.x, backingSize.y, 0.018f);
                var renderer = backingRoot.GetComponent<Renderer>();
                if (renderer != null && backingMaterial != null)
                {
                    renderer.sharedMaterial = backingMaterial;
                }
            }

            SetMaterialColor(backingMaterial, backingColor);
            if (textMesh != null)
            {
                textMesh.text = label;
                textMesh.color = textColor;
            }
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
