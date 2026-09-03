import 'package:flutter/services.dart';

/// Dart-side wrapper for MainActivity's real microphone/playback native
/// plumbing (Phase 6 Part E/J) - com.wowai.app/voice. Real RECORD_AUDIO
/// capture via Android's AudioRecord and real playback via AudioTrack,
/// never a stub - see VoiceRecorder.kt/VoicePlayer.kt.
class WowVoiceBridge {
  static const _channel = MethodChannel('com.wowai.app/voice');

  /// Raw PCM16 mono audio is always recorded/expected at this rate - the
  /// exact format the backend's real STT/VAD pipeline requires.
  static const sampleRate = 16000;

  static Future<bool> hasPermission() async {
    final result = await _channel.invokeMethod<bool>('hasPermission');
    return result ?? false;
  }

  /// Triggers the real Android RECORD_AUDIO runtime-permission dialog and
  /// returns the real resulting state.
  static Future<bool> requestPermission() async {
    final result = await _channel.invokeMethod<bool>('requestPermission');
    return result ?? false;
  }

  /// Starts real microphone capture. Throws a PlatformException if
  /// RECORD_AUDIO isn't granted or the device can't record at 16kHz mono.
  static Future<void> startRecording() => _channel.invokeMethod<void>('start');

  /// Stops capture and returns everything really recorded, as raw PCM16
  /// mono bytes at [sampleRate] - empty if nothing was ever started.
  static Future<Uint8List> stopRecording() async {
    final result = await _channel.invokeMethod<Uint8List>('stop');
    return result ?? Uint8List(0);
  }

  /// Plays real PCM16 mono audio (the backend's real synthesized reply)
  /// back to the user through the device speaker/earpiece.
  static Future<void> play(Uint8List pcm16, int sampleRate) =>
      _channel.invokeMethod<void>('play', {'bytes': pcm16, 'sampleRate': sampleRate});
}
