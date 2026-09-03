package com.wowai.app

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import android.util.Log
import androidx.core.content.ContextCompat

private const val TAG = "WowCallStateObserver"

/**
 * Logs the real incoming-call lifecycle (RINGING -> OFFHOOK -> IDLE) -
 * WowCallScreeningService.onScreenCall() alone only reports "a call is
 * arriving"; this captures the fuller state machine (answered/active,
 * ended) a real call actually goes through, using the same
 * android.telephony call-state broadcast every phone/dialer app relies
 * on. Requires READ_PHONE_STATE (requested by MainActivity).
 *
 * TelephonyCallback (API 31+) replaces the deprecated PhoneStateListener;
 * this project's minSdk is 26, so PhoneStateListener remains the fallback
 * for API 26-30 rather than silently doing nothing on older devices.
 *
 * Also the real trigger point for Phase 2 Block 7's auto-answer: a RINGING
 * transition starts WowAutoAnswer's timer, and any other transition cancels
 * it - the human already handled the call, so WOW does nothing.
 */
object CallStateObserver {
    private var started = false

    fun start(context: Context) {
        if (started) return
        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.READ_PHONE_STATE)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "READ_PHONE_STATE not granted yet - call-state lifecycle logging not started")
            return
        }

        val telephonyManager = context.getSystemService(Context.TELEPHONY_SERVICE) as? TelephonyManager
        if (telephonyManager == null) {
            Log.w(TAG, "TelephonyManager unavailable")
            return
        }

        val appContext = context.applicationContext
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val callback = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
                override fun onCallStateChanged(state: Int) {
                    logState(appContext, state)
                }
            }
            telephonyManager.registerTelephonyCallback(context.mainExecutor, callback)
            Log.i(TAG, "Registered TelephonyCallback (API ${Build.VERSION.SDK_INT})")
        } else {
            @Suppress("DEPRECATION")
            val listener = object : android.telephony.PhoneStateListener() {
                @Suppress("DEPRECATION")
                override fun onCallStateChanged(state: Int, phoneNumber: String?) {
                    logState(appContext, state)
                }
            }
            @Suppress("DEPRECATION")
            telephonyManager.listen(listener, android.telephony.PhoneStateListener.LISTEN_CALL_STATE)
            Log.i(TAG, "Registered legacy PhoneStateListener (API ${Build.VERSION.SDK_INT})")
        }

        started = true
    }

    private fun logState(context: Context, state: Int) {
        val label = when (state) {
            TelephonyManager.CALL_STATE_IDLE -> "IDLE"
            TelephonyManager.CALL_STATE_RINGING -> "RINGING"
            TelephonyManager.CALL_STATE_OFFHOOK -> "OFFHOOK (active/answered)"
            else -> "UNKNOWN($state)"
        }
        Log.i(TAG, "call state -> $label")

        if (state == TelephonyManager.CALL_STATE_RINGING) {
            WowAutoAnswer.onCallRinging(context)
        } else {
            WowAutoAnswer.onCallLeftRinging("call state -> $label")
        }
    }
}
