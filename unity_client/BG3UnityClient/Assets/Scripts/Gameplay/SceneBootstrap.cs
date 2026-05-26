using BG3UnityClient.Api;
using BG3UnityClient.UI;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace BG3UnityClient.Gameplay
{
    public sealed class SceneBootstrap : MonoBehaviour
    {
        private const float RoomSize = 12f;
        private const float CharacterY = 1f;
        private const float MovementHalfExtent = 5.2f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void EnsureSampleSceneBootstrap()
        {
            if (SceneManager.GetActiveScene().name == "SampleScene")
            {
                EnsureShellExists();
            }
        }

        private void Start()
        {
            EnsureShellExists();
        }

        public static void EnsureShellExists()
        {
            if (GameObject.Find("TacticalRoomRoot") != null)
            {
                return;
            }

            RenderSettings.ambientLight = new Color(0.13f, 0.15f, 0.18f);

            var root = new GameObject("TacticalRoomRoot");
            CreateRoom(root.transform);

            var player = CreateCapsule(
                "Player",
                new Vector3(0f, CharacterY, -2f),
                new Color(1f, 0.48f, 0.12f));
            player.transform.SetParent(root.transform, true);
            player.transform.rotation = Quaternion.LookRotation(Vector3.forward, Vector3.up);
            player.AddComponent<PlayerController>().ConfigureBounds(MovementHalfExtent, MovementHalfExtent);

            var astarion = CreateCompanion(root.transform, "Astarion", new Vector3(-0.65f, CharacterY, -3.25f), new Color(0.48f, 0.05f, 0.08f), player.transform, 1.35f, -0.55f);
            CreateCompanion(root.transform, "Shadowheart", new Vector3(0.65f, CharacterY, -4.35f), new Color(0.18f, 0.12f, 0.42f), player.transform, 2.35f, 0.55f);
            CreateCompanion(root.transform, "Lae'zel", new Vector3(0f, CharacterY, -5.2f), new Color(0.18f, 0.48f, 0.18f), player.transform, 3.25f, 0f);

            var studyRoot = CreateSecretStudyPresentation(root.transform);
            var gribboLabRoot = CreateGribboLabPresentation(root.transform);
            var trapZone = CreateTrapMoment(root.transform, player.transform, astarion.transform);
            var bossMarker = CreateBossMoment(root.transform);
            var bossZone = CreateBossZone(root.transform, player.transform, bossMarker);
            var keyFeedback = CreateKeyFeedback(root.transform, player.transform);
            var actFlow = CreateActFlow(root.transform, player.transform, trapZone, bossMarker, bossZone, keyFeedback, studyRoot.transform, gribboLabRoot.transform);
            CreateAct2CorridorTrigger(root.transform, player.transform, actFlow);
            ConfigureCamera(player.transform);
            ConfigureLighting();
            Debug.Log("BG3 tactical room shell ready: player + 3 companions + curated Act Flow.");
        }

        private static void CreateRoom(Transform root)
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "Floor";
            floor.transform.SetParent(root, true);
            floor.transform.position = new Vector3(0f, -0.1f, 0f);
            floor.transform.localScale = new Vector3(RoomSize, 0.2f, RoomSize);
            SetMaterial(floor, new Color(0.12f, 0.125f, 0.13f));

            CreateFloorInset(root, "CorridorRunner", new Vector3(0f, 0.012f, -1.15f), new Vector3(2.45f, 0.035f, 8.2f), new Color(0.16f, 0.17f, 0.17f));
            CreateFloorInset(root, "BossArenaFloor", new Vector3(0f, 0.02f, 3.7f), new Vector3(5.2f, 0.045f, 3.35f), new Color(0.18f, 0.13f, 0.145f));

            CreateWall(root, "NorthWall", new Vector3(0f, 1.1f, 6f), new Vector3(RoomSize, 2.2f, 0.3f));
            CreateWall(root, "SouthWall", new Vector3(0f, 1.1f, -6f), new Vector3(RoomSize, 2.2f, 0.3f));
            CreateWall(root, "WestWall", new Vector3(-6f, 1.1f, 0f), new Vector3(0.3f, 2.2f, RoomSize));
            CreateWall(root, "EastWall", new Vector3(6f, 1.1f, 0f), new Vector3(0.3f, 2.2f, RoomSize));
            CreateWallBlocks(root);

            var door = GameObject.CreatePrimitive(PrimitiveType.Cube);
            door.name = "DoorMarker";
            door.transform.SetParent(root, true);
            door.transform.position = new Vector3(0f, 1.05f, 5.78f);
            door.transform.localScale = new Vector3(1.8f, 2.1f, 0.22f);
            SetMaterial(door, new Color(0.14f, 0.23f, 0.31f));

        }

        private static void CreateFloorInset(Transform root, string name, Vector3 position, Vector3 scale, Color color)
        {
            var inset = GameObject.CreatePrimitive(PrimitiveType.Cube);
            inset.name = name;
            inset.transform.SetParent(root, true);
            inset.transform.position = position;
            inset.transform.localScale = scale;
            SetMaterial(inset, color);

            var collider = inset.GetComponent<Collider>();
            if (collider != null)
            {
                if (Application.isPlaying)
                {
                    Object.Destroy(collider);
                }
                else
                {
                    Object.DestroyImmediate(collider);
                }
            }
        }

        private static void CreateWallBlocks(Transform root)
        {
            for (var i = -4; i <= 4; i += 2)
            {
                CreateWall(root, $"NorthBlock_{i}", new Vector3(i, 0.72f, 5.72f), new Vector3(0.82f, 1.44f, 0.36f));
                CreateWall(root, $"SouthBlock_{i}", new Vector3(i, 0.72f, -5.72f), new Vector3(0.82f, 1.44f, 0.36f));
            }

            CreateWall(root, "WestBossBlock", new Vector3(-5.72f, 0.82f, 3.65f), new Vector3(0.36f, 1.64f, 1.1f));
            CreateWall(root, "EastBossBlock", new Vector3(5.72f, 0.82f, 3.65f), new Vector3(0.36f, 1.64f, 1.1f));
            CreateWall(root, "DoorLintel", new Vector3(0f, 2.28f, 5.55f), new Vector3(2.35f, 0.32f, 0.5f));
        }

        private static void CreateWall(Transform root, string name, Vector3 position, Vector3 scale)
        {
            var wall = GameObject.CreatePrimitive(PrimitiveType.Cube);
            wall.name = name;
            wall.transform.SetParent(root, true);
            wall.transform.position = position;
            wall.transform.localScale = scale;
            SetMaterial(wall, new Color(0.32f, 0.33f, 0.36f));
        }

        private static GameObject CreateCapsule(string name, Vector3 position, Color color)
        {
            var capsule = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            capsule.name = name;
            capsule.transform.position = position;
            capsule.transform.localScale = new Vector3(0.58f, 1f, 0.58f);
            SetMaterial(capsule, color);
            return capsule;
        }

        private static GameObject CreateCompanion(
            Transform root,
            string name,
            Vector3 position,
            Color color,
            Transform player,
            float distance,
            float sideOffset)
        {
            var companion = CreateCapsule(name, position, color);
            companion.transform.SetParent(root, true);
            companion.AddComponent<CompanionFollower>().Configure(player, distance, sideOffset, MovementHalfExtent, MovementHalfExtent);
            return companion;
        }

        private static TrapZone CreateTrapMoment(Transform root, Transform player, Transform astarion)
        {
            var trapPosition = new Vector3(2.3f, 0f, 1.55f);

            var markerObject = new GameObject("GasTrapMarker");
            markerObject.transform.SetParent(root, true);
            var marker = markerObject.AddComponent<TrapMarker>();
            marker.Configure(trapPosition);

            var zoneObject = new GameObject("GasTrapProximityZone");
            zoneObject.transform.SetParent(root, true);
            zoneObject.transform.position = trapPosition;
            var zone = zoneObject.AddComponent<TrapZone>();
            zone.Configure(
                Object.FindAnyObjectByType<BackendClient>(),
                marker,
                player,
                astarion,
                Object.FindAnyObjectByType<BackendDebugPanel>(),
                Object.FindAnyObjectByType<BarkPanel>());
            return zone;
        }

        private static BossEncounterMarker CreateBossMoment(Transform root)
        {
            var bossObject = new GameObject("BossEncounterMarker");
            bossObject.transform.SetParent(root, true);
            var bossMarker = bossObject.AddComponent<BossEncounterMarker>();
            bossMarker.Configure(
                new Vector3(-2.8f, CharacterY, 3.45f),
                new Vector3(0f, 1.05f, 5.65f),
                new Vector3(2.85f, 0.5f, 3.1f));
            return bossMarker;
        }

        private static BossEncounterZone CreateBossZone(Transform root, Transform player, BossEncounterMarker bossMarker)
        {
            var zoneObject = new GameObject("BossEncounterZone");
            zoneObject.transform.SetParent(root, true);
            zoneObject.transform.position = new Vector3(-1.85f, 0f, 3.65f);
            var zone = zoneObject.AddComponent<BossEncounterZone>();
            zone.Configure(
                player,
                bossMarker,
                Object.FindAnyObjectByType<BackendDebugPanel>(),
                2.35f);
            return zone;
        }

        private static KeyPickupFeedback CreateKeyFeedback(Transform root, Transform player)
        {
            var feedbackObject = new GameObject("KeyPickupFeedback");
            feedbackObject.transform.SetParent(root, true);
            feedbackObject.transform.position = player.position + new Vector3(0.72f, 1.42f, -0.18f);
            var feedback = feedbackObject.AddComponent<KeyPickupFeedback>();
            feedback.Configure(player);
            return feedback;
        }

        private static GameObject CreateSecretStudyPresentation(Transform root)
        {
            var studyRoot = new GameObject("Act3SecretStudyPresentation");
            studyRoot.transform.SetParent(root, true);

            var desk = GameObject.CreatePrimitive(PrimitiveType.Cube);
            desk.name = "SecretStudyDesk";
            desk.transform.SetParent(studyRoot.transform, true);
            desk.transform.position = new Vector3(-3.85f, 0.42f, 1.22f);
            desk.transform.localScale = new Vector3(1.75f, 0.32f, 0.72f);
            SetMaterial(desk, new Color(0.28f, 0.22f, 0.16f));

            CreateReadableMarker(studyRoot.transform, "ChemicalNotesMarker", "Chemical Notes", new Vector3(-4.25f, 0.68f, 1.08f), new Color(0.64f, 0.9f, 0.7f));
            CreateReadableMarker(studyRoot.transform, "NecromancerDiaryMarker", "Necromancer Diary", new Vector3(-3.42f, 0.68f, 1.08f), new Color(0.92f, 0.74f, 0.42f));
            CreateWorldLabel(studyRoot.transform, "SecretStudyLabel", "Act3 Secret Study", new Vector3(-3.84f, 1.34f, 1.02f), new Color(0.92f, 0.94f, 1f));
            return studyRoot;
        }

        private static GameObject CreateGribboLabPresentation(Transform root)
        {
            var labRoot = new GameObject("Act4GribboLabPresentation");
            labRoot.transform.SetParent(root, true);
            CreateWorldLabel(labRoot.transform, "GribboLabLabel", "Act4 Gribbo Lab", new Vector3(0f, 1.72f, 4.55f), new Color(0.86f, 1f, 0.38f));
            return labRoot;
        }

        private static ActFlowController CreateActFlow(
            Transform root,
            Transform player,
            TrapZone trapZone,
            BossEncounterMarker bossMarker,
            BossEncounterZone bossZone,
            KeyPickupFeedback keyFeedback,
            Transform studyRoot,
            Transform labRoot)
        {
            var flowObject = new GameObject("ActFlowController");
            flowObject.transform.SetParent(root, true);
            var flow = flowObject.AddComponent<ActFlowController>();
            flow.Configure(
                Object.FindAnyObjectByType<BackendClient>(),
                Object.FindAnyObjectByType<BackendDebugPanel>(),
                Object.FindAnyObjectByType<BarkPanel>(),
                trapZone,
                bossMarker,
                bossZone,
                keyFeedback,
                player,
                studyRoot,
                labRoot);
            return flow;
        }

        private static void CreateAct2CorridorTrigger(Transform root, Transform player, ActFlowController actFlow)
        {
            var triggerObject = new GameObject("Act2CorridorTrigger");
            triggerObject.transform.SetParent(root, true);
            triggerObject.transform.position = new Vector3(0f, 0f, -0.58f);
            triggerObject.AddComponent<ActFlowTriggerZone>().Configure(
                actFlow,
                player,
                ActFlowStage.Act2PoisonCorridor,
                1.25f);
            CreateWorldLabel(root, "CorridorTriggerLabel", "Corridor", new Vector3(-1.15f, 0.2f, -0.58f), new Color(0.58f, 0.82f, 1f));
        }

        private static void CreateReadableMarker(Transform root, string name, string label, Vector3 position, Color color)
        {
            var marker = GameObject.CreatePrimitive(PrimitiveType.Cube);
            marker.name = name;
            marker.transform.SetParent(root, true);
            marker.transform.position = position;
            marker.transform.localScale = new Vector3(0.36f, 0.04f, 0.26f);
            SetMaterial(marker, color);
            CreateWorldLabel(root, $"{name}Label", label, position + new Vector3(0f, 0.34f, 0f), color);
        }

        private static WorldBillboardLabel CreateWorldLabel(Transform root, string objectName, string label, Vector3 position, Color color)
        {
            var labelObject = new GameObject(objectName, typeof(WorldBillboardLabel));
            labelObject.transform.SetParent(root, true);
            labelObject.transform.position = position;
            var billboard = labelObject.GetComponent<WorldBillboardLabel>();
            var width = Mathf.Clamp(label.Length * 0.058f, 0.42f, 1.12f);
            billboard.Configure(label, position, color, new Color(0.018f, 0.022f, 0.028f, 0.76f), new Vector2(width, 0.16f));
            return billboard;
        }

        private static void ConfigureCamera(Transform player)
        {
            var camera = Camera.main;
            if (camera == null)
            {
                var cameraObject = new GameObject("Main Camera", typeof(Camera), typeof(AudioListener));
                cameraObject.tag = "MainCamera";
                camera = cameraObject.GetComponent<Camera>();
            }

            camera.fieldOfView = 45f;
            camera.nearClipPlane = 0.1f;
            camera.farClipPlane = 100f;

            var follow = camera.GetComponent<TopDownCameraFollow>();
            if (follow == null)
            {
                follow = camera.gameObject.AddComponent<TopDownCameraFollow>();
            }

            camera.transform.position = player.position + new Vector3(0f, 8.5f, -7.5f);
            camera.transform.LookAt(player.position + Vector3.up * 0.8f, Vector3.up);
            follow.Configure(player);
        }

        private static void ConfigureLighting()
        {
            var light = Object.FindAnyObjectByType<Light>();
            if (light == null)
            {
                var lightObject = new GameObject("Directional Light", typeof(Light));
                light = lightObject.GetComponent<Light>();
                light.type = LightType.Directional;
            }

            light.transform.rotation = Quaternion.Euler(50f, -35f, 0f);
            light.color = new Color(1f, 0.94f, 0.84f);
            light.intensity = 1.25f;

            var bossLightObject = new GameObject("BossArenaWarmLight", typeof(Light));
            var bossLight = bossLightObject.GetComponent<Light>();
            bossLight.type = LightType.Point;
            bossLight.transform.position = new Vector3(0f, 3.1f, 3.75f);
            bossLight.color = new Color(1f, 0.65f, 0.36f);
            bossLight.intensity = 1.3f;
            bossLight.range = 5.6f;
        }

        private static void SetMaterial(GameObject target, Color color)
        {
            var renderer = target.GetComponent<Renderer>();
            if (renderer == null)
            {
                return;
            }

            var shader = Shader.Find("Universal Render Pipeline/Unlit")
                ?? Shader.Find("Unlit/Color")
                ?? Shader.Find("Universal Render Pipeline/Lit")
                ?? Shader.Find("Standard")
                ?? Shader.Find("Sprites/Default");
            if (shader == null)
            {
                return;
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

            renderer.sharedMaterial = material;
        }
    }
}
