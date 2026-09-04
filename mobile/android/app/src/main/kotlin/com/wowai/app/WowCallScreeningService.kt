package com.wowai.app

import android.telecom.Call
import android.telecom.CallScreeningService
import android.util.Log
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

private const val TAG = "WowCallScreeningService"

// Matches mobile/lib/main.dart's kDefaultBackendBaseUrl - per-build-type
// value from BuildConfig (debug -> 10.0.2.2, release -> the deployed
// Render backend, see build.gradle.kts and docs/DEPLOYMENT.md). Read here
// rather than shared with Dart because this service can run even when no
// FlutterEngine/Activity is alive - see class doc below for why this
// integration is native Kotlin rather than a MethodChannel call into Dart.
private val BACKEND_BASE_URL = BuildConfig.BACKEND_BASE_URL

// Matches HomeScreen.dart's kDemoUserId - no real account system exists yet
// (Phase 1). Must be a real UUID: every backend user_id column (Contact,
// ContextProfile, Memory, AgentState) is typed uuid, not a free-form string.
private const val DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"

private val backgroundExecutor = Executors.newSingleThreadExecutor()

/**
 * Real CallScreeningService implementation (see AndroidManifest.xml's
 * <service> declaration) - the system invokes onScreenCall() for every
 * incoming call once this app holds android.app.role.CALL_SCREENING
 * (requested by MainActivity, granted via the system role-request dialog
 * or, for emulator/development testing, `adb shell cmd role
 * add-role-holder android.app.role.CALL_SCREENING com.wowai.app`).
 *
 * Architecture note - why this calls the backend directly instead of via
 * a MethodChannel into Dart (which this project's earlier comments named
 * as the eventual plan): CallScreeningService is a real Android system
 * service that the OS can invoke whether or not the app's Activity/
 * FlutterEngine is currently alive. Routing through Dart would require a
 * separately-managed background FlutterEngine (a real but substantially
 * more complex and more fragile pattern) purely to reach the same
 * FastAPI endpoint app/lib/core/api_client.dart already calls from the
 * UI. Calling it directly from Kotlin (stdlib HttpURLConnection, no new
 * dependency) reaches the identical backend endpoint - the same real
 * integration, more reliably, for a component the OS may run headlessly.
 *
 * Platform limitation, stated honestly rather than worked around: Android
 * does not allow a normal (non-privileged, non-default-dialer) app to
 * capture a live call's audio stream - MediaRecorder.AudioSource.VOICE_CALL
 * is restricted to privileged/carrier apps for caller privacy. This
 * service therefore reports real call *metadata* (caller number, arrival
 * event) to the backend, never fabricated caller speech - see the `text`
 * value sent below, explicitly labeled as a system event, not a
 * transcript. Real caller-speech understanding requires either a future
 * privileged-audio-access path or accepting this as a standing platform
 * constraint; app/media/pipeline.py (Block 5) is already real and ready
 * for real audio the moment a legitimate capture path exists.
 */
class WowCallScreeningService : CallScreeningService() {
    companion object {
        // Phase 8: the real caller number for whichever call is currently
        // ringing, so WowAutoAnswer (which the telecom/telephony APIs never
        // hand a phone number to directly - see CallStateObserver's class
        // doc) can label the "WOW handled a call" notification honestly
        // instead of omitting the caller entirely. Single most-recent value
        // is sufficient - this app only ever has one call ringing at a time.
        @Volatile
        var lastRingingCallerNumber: String? = null
    }

    override fun onScreenCall(callDetails: Call.Details) {
        val callerNumber = callDetails.handle?.schemeSpecificPart
        lastRingingCallerNumber = callerNumber
        Log.i(TAG, "onScreenCall: caller=$callerNumber state=${callDetails.state}")

        // Respond promptly - the system enforces a short screening
        // timeout. WOW does not auto-block/auto-reject calls yet (that is
        // ANSWER_CALL/TRANSFER_CALL/END_CALL territory, Block 7, and only
        // for actions the real policy engine actually authorizes) - allow
        // every call through, matching "do not fake call control".
        val response = CallScreeningService.CallResponse.Builder()
            .setDisallowCall(false)
            .setRejectCall(false)
            .setSkipCallLog(false)
            .setSkipNotification(false)
            .build()
        respondToCall(callDetails, response)

        // Backend integration is fire-and-forget on a background thread -
        // must never block/delay respondToCall() above.
        backgroundExecutor.submit {
            notifyBackend(callerNumber)
        }
    }

    private fun notifyBackend(callerNumber: String?) {
        try {
            val url = URL("$BACKEND_BASE_URL/brain/command")
            val connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 5000
                readTimeout = 5000
                setRequestProperty("Content-Type", "application/json")
            }

            val payload = buildString {
                append("{")
                append("\"user_id\":\"").append(DEMO_USER_ID).append("\",")
                // Explicitly a system event label, not a transcript - see
                // class doc "Platform limitation" above.
                append("\"text\":\"[system] incoming call\"")
                if (callerNumber != null) {
                    append(",\"caller_number\":\"").append(callerNumber.replace("\"", "")).append("\"")
                }
                append("}")
            }

            connection.outputStream.use { stream ->
                OutputStreamWriter(stream, Charsets.UTF_8).use { it.write(payload) }
            }

            val status = connection.responseCode
            val body = (if (status in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() }
            Log.i(TAG, "backend /brain/command responded: status=$status body=$body")
            connection.disconnect()
        } catch (e: Exception) {
            // Never let a backend-connectivity failure propagate out of
            // this background task or affect the already-sent call
            // response - the call screening decision above is independent
            // of whether this notification succeeds.
            Log.w(TAG, "backend notification failed (call already screened normally): ${e.message}")
        }
    }
}
