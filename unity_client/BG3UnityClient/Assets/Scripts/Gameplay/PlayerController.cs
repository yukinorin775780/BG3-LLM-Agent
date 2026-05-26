using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.UI;

namespace BG3UnityClient.Gameplay
{
    public sealed class PlayerController : MonoBehaviour
    {
        [SerializeField] private float moveSpeed = 4f;
        [SerializeField] private Vector2 roomBounds = new Vector2(5.35f, 5.35f);

        public Vector3 LastMoveDirection { get; private set; } = Vector3.forward;

        public void ConfigureBounds(float halfWidth, float halfDepth)
        {
            roomBounds = new Vector2(halfWidth, halfDepth);
        }

        private void Update()
        {
            ClearUiFocusOnWorldClick();

            if (IsTextInputFocused())
            {
                return;
            }

            var movement = ReadKeyboardMovement();
            if (movement.sqrMagnitude <= 0.001f)
            {
                return;
            }

            movement.Normalize();
            LastMoveDirection = movement;
            transform.rotation = Quaternion.LookRotation(movement, Vector3.up);

            var nextPosition = transform.position + movement * moveSpeed * Time.deltaTime;
            nextPosition.x = Mathf.Clamp(nextPosition.x, -roomBounds.x, roomBounds.x);
            nextPosition.z = Mathf.Clamp(nextPosition.z, -roomBounds.y, roomBounds.y);
            transform.position = nextPosition;
        }

        private static Vector3 ReadKeyboardMovement()
        {
            var keyboard = Keyboard.current;
            if (keyboard == null)
            {
                return Vector3.zero;
            }

            var x = 0f;
            var z = 0f;

            if (keyboard.aKey.isPressed || keyboard.leftArrowKey.isPressed)
            {
                x -= 1f;
            }

            if (keyboard.dKey.isPressed || keyboard.rightArrowKey.isPressed)
            {
                x += 1f;
            }

            if (keyboard.sKey.isPressed || keyboard.downArrowKey.isPressed)
            {
                z -= 1f;
            }

            if (keyboard.wKey.isPressed || keyboard.upArrowKey.isPressed)
            {
                z += 1f;
            }

            return new Vector3(x, 0f, z);
        }

        private static bool IsTextInputFocused()
        {
            var selected = EventSystem.current == null ? null : EventSystem.current.currentSelectedGameObject;
            if (selected == null)
            {
                return false;
            }

            return selected.GetComponent<InputField>() != null || selected.GetComponentInParent<InputField>() != null;
        }

        private static void ClearUiFocusOnWorldClick()
        {
            if (Mouse.current == null || EventSystem.current == null)
            {
                return;
            }

            if (Mouse.current.leftButton.wasPressedThisFrame && !EventSystem.current.IsPointerOverGameObject())
            {
                EventSystem.current.SetSelectedGameObject(null);
            }
        }
    }
}
