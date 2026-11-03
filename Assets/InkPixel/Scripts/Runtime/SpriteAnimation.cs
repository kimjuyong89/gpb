// InkPixel — a flip-book animation asset (ASSET_SPEC §7.2). Built by Tools/InkPixel/2. Build Animations.
using UnityEngine;

namespace InkPixel
{
    /// <summary>
    /// A list of sprite frames played at a fixed frame rate. Assets are generated from the
    /// "animations" array of a sheet's sidecar as "Generated/Animations/&lt;sheet&gt;_&lt;anim&gt;.asset"
    /// (and "&lt;sheet&gt;_strip.asset" for FX strips).
    /// </summary>
    [CreateAssetMenu(fileName = "NewSpriteAnimation", menuName = "InkPixel/Sprite Animation", order = 100)]
    public class SpriteAnimation : ScriptableObject
    {
        [Tooltip("Frames in playback order.")]
        public Sprite[] frames = new Sprite[0];

        [Tooltip("Frames per second. 0 = static (the first frame is shown and the clip completes at once).")]
        [Min(0f)]
        public float fps = 8f;

        [Tooltip("Wrap around at the end instead of stopping on the last frame.")]
        public bool loop = true;

        [Header("Metadata (filled by the editor builders, informational)")]
        [Tooltip("Sheet the frames were sliced from, e.g. \"hero_1\".")]
        public string sheet = "";
        [Tooltip("State name from the sidecar, e.g. \"walk\", \"attack\", \"idle\", \"hurt\", \"strip\".")]
        public string state = "";
        [Tooltip("\"down\", \"up\", \"left\", \"right\" or \"\" for non-directional clips.")]
        public string direction = "";

        /// <summary>Number of frames (0 when the array is missing).</summary>
        public int FrameCount
        {
            get { return frames != null ? frames.Length : 0; }
        }

        /// <summary>Seconds one frame stays on screen; 0 when fps is 0.</summary>
        public float FrameDuration
        {
            get { return fps > 0f ? 1f / fps : 0f; }
        }

        /// <summary>Total length of one pass in seconds (frames / fps); 0 for static or empty clips.</summary>
        public float Duration
        {
            get { return fps > 0f ? FrameCount / fps : 0f; }
        }

        public bool IsEmpty
        {
            get { return FrameCount == 0; }
        }

        /// <summary>Frame at <paramref name="index"/>, clamped to the valid range; null for an empty clip.</summary>
        public Sprite FrameAt(int index)
        {
            int count = FrameCount;
            if (count == 0) return null;
            if (index < 0) index = 0;
            else if (index >= count) index = count - 1;
            return frames[index];
        }

        /// <summary>Frame index shown at <paramref name="time"/> seconds (wrapping when looping, clamping otherwise).</summary>
        public int FrameIndexAt(float time)
        {
            int count = FrameCount;
            if (count == 0 || fps <= 0f) return 0;
            if (time <= 0f) return 0;
            float duration = count / fps;
            if (loop) time = Mathf.Repeat(time, duration);
            int index = Mathf.FloorToInt(time * fps);
            return index >= count ? count - 1 : index;
        }
    }
}
