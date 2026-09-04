package com.wowai.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

private const val TAG = "WowNotificationHelper"
private const val CHANNEL_ID = "wow_call_events"
private const val NOTIFICATION_ID = 1001

/** Action MainActivity checks for on launch/onNewIntent to know the user
 * tapped a "WOW handled a call" notification rather than the launcher icon
 * - see MainActivity's NOTIFICATIONS_CHANNEL and mobile/lib/features/splash/
 * splash_screen.dart, which routes to HistoryScreen when this fires. */
const val ACTION_OPEN_CALL_HISTORY = "com.wowai.app.OPEN_CALL_HISTORY"

/**
 * Phase 8: the real Android notification posted after WowAutoAnswer
 * actually auto-answers a call on the user's behalf (see that class's
 * `answerRingingCall()`) - not posted for every screened call, since WOW
 * only "handles" a call when the human didn't pick up within the real
 * 10-second window and WOW auto-answered it. Corresponds to the real Call
 * row WowCallScreeningService.onScreenCall() already sent to the backend
 * for this same caller.
 */
object NotificationHelper {
    fun notifyCallHandled(context: Context, callerNumber: String?) {
        ensureChannel(context)

        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "POST_NOTIFICATIONS not granted - cannot show the real 'WOW handled a call' notification")
            return
        }

        val contentIntent = Intent(context, MainActivity::class.java).apply {
            action = ACTION_OPEN_CALL_HISTORY
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            contentIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val callerLabel = callerNumber?.takeIf { it.isNotBlank() } ?: "an unknown number"
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(context.applicationInfo.icon)
            .setContentTitle("WOW handled a call")
            .setContentText("WOW answered a call from $callerLabel while you were unavailable.")
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(pendingIntent)
            .build()

        val manager = ContextCompat.getSystemService(context, NotificationManager::class.java)
        manager?.notify(NOTIFICATION_ID, notification)
        Log.i(TAG, "Posted 'WOW handled a call' notification for caller=$callerNumber")
    }

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "WOW call handling",
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = "Notifies you when WOW answers a call on your behalf"
        }
        manager.createNotificationChannel(channel)
    }
}
