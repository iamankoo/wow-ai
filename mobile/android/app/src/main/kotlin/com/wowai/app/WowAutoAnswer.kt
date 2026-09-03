package com.wowai.app

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.telecom.TelecomManager
import android.util.Log
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

private const val TAG = "WowAutoAnswer"

// Matches the "give the user ~10 seconds to handle it themselves" behavior -
// only once a real incoming call has been RINGING this long with no human
// answer/decline does WOW consider taking it, and only for a user who has
// explicitly opted in (see checkAndMaybeAnswer's call_assistant_enabled
// check below) - WOW never activates itself.
private const val AUTO_ANSWER_DELAY_MS = 10_000L

/**
 * Phase 2 Block 7: real ANSWER_CALL - not a fake button.
 *
 * android.telecom.TelecomManager#acceptRingingCall() is a genuine,
 * non-privileged capability: unlike ending or transferring a call (see
 * WowCallScreeningService's class doc for why those two remain
 * unimplemented), Android has permitted a normal app holding
 * android.permission.ANSWER_PHONE_CALLS (API 26+, a regular runtime-
 * grantable "dangerous" permission - already requested by MainActivity) to
 * answer the current ringing call since API 28, specifically so call-
 * screening-style apps do not need the default-dialer/InCallService role
 * just to pick up. This class is the real, permission-checked, opt-in-gated
 * caller of that API.
 *
 * Started by CallStateObserver on every RINGING transition; the timer is
 * cancelled the moment the call leaves RINGING for any other reason (the
 * human answered or declined it - see the "WOW does nothing" requirement).
 *
 * Verification note: CallStateObserver's RINGING/IDLE detection and
 * WowCallScreeningService's onScreenCall() -> real backend round trip were
 * both independently confirmed against real `adb emu gsm call` traffic on
 * the Medium_Phone_API_36.1 emulator (Phase 2 Block 6). GET
 * /users/{id}.call_assistant_enabled was independently confirmed live
 * against the real Postgres-backed endpoint. This class's own
 * acceptRingingCall() call could not get a live end-to-end demonstration in
 * this session: after an unrelated emulator crash/restart, the emulator's
 * `gsm call` console simulation stopped creating calls at all (`gsm list`
 * reports zero calls after every `gsm call`, confirmed reproducible across
 * a full emulator relaunch and an `adb reboot`) - a real environment
 * defect, not a WOW code path. The implementation is written against the
 * documented, verified API contract; re-verify live end-to-end once GSM
 * call simulation is working again in this environment.
 */
object WowAutoAnswer {
    private const val BACKEND_BASE_URL = "http://10.0.2.2:8000"
    // Matches WowCallScreeningService.DEMO_USER_ID / home_screen.dart's
    // kDemoUserId - no real account system exists yet (Phase 1).
    private const val DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"

    private val mainHandler = Handler(Looper.getMainLooper())
    private val backgroundExecutor = Executors.newSingleThreadExecutor()
    private var pendingRunnable: Runnable? = null

    fun onCallRinging(context: Context) {
        cancelPending("new RINGING call")
        val runnable = Runnable { checkAndMaybeAnswer(context.applicationContext) }
        pendingRunnable = runnable
        mainHandler.postDelayed(runnable, AUTO_ANSWER_DELAY_MS)
        Log.i(TAG, "Call is RINGING - will consider auto-answer in ${AUTO_ANSWER_DELAY_MS}ms if still unanswered")
    }

    /** Any non-RINGING transition means a human (or the system) already
     * resolved the call - WOW must not act on it. "WOW does nothing" is the
     * default outcome, enforced by simply never letting the timer fire. */
    fun onCallLeftRinging(reason: String) {
        cancelPending(reason)
    }

    private fun cancelPending(reason: String) {
        val runnable = pendingRunnable ?: return
        mainHandler.removeCallbacks(runnable)
        pendingRunnable = null
        Log.i(TAG, "Auto-answer timer cancelled: $reason")
    }

    private fun checkAndMaybeAnswer(context: Context) {
        if (pendingRunnable == null) {
            // Already cancelled (the call left RINGING) between the
            // background-thread hop and now - do nothing.
            return
        }
        backgroundExecutor.submit {
            val enabled = fetchCallAssistantEnabled()
            mainHandler.post {
                if (pendingRunnable == null) {
                    Log.i(TAG, "Call left RINGING while checking authorization - not answering")
                    return@post
                }
                pendingRunnable = null
                if (enabled != true) {
                    Log.i(
                        TAG,
                        "Not auto-answering: call_assistant_enabled=$enabled " +
                            "(WOW only acts when the user has explicitly turned it on)"
                    )
                    return@post
                }
                answerRingingCall(context)
            }
        }
    }

    /** Real HTTP GET against the existing /users/{id} route - reports the
     * User.call_assistant_enabled column real value (see
     * app/agent/builtin_tools.py EnableCallAssistantTool/
     * DisableCallAssistantTool for how it's set). Returns null (never
     * true) on any failure - explicit failure, not a silent default-on. */
    private fun fetchCallAssistantEnabled(): Boolean? {
        return try {
            val url = URL("$BACKEND_BASE_URL/users/$DEMO_USER_ID")
            val connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 5000
                readTimeout = 5000
            }
            val status = connection.responseCode
            if (status != 200) {
                Log.w(TAG, "GET /users/$DEMO_USER_ID failed: status=$status")
                connection.disconnect()
                return null
            }
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            connection.disconnect()
            JSONObject(body).optBoolean("call_assistant_enabled", false)
        } catch (e: Exception) {
            Log.w(TAG, "Could not check call_assistant_enabled - not answering: ${e.message}")
            null
        }
    }

    private fun answerRingingCall(context: Context) {
        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.ANSWER_PHONE_CALLS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "ANSWER_PHONE_CALLS not granted - cannot auto-answer (explicit failure, no fallback)")
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            // TelecomManager#acceptRingingCall() ignores its argument and
            // requires ANSWER_PHONE_CALLS only from API 28 (P) onward.
            Log.w(TAG, "acceptRingingCall() needs API 28+; this device is API ${Build.VERSION.SDK_INT} - skipping")
            return
        }
        val telecomManager = context.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager
        if (telecomManager == null) {
            Log.w(TAG, "TelecomManager unavailable")
            return
        }
        try {
            telecomManager.acceptRingingCall()
            Log.i(TAG, "WOW auto-answered the call via TelecomManager.acceptRingingCall()")
        } catch (e: SecurityException) {
            Log.e(TAG, "acceptRingingCall() denied: ${e.message}")
        }
    }
}
