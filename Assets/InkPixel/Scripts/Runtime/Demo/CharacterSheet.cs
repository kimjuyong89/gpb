// InkPixel demo — 128x64 character sheet slicing (ASSET_SPEC §5.1) identical to GPA's RegionView.Frames.
using System.Collections.Generic;
using UnityEngine;

namespace InkPixel.Demo
{
    /// <summary>
    /// Static slicer for the §5.1 character sheet layout:
    /// columns 0-3 = walk for directions down, up, left, right with rows 0-3 = frames (row 0 = standing);
    /// columns 4-7 = attack for the same directions with rows 0-2 = wind-up, strike, recover and
    /// row 3 = hurt pose. Every cell is 16x16 and sliced as
    /// rect = (col*16, tex.height - (row+1)*16, 16, 16) with Sprite.Create(tex, rect, Vector2.zero, 16),
    /// exactly what GPA's RegionView.Frames / Ui.Frame do. Results are cached per texture.
    /// </summary>
    public static class CharacterSheet
    {
        public const int FrameSize = 16;
        /// <summary>down, up, left, right (sheet column order).</summary>
        public const int DirectionCount = 4;
        public const int WalkFrameCount = 4;
        public const int AttackFrameCount = 3;
        /// <summary>First attack column (columns 4-7).</summary>
        public const int AttackColumn = 4;
        /// <summary>Row of the hurt pose in the attack columns.</summary>
        public const int HurtRow = 3;
        public const int SheetWidth = 128;
        public const int SheetHeight = 64;

        public const int Down = 0;
        public const int Up = 1;
        public const int Left = 2;
        public const int Right = 3;
        public static readonly string[] DirectionNames = { "down", "up", "left", "right" };

        private static readonly Dictionary<Texture2D, Sprite[,]> walkCache = new Dictionary<Texture2D, Sprite[,]>();
        private static readonly Dictionary<Texture2D, Sprite[,]> attackCache = new Dictionary<Texture2D, Sprite[,]>();
        private static readonly Dictionary<Texture2D, Sprite[]> hurtCache = new Dictionary<Texture2D, Sprite[]>();

        /// <summary>Walk frames [direction, frame] — GPA RegionView.Frames(sheet). Null for a null sheet.</summary>
        public static Sprite[,] Frames(Texture2D sheet)
        {
            if (sheet == null) return null;
            Sprite[,] frames;
            if (walkCache.TryGetValue(sheet, out frames) && Alive(frames)) return frames;
            frames = new Sprite[DirectionCount, WalkFrameCount];
            for (int d = 0; d < DirectionCount; d++)
                for (int i = 0; i < WalkFrameCount; i++)
                    frames[d, i] = Cell(sheet, d, i);
            walkCache[sheet] = frames;
            return frames;
        }

        /// <summary>Attack frames [direction, frame 0..2] from columns 4-7, rows 0-2. Null for a null sheet.</summary>
        public static Sprite[,] AttackFrames(Texture2D sheet)
        {
            if (sheet == null) return null;
            Sprite[,] frames;
            if (attackCache.TryGetValue(sheet, out frames) && Alive(frames)) return frames;
            frames = new Sprite[DirectionCount, AttackFrameCount];
            for (int d = 0; d < DirectionCount; d++)
                for (int i = 0; i < AttackFrameCount; i++)
                    frames[d, i] = Cell(sheet, AttackColumn + d, i);
            attackCache[sheet] = frames;
            return frames;
        }

        /// <summary>Hurt pose per direction from columns 4-7, row 3. Null for a null sheet.</summary>
        public static Sprite[] Hurt(Texture2D sheet)
        {
            if (sheet == null) return null;
            Sprite[] frames;
            if (hurtCache.TryGetValue(sheet, out frames) && Alive(frames)) return frames;
            frames = new Sprite[DirectionCount];
            for (int d = 0; d < DirectionCount; d++)
                frames[d] = Cell(sheet, AttackColumn + d, HurtRow);
            hurtCache[sheet] = frames;
            return frames;
        }

        /// <summary>One 16x16 cell: rect = (col*16, tex.height - (row+1)*16, 16, 16), pivot (0,0), PPU 16 (GPA Ui.Frame).</summary>
        public static Sprite Cell(Texture2D sheet, int col, int row)
        {
            return CellSlicer.Slice(sheet, col, row, 1, 1);
        }

        /// <summary>True when the texture is at least 64x64 (four walk columns and rows fit).</summary>
        public static bool HasWalkColumns(Texture2D sheet)
        {
            return sheet != null && sheet.width >= DirectionCount * FrameSize && sheet.height >= WalkFrameCount * FrameSize;
        }

        /// <summary>True when the texture is at least 128x64 (attack and hurt columns exist).</summary>
        public static bool HasAttackColumns(Texture2D sheet)
        {
            return sheet != null && sheet.width >= (AttackColumn + DirectionCount) * FrameSize && sheet.height >= WalkFrameCount * FrameSize;
        }

        /// <summary>True for the exact §5.1 size (128x64).</summary>
        public static bool IsStandardSheet(Texture2D sheet)
        {
            return sheet != null && sheet.width == SheetWidth && sheet.height == SheetHeight;
        }

        /// <summary>Direction that faces back toward <paramref name="direction"/> (GPA's "NPC looks at the hero").</summary>
        public static int Opposite(int direction)
        {
            switch (direction)
            {
                case Down: return Up;
                case Up: return Down;
                case Left: return Right;
                default: return Left;
            }
        }

        /// <summary>Walk frame index GPA shows at <paramref name="time"/> while walking: (int)(time * 8) % 4.</summary>
        public static int WalkFrameAt(float time)
        {
            int i = (int)(time * 8f) % WalkFrameCount;
            return i < 0 ? i + WalkFrameCount : i;
        }

        public static void ClearCache()
        {
            walkCache.Clear();
            attackCache.Clear();
            hurtCache.Clear();
        }

        // A cached entry is reusable when its first sprite was never created (true null) or is still alive;
        // a destroyed sprite (fake null after a scene reload) forces re-slicing.
        private static bool Alive(Sprite[,] frames)
        {
            if (frames == null) return false;
            Sprite s = frames[0, 0];
            return ReferenceEquals(s, null) || s != null;
        }

        private static bool Alive(Sprite[] frames)
        {
            if (frames == null || frames.Length == 0) return false;
            Sprite s = frames[0];
            return ReferenceEquals(s, null) || s != null;
        }
    }
}
