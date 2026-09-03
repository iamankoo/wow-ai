import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wow_ai/app.dart';
import 'package:wow_ai/core/api_client.dart';
import 'package:wow_ai/features/onboarding/onboarding_flow.dart';
import 'package:wow_ai/features/splash/splash_screen.dart';

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
  testWidgets('splash routes to onboarding when the real profile is incomplete', (tester) async {
    await tester.pumpWidget(WowAiApp(apiClient: _clientReturning(_user(complete: false))));

    expect(find.byType(SplashScreen), findsOneWidget);
    await tester.pump(SplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.byType(OnboardingFlow), findsOneWidget);
    expect(find.text('Set up your profile'), findsOneWidget);
  });

  testWidgets('splash routes to HomeScreen when the real profile is complete', (tester) async {
    await tester.pumpWidget(WowAiApp(apiClient: _clientReturning(_user(complete: true))));

    await tester.pump(SplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text('Your AI Call Assistant'), findsOneWidget);
    expect(find.text('Choose duration'), findsOneWidget);
    expect(find.text('Text Command'), findsOneWidget);
  });

  testWidgets('Text Command opens the real send-to-brain sheet', (tester) async {
    await tester.pumpWidget(WowAiApp(apiClient: _clientReturning(_user(complete: true))));
    await tester.pump(SplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.text('Text Command'));
    await tester.pumpAndSettle();

    expect(find.text('Send to brain'), findsOneWidget);
  });
}
