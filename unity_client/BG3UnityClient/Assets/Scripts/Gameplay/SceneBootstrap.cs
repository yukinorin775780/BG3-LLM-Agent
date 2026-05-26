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

            RenderSettings.ambientLight = new Color(0.22f, 0.24f, 0.28f);

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

            CreateTrapMoment(root.transform, player.transform, astarion.transform);
            var bossMarker = CreateBossMoment(root.transform);
            CreateBossZone(root.transform, player.transform, bossMarker);
            CreateKeyFeedback(root.transform, player.transform);
            ConfigureCamera(player.transform);
            ConfigureLighting();
            Debug.Log("BG3 tactical room shell ready: player + 3 companions.");
        }

        private static void CreateRoom(Transform root)
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "Floor";
            floor.transform.SetParent(root, true);
            floor.transform.position = new Vector3(0f, -0.1f, 0f);
            floor.transform.localScale = new Vector3(RoomSize, 0.2f, RoomSize);
            SetMaterial(floor, new Color(0.22f, 0.24f, 0.25f));

            CreateWall(root, "NorthWall", new Vector3(0f, 1.1f, 6f), new Vector3(RoomSize, 2.2f, 0.3f));
            CreateWall(root, "SouthWall", new Vector3(0f, 1.1f, -6f), new Vector3(RoomSize, 2.2f, 0.3f));
            CreateWall(root, "WestWall", new Vector3(-6f, 1.1f, 0f), new Vector3(0.3f, 2.2f, RoomSize));
            CreateWall(root, "EastWall", new Vector3(6f, 1.1f, 0f), new Vector3(0.3f, 2.2f, RoomSize));

            var door = GameObject.CreatePrimitive(PrimitiveType.Cube);
            door.name = "DoorMarker";
            door.transform.SetParent(root, true);
            door.transform.position = new Vector3(0f, 1.05f, 5.78f);
            door.transform.localScale = new Vector3(1.8f, 2.1f, 0.22f);
            SetMaterial(door, new Color(0.12f, 0.36f, 0.52f));

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

        private static void CreateTrapMoment(Transform root, Transform player, Transform astarion)
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

        private static void CreateBossZone(Transform root, Transform player, BossEncounterMarker bossMarker)
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
        }

        private static void CreateKeyFeedback(Transform root, Transform player)
        {
            var feedbackObject = new GameObject("KeyPickupFeedback");
            feedbackObject.transform.SetParent(root, true);
            feedbackObject.transform.position = player.position + new Vector3(0.72f, 1.42f, -0.18f);
            feedbackObject.AddComponent<KeyPickupFeedback>().Configure(player);
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
            light.intensity = 1.7f;
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
