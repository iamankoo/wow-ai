package com.wowai.app

import android.app.role.RoleManager
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.core.app.ActivityCompat
import io.flutter.embedding.android.FlutterActivity

private const val TAG = "WowMainActivity"
private const val CALL_SCREENING_ROLE_REQUEST_CODE = 4001
private const val PHONE_PERMISSIONS_REQUEST_CODE = 4002

/**
 * Phase 2 Block 6: real Android call integration.
 *
 * On launch, requests (1) the dangerous runtime permissions
 * WowCallScreeningService/CallStateObserver need (READ_PHONE_STATE,
 * ANSWER_PHONE_CALLS - the latter is declared now for the ANSWER_CALL
 * action Block 7 wires up, not used yet in this block) and (2) the
 * android.app.role.CALL_SCREENING role, which Android requires an app to
 * hold before the system will ever invoke its CallScreeningService -
 * unlike a normal permission, a role cannot be granted via the manifest
 * alone; the user (or, for emulator/development testing, `adb shell cmd
 * role add-role-holder`) must grant it explicitly.
 *
 * This app deliberately does not request the default-dialer role /
 * implement InCallService - CallScreeningService is the lighter-weight,
 * non-default-dialer path Android provides for observing/screening
 * incoming calls, matching what this project's manifest and this file
 * already named as the Phase 2 plan (see git history) - not a
 * SIP/carrier stack, not a different telephony architecture.
 */
class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestPhonePermissionsIfNeeded()
        requestCallScreeningRoleIfNeeded()
        CallStateObserver.start(applicationContext)
    }

    private fun requestPhonePermissionsIfNeeded() {
        val needed = listOf(
            android.Manifest.permission.READ_PHONE_STATE,
            android.Manifest.permission.ANSWER_PHONE_CALLS,
        ).filter {
            ActivityCompat.checkSelfPermission(this, it) != android.content.pm.PackageManager.PERMISSION_GRANTED
        }
        if (needed.isNotEmpty()) {
            Log.i(TAG, "Requesting phone permissions: $needed")
            ActivityCompat.requestPermissions(this, needed.toTypedArray(), PHONE_PERMISSIONS_REQUEST_CODE)
        } else {
            Log.i(TAG, "Phone permissions already granted")
        }
    }

    private fun requestCallScreeningRoleIfNeeded() {
        // RoleManager/ROLE_CALL_SCREENING was added in API 29 - minSdk is
        // 26, so this must be guarded, not called unconditionally.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            Log.w(TAG, "ROLE_CALL_SCREENING requires API 29+; this device is API ${Build.VERSION.SDK_INT} - skipping")
            return
        }
        val roleManager = getSystemService(RoleManager::class.java) ?: run {
            Log.w(TAG, "RoleManager service unavailable")
            return
        }
        if (!roleManager.isRoleAvailable(RoleManager.ROLE_CALL_SCREENING)) {
            Log.w(TAG, "ROLE_CALL_SCREENING not available on this device")
            return
        }
        if (roleManager.isRoleHeld(RoleManager.ROLE_CALL_SCREENING)) {
            Log.i(TAG, "CALL_SCREENING role already held")
            return
        }
        Log.i(TAG, "Requesting CALL_SCREENING role")
        val intent: Intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING)
        startActivityForResult(intent, CALL_SCREENING_ROLE_REQUEST_CODE)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == CALL_SCREENING_ROLE_REQUEST_CODE) {
            Log.i(TAG, "CALL_SCREENING role request result: resultCode=$resultCode")
        }
    }
}
