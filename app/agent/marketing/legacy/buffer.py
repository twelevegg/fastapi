import re
from typing import Optional, List

class StreamBuffer:
    """
    STT Stream Buffer.
    Accumulates fragmented text chunks and releases complete sentences.
    Filters out short noise (backchannels) like "네", "아", "음".
    """
    def __init__(self, min_length: int = 5, timeout_seconds: float = 2.0):
        self.buffer = ""
        self.min_length = min_length
        # Regex for Sentence Endings: . ? ! or common Korean sentence endings (다, 요, 까, 죠, 뇬) followed by space/end
        # Note: STT often ignores punctuation, so we rely on heuristics.
        self.eos_pattern = re.compile(r"([.?!]|(?:다|요|까|죠|니)\s*$|(?:\r?\n)+)")
        
        # Noise filter: explicit short backchannels
        self.noise_pattern = re.compile(r"^(네|아|음|어|예|그|저기|그게)\s*([.?!])?$")
        
        # [NEW] Prefetch Triggers
        # Keywords that indicate high probability of marketing/intent
        self.trigger_keywords = ["데이터", "요금", "할인", "약정", "결합", "해지", "위약금", "혜택"]

    def check_prefetch_trigger(self, chunk: str) -> Optional[str]:
        """
        Returns the keyword if a chunk contains a trigger, else None.
        Used to start background search before EOS.
        """
        for kw in self.trigger_keywords:
            if kw in chunk:
                return kw
        return None

    def add_chunk(self, text: str) -> Optional[str]:
        """
        Adds a new text chunk.
        Returns a complete sentence if detected, otherwise None.
        """
        if not text:
            return None
            
        clean_text = text.strip()
        if not clean_text:
            return None

        # Determine if we should append with space
        if self.buffer and not self.buffer.endswith(" ") and not clean_text.startswith(" "):
             self.buffer += " "
        self.buffer += clean_text
        
        return self._try_pop_sentence()

    def _try_pop_sentence(self) -> Optional[str]:
        """
        Checks if the buffer contains a complete sentence.
        If yes, pops it and returns.
        """
        text = self.buffer.strip()
        
        # 1. Check strict EOS punctuation or endings
        match = self.eos_pattern.search(text)
        if match:
            # Found end of sentence
            end_idx = match.end()
            sentence = text[:end_idx].strip()
            remainder = text[end_idx:].strip()
            
            self.buffer = remainder
            
            # Post-processing: Filter noise
            if self._is_noise(sentence):
                return None
            
            # Length check
            if len(sentence) < self.min_length:
                return None # Too short, maybe noise or incomplete

            return sentence
            
        return None

    def force_flush(self) -> Optional[str]:
        """
        Forcefully returns the current buffer contents (e.g., on timeout or call end).
        """
        s = self.buffer.strip()
        self.buffer = ""
        if s and not self._is_noise(s) and len(s) >= self.min_length:
            return s
        return None
        
    def _is_noise(self, text: str) -> bool:
        """
        Returns True if text is just a backchannel.
        """
        return bool(self.noise_pattern.match(text))
