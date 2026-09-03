import 'dart:convert';

import 'package:http/http.dart' as http;

/// Carries the backend's real error detail (FastAPI's HTTPException
/// `detail` string, e.g. "WOW requires you to be 18 or older to continue")
/// so the UI can show the actual reason a request failed instead of a
/// generic message.
class WowApiException implements Exception {
  WowApiException(this.statusCode, this.detail);

  final int statusCode;
  final String detail;

  @override
  String toString() => detail;
}

Never _throwApiException(http.Response response) {
  String detail = response.body;
  try {
    final decoded = jsonDecode(response.body);
    if (decoded is Map && decoded['detail'] != null) {
      detail = decoded['detail'].toString();
    }
  } catch (_) {
    // Body wasn't JSON - fall back to the raw text above.
  }
  throw WowApiException(response.statusCode, detail);
}

/// Thin client for the WOW AI backend. Talks to the FastAPI service defined
/// in /backend - not to any third-party AI API.
class WowApiClient {
  WowApiClient({required this.baseUrl, http.Client? httpClient})
      : _client = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<bool> checkHealth() async {
    final response = await _client.get(Uri.parse('$baseUrl/health'));
    return response.statusCode == 200;
  }

  /// GET /users/{id} - reports the real persisted User row, including
  /// call_assistant_enabled (Phase 2 Block 7's real ANSWER_CALL
  /// authorization flag, also checked by WowAutoAnswer.kt).
  Future<Map<String, dynamic>> getUser(String userId) async {
    final response = await _client.get(Uri.parse('$baseUrl/users/$userId'));
    if (response.statusCode != 200) _throwApiException(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// PATCH /users/{id} - the real profile-edit path (Phase 6 Part C/N).
  /// The backend enforces the 18+ requirement and resets mobile_verified/
  /// email_verified when phone_number/email actually changes - this
  /// client never re-implements that logic, it only surfaces the real
  /// resulting user row (or the real rejection reason via WowApiException).
  Future<Map<String, dynamic>> updateProfile(
    String userId, {
    String? displayName,
    String? phoneNumber,
    String? email,
    DateTime? dateOfBirth,
    String? preferredLanguage,
    String? voiceGender,
  }) async {
    final body = <String, dynamic>{
      if (displayName != null) 'display_name': displayName,
      if (phoneNumber != null) 'phone_number': phoneNumber,
      if (email != null) 'email': email,
      if (dateOfBirth != null)
        'date_of_birth':
            '${dateOfBirth.year.toString().padLeft(4, '0')}-${dateOfBirth.month.toString().padLeft(2, '0')}-${dateOfBirth.day.toString().padLeft(2, '0')}',
      if (preferredLanguage != null) 'preferred_language': preferredLanguage,
      if (voiceGender != null) 'voice_gender': voiceGender,
    };
    final response = await _client.patch(
      Uri.parse('$baseUrl/users/$userId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (response.statusCode != 200) _throwApiException(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// POST /users/{id}/verify/{channel}/request - real code generation +
  /// delivery attempt. `dev_code` is only ever populated while no real
  /// SMS/email vendor is configured server-side (see app/config.py's
  /// otp_expose_dev_code) - the onboarding UI shows it labeled as such,
  /// never as if it arrived over a real channel.
  Future<String?> requestVerificationCode(String userId, String channel) async {
    final response =
        await _client.post(Uri.parse('$baseUrl/users/$userId/verify/$channel/request'));
    if (response.statusCode != 200) _throwApiException(response);
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return decoded['dev_code'] as String?;
  }

  /// POST /users/{id}/verify/{channel}/confirm - real hash-compare against
  /// the stored code; throws WowApiException with the real reason
  /// (incorrect code, expired, too many attempts) on failure.
  Future<void> confirmVerificationCode(String userId, String channel, String code) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/users/$userId/verify/$channel/confirm'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'code': code}),
    );
    if (response.statusCode != 200) _throwApiException(response);
  }

  Future<Map<String, dynamic>> sendBrainCommand({
    required String userId,
    required String text,
    String? conversationId,
    String? callerNumber,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/brain/command'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'user_id': userId,
        'text': text,
        if (conversationId != null) 'conversation_id': conversationId,
        if (callerNumber != null) 'caller_number': callerNumber,
      }),
    );
    if (response.statusCode != 200) _throwApiException(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  void dispose() => _client.close();
}
