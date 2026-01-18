#!/usr/bin/env python3
"""
Configuration for COSA Podcast Generator Agent.

Design decisions:
- Opus 4.5 for script generation (higher reasoning for natural dialogue)
- Customizable host personalities for A/B content comparison
- ElevenLabs voice mapping with quality profiles
- Prosody annotation support for expressive TTS
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class HostPersonality:
    """
    Personality template for a podcast host.

    Defines the host's role, tone, and behavioral characteristics
    for script generation.

    Requires:
        - name is a non-empty string
        - role is a descriptive string

    Ensures:
        - Provides complete personality profile for prompt generation
    """

    name              : str
    role              : str
    tone              : str   = "conversational"
    expertise_level   : str   = "knowledgeable"
    curiosity_level   : str   = "moderate"
    speaking_style    : str   = "clear and engaging"
    typical_phrases   : list  = field( default_factory=list )
    interaction_style : str   = "collaborative"

    def to_prompt_description( self ) -> str:
        """
        Generate a prompt-friendly description of this personality.

        Ensures:
            - Returns multi-line string suitable for system prompts
            - Captures all personality aspects

        Returns:
            str: Personality description for prompts
        """
        phrases = ", ".join( self.typical_phrases ) if self.typical_phrases else "none specified"
        return f"""Host: {self.name}
Role: {self.role}
Tone: {self.tone}
Expertise: {self.expertise_level}
Curiosity: {self.curiosity_level}
Speaking Style: {self.speaking_style}
Typical Phrases: {phrases}
Interaction Style: {self.interaction_style}"""


@dataclass
class VoiceProfile:
    """
    ElevenLabs voice configuration for a host.

    Configures TTS parameters for consistent, natural speech.

    Requires:
        - voice_id is a valid ElevenLabs voice ID

    Ensures:
        - All TTS parameters are within valid ranges
    """

    voice_id         : str
    name             : str   = "Default"
    stability        : float = 0.65
    similarity_boost : float = 0.75
    style            : float = 0.35
    use_speaker_boost: bool  = True

    def __post_init__( self ):
        """Validate parameter ranges."""
        assert 0.0 <= self.stability <= 1.0, "stability must be 0.0-1.0"
        assert 0.0 <= self.similarity_boost <= 1.0, "similarity_boost must be 0.0-1.0"
        assert 0.0 <= self.style <= 1.0, "style must be 0.0-1.0"


# =============================================================================
# Default Voice Profiles
# =============================================================================

# ElevenLabs voice IDs for default duo
# These are example IDs - replace with actual licensed voices
DEFAULT_VOICE_CURIOUS = VoiceProfile(
    voice_id         = "EXAVITQu4vr4xnSDxMaL",  # Sarah - curious, expressive
    name             = "Sarah",
    stability        = 0.60,
    similarity_boost = 0.75,
    style            = 0.40,  # More expressive for curiosity
)

DEFAULT_VOICE_EXPERT = VoiceProfile(
    voice_id         = "VR6AewLTigWG4xSOukaG",  # Arnold - grounded, authoritative
    name             = "Arnold",
    stability        = 0.70,
    similarity_boost = 0.80,
    style            = 0.30,  # More grounded for expertise
)


# =============================================================================
# Default Host Personalities
# =============================================================================

DEFAULT_CURIOUS_HOST = HostPersonality(
    name              = "Alex",
    role              = "Curious Questioner",
    tone              = "enthusiastic and inquisitive",
    expertise_level   = "educated layperson",
    curiosity_level   = "high",
    speaking_style    = "casual but articulate",
    typical_phrases   = [
        "Wait, so what you're saying is...",
        "That's fascinating!",
        "But here's what I'm wondering...",
        "Help me understand...",
        "So if I'm following you correctly...",
    ],
    interaction_style = "asks follow-up questions, seeks clarification",
)

DEFAULT_EXPERT_HOST = HostPersonality(
    name              = "Jordan",
    role              = "Knowledgeable Explainer",
    tone              = "warm and authoritative",
    expertise_level   = "expert",
    curiosity_level   = "moderate",
    speaking_style    = "clear explanations with analogies",
    typical_phrases   = [
        "Great question. Here's the key thing...",
        "Let me break that down...",
        "Think of it this way...",
        "The interesting part is...",
        "What most people don't realize...",
    ],
    interaction_style = "explains concepts, provides examples, builds on questions",
)


@dataclass
class PodcastConfig:
    """
    Configuration for the podcast generator agent.

    Requires:
        - All numeric values must be positive

    Ensures:
        - Provides sensible defaults for all parameters
        - Host personalities and voices are customizable
    """

    # === Model Selection ===
    script_model : str = "claude-opus-4-20250514"

    # === Host Configuration ===
    host_a_personality : HostPersonality = field( default_factory=lambda: DEFAULT_CURIOUS_HOST )
    host_b_personality : HostPersonality = field( default_factory=lambda: DEFAULT_EXPERT_HOST )
    host_a_voice       : VoiceProfile    = field( default_factory=lambda: DEFAULT_VOICE_CURIOUS )
    host_b_voice       : VoiceProfile    = field( default_factory=lambda: DEFAULT_VOICE_EXPERT )

    # === Script Generation ===
    target_duration_minutes    : int   = 10
    min_exchanges              : int   = 8
    max_exchanges              : int   = 20
    include_intro              : bool  = True
    include_outro              : bool  = True
    prosody_annotation_level   : Literal[ "minimal", "moderate", "detailed" ] = "moderate"

    # === Content Processing ===
    max_research_doc_tokens    : int   = 100000
    key_topics_to_extract      : int   = 5
    examples_per_topic         : int   = 2

    # === Execution Limits ===
    max_script_revisions       : int   = 3
    feedback_timeout_seconds   : int   = 300

    # === Output Configuration ===
    output_dir_template        : str   = "io/podcasts/{user}"
    script_filename_template   : str   = "{timestamp}-{topic}-script.md"
    audio_filename_template    : str   = "{timestamp}-{topic}-podcast.mp3"

    # === Audio Settings (Phase 2) ===
    audio_format               : Literal[ "mp3", "wav" ] = "mp3"
    audio_bitrate              : str   = "192k"
    silence_between_speakers_ms: int   = 300
    intro_music_path           : Optional[ str ] = None
    outro_music_path           : Optional[ str ] = None

    # === COSA Integration ===
    stream_thoughts_to_voice   : bool  = True
    narrate_progress           : bool  = True

    def get_host_a_name( self ) -> str:
        """Get Host A's name."""
        return self.host_a_personality.name

    def get_host_b_name( self ) -> str:
        """Get Host B's name."""
        return self.host_b_personality.name

    def get_output_path( self, user_id: str, topic: str, file_type: str = "script" ) -> str:
        """
        Generate output file path for script or audio.

        Requires:
            - user_id is a valid email or identifier
            - topic is a non-empty string
            - file_type is "script" or "audio"

        Ensures:
            - Returns full path with proper formatting
            - Timestamps are included for uniqueness

        Args:
            user_id: User identifier for directory
            topic: Topic slug for filename
            file_type: "script" or "audio"

        Returns:
            str: Complete file path
        """
        import cosa.utils.util as cu
        from datetime import datetime

        timestamp = datetime.now().strftime( "%Y.%m.%d-%H%M%S" )

        # Sanitize topic for filename
        topic_slug = topic.lower().replace( " ", "-" )[ :50 ]

        # Build directory path
        dir_path = self.output_dir_template.format( user=user_id.replace( "@", "_at_" ) )
        full_dir = cu.get_project_root() + "/" + dir_path

        # Build filename
        if file_type == "script":
            filename = self.script_filename_template.format(
                timestamp = timestamp,
                topic     = topic_slug,
            )
        else:
            filename = self.audio_filename_template.format(
                timestamp = timestamp,
                topic     = topic_slug,
            )

        return full_dir + "/" + filename


def quick_smoke_test():
    """Quick smoke test for PodcastConfig."""
    import cosa.utils.util as cu

    cu.print_banner( "PodcastConfig Smoke Test", prepend_nl=True )

    try:
        # Test 1: Default instantiation
        print( "Testing default config..." )
        config = PodcastConfig()
        assert config.script_model == "claude-opus-4-20250514"
        assert config.target_duration_minutes == 10
        print( "✓ Default config created" )

        # Test 2: Host personalities
        print( "Testing host personalities..." )
        assert config.host_a_personality.name == "Alex"
        assert config.host_b_personality.name == "Jordan"
        assert config.host_a_personality.role == "Curious Questioner"
        assert config.host_b_personality.role == "Knowledgeable Explainer"
        print( f"✓ Host A: {config.get_host_a_name()} ({config.host_a_personality.role})" )
        print( f"✓ Host B: {config.get_host_b_name()} ({config.host_b_personality.role})" )

        # Test 3: Voice profiles
        print( "Testing voice profiles..." )
        assert config.host_a_voice.name == "Sarah"
        assert config.host_b_voice.name == "Arnold"
        assert 0.0 <= config.host_a_voice.stability <= 1.0
        assert 0.0 <= config.host_b_voice.style <= 1.0
        print( f"✓ Host A voice: {config.host_a_voice.name} (stability={config.host_a_voice.stability})" )
        print( f"✓ Host B voice: {config.host_b_voice.name} (stability={config.host_b_voice.stability})" )

        # Test 4: HostPersonality.to_prompt_description
        print( "Testing personality prompt generation..." )
        prompt_desc = config.host_a_personality.to_prompt_description()
        assert "Alex" in prompt_desc
        assert "Curious Questioner" in prompt_desc
        assert "enthusiastic" in prompt_desc
        print( "✓ Personality prompt description generated" )

        # Test 5: Custom personalities
        print( "Testing custom personality..." )
        custom_host = HostPersonality(
            name              = "Dr. Smith",
            role              = "Academic Expert",
            tone              = "scholarly",
            expertise_level   = "professor",
            typical_phrases   = [ "In my research...", "The data suggests..." ],
        )
        assert custom_host.name == "Dr. Smith"
        assert "In my research..." in custom_host.to_prompt_description()
        print( "✓ Custom personality works" )

        # Test 6: VoiceProfile validation
        print( "Testing VoiceProfile validation..." )
        try:
            invalid_voice = VoiceProfile(
                voice_id  = "test",
                stability = 1.5,  # Invalid: > 1.0
            )
            print( "✗ Should have raised AssertionError" )
        except AssertionError:
            print( "✓ VoiceProfile validates parameters correctly" )

        # Test 7: Output path generation
        print( "Testing output path generation..." )
        path = config.get_output_path(
            user_id   = "user@example.com",
            topic     = "Quantum Computing Explained",
            file_type = "script",
        )
        assert "user_at_example.com" in path
        assert "quantum-computing-explained" in path
        assert path.endswith( "-script.md" )
        print( f"✓ Output path: ...{path[ -60: ]}" )

        print( "\n✓ PodcastConfig smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
