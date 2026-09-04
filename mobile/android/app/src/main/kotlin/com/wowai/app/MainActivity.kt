package com.wowai.app

import android.app.role.RoleManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.content.pm.PackageInfoCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

private const val TAG = "WowMainActivity"
private const val CALL_SCREENING_ROLE_REQUEST_CODE = 4001
private const val PHONE_PERMISSIONS_REQUEST_CODE = 4002
private const val OVERLAY_PERMISSION_REQUEST_CODE = 4003
private const val INSTALL_PERMISSION_REQUEST_CODE = 4004
private const val VOICE_PERMISSION_REQUEST_CODE = 4005
private const val NOTIFICATION_PERMISSION_REQUEST_CODE = 4006
private const val PERMISSIONS_CHANNEL = "com.wowai.app/permissions"
private const val OVERLAY_CHANNEL = "com.wowai.app/overlay"
private const val UPDATE_CHANNEL = "com.wowai.app/update"
private const val VOICE_CHANNEL = "com.wowai.app/voice"
private const val NOTIFICATIONS_CHANNEL = "com.wowai.app/notifications"

/**
 * Phase 2 Block 6 + Phase 6 Part D: real Android call integration and the
 * real, explicit (not silent-on-launch) permission/role flow the
 * onboarding screen drives.
 *
 * Prior to Phase 6, this class requested READ_PHONE_STATE/
 * ANSWER_PHONE_CALLS and the CALL_SCREENING role unconditionally in
 * onCreate(), with no user-facing explanation - fine for the emulator
 * verification Phase 2 needed, wrong for a real onboarding flow that must
 * explain why a permission is needed before requesting it (Part D). This
 * MethodChannel exposes the same real native permission/role plumbing to
 * Dart on demand: `status` (query only, no prompt), `requestPhoneAndContacts`
 * and `requestCallScreeningRole` (each triggers exactly one real Android
 * system prompt/screen). No new Flutter plugin dependency - Android's own
 * ActivityCompat/RoleManager APIs, called explicitly instead of
 * automatically.
 *
 * Does not request the default-dialer role / implement InCallService -
 * CallScreeningService remains the lighter-weight, non-default-dialer path
 * this project uses (see WowCallScreeningService's class doc).
 *
 * Phase 6 Part H adds a second channel, OVERLAY_CHANNEL, for the real
 * floating WOW button: `hasPermission`/`requestPermission` drive
 * SYSTEM_ALERT_WINDOW (granted via Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
 * a settings screen, not a runtime dialog - hence its own
 * startActivityForResult/onActivityResult path), and `start`/`stop` control
 * WowFloatingButtonService, the actual overlay Window.
 *
 * Phase 6 Part T adds a third channel, UPDATE_CHANNEL, for the real
 * GitHub-Release update flow: `currentVersion`/`downloadsDir` give Dart
 * what it needs to check/download a real release APK, and
 * `hasInstallPermission`/`requestInstallPermission`/`installApk` drive the
 * real REQUEST_INSTALL_PACKAGES grant (another settings-screen permission,
 * Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES) and hand the downloaded file
 * to the real system package installer via FileProvider.
 *
 * Phase 6 Part E/J adds a fourth channel, VOICE_CHANNEL, for the real
 * voice-command round trip: `hasPermission`/`requestPermission` drive the
 * real RECORD_AUDIO runtime-permission dialog (a normal dangerous
 * permission, so this reuses the same ActivityCompat.requestPermissions
 * path as requestPhoneAndContacts, not a settings screen), `start`/`stop`
 * drive a real VoiceRecorder capturing raw mic audio, and `play` hands
 * the backend's real synthesized reply audio to VoicePlayer.
 */
class MainActivity : FlutterActivity() {
    private var pendingPermissionsResult: MethodChannel.Result? = null
    private var pendingRoleResult: MethodChannel.Result? = null
    private var pendingOverlayResult: MethodChannel.Result? = null
    private var pendingInstallPermissionResult: MethodChannel.Result? = null
    private var pendingVoicePermissionResult: MethodChannel.Result? = null
    private val voiceRecorder = VoiceRecorder()
    // Phase 8: set when this Activity was (re)launched by tapping the real
    // "WOW handled a call" notification (see NotificationHelper) - consumed
    // (read-then-cleared) by Dart via NOTIFICATIONS_CHANNEL so
    // splash_screen.dart can route straight to call history instead of the
    // normal Home/onboarding destination.
    private var pendingOpenCallHistory = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Safe to start unconditionally - it's a no-op unless
        // READ_PHONE_STATE is already granted, and registers no dialog.
        CallStateObserver.start(applicationContext)
        requestNotificationPermissionIfNeeded()
        consumeOpenCallHistoryIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // launchMode="singleTop" (see AndroidManifest.xml) means a
        // notification tap while the Activity is already running arrives
        // here instead of a fresh onCreate() - handle both paths.
        consumeOpenCallHistoryIntent(intent)
    }

    private fun consumeOpenCallHistoryIntent(intent: Intent) {
        if (intent.action == ACTION_OPEN_CALL_HISTORY) {
            pendingOpenCallHistory = true
        }
    }

    /** Fire-and-forget: notification permission has no meaningful
     * "denied, now what" flow here (NotificationHelper simply skips posting
     * if it's absent), so this doesn't need the pendingXResult tracking the
     * other permissions use. */
    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (hasPermission(android.Manifest.permission.POST_NOTIFICATIONS)) return
        ActivityCompat.requestPermissions(
            this, arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_PERMISSION_REQUEST_CODE
        )
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, PERMISSIONS_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "status" -> result.success(currentStatus())
                    "requestPhoneAndContacts" -> requestPhoneAndContacts(result)
                    "requestCallScreeningRole" -> requestCallScreeningRole(result)
                    else -> result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, OVERLAY_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "hasPermission" -> result.success(Settings.canDrawOverlays(this))
                    "requestPermission" -> requestOverlayPermission(result)
                    "start" -> startFloatingButton(result)
                    "stop" -> {
                        stopService(Intent(this, WowFloatingButtonService::class.java))
                        result.success(true)
                    }
                    else -> result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, UPDATE_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "currentVersion" -> result.success(currentVersion())
                    "downloadsDir" -> result.success(updatesDir().absolutePath)
                    "hasInstallPermission" -> result.success(packageManager.canRequestPackageInstalls())
                    "requestInstallPermission" -> requestInstallPermission(result)
                    "installApk" -> installApk(call.argument<String>("path"), result)
                    else -> result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, NOTIFICATIONS_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "consumePendingOpenCallHistory" -> {
                        val pending = pendingOpenCallHistory
                        pendingOpenCallHistory = false
                        result.success(pending)
                    }
                    else -> result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, VOICE_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "hasPermission" ->
                        result.success(hasPermission(android.Manifest.permission.RECORD_AUDIO))
                    "requestPermission" -> requestVoicePermission(result)
                    "start" -> {
                        try {
                            voiceRecorder.start()
                            result.success(true)
                        } catch (e: IllegalStateException) {
                            result.error("RECORD_FAILED", e.message, null)
                        }
                    }
                    "stop" -> result.success(voiceRecorder.stop())
                    "play" -> {
                        val bytes = call.argument<ByteArray>("bytes") ?: ByteArray(0)
                        val sampleRate = call.argument<Int>("sampleRate") ?: VOICE_SAMPLE_RATE
                        VoicePlayer.play(bytes, sampleRate)
                        result.success(true)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private fun requestVoicePermission(result: MethodChannel.Result) {
        if (hasPermission(android.Manifest.permission.RECORD_AUDIO)) {
            result.success(true)
            return
        }
        if (pendingVoicePermissionResult != null) {
            result.error("BUSY", "A permission request is already in progress", null)
            return
        }
        pendingVoicePermissionResult = result
        Log.i(TAG, "Requesting RECORD_AUDIO")
        ActivityCompat.requestPermissions(
            this, arrayOf(android.Manifest.permission.RECORD_AUDIO), VOICE_PERMISSION_REQUEST_CODE
        )
    }

    private fun currentVersion(): Map<String, Any> {
        val info = packageManager.getPackageInfo(packageName, 0)
        return mapOf(
            "versionName" to (info.versionName ?: "0.0.0"),
            "versionCode" to PackageInfoCompat.getLongVersionCode(info),
        )
    }

    private fun updatesDir(): File {
        val dir = File(getExternalFilesDir(null), "updates")
        dir.mkdirs()
        return dir
    }

    private fun requestInstallPermission(result: MethodChannel.Result) {
        if (packageManager.canRequestPackageInstalls()) {
            result.success(true)
            return
        }
        if (pendingInstallPermissionResult != null) {
            result.error("BUSY", "An install-permission request is already in progress", null)
            return
        }
        pendingInstallPermissionResult = result
        Log.i(TAG, "Requesting REQUEST_INSTALL_PACKAGES via settings screen")
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:$packageName"),
        )
        startActivityForResult(intent, INSTALL_PERMISSION_REQUEST_CODE)
    }

    private fun installApk(path: String?, result: MethodChannel.Result) {
        if (path.isNullOrBlank()) {
            result.error("BAD_ARGS", "installApk requires a real file path", null)
            return
        }
        val file = File(path)
        if (!file.exists()) {
            result.error("NOT_FOUND", "No downloaded APK at $path", null)
            return
        }
        if (!packageManager.canRequestPackageInstalls()) {
            result.error("NO_PERMISSION", "REQUEST_INSTALL_PACKAGES is not granted", null)
            return
        }
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        Log.i(TAG, "Launching real package installer for $path")
        startActivity(intent)
        result.success(true)
    }

    private fun requestOverlayPermission(result: MethodChannel.Result) {
        if (Settings.canDrawOverlays(this)) {
            result.success(true)
            return
        }
        if (pendingOverlayResult != null) {
            result.error("BUSY", "An overlay permission request is already in progress", null)
            return
        }
        pendingOverlayResult = result
        Log.i(TAG, "Requesting SYSTEM_ALERT_WINDOW via settings screen")
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:$packageName"),
        )
        startActivityForResult(intent, OVERLAY_PERMISSION_REQUEST_CODE)
    }

    private fun startFloatingButton(result: MethodChannel.Result) {
        if (!Settings.canDrawOverlays(this)) {
            result.error("NO_PERMISSION", "SYSTEM_ALERT_WINDOW is not granted", null)
            return
        }
        startService(Intent(this, WowFloatingButtonService::class.java))
        result.success(true)
    }

    private fun hasPermission(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun callScreeningRoleHeld(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false
        val roleManager = getSystemService(RoleManager::class.java) ?: return false
        return roleManager.isRoleAvailable(RoleManager.ROLE_CALL_SCREENING) &&
            roleManager.isRoleHeld(RoleManager.ROLE_CALL_SCREENING)
    }

    private fun currentStatus(): Map<String, Any> = mapOf(
        "readPhoneState" to hasPermission(android.Manifest.permission.READ_PHONE_STATE),
        "answerPhoneCalls" to hasPermission(android.Manifest.permission.ANSWER_PHONE_CALLS),
        "contacts" to hasPermission(android.Manifest.permission.READ_CONTACTS),
        "callScreeningRole" to callScreeningRoleHeld(),
        "callScreeningRoleAvailable" to (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q),
    )

    private fun requestPhoneAndContacts(result: MethodChannel.Result) {
        val needed = listOf(
            android.Manifest.permission.READ_PHONE_STATE,
            android.Manifest.permission.ANSWER_PHONE_CALLS,
            android.Manifest.permission.READ_CONTACTS,
        ).filter { !hasPermission(it) }

        if (needed.isEmpty()) {
            Log.i(TAG, "Phone/contacts permissions already granted")
            result.success(currentStatus())
            return
        }
        if (pendingPermissionsResult != null) {
            result.error("BUSY", "A permission request is already in progress", null)
            return
        }
        pendingPermissionsResult = result
        Log.i(TAG, "Requesting permissions: $needed")
        ActivityCompat.requestPermissions(this, needed.toTypedArray(), PHONE_PERMISSIONS_REQUEST_CODE)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == PHONE_PERMISSIONS_REQUEST_CODE) {
            Log.i(TAG, "Permission result: ${permissions.zip(grantResults.toTypedArray())}")
            pendingPermissionsResult?.success(currentStatus())
            pendingPermissionsResult = null
        }
        if (requestCode == VOICE_PERMISSION_REQUEST_CODE) {
            val granted = hasPermission(android.Manifest.permission.RECORD_AUDIO)
            Log.i(TAG, "RECORD_AUDIO permission result: granted=$granted")
            pendingVoicePermissionResult?.success(granted)
            pendingVoicePermissionResult = null
        }
    }

    private fun requestCallScreeningRole(result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            Log.w(TAG, "ROLE_CALL_SCREENING requires API 29+; this device is API ${Build.VERSION.SDK_INT}")
            result.success(currentStatus())
            return
        }
        val roleManager = getSystemService(RoleManager::class.java)
        if (roleManager == null || !roleManager.isRoleAvailable(RoleManager.ROLE_CALL_SCREENING)) {
            Log.w(TAG, "ROLE_CALL_SCREENING unavailable on this device")
            result.success(currentStatus())
            return
        }
        if (roleManager.isRoleHeld(RoleManager.ROLE_CALL_SCREENING)) {
            result.success(currentStatus())
            return
        }
        if (pendingRoleResult != null) {
            result.error("BUSY", "A role request is already in progress", null)
            return
        }
        pendingRoleResult = result
        Log.i(TAG, "Requesting CALL_SCREENING role")
        val intent: Intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING)
        startActivityForResult(intent, CALL_SCREENING_ROLE_REQUEST_CODE)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == CALL_SCREENING_ROLE_REQUEST_CODE) {
            Log.i(TAG, "CALL_SCREENING role request result: resultCode=$resultCode")
            pendingRoleResult?.success(currentStatus())
            pendingRoleResult = null
        }
        if (requestCode == OVERLAY_PERMISSION_REQUEST_CODE) {
            val granted = Settings.canDrawOverlays(this)
            Log.i(TAG, "Overlay permission request result: granted=$granted")
            pendingOverlayResult?.success(granted)
            pendingOverlayResult = null
        }
        if (requestCode == INSTALL_PERMISSION_REQUEST_CODE) {
            val granted = packageManager.canRequestPackageInstalls()
            Log.i(TAG, "Install-permission request result: granted=$granted")
            pendingInstallPermissionResult?.success(granted)
            pendingInstallPermissionResult = null
        }
    }
}
