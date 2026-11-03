// InkPixel demo — runtime cell slicing identical to GPA's World/RegionView.Slice (ASSET_SPEC §7, §7.2).
using System.Collections.Generic;
using UnityEngine;

namespace InkPixel.Demo
{
    /// <summary>
    /// Slices 16px cells out of a sheet exactly like GPA's RegionView.Slice:
    /// rect = (cell.x*16, tex.height - (cell.y + size.y)*16, size.x*16, size.y*16), pivot (0,0), PPU 16.
    /// Cells are counted from the TOP-LEFT of the PNG (the same convention as the sidecars and
    /// GPA's TileDef.cell). Sprites are cached per texture and rect; a rect outside the texture
    /// yields null with one warning instead of an exception.
    /// </summary>
    public static class CellSlicer
    {
        public const int Cell = InkPixelPaths.CellSize;

        private static readonly Dictionary<Texture2D, Dictionary<RectInt, Sprite>> cache = new Dictionary<Texture2D, Dictionary<RectInt, Sprite>>();
        private static readonly HashSet<string> warned = new HashSet<string>();

        /// <summary>GPA RegionView.Slice(sheet, cell, size).</summary>
        public static Sprite Slice(Texture2D sheet, Vector2Int cell, Vector2Int size)
        {
            return Slice(sheet, cell.x, cell.y, size.x, size.y);
        }

        /// <summary>GPA RegionView.Slice with the cell and size spelled out (sizes below 1 are clamped to 1).</summary>
        public static Sprite Slice(Texture2D sheet, int cellX, int cellY, int sizeX = 1, int sizeY = 1)
        {
            if (sheet == null) return null;
            if (sizeX < 1) sizeX = 1;
            if (sizeY < 1) sizeY = 1;
            var rect = new RectInt(cellX * Cell, sheet.height - (cellY + sizeY) * Cell, sizeX * Cell, sizeY * Cell);
            return SliceRect(sheet, rect);
        }

        /// <summary>
        /// A sprite for an arbitrary pixel rect (Unity bottom-left based) with pivot (0,0) and PPU 16,
        /// created with Sprite.Create exactly like GPA. Cached; null (with one warning) when the rect
        /// does not fit the texture.
        /// </summary>
        public static Sprite SliceRect(Texture2D sheet, RectInt rect)
        {
            if (sheet == null) return null;
            Dictionary<RectInt, Sprite> perTexture;
            if (!cache.TryGetValue(sheet, out perTexture))
            {
                perTexture = new Dictionary<RectInt, Sprite>();
                cache[sheet] = perTexture;
            }
            Sprite sprite;
            if (perTexture.TryGetValue(rect, out sprite) && sprite != null) return sprite;

            if (rect.width <= 0 || rect.height <= 0 || rect.xMin < 0 || rect.yMin < 0 || rect.xMax > sheet.width || rect.yMax > sheet.height)
            {
                string key = sheet.name + "|" + rect.x + "," + rect.y + "," + rect.width + "," + rect.height;
                if (warned.Add(key))
                    Debug.LogWarning("[InkPixel] CellSlicer: rect " + rect + " lies outside '" + sheet.name + "' (" + sheet.width + "x" + sheet.height + "); no sprite.");
                return null;
            }

            sprite = Sprite.Create(sheet, new Rect(rect.x, rect.y, rect.width, rect.height), Vector2.zero, InkPixelPaths.PixelsPerUnit);
            sprite.name = sheet.name + "_" + rect.x + "_" + rect.y + "_" + rect.width + "x" + rect.height;
            perTexture[rect] = sprite;
            return sprite;
        }

        /// <summary>Number of sprites currently cached (diagnostics).</summary>
        public static int CachedCount
        {
            get
            {
                int n = 0;
                foreach (KeyValuePair<Texture2D, Dictionary<RectInt, Sprite>> kv in cache) n += kv.Value.Count;
                return n;
            }
        }

        /// <summary>Forgets every cached sprite (they are plain objects; Unity frees unreferenced ones on scene load).</summary>
        public static void ClearCache()
        {
            cache.Clear();
            warned.Clear();
        }
    }
}
