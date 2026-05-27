import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';
import 'league_browser_screen.dart';
import 'leagues_screen.dart';

class _MyTeam {
  final String teamId;
  final String teamName;
  final String leagueId;
  final String leagueName;
  final String conference;
  final String division;

  _MyTeam.fromJson(Map<String, dynamic> j)
      : teamId     = j['team_id'],
        teamName   = j['team_name'],
        leagueId   = j['league_id'],
        leagueName = j['league_name'],
        conference = j['conference'],
        division   = j['division'];
}

class TeamHubScreen extends StatefulWidget {
  const TeamHubScreen({super.key});

  @override
  State<TeamHubScreen> createState() => _TeamHubScreenState();
}

class _TeamHubScreenState extends State<TeamHubScreen> {
  List<_MyTeam>? _teams;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _teams = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/coaches/me/teams'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load teams (${res.statusCode}): ${res.body}');
      final data = jsonDecode(res.body) as List;
      setState(() {
        _teams = data.map((j) => _MyTeam.fromJson(j as Map<String, dynamic>)).toList();
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  Future<void> _selectTeam(_MyTeam team) async {
    final auth = context.read<AuthProvider>();
    await auth.setActiveTeam(team.teamId, team.leagueId, team.teamName);
    if (!mounted) return;
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const LeaguesScreen()),
    );
  }

  void _joinLeague() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const LeagueBrowserScreen()),
    ).then((_) => _load());
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Gridiron Empire'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => auth.logout(),
          ),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _teams == null
              ? const Center(child: CircularProgressIndicator())
              : _buildBody(),
    );
  }

  Widget _buildBody() {
    final teams = _teams!;

    if (teams.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.sports_football, size: 64),
            const SizedBox(height: 16),
            Text(
              'No teams yet',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              'Join a league to get started.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              icon: const Icon(Icons.add),
              label: const Text('Join a League'),
              onPressed: _joinLeague,
            ),
          ],
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (final team in teams) ...[
          _teamCard(team),
          const SizedBox(height: 12),
        ],
        const SizedBox(height: 8),
        OutlinedButton.icon(
          icon: const Icon(Icons.add),
          label: const Text('Join Another League'),
          onPressed: _joinLeague,
        ),
      ],
    );
  }

  Widget _teamCard(_MyTeam team) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => _selectTeam(team),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      team.teamName,
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${team.leagueName}  ·  ${team.conference} ${team.division}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}
