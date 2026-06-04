import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'firebase_options.dart';
import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/team_hub_screen.dart';

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

  final auth = AuthProvider();
  await auth.init();

  // Request permission and register FCM token if already logged in.
  await _setupFcm(auth);

  // Re-register whenever FCM rotates the token.
  FirebaseMessaging.instance.onTokenRefresh.listen((token) {
    auth.setFcmToken(token);
  });

  runApp(
    ChangeNotifierProvider.value(
      value: auth,
      child: const FootballSimApp(),
    ),
  );
}

Future<void> _setupFcm(AuthProvider auth) async {
  await FirebaseMessaging.instance.requestPermission();
  final token = await FirebaseMessaging.instance.getToken();
  if (token != null) await auth.setFcmToken(token);
}

class FootballSimApp extends StatelessWidget {
  const FootballSimApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Gridiron Empire',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF2E7D32),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: Builder(builder: (context) {
        final auth = context.watch<AuthProvider>();
        if (!auth.isLoggedIn) return const LoginScreen();
        return const TeamHubScreen();
      }),
    );
  }
}
