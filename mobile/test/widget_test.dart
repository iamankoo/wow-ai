import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wow_ai/app.dart';
import 'package:wow_ai/core/api_client.dart';
import 'package:wow_ai/features/onboarding/onboarding_flow.dart';
import 'package:wow_ai/features/splash/splash_screen.dart';

const _notificationsChannel = MethodChannel('com.wowai.app/notifications');

Map<String, dynamic> _user({required bool complete}) => {
      'id': '00000000-0000-0000-0000-000000000001',
      'display_name': complete ? 'Aniket' : '',
      'phone_number': complete ? '+10000000000' : '',
      'email': complete ? 'a@example.com' : null,
      'date_of_birth': complete ? '1995-01-01' : null,
      'age': complete ? 30 : null,
      'mobile_verified': complete,
      'email_verified': complete,
      'personalization_completed': complete,
      'preferred_language': 'english',
      'voice_gender': 'female',
      'profile_complete': complete,
      'call_assistant_enabled': false,
    };

WowApiClient _clientReturning(Map<String, dynamic> user) {
  final mock = MockClient((request) async {
    if (request.method == 'GET' && request.url.path.startsWith('/users/')) {
      return http.Response(jsonEncode(user), 200, headers: {'content-type': 'application/json'});
    }
    return http.Response('not found', 404);
  });
  return WowApiClient(baseUrl: 'http://localhost:8000', httpClient: mock);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // No native platform host runs under flutter test - mock the real
  // com.wowai.app/notifications channel splash_screen.dart now calls on
  // every launch (Phase 8) so it resolves like "not opened from a call
  // notification" instead of leaving that await pending forever.
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(_notificationsChannel, (call) async => false);

  testWidgets('splash routes to onboarding when the real profile is incomplete', (tester) async {
    await tester.pumpWidget(WowAiApp(apiClient: _clientReturning(_user(complete: false))));

    expect(find.byType(SplashScreen), findsOneWidget);
    await tester.pump(SplashScreen.duration);
    // Two async gaps now follow the splash delay (GET /users/{id}, then the
    // real "opened from a call notification?" native-channel check) -
    // pumpAndSettle rather than a single fixed-duration pump so both
    // resolve regardless of exact timing.
    await tester.pumpAndSettle();

    expect(find.byType(OnboardingFlow), findsOneWidget);
    expect(find.text('Set up your profile'), findsOneWidget);
  });

  testWidgets('splash routes to HomeScreen when the real profile is complete', (tester) async {
    await tester.pumpWidget(WowAiApp(apiClient: _clientReturning(_user(complete: true))));

    await tester.pump(SplashScreen.duration);
    // Two async gaps now follow the splash delay (GET /users/{id}, then the
    // real "opened from a call notification?" native-channel check) -
    // pumpAndSettle rather than a single fixed-duration pump so both
    // resolve regardless of exact timing.
    await tester.pumpAndSettle();

    expect(find.text('Your AI Call Assistant'), findsOneWidget);
    expect(find.text('Choose duration'), findsOneWidget);
    expect(find.text('Text'), findsOneWidget);
  });

  testWidgets('Text tile opens the real send-to-brain sheet', (tester) async {
    await tester.pumpWidget(WowAiApp(apiClient: _clientReturning(_user(complete: true))));
    await tester.pump(SplashScreen.duration);
    // Two async gaps now follow the splash delay (GET /users/{id}, then the
    // real "opened from a call notification?" native-channel check) -
    // pumpAndSettle rather than a single fixed-duration pump so both
    // resolve regardless of exact timing.
    await tester.pumpAndSettle();

    await tester.tap(find.text('Text'));
    await tester.pumpAndSettle();

    expect(find.text('Send to brain'), findsOneWidget);
  });
}
