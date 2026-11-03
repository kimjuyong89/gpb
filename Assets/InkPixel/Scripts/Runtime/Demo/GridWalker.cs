// InkPixel demo — cell-by-cell movement state extracted from GPA's World/RegionView.cs (ASSET_SPEC §7.2).
using System;
using UnityEngine;

namespace InkPixel.Demo
{
    /// <summary>
    /// Grid walking the way GPA's RegionView does it: a current cell, a target cell and a 0..1
    /// progress; direction indices follow the sheet column order (0 down, 1 up, 2 left, 3 right);
    /// rows count from the top, so "up" decreases the row. Plain serializable class, no Unity messages.
    /// </summary>
    [Serializable]
    public class GridWalker
    {
        public const int Down = 0;
        public const int Up = 1;
        public const int Left = 2;
        public const int Right = 3;
        /// <summary>GPA RegionView.LeapReach: cells a 경공 leap can cover.</summary>
        public const int DefaultLeapReach = 3;

        /// <summary>World-space direction per index (sheet column order) — GPA RegionView.Dirs.</summary>
        public static readonly Vector2Int[] Dirs = { Vector2Int.down, Vector2Int.up, Vector2Int.left, Vector2Int.right };

        [Tooltip("Cell the walker stands on (or leaves while moving); x = column, y = row from the top.")]
        public Vector2Int cell;
        [Tooltip("Cell being walked to (equals cell when idle).")]
        public Vector2Int target;
        [Tooltip("Cell left most recently (GPA: where to return from a locked entrance).")]
        public Vector2Int previous;
        [Tooltip("Facing direction: 0 down, 1 up, 2 left, 3 right.")]
        public int facing;
        [Tooltip("0..1 progress from cell to target; 1 = idle.")]
        public float moveT = 1f;
        [Tooltip("Cells covered by the current leap, 0 when walking.")]
        public int leapCells;

        public bool Moving
        {
            get { return moveT < 1f; }
        }

        public bool Leaping
        {
            get { return leapCells > 0; }
        }

        /// <summary>Row/column delta of a direction: rows grow downward, so "up" is (0, -1) — GPA RegionView.Step.</summary>
        public static Vector2Int Step(int dir)
        {
            Vector2Int d = Dirs[Mathf.Clamp(dir, 0, 3)];
            return new Vector2Int(d.x, -d.y);
        }

        /// <summary>The direction looking back at <paramref name="dir"/> (NPCs turn to face the hero).</summary>
        public static int Opposite(int dir)
        {
            switch (dir)
            {
                case Down: return Up;
                case Up: return Down;
                case Left: return Right;
                default: return Left;
            }
        }

        /// <summary>Teleports to <paramref name="c"/> and stops.</summary>
        public void Place(Vector2Int c)
        {
            cell = target = previous = c;
            moveT = 1f;
            leapCells = 0;
        }

        /// <summary>
        /// Faces <paramref name="dir"/> and, when the next cell is walkable and nothing is in progress,
        /// starts walking there (GPA RegionView.Move). Returns true when a step started.
        /// </summary>
        public bool TryMove(int dir, Func<Vector2Int, bool> walkable)
        {
            if (Moving) return false;
            facing = Mathf.Clamp(dir, 0, 3);
            Vector2Int next = cell + Step(facing);
            if (walkable == null || !walkable(next)) return false;
            target = next;
            moveT = 0f;
            return true;
        }

        /// <summary>
        /// 경공 leap (GPA RegionView.Leap): jumps to the farthest walkable cell within <paramref name="reach"/>
        /// in the facing direction, at least two cells away. Returns false when nothing is reachable.
        /// </summary>
        public bool TryLeap(Func<Vector2Int, bool> walkable, int reach = DefaultLeapReach)
        {
            if (Moving || walkable == null) return false;
            for (int d = reach; d >= 2; d--)
            {
                Vector2Int landing = cell + Step(facing) * d;
                if (!walkable(landing)) continue;
                target = landing;
                moveT = 0f;
                leapCells = d;
                return true;
            }
            return false;
        }

        /// <summary>
        /// Advances the current step. <paramref name="cellsPerSecond"/> is the walking speed; a leap keeps
        /// its total duration independent of distance (speed / leapCells, as in GPA). Returns true in the
        /// frame the target cell is reached.
        /// </summary>
        public bool Advance(float deltaTime, float cellsPerSecond)
        {
            if (!Moving) return false;
            float speed = leapCells > 0 ? cellsPerSecond / leapCells : cellsPerSecond;
            moveT = Mathf.Min(1f, moveT + deltaTime * speed);
            if (moveT < 1f) return false;
            previous = cell;
            cell = target;
            leapCells = 0;
            return true;
        }

        /// <summary>Returns to the cell just left (GPA RegionView.StepBack).</summary>
        public void StepBack()
        {
            cell = target = previous;
            moveT = 1f;
            leapCells = 0;
        }

        /// <summary>Interpolated position between the two cells' world positions.</summary>
        public Vector2 Lerp(Vector2 fromWorld, Vector2 toWorld)
        {
            return Vector2.Lerp(fromWorld, toWorld, moveT);
        }
    }
}
