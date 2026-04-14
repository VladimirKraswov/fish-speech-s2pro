import inspect
import logging
import os


logger = logging.getLogger("tts_render.vllm_omni_compat")


def _apply_fish_speech_dac_decode_compat() -> None:
    if os.getenv("FISH_SPEECH_VLLM_OMNI_DAC_COMPAT", "").lower() not in {"1", "true", "yes", "on"}:
        return

    try:
        import torch
        from fish_speech.models.dac.modded_dac import DAC
    except Exception:
        logger.debug("Fish Speech DAC compatibility patch skipped: imports unavailable", exc_info=True)
        return

    if getattr(DAC.decode, "_vllm_omni_compat_patched", False):
        return

    try:
        signature = inspect.signature(DAC.decode)
    except Exception:
        logger.debug("Fish Speech DAC compatibility patch skipped: signature inspection failed", exc_info=True)
        return

    params = list(signature.parameters.values())
    if len(params) != 2:
        return

    original_decode = DAC.decode

    def decode_compat(self, z_or_codes, feature_lengths=None):
        if feature_lengths is None:
            return original_decode(self, z_or_codes)

        if torch.is_tensor(z_or_codes) and not torch.is_floating_point(z_or_codes):
            indices = z_or_codes.to(dtype=torch.long)
            if indices.ndim == 2:
                indices = indices.unsqueeze(0)

            # Match the pre-S2 Fish Speech DAC API that vllm-omni expects:
            # decode discrete codebook indices and report output lengths in
            # audio samples via feature_lengths * frame_length.
            z = self.quantizer.decode(indices)
            wav_batch = self.decoder(z)
        else:
            wav_batch = original_decode(self, z_or_codes)

        lengths = feature_lengths
        if not torch.is_tensor(lengths):
            lengths = torch.as_tensor(lengths, device=wav_batch.device, dtype=torch.long)
        else:
            lengths = lengths.to(device=wav_batch.device, dtype=torch.long)

        frame_length = int(getattr(self, "frame_length", 0) or 0)
        if frame_length <= 0:
            hop_length = int(getattr(self, "hop_length", 0) or 0)
            frame_length = hop_length * 4 if hop_length > 0 else 2048
        audio_lengths = lengths * frame_length

        return wav_batch, audio_lengths

    decode_compat._vllm_omni_compat_patched = True  # type: ignore[attr-defined]
    DAC.decode = decode_compat
    logger.info("Applied Fish Speech DAC decode compatibility patch for vllm-omni")


_apply_fish_speech_dac_decode_compat()
