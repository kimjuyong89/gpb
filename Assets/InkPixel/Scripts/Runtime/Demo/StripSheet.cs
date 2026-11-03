// InkPixel demo — FX strip slicing by equal division, identical to GPA's UI/Ui.Strip (ASSET_SPEC §5.4, §7.2).
using System.Collections.Generic;
using UnityEngine;

namespace InkPixel.Demo
{
    /// <summary>
    /// Splits a horizontal strip into <c>count</c> equal frames the way GPA's Ui.Strip does:
    /// frame i = Ui.Frame(t, i, 0, t.width / count, t.height) =
    /// Sprite.Create(t, new Rect(i * w, t.height - h, w, h), Vector2.zero, 16) with w = width / count, h = height.
    /// Results are cached per texture and count.
    /// </summary>
    public static class StripSheet
    {
        private static readonly Dictionary<Texture2D, Dictionary<int, Sprite[]>> cache = new Dictionary<Texture2D, Dictionary<int, Sprite[]>>();
        private static readonly HashSet<string> warned = new HashSet<string>();

        /// <summary>The <paramref name="count"/> frames of <paramref name="texture"/>, left to right. Empty for a null texture.</summary>
        public static Sprite[] Strip(Texture2D texture, int count)
        {
            if (texture == null) return new Sprite[0];
            if (count < 1)
            {
                Warn(texture.name + "|count", "StripSheet: '" + texture.name + "' asked for " + count + " frame(s); using 1.");
                count = 1;
            }

            Dictionary<int, Sprite[]> perTexture;
            if (!cache.TryGetValue(texture, out perTexture))
            {
                perTexture = new Dictionary<int, Sprite[]>();
                cache[texture] = perTexture;
            }
            Sprite[] frames;
            if (perTexture.TryGetValue(count, out frames) && Alive(frames)) return frames;

            int w = texture.width / count;
            int h = texture.height;
            if (w <= 0)
            {
                Warn(texture.name + "|narrow", "StripSheet: '" + texture.name + "' (" + texture.width + "px wide) cannot hold " + count + " frame(s).");
                return new Sprite[0];
            }
            if (texture.width % count != 0)
                Warn(texture.name + "|uneven", "StripSheet: '" + texture.name + "' width " + texture.width + " is not a multiple of " + count + "; frames are " + w + "px wide.");

            frames = new Sprite[count];
            for (int i = 0; i < count; i++)
                frames[i] = CellSlicer.SliceRect(texture, new RectInt(i * w, texture.height - h, w, h));
            perTexture[count] = frames;
            return frames;
        }

        /// <summary>Frame count guessed from square frames (width / height); 1 when the texture is not a multiple of its height.</summary>
        public static int GuessFrameCount(Texture2D texture)
        {
            if (texture == null || texture.height <= 0) return 1;
            return texture.width % texture.height == 0 ? Mathf.Max(1, texture.width / texture.height) : 1;
        }

        public static void ClearCache()
        {
            cache.Clear();
            warned.Clear();
        }

        private static bool Alive(Sprite[] frames)
        {
            if (frames == null || frames.Length == 0) return false;
            Sprite s = frames[0];
            return ReferenceEquals(s, null) || s != null;
        }

        private static void Warn(string key, string message)
        {
            if (warned.Add(key)) Debug.LogWarning("[InkPixel] " + message);
        }
    }
}
