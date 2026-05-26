using UnityEngine;

namespace BG3UnityClient.Gameplay
{
    public enum BossDoorVisualState
    {
        Locked,
        Ready,
        Open
    }

    public sealed class BossEncounterMarker : MonoBehaviour
    {
        [SerializeField] private Transform gribboRoot;
        [SerializeField] private Transform finalDoorRoot;
        [SerializeField] private Transform potionTankRoot;
        [SerializeField] private Transform doorHighlightRoot;
        [SerializeField] private Transform keyRoot;
        [SerializeField] private TextMesh gribboLabel;
        [SerializeField] private TextMesh doorLabel;
        [SerializeField] private bool bossReady;
        [SerializeField] private bool keyObtained;
        [SerializeField] private BossDoorVisualState doorState = BossDoorVisualState.Locked;

        private Material gribboMaterial;
        private Material doorMaterial;
        private Material tankMaterial;
        private Material highlightMaterial;
        private Material keyMaterial;
        private readonly Vector3 gribboBaseScale = new Vector3(0.72f, 1.18f, 0.72f);

        public bool BossReady => bossReady;
        public bool KeyObtained => keyObtained;
        public BossDoorVisualState DoorState => doorState;

        public void Configure(Vector3 gribboPosition, Vector3 doorPosition, Vector3 tankPosition)
        {
            EnsureVisuals(gribboPosition, doorPosition, tankPosition);
            ApplyVisualState();
        }

        public void SetBossReady(bool ready)
        {
            bossReady = ready;
            EnsureVisuals();
            ApplyVisualState();
        }

        public void SetKeyObtained(bool obtained)
        {
            keyObtained = obtained;
            if (obtained && doorState == BossDoorVisualState.Locked)
            {
                doorState = BossDoorVisualState.Ready;
            }

            EnsureVisuals();
            ApplyVisualState();
        }

        public void SetDoorOpen()
        {
            keyObtained = true;
            doorState = BossDoorVisualState.Open;
            EnsureVisuals();
            ApplyVisualState();
        }

        private void Awake()
        {
            EnsureVisuals();
            ApplyVisualState();
        }

        private void Update()
        {
            if (gribboRoot != null && bossReady && !keyObtained)
            {
                var pulse = 1f + Mathf.Sin(Time.time * 3.8f) * 0.04f;
                gribboRoot.localScale = gribboBaseScale * pulse;
            }
            else if (gribboRoot != null)
            {
                gribboRoot.localScale = gribboBaseScale;
            }
        }

        private void LateUpdate()
        {
            FaceCamera(gribboLabel);
            FaceCamera(doorLabel);
        }

        private void EnsureVisuals()
        {
            EnsureVisuals(
                gribboRoot == null ? new Vector3(-2.8f, 1f, 3.45f) : gribboRoot.position,
                finalDoorRoot == null ? new Vector3(0f, 1.05f, 5.65f) : finalDoorRoot.position,
                potionTankRoot == null ? new Vector3(2.85f, 0.5f, 3.1f) : potionTankRoot.position);
        }

        private void EnsureVisuals(Vector3 gribboPosition, Vector3 doorPosition, Vector3 tankPosition)
        {
            if (gribboRoot == null)
            {
                var gribbo = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                gribbo.name = "Gribbo";
                gribbo.transform.SetParent(transform, true);
                gribbo.transform.position = gribboPosition;
                gribbo.transform.localScale = gribboBaseScale;
                gribboRoot = gribbo.transform;
            }

            if (finalDoorRoot == null)
            {
                var door = GameObject.CreatePrimitive(PrimitiveType.Cube);
                door.name = "FinalDoorMarker";
                door.transform.SetParent(transform, true);
                door.transform.position = doorPosition;
                door.transform.localScale = new Vector3(1.65f, 2.15f, 0.26f);
                finalDoorRoot = door.transform;
            }

            if (potionTankRoot == null)
            {
                var tank = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                tank.name = "PotionTankPlaceholder";
                tank.transform.SetParent(transform, true);
                tank.transform.position = tankPosition;
                tank.transform.localScale = new Vector3(0.42f, 0.72f, 0.42f);
                potionTankRoot = tank.transform;
            }

            if (doorHighlightRoot == null)
            {
                doorHighlightRoot = CreateCylinder(
                    "FinalDoorReadyRing",
                    new Vector3(1.25f, 0.025f, 0.42f),
                    finalDoorRoot.position + new Vector3(0f, -1.02f, -0.42f)).transform;
                doorHighlightRoot.SetParent(transform, true);
            }

            if (keyRoot == null)
            {
                keyRoot = CreateCylinder(
                    "HeavyIronKeyMarker",
                    new Vector3(0.24f, 0.035f, 0.24f),
                    finalDoorRoot.position + new Vector3(0f, 1.32f, -0.3f)).transform;
                keyRoot.SetParent(transform, true);
            }

            if (gribboLabel == null)
            {
                gribboLabel = CreateLabel("GribboLabel", "Gribbo", gribboRoot.position + new Vector3(0f, 1.45f, 0f), new Color(0.86f, 1f, 0.38f, 1f));
            }

            if (doorLabel == null)
            {
                doorLabel = CreateLabel("ExitDoorLabel", "Exit Door", finalDoorRoot.position + new Vector3(0f, 1.4f, -0.2f), new Color(1f, 0.84f, 0.34f, 1f));
            }

            if (gribboMaterial == null)
            {
                gribboMaterial = CreateMaterial(new Color(0.62f, 0.76f, 0.16f, 1f));
            }

            if (doorMaterial == null)
            {
                doorMaterial = CreateMaterial(new Color(0.08f, 0.32f, 0.62f, 1f));
            }

            if (tankMaterial == null)
            {
                tankMaterial = CreateMaterial(new Color(0.32f, 0.82f, 0.34f, 1f));
            }

            if (highlightMaterial == null)
            {
                highlightMaterial = CreateMaterial(new Color(1f, 0.78f, 0.16f, 0.88f));
            }

            if (keyMaterial == null)
            {
                keyMaterial = CreateMaterial(new Color(1f, 0.72f, 0.12f, 1f));
            }

            SetRendererMaterial(gribboRoot, gribboMaterial);
            SetRendererMaterial(finalDoorRoot, doorMaterial);
            SetRendererMaterial(potionTankRoot, tankMaterial);
            SetRendererMaterial(doorHighlightRoot, highlightMaterial);
            SetRendererMaterial(keyRoot, keyMaterial);
        }

        private void ApplyVisualState()
        {
            if (gribboMaterial != null)
            {
                SetMaterialColor(gribboMaterial, keyObtained ? new Color(0.48f, 0.62f, 0.22f, 1f) : new Color(0.62f, 0.76f, 0.16f, 1f));
            }

            if (doorMaterial != null)
            {
                var doorColor = new Color(0.08f, 0.32f, 0.62f, 1f);
                if (doorState == BossDoorVisualState.Open)
                {
                    doorColor = new Color(0.08f, 0.58f, 0.32f, 1f);
                }
                else if (doorState == BossDoorVisualState.Ready)
                {
                    doorColor = new Color(0.96f, 0.66f, 0.18f, 1f);
                }

                SetMaterialColor(doorMaterial, doorColor);
            }

            if (doorHighlightRoot != null)
            {
                doorHighlightRoot.gameObject.SetActive(keyObtained || doorState != BossDoorVisualState.Locked);
            }

            if (keyRoot != null)
            {
                keyRoot.gameObject.SetActive(keyObtained);
            }

            if (finalDoorRoot != null)
            {
                finalDoorRoot.localRotation = doorState == BossDoorVisualState.Open
                    ? Quaternion.Euler(0f, 58f, 0f)
                    : Quaternion.identity;
            }
        }

        private TextMesh CreateLabel(string objectName, string label, Vector3 position, Color color)
        {
            var labelObject = new GameObject(objectName, typeof(TextMesh));
            labelObject.transform.SetParent(transform, true);
            labelObject.transform.position = position;

            var textMesh = labelObject.GetComponent<TextMesh>();
            textMesh.text = label;
            textMesh.anchor = TextAnchor.MiddleCenter;
            textMesh.alignment = TextAlignment.Center;
            textMesh.characterSize = 0.16f;
            textMesh.fontSize = 48;
            textMesh.color = color;
            var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf")
                ?? Resources.GetBuiltinResource<Font>("Arial.ttf");
            if (font != null)
            {
                textMesh.font = font;
                var renderer = labelObject.GetComponent<MeshRenderer>();
                if (renderer != null)
                {
                    renderer.sharedMaterial = font.material;
                }
            }

            return textMesh;
        }

        private static GameObject CreateCylinder(string objectName, Vector3 localScale, Vector3 position)
        {
            var visual = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            visual.name = objectName;
            visual.transform.position = position;
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

            var material = new Material(shader);
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
