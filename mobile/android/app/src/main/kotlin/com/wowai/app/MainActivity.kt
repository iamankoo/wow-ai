package com.wowai.app

import io.flutter.embedding.android.FlutterActivity

/**
 * Phase 1: plain Flutter host activity, no platform channels yet.
 * Phase 2 will add a MethodChannel here (e.g. "com.wowai.app/telephony")
 * bridging Android's CallScreeningService/InCallService into Dart so the
 * brain can be driven from a real incoming call.
 */
class MainActivity : FlutterActivity()
