// InkPixel demo — tiny UnityEngine.UI helpers (built-in LegacyRuntime font, ink/paper colors) shared by the demo.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace InkPixel.Demo
{
    /// <summary>
    /// Creates the few uGUI pieces the demo needs (overlay canvases, Text, Image) with the pack's
    /// ink / paper palette and the built-in <c>LegacyRuntime.ttf</c> font, and slices a face PNG into
    /// one full-texture sprite the way GPA's Ui.Face does.
    /// </summary>
    public static class DemoUi
    {
        /// <summary>Reference resolution of the overlay canvases (GPA's UI is designed at 1280x720).</summary>
        public static readonly Vector2 ReferenceResolution = new Vector2(1280f, 720f);

        // ASSET_SPEC §2.1 palette entries used by the UI.
        public static readonly Color Ink = Hex(0x1e1b18);
        public static readonly Color InkDark = Hex(0x3a342e);
        public static readonly Color InkLight = Hex(0x8a8378);
        public static readonly Color Paper = Hex(0xe9dec6);
        public static readonly Color PaperLight = Hex(0xf4ecdc);
        public static readonly Color Vermilion = Hex(0x9e241c);
        public static readonly Color VermilionLight = Hex(0xc4473a);
        public static readonly Color Jade = Hex(0x3f8a73);
        public static readonly Color Gold = Hex(0xc9a24a);

        private static Font font;
        private static bool fontWarned;
        private static readonly Dictionary<Texture2D, Sprite> fullSprites = new Dictionary<Texture2D, Sprite>();

        /// <summary>Color from 0xRRGGBB.</summary>
        public static Color Hex(int rgb)
        {
            return new Color(((rgb >> 16) & 0xff) / 255f, ((rgb >> 8) & 0xff) / 255f, (rgb & 0xff) / 255f, 1f);
        }

        /// <summary>The built-in dynamic font (Unity 2022+: "LegacyRuntime.ttf"); null (with one warning) when unavailable.</summary>
        public static Font DefaultFont()
        {
            if (font != null) return font;
            try
            {
                font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            }
            catch (Exception ex)
            {
                if (!fontWarned) Debug.LogWarning("[InkPixel] DemoUi: built-in font unavailable (" + ex.Message + "); labels stay empty.");
                fontWarned = true;
            }
            if (font == null && !fontWarned)
            {
                Debug.LogWarning("[InkPixel] DemoUi: Resources.GetBuiltinResource<Font>(\"LegacyRuntime.ttf\") returned null.");
                fontWarned = true;
            }
            return font;
        }

        /// <summary>A Screen Space - Overlay canvas scaled to 1280x720 with a GraphicRaycaster.</summary>
        public static Canvas CreateOverlayCanvas(string name, int sortingOrder, Transform parent = null)
        {
            var go = new GameObject(name, typeof(RectTransform));
            if (parent != null) go.transform.SetParent(parent, false);
            var canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = sortingOrder;
            canvas.pixelPerfect = true;
            var scaler = go.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = ReferenceResolution;
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = 0.5f;
            go.AddComponent<GraphicRaycaster>();
            return canvas;
        }

        /// <summary>An empty RectTransform child.</summary>
        public static RectTransform CreateRect(string name, Transform parent)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            return (RectTransform)go.transform;
        }

        /// <summary>Anchors, pivot, position and size in one call.</summary>
        public static void Layout(RectTransform rt, Vector2 anchorMin, Vector2 anchorMax, Vector2 pivot, Vector2 anchoredPosition, Vector2 size)
        {
            rt.anchorMin = anchorMin;
            rt.anchorMax = anchorMax;
            rt.pivot = pivot;
            rt.anchoredPosition = anchoredPosition;
            rt.sizeDelta = size;
        }

        /// <summary>A plain colored Image (no sprite) — the demo's panel background.</summary>
        public static Image CreateImage(string name, Transform parent, Color color)
        {
            RectTransform rt = CreateRect(name, parent);
            var image = rt.gameObject.AddComponent<Image>();
            image.color = color;
            image.raycastTarget = false;
            return image;
        }

        /// <summary>A Text using the built-in font; overflow is allowed so long labels are never clipped.</summary>
        public static Text CreateText(string name, Transform parent, string text, int fontSize, Color color, TextAnchor alignment)
        {
            RectTransform rt = CreateRect(name, parent);
            var label = rt.gameObject.AddComponent<Text>();
            label.font = DefaultFont();
            label.fontSize = fontSize;
            label.color = color;
            label.alignment = alignment;
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            label.verticalOverflow = VerticalWrapMode.Overflow;
            label.supportRichText = false;
            label.raycastTarget = false;
            label.text = text ?? "";
            return label;
        }

        /// <summary>
        /// One sprite covering the whole texture with pivot (0,0) and PPU 16 — GPA Ui.Face
        /// (Sprite.Create(t, new Rect(0, 0, t.width, t.height), Vector2.zero, 16)). Cached per texture.
        /// </summary>
        public static Sprite FullSprite(Texture2D texture)
        {
            if (texture == null) return null;
            Sprite sprite;
            if (fullSprites.TryGetValue(texture, out sprite) && sprite != null) return sprite;
            sprite = Sprite.Create(texture, new Rect(0f, 0f, texture.width, texture.height), Vector2.zero, InkPixelPaths.PixelsPerUnit);
            sprite.name = texture.name + "_full";
            fullSprites[texture] = sprite;
            return sprite;
        }

        public static void ClearCache()
        {
            fullSprites.Clear();
        }
    }
}
