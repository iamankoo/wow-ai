package com.wowai.app

import android.annotation.SuppressLint
import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.os.IBinder
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.ImageView
import kotlin.math.abs

private const val TAG = "WowFloatingButton"

/**
 * Phase 6 Part H: the real floating WOW button - a draggable
 * TYPE_APPLICATION_OVERLAY bubble added directly via WindowManager, not a
 * decorative in-app switch. Requires SYSTEM_ALERT_WINDOW, granted through
 * Android's dedicated "display over other apps" settings screen
 * (MainActivity's overlay channel drives that flow before ever starting
 * this service).
 *
 * Real, honestly-scoped behavior: tapping the bubble brings WOW back to the
 * foreground - it does not open a voice-command sheet directly, since real
 * in-overlay voice capture is separate, unbuilt work (Part J). A plain
 * (non-foreground) Service, not a foreground service with a persistent
 * notification: the overlay Window survives independently of the Service's
 * foreground state as long as this process is alive, but Android can still
 * reclaim a background service like this one under memory pressure, same
 * as any other app's - that is a real, documented limitation, not
 * something this class pretends around.
 */
class WowFloatingButtonService : Service() {
    private var windowManager: WindowManager? = null
    private var bubbleView: View? = null

    override fun onBind(intent: Intent?): IBinder? = null

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate() {
        super.onCreate()
        if (!Settings.canDrawOverlays(this)) {
            Log.w(TAG, "SYSTEM_ALERT_WINDOW not granted; refusing to show the floating button")
            stopSelf()
            return
        }
        if (bubbleView != null) return // already showing - startService() re-delivers onStartCommand, not onCreate, but guard anyway

        val wm = getSystemService(WINDOW_SERVICE) as WindowManager
        windowManager = wm

        val size = (56 * resources.displayMetrics.density).toInt()
        val bubble = ImageView(this).apply {
            setImageResource(R.mipmap.ic_launcher)
            layoutParams = ViewGroup.LayoutParams(size, size)
        }

        val params = WindowManager.LayoutParams(
            size,
            size,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = 300
        }

        var downRawX = 0f
        var downRawY = 0f
        var startX = 0
        var startY = 0
        var dragged = false

        bubble.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    downRawX = event.rawX
                    downRawY = event.rawY
                    startX = params.x
                    startY = params.y
                    dragged = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - downRawX).toInt()
                    val dy = (event.rawY - downRawY).toInt()
                    if (abs(dx) > 8 || abs(dy) > 8) dragged = true
                    params.x = startX + dx
                    params.y = startY + dy
                    wm.updateViewLayout(view, params)
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!dragged) {
                        // Real action: bring the real app to the foreground.
                        packageManager.getLaunchIntentForPackage(packageName)?.let { launch ->
                            launch.addFlags(
                                Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
                            )
                            startActivity(launch)
                        }
                    }
                    true
                }
                else -> false
            }
        }

        wm.addView(bubble, params)
        bubbleView = bubble
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        super.onDestroy()
        bubbleView?.let { view ->
            try {
                windowManager?.removeView(view)
            } catch (e: IllegalArgumentException) {
                Log.w(TAG, "Bubble view was already detached", e)
            }
        }
        bubbleView = null
        windowManager = null
    }
}
