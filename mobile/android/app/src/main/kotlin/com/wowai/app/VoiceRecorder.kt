package com.wowai.app

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import java.io.ByteArrayOutputStream
import kotlin.concurrent.thread

private const val TAG = "WowVoiceRecorder"
const val VOICE_SAMPLE_RATE = 16000
private const val MAX_DURATION_MS = 30_000L

/**
 * Phase 6 Part E/J: real microphone capture - raw 16-bit PCM mono at
 * 16kHz, the exact format the backend's real STT/VAD pipeline expects
 * (see backend/app/media/pipeline.py and app/providers/stt/local_whisper.py),
 * so no resampling is needed on either end. AudioSource.VOICE_RECOGNITION
 * is used deliberately over MIC - it asks the device to skip
 * AGC/noise-suppression processing tuned for media capture, which can
 * distort speech recognition input.
 *
 * Buffers the whole utterance in memory (bounded to MAX_DURATION_MS, a
 * real safety cap against a stuck/forgotten recording growing forever)
 * and hands it back in one piece from stop() - a bounded press-to-talk
 * recording, not a live stream; MediaPipeline.process_call_audio on the
 * backend is fed the complete recording in one request either way (see
 * app.media.pipeline.chunk_pcm16's docstring for why it still needs
 * frame-sized chunking there).
 */
class VoiceRecorder {
    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null
    @Volatile private var isRecording = false
    private val buffer = ByteArrayOutputStream()

    fun start() {
        if (isRecording) return
        val minBufferSize = AudioRecord.getMinBufferSize(
            VOICE_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBufferSize <= 0) {
            throw IllegalStateException("Device does not support 16kHz mono PCM16 recording")
        }
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            VOICE_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minBufferSize * 4,
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            throw IllegalStateException("AudioRecord failed to initialize - is RECORD_AUDIO granted?")
        }

        buffer.reset()
        audioRecord = record
        isRecording = true
        record.startRecording()

        val startedAt = System.currentTimeMillis()
        recordingThread = thread(start = true) {
            val chunk = ByteArray(minBufferSize)
            while (isRecording && System.currentTimeMillis() - startedAt < MAX_DURATION_MS) {
                val read = record.read(chunk, 0, chunk.size)
                if (read > 0) {
                    synchronized(buffer) { buffer.write(chunk, 0, read) }
                }
            }
        }
    }

    /** Stops recording and returns everything real audio captured, as raw PCM16 bytes. */
    fun stop(): ByteArray {
        if (!isRecording) return ByteArray(0)
        isRecording = false
        try {
            recordingThread?.join(1000)
        } catch (e: InterruptedException) {
            Log.w(TAG, "Interrupted waiting for the recording thread to finish", e)
        }
        recordingThread = null
        audioRecord?.let {
            try {
                it.stop()
            } catch (e: IllegalStateException) {
                Log.w(TAG, "AudioRecord.stop() called in an invalid state", e)
            }
            it.release()
        }
        audioRecord = null
        return synchronized(buffer) { buffer.toByteArray() }
    }
}
