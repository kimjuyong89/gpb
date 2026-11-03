// InkPixel demo — clip lists → Play(name) / Music(name), the shape of GPA's UI/Sound.cs without Resources.Load.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace InkPixel.Demo
{
    /// <summary>
    /// Holds every SFX and music clip of the pack (assigned by the demo scene builder from
    /// Audio/Sfx and Audio/Music) and plays them by clip name, case-insensitively:
    /// <c>Play("Slash")</c> one-shots, <c>Music("Town")</c> loops. One instance per scene
    /// (<see cref="Instance"/>); the static <see cref="TryPlay"/> / <see cref="TryMusic"/> helpers are
    /// no-ops when none exists, so other components never need null checks.
    /// </summary>
    [AddComponentMenu("InkPixel/Simple Audio")]
    [DisallowMultipleComponent]
    public class SimpleAudio : MonoBehaviour
    {
        [Tooltip("Sound effects, looked up by clip name (Audio/Sfx/*.wav).")]
        public List<AudioClip> sfx = new List<AudioClip>();
        [Tooltip("Music loops, looked up by clip name (Audio/Music/*.ogg).")]
        public List<AudioClip> music = new List<AudioClip>();
        [Tooltip("One-shot volume (GPA Sound: 0.7).")]
        [Range(0f, 1f)] public float sfxVolume = 0.7f;
        [Tooltip("Music volume (GPA Sound: 0.4).")]
        [Range(0f, 1f)] public float musicVolume = 0.4f;
        [Tooltip("Music clip name started in Start(); empty for silence.")]
        public string musicOnStart = "";

        private static SimpleAudio instance;

        private AudioSource sfxSource;
        private AudioSource musicSource;
        private Dictionary<string, AudioClip> sfxByName;
        private Dictionary<string, AudioClip> musicByName;
        private readonly HashSet<string> warned = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private string currentMusic = "";

        /// <summary>The scene's SimpleAudio (found on demand), or null.</summary>
        public static SimpleAudio Instance
        {
            get
            {
                if (instance == null) instance = FindFirstObjectByType<SimpleAudio>();
                return instance;
            }
        }

        /// <summary>Name of the music clip playing, "" when silent.</summary>
        public string CurrentMusic
        {
            get { return currentMusic; }
        }

        private void Awake()
        {
            if (instance != null && instance != this)
                Debug.LogWarning("[InkPixel] SimpleAudio: a second instance on '" + name + "' replaces the one on '" + instance.name + "'.", this);
            instance = this;
            EnsureSources();
            RebuildIndex();
        }

        private void Start()
        {
            if (!string.IsNullOrEmpty(musicOnStart)) Music(musicOnStart);
        }

        private void OnDestroy()
        {
            if (instance == this) instance = null;
        }

        private void EnsureSources()
        {
            if (sfxSource == null)
            {
                sfxSource = gameObject.AddComponent<AudioSource>();
                sfxSource.playOnAwake = false;
            }
            if (musicSource == null)
            {
                musicSource = gameObject.AddComponent<AudioSource>();
                musicSource.playOnAwake = false;
                musicSource.loop = true;
            }
        }

        /// <summary>Rebuilds the name lookups after the lists changed at runtime.</summary>
        public void RebuildIndex()
        {
            sfxByName = Index(sfx, "sfx");
            musicByName = Index(music, "music");
        }

        private static Dictionary<string, AudioClip> Index(List<AudioClip> clips, string what)
        {
            var dict = new Dictionary<string, AudioClip>(StringComparer.OrdinalIgnoreCase);
            if (clips == null) return dict;
            foreach (AudioClip clip in clips)
            {
                if (clip == null) continue;
                if (dict.ContainsKey(clip.name))
                    Debug.LogWarning("[InkPixel] SimpleAudio: duplicate " + what + " clip name '" + clip.name + "'; keeping the first.");
                else
                    dict.Add(clip.name, clip);
            }
            return dict;
        }

        /// <summary>Plays a one-shot by clip name (case-insensitive). False (one warning per name) when unknown.</summary>
        public bool Play(string clipName)
        {
            if (string.IsNullOrEmpty(clipName)) return false;
            if (sfxByName == null) RebuildIndex();
            EnsureSources();
            AudioClip clip;
            if (!sfxByName.TryGetValue(clipName, out clip) || clip == null)
            {
                if (warned.Add("sfx:" + clipName))
                    Debug.LogWarning("[InkPixel] SimpleAudio: no SFX named '" + clipName + "'.", this);
                return false;
            }
            sfxSource.PlayOneShot(clip, sfxVolume);
            return true;
        }

        /// <summary>Starts a looping music clip by name; a clip already playing is left alone (GPA Sound.Music).</summary>
        public bool Music(string clipName)
        {
            if (string.IsNullOrEmpty(clipName))
            {
                StopMusic();
                return true;
            }
            if (musicByName == null) RebuildIndex();
            EnsureSources();
            AudioClip clip;
            if (!musicByName.TryGetValue(clipName, out clip) || clip == null)
            {
                if (warned.Add("music:" + clipName))
                    Debug.LogWarning("[InkPixel] SimpleAudio: no music named '" + clipName + "'.", this);
                return false;
            }
            musicSource.volume = musicVolume;
            if (musicSource.clip == clip && musicSource.isPlaying) return true;
            musicSource.clip = clip;
            musicSource.loop = true;
            musicSource.Play();
            currentMusic = clip.name;
            return true;
        }

        public void StopMusic()
        {
            if (musicSource != null) musicSource.Stop();
            currentMusic = "";
        }

        public bool HasSfx(string clipName)
        {
            if (sfxByName == null) RebuildIndex();
            return !string.IsNullOrEmpty(clipName) && sfxByName.ContainsKey(clipName);
        }

        public bool HasMusic(string clipName)
        {
            if (musicByName == null) RebuildIndex();
            return !string.IsNullOrEmpty(clipName) && musicByName.ContainsKey(clipName);
        }

        /// <summary>Clip names of the SFX list, in list order.</summary>
        public List<string> SfxNames()
        {
            return Names(sfx);
        }

        /// <summary>Clip names of the music list, in list order.</summary>
        public List<string> MusicNames()
        {
            return Names(music);
        }

        private static List<string> Names(List<AudioClip> clips)
        {
            var names = new List<string>();
            if (clips == null) return names;
            foreach (AudioClip c in clips)
                if (c != null) names.Add(c.name);
            return names;
        }

        private void OnValidate()
        {
            if (musicSource != null) musicSource.volume = musicVolume;
        }

        /// <summary>Play(name) on the scene instance; false when there is none or the clip is unknown.</summary>
        public static bool TryPlay(string clipName)
        {
            SimpleAudio audio = Instance;
            return audio != null && audio.Play(clipName);
        }

        /// <summary>Music(name) on the scene instance; false when there is none or the clip is unknown.</summary>
        public static bool TryMusic(string clipName)
        {
            SimpleAudio audio = Instance;
            return audio != null && audio.Music(clipName);
        }
    }
}
