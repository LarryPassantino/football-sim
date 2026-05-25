import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import 'standings_screen.dart';

class LeaguesScreen extends StatelessWidget {
  const LeaguesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Team'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => auth.logout(),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.sports_football, size: 40),
              title: const Text('Season 1'),
              subtitle: const Text('Regular season in progress'),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              icon: const Icon(Icons.bar_chart),
              label: const Text('Standings'),
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => StandingsScreen(leagueId: auth.leagueId!),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
