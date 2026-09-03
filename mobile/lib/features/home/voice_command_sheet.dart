import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/voice_bridge.dart';
import '../../core/wow_theme.dart';

enum _VoiceState { idle, recording, sending, done, noSpeech, permissionDenied, error }

const _recordingColor = Color(0xFFEF4444);

/// Phase 6 Part E/J - the real voice-command flow: records real
/// microphone audio (WowVoiceBridge -> Android's AudioRecord), sends it
/// to the real backend endpoint (WowApiClient.sendVoiceCommand ->
/// MediaPipeline's real VAD/STT/agent/TTS), and plays the real
/// synthesized reply back through the device speaker
/// (WowVoiceBridge.play -> AudioTrack). Replaces the earlier honest
/// "real speech capture isn't wired yet, type instead" placeholder - this
/// is the real thing now.
class VoiceCommandSheet extends StatefulWidget {
  const VoiceCommandSheet({super.key, required this.apiClient, required this.userId});

  final WowApiClient apiClient;
  final String userId;

  @override
  State<VoiceCommandSheet> createState() => _VoiceCommandSheetState();
}

class _VoiceCommandSheetState extends State<VoiceCommandSheet> {
  _VoiceState _state = _VoiceState.idle;
  String? _transcript;
  String? _replyText;
  String? _error;

  Future<void> _startRecording() async {
    var granted = await WowVoiceBridge.hasPermission();
    if (!granted) granted = await WowVoiceBridge.requestPermission();
    if (!granted) {
      setState(() => _state = _VoiceState.permissionDenied);
      return;
    }
    try {
      await WowVoiceBridge.startRecording();
      setState(() {
        _state = _VoiceState.recording;
        _transcript = null;
        _replyText = null;
        _error = null;
      });
    } catch (e) {
      setState(() {
        _state = _VoiceState.error;
        _error = 'Could not start recording: $e';
      });
    }
  }

  Future<void> _stopAndSend() async {
    setState(() => _state = _VoiceState.sending);
    try {
      final pcm = await WowVoiceBridge.stopRecording();
      if (pcm.isEmpty) {
        setState(() => _state = _VoiceState.noSpeech);
        return;
      }

      final result = await widget.apiClient.sendVoiceCommand(
        userId: widget.userId,
        pcm16: pcm,
        sampleRate: WowVoiceBridge.sampleRate,
      );
      final transcript = (result['transcript'] as String?) ?? '';
      final replyText = (result['reply_text'] as String?) ?? '';
      final replyAudioBase64 = (result['reply_audio_base64'] as String?) ?? '';
      final replySampleRate =
          (result['reply_sample_rate'] as num?)?.toInt() ?? WowVoiceBridge.sampleRate;

      if (transcript.trim().isEmpty) {
        if (mounted) setState(() => _state = _VoiceState.noSpeech);
        return;
      }

      if (mounted) {
        setState(() {
          _state = _VoiceState.done;
          _transcript = transcript;
          _replyText = replyText;
        });
      }

      if (replyAudioBase64.isNotEmpty) {
        await WowVoiceBridge.play(base64Decode(replyAudioBase64), replySampleRate);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _state = _VoiceState.error;
          _error = 'Voice command failed: $e';
        });
      }
    }
  }

  String get _statusText {
    switch (_state) {
      case _VoiceState.idle:
        return 'Tap the mic and say something to WOW.';
      case _VoiceState.recording:
        return 'Listening - tap again to stop.';
      case _VoiceState.sending:
        return 'Sending to WOW...';
      case _VoiceState.done:
        return 'You said: "$_transcript"';
      case _VoiceState.noSpeech:
        return "Didn't catch any speech - tap the mic and try again.";
      case _VoiceState.permissionDenied:
        return 'WOW needs microphone access to hear you. Tap the mic to allow it.';
      case _VoiceState.error:
        return _error ?? 'Something went wrong.';
    }
  }

  IconData get _micIcon => _state == _VoiceState.recording ? Icons.stop : Icons.mic;

  @override
  Widget build(BuildContext context) {
    final busy = _state == _VoiceState.sending;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('Voice command',
              style: TextStyle(color: WowColors.textPrimary, fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          const Text("Real microphone capture, sent to WOW's real voice pipeline.",
              style: TextStyle(color: WowColors.textMuted, fontSize: 12.5)),
          const SizedBox(height: 24),
          Center(
            child: GestureDetector(
              onTap: busy
                  ? null
                  : (_state == _VoiceState.recording ? _stopAndSend : _startRecording),
              child: Container(
                width: 84,
                height: 84,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _state == _VoiceState.recording
                      ? _recordingColor.withValues(alpha: 0.85)
                      : WowColors.primaryBlue,
                  boxShadow: [
                    BoxShadow(
                      color: (_state == _VoiceState.recording ? _recordingColor : WowColors.primaryBlue)
                          .withValues(alpha: 0.35),
                      blurRadius: 20,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: busy
                    ? const Padding(
                        padding: EdgeInsets.all(24),
                        child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white),
                      )
                    : Icon(_micIcon, color: Colors.white, size: 34),
              ),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            _statusText,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: _state == _VoiceState.error ? const Color(0xFFFFB4B4) : WowColors.textSecondary,
              fontSize: 13.5,
              height: 1.4,
            ),
          ),
          if (_state == _VoiceState.done && (_replyText ?? '').isNotEmpty) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: WowColors.surfaceVariant,
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.smart_toy_outlined, color: WowColors.primaryBlue, size: 18),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(_replyText!,
                        style: const TextStyle(color: WowColors.textPrimary, fontSize: 13.5, height: 1.4)),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
