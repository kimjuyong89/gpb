// InkPixel demo — loops an FX strip (ASSET_SPEC §5.4) on a SpriteRenderer using StripSheet's equal division.
using UnityEngine;

namespace InkPixel.Demo
{
    /// <summary>
    /// Plays a horizontal strip on the SpriteRenderer of the same GameObject at a fixed fps,
    /// slicing it with <see cref="StripSheet.Strip"/> (GPA Ui.Strip). fps 0 holds the first frame
    /// (Arrow / Shadow). Non-looping strips stop on their last frame and can destroy themselves.
    /// </summary>
    [AddComponentMenu("InkPixel/Strip Player")]
    [RequireComponent(typeof(SpriteRenderer))]
    [DisallowMultipleComponent]
    public class StripPlayer : MonoBehaviour
    {
        [Tooltip("Strip texture: N frames of equal width laid out left to right (e.g. FX/Slash.png).")]
        public Texture2D strip;
        [Tooltip("Number of frames in the strip (sidecar stripFrames).")]
        [Min(1)] public int frames = 1;
        [Tooltip("Playback frames per second (sidecar stripFps); 0 shows the first frame only.")]
        [Min(0f)] public float fps = 12f;
        [Tooltip("Wrap around at the end instead of stopping on the last frame.")]
        public bool loop = true;
        [Tooltip("Start playing in OnEnable.")]
        public bool playOnEnable = true;
        [Tooltip("Start at a random point of the loop so neighbouring strips are not in sync.")]
        public bool randomPhase;
        [Tooltip("Destroy the GameObject when a non-looping strip finishes.")]
        public bool destroyWhenDone;

        private SpriteRenderer spriteRenderer;
        private Sprite[] sprites;
        private float time;
        private bool playing;
        private int frameIndex = -1;

        public bool IsPlaying
        {
            get { return playing; }
        }

        /// <summary>Index of the frame currently shown, -1 before the first one.</summary>
        public int FrameIndex
        {
            get { return frameIndex; }
        }

        /// <summary>Seconds of one pass; 0 for a static strip.</summary>
        public float Duration
        {
            get { return fps > 0f ? Mathf.Max(1, frames) / fps : 0f; }
        }

        public SpriteRenderer TargetRenderer
        {
            get
            {
                if (spriteRenderer == null) spriteRenderer = GetComponent<SpriteRenderer>();
                return spriteRenderer;
            }
        }

        private void Awake()
        {
            spriteRenderer = GetComponent<SpriteRenderer>();
        }

        private void OnEnable()
        {
            if (playOnEnable && strip != null) Play(strip, frames, fps, loop);
        }

        /// <summary>Starts (or restarts) a strip. Safe with a null texture (the renderer is cleared).</summary>
        public void Play(Texture2D texture, int frameCount, float framesPerSecond, bool looping)
        {
            strip = texture;
            frames = Mathf.Max(1, frameCount);
            fps = Mathf.Max(0f, framesPerSecond);
            loop = looping;
            sprites = texture != null ? StripSheet.Strip(texture, frames) : null;
            time = randomPhase && fps > 0f && sprites != null && sprites.Length > 0 ? Random.Range(0f, sprites.Length / fps) : 0f;
            frameIndex = -1;
            playing = sprites != null && sprites.Length > 0;
            Apply();
        }

        /// <summary>Restarts the strip assigned in the inspector.</summary>
        public void Play()
        {
            Play(strip, frames, fps, loop);
        }

        /// <summary>Stops advancing; the current frame stays visible.</summary>
        public void Stop()
        {
            playing = false;
        }

        private void Update()
        {
            if (!playing) return;
            time += Time.deltaTime;
            Apply();
        }

        private void Apply()
        {
            SpriteRenderer sr = TargetRenderer;
            if (sprites == null || sprites.Length == 0)
            {
                if (sr != null) sr.sprite = null;
                playing = false;
                return;
            }
            int index;
            if (fps <= 0f)
            {
                index = 0;
                if (!loop) playing = false;
            }
            else
            {
                index = Mathf.FloorToInt(time * fps);
                if (loop)
                {
                    index %= sprites.Length;
                }
                else if (index >= sprites.Length)
                {
                    index = sprites.Length - 1;
                    playing = false;
                    if (destroyWhenDone && Application.isPlaying)
                    {
                        if (sr != null) sr.sprite = sprites[index];
                        frameIndex = index;
                        Destroy(gameObject);
                        return;
                    }
                }
            }
            if (index != frameIndex)
            {
                frameIndex = index;
                if (sr != null) sr.sprite = sprites[index];
            }
        }
    }
}
