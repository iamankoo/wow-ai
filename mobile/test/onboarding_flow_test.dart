import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wow_ai/core/api_client.dart';
import 'package:wow_ai/features/onboarding/onboarding_flow.dart';

/// Regression test for a real bug caught by live device testing: the
/// mobile-verify and email-verify steps share the same _VerifyStep widget
/// type at the same tree position, so without distinct Keys Flutter
/// reused the mobile step's State object (dev code, typed digits, "sent"
/// flag) when advancing to the email step - the email screen showed the
/// mobile code and a pre-filled text field instead of its own fresh
/// state. Fixed by giving each _VerifyStep a ValueKey per channel.
void main() {
  testWidgets('mobile and email verify steps do not share state', (tester) async {
    var user = {
      'id': '00000000-0000-0000-0000-000000000001',
      'display_name': 'Aniket',
      'phone_number': '+10000000000',
      'email': 'a@example.com',
      'date_of_birth': '1995-01-01',
      'mobile_verified': false,
      'email_verified': false,
      'preferred_language': 'english',
      'voice_gender': 'female',
      'profile_complete': false,
    };

    final mock = MockClient((request) async {
      if (request.method == 'POST' && request.url.path.contains('/verify/mobile/request')) {
        return http.Response(jsonEncode({'sent': true, 'dev_code': '111111'}), 200);
      }
      if (request.method == 'POST' && request.url.path.contains('/verify/mobile/confirm')) {
        user = {...user, 'mobile_verified': true};
        return http.Response(jsonEncode({'verified': true}), 200);
      }
      if (request.method == 'POST' && request.url.path.contains('/verify/email/request')) {
        return http.Response(jsonEncode({'sent': true, 'dev_code': '222222'}), 200);
      }
      if (request.method == 'GET' && request.url.path.startsWith('/users/')) {
        return http.Response(jsonEncode(user), 200);
      }
      return http.Response('not found', 404);
    });
    final apiClient = WowApiClient(baseUrl: 'http://localhost:8000', httpClient: mock);

    await tester.pumpWidget(MaterialApp(
      home: OnboardingFlow(apiClient: apiClient, initialUser: user),
    ));

    // Land directly on the mobile-verify step (name/phone/dob already set).
    await tester.tap(find.text('Send code'));
    await tester.pumpAndSettle();
    expect(find.text('Dev mode (no SMS/email service configured yet): your code is 111111'),
        findsOneWidget);

    await tester.enterText(find.byType(TextField).last, '111111');
    await tester.tap(find.text('Verify'));
    await tester.pumpAndSettle();

    // Now on the email-verify step - must be fresh, not the mobile step's
    // leftover state.
    expect(find.text('Verify your email address'), findsOneWidget);
    expect(find.text('Dev mode (no SMS/email service configured yet): your code is 111111'),
        findsNothing);

    await tester.tap(find.text('Send code'));
    await tester.pumpAndSettle();
    expect(find.text('Dev mode (no SMS/email service configured yet): your code is 222222'),
        findsOneWidget);

    final codeField = tester.widget<TextField>(find.byType(TextField).last);
    expect(codeField.controller?.text ?? '', isEmpty);
  });
}
