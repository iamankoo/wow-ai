import 'package:flutter_test/flutter_test.dart';
import 'package:wow_ai/app.dart';
import 'package:wow_ai/core/api_client.dart';
import 'package:wow_ai/features/splash/splash_screen.dart';

void main() {
  testWidgets('splash screen shows for 3 seconds then reveals HomeScreen',
      (tester) async {
    await tester.pumpWidget(
      WowAiApp(apiClient: WowApiClient(baseUrl: 'http://localhost:8000')),
    );

    // Splash is up first - the real home content is not there yet.
    expect(find.byType(SplashScreen), findsOneWidget);
    expect(find.text('Your AI Call Assistant'), findsNothing);

    await tester.pump(SplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Your AI Call Assistant'), findsOneWidget);
    expect(find.text('Choose duration'), findsOneWidget);
    expect(find.text('Text Command'), findsOneWidget);
  });

  testWidgets('Text Command opens the real send-to-brain sheet', (tester) async {
    await tester.pumpWidget(
      WowAiApp(apiClient: WowApiClient(baseUrl: 'http://localhost:8000')),
    );
    await tester.pump(SplashScreen.duration);
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.text('Text Command'));
    await tester.pumpAndSettle();

    expect(find.text('Send to brain'), findsOneWidget);
  });
}
