import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/team_hub_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final auth = AuthProvider();
  await auth.init();
  runApp(
    ChangeNotifierProvider.value(
      value: auth,
      child: const FootballSimApp(),
    ),
  );
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
