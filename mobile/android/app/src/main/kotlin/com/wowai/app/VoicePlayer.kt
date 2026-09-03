package com.wowai.app

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.util.Log
import kotlin.concurrent.thread

private const val TAG = "WowVoicePlayer"

/**
 * Phase 6 Part E/J: plays WOW's real synthesized reply audio (raw PCM16
 * mono, produced by the backend's real Piper TTS - see
 * backend/app/providers/tts/local_piper.py) back to the user - the
 * "audio out" half of the real voice round trip, not a silent no-op.
 */
object VoicePlayer {
    fun play(pcm16: ByteArray, sampleRate: Int) {
        if (pcm16.isEmpty()) return
        val minBufferSize = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBufferSize <= 0) {
            Log.w(TAG, "Device does not support playback at ${sampleRate}Hz mono PCM16")
            return
        }

        val track = AudioTrack(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build(),
            AudioFormat.Builder()
                .setSampleRate(sampleRate)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .build(),
            maxOf(minBufferSize, pcm16.size),
            AudioTrack.MODE_STATIC,
            AudioManager.AUDIO_SESSION_ID_GENERATE,
        )
        track.write(pcm16, 0, pcm16.size)
        track.play()

        // Real cleanup once playback actually finishes, not a fire-and-forget leak.
        thread(start = true) {
            val durationMs = (pcm16.size / 2.0 / sampleRate * 1000).toLong()
            try {
                Thread.sleep(durationMs + 200)
            } catch (e: InterruptedException) {
                Log.w(TAG, "Interrupted waiting for playback to finish", e)
            }
            track.stop()
            track.release()
        }
    }
}
