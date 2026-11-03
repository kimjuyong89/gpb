// InkPixel — plays a SpriteAnimation on a SpriteRenderer and/or a UI Image (ASSET_SPEC §7.2).
using System;
using UnityEngine;
using UnityEngine.UI;

namespace InkPixel
{
    /// <summary>
    /// Minimal flip-book player. Targets are auto-detected on the same GameObject when not assigned.
    /// Call <see cref="Play(SpriteAnimation, bool)"/> to switch clips; <see cref="OnComplete"/> fires
    /// when a non-looping clip reaches its last frame (playback has already stopped by then).
    /// </summary>
    [AddComponentMenu("InkPixel/Sprite Animator")]
    [DisallowMultipleComponent]
    public class SpriteAnimator : MonoBehaviour
    {
        [Tooltip("Played automatically in OnEnable when Play On Enable is set.")]
        [SerializeField] private SpriteAnimation defaultAnimation;
        [SerializeField] private bool playOnEnable = true;
        [Tooltip("Playback speed multiplier (1 = the clip's own fps).")]
        [SerializeField] private float speed = 1f;
        [Tooltip("Advance with Time.unscaledDeltaTime instead of Time.deltaTime.")]
        [SerializeField] private bool useUnscaledTime;

        [Header("Targets (auto-detected on this GameObject when empty)")]
        [SerializeField] private SpriteRenderer spriteRenderer;
        [SerializeField] private Image image;

        /// <summary>Raised once when a non-looping clip finishes (after playback stopped on the last frame).</summary>
        public event Action OnComplete;
        /// <summary>Raised each time a looping clip wraps around to its first frame.</summary>
        public event Action OnLoop;
        /// <summary>Raised whenever the displayed frame index changes (argument = new frame index).</summary>
        public event Action<int> OnFrame;

        private SpriteAnimation current;
        private bool playing;
        private float time;
        private int frameIndex = -1;

        /// <summary>The clip last passed to Play (kept after Stop).</summary>
        public SpriteAnimation Current
        {
            get { return current; }
        }

        public bool IsPlaying
        {
            get { return playing; }
        }

        /// <summary>Index of the frame currently shown, -1 before the first frame.</summary>
        public int FrameIndex
        {
            get { return frameIndex; }
        }

        /// <summary>0..1 position inside the current pass of the clip.</summary>
        public float NormalizedTime
        {
            get
            {
                if (current == null) return 0f;
                float duration = current.Duration;
                return duration > 0f ? Mathf.Clamp01(time / duration) : 0f;
            }
        }

        public float Speed
        {
            get { return speed; }
            set { speed = value; }
        }

        public bool UseUnscaledTime
        {
            get { return useUnscaledTime; }
            set { useUnscaledTime = value; }
        }

        public bool PlayOnEnable
        {
            get { return playOnEnable; }
            set { playOnEnable = value; }
        }

        public SpriteAnimation DefaultAnimation
        {
            get { return defaultAnimation; }
            set { defaultAnimation = value; }
        }

        public SpriteRenderer TargetRenderer
        {
            get { return spriteRenderer; }
            set { spriteRenderer = value; }
        }

        public Image TargetImage
        {
            get { return image; }
            set { image = value; }
        }

        private void Awake()
        {
            ResolveTargets();
        }

        private void OnEnable()
        {
            if (playOnEnable && defaultAnimation != null) Play(defaultAnimation, true);
        }

        private void Update()
        {
            if (!playing || current == null) return;
            float dt = useUnscaledTime ? Time.unscaledDeltaTime : Time.deltaTime;
            Advance(dt * speed);
        }

        /// <summary>
        /// Starts <paramref name="animation"/>. When it is already playing and <paramref name="restart"/>
        /// is false this is a no-op (so it can be called every frame from a state machine).
        /// </summary>
        public void Play(SpriteAnimation animation, bool restart = false)
        {
            if (animation == null)
            {
                Stop();
                return;
            }
            if (!restart && playing && current == animation) return;
            if (spriteRenderer == null && image == null) ResolveTargets();

            current = animation;
            time = 0f;
            frameIndex = -1;
            playing = true;
            ShowFrame(0);
            if (current.FrameCount == 0)
            {
                playing = false;
                Debug.LogWarning("[InkPixel] SpriteAnimator on '" + name + "': animation '" + animation.name + "' has no frames.", this);
            }
        }

        /// <summary>Resumes the current clip, or starts the default clip when nothing was played yet.</summary>
        public void Play()
        {
            if (current != null) Play(current, false);
            else if (defaultAnimation != null) Play(defaultAnimation, false);
        }

        /// <summary>Stops advancing; the current frame stays visible.</summary>
        public void Stop()
        {
            playing = false;
        }

        /// <summary>Stops and optionally clears the sprite on the targets.</summary>
        public void Stop(bool clearSprite)
        {
            playing = false;
            if (clearSprite)
            {
                frameIndex = -1;
                ApplySprite(null);
            }
        }

        /// <summary>Jumps to a frame of the current clip without changing the play state.</summary>
        public void SetFrame(int index)
        {
            if (current == null || current.FrameCount == 0) return;
            index = Mathf.Clamp(index, 0, current.FrameCount - 1);
            time = index * current.FrameDuration;
            ShowFrame(index);
        }

        /// <summary>Advances playback by <paramref name="deltaTime"/> seconds (already multiplied by Speed in Update).</summary>
        public void Advance(float deltaTime)
        {
            if (current == null) return;
            int count = current.FrameCount;
            if (count == 0)
            {
                Finish();
                return;
            }

            float frameDuration = current.FrameDuration;
            if (frameDuration <= 0f)
            {
                // Static clip (fps 0, e.g. the Arrow/Shadow strips): hold the first frame.
                ShowFrame(0);
                if (!current.loop) Finish();
                return;
            }

            time += deltaTime;
            if (time < 0f) time = 0f;
            float duration = count * frameDuration;
            if (time >= duration)
            {
                if (current.loop)
                {
                    time = Mathf.Repeat(time, duration);
                    ShowFrame(Mathf.Min(Mathf.FloorToInt(time / frameDuration), count - 1));
                    if (OnLoop != null) OnLoop();
                    return;
                }
                ShowFrame(count - 1);
                Finish();
                return;
            }
            ShowFrame(Mathf.Min(Mathf.FloorToInt(time / frameDuration), count - 1));
        }

        private void Finish()
        {
            playing = false;
            if (OnComplete != null) OnComplete();
        }

        private void ShowFrame(int index)
        {
            if (index == frameIndex) return;
            frameIndex = index;
            ApplySprite(current != null ? current.FrameAt(index) : null);
            if (OnFrame != null) OnFrame(index);
        }

        private void ApplySprite(Sprite sprite)
        {
            if (spriteRenderer != null) spriteRenderer.sprite = sprite;
            if (image != null) image.sprite = sprite;
        }

        private void ResolveTargets()
        {
            if (spriteRenderer == null) spriteRenderer = GetComponent<SpriteRenderer>();
            if (image == null) image = GetComponent<Image>();
        }
    }
}
