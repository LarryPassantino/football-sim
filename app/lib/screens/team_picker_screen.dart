import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _TeamItem {
  final String id;
  final String name;
  final String conference;
  final String division;

  _TeamItem.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        conference = j['conference'],
        division = j['division'];
}

class TeamPickerScreen extends StatefulWidget {
  final String leagueId;
  final String leagueName;

  const TeamPickerScreen({
    super.key,
    required this.leagueId,
    required this.leagueName,
  });

  @override
  State<TeamPickerScreen> createState() => _TeamPickerScreenState();
}

class _TeamPickerScreenState extends State<TeamPickerScreen> {
  List<_TeamItem>? _teams;
  String? _error;
  String? _claiming;

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
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/available'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load teams');
      final data = jsonDecode(res.body) as List;
      setState(() {
        _teams = data.map((j) => _TeamItem.fromJson(j as Map<String, dynamic>)).toList();
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  Future<void> _claim(String teamId) async {
    setState(() { _claiming = teamId; });
    try {
      await context.read<AuthProvider>().claimTeam(widget.leagueId, teamId);
      // AuthProvider notifies listeners → main.dart rebuilds to LeaguesScreen
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() { _claiming = null; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.leagueName)),
      body: _error != null
          ? Center(child: Text(_error!))
          : _teams == null
              ? const Center(child: CircularProgressIndicator())
              : _buildTeamList(),
    );
  }

  Widget _buildTeamList() {
    // Group by conference → division
    final Map<String, Map<String, List<_TeamItem>>> grouped = {};
    for (final t in _teams!) {
      grouped.putIfAbsent(t.conference, () => {});
      grouped[t.conference]!.putIfAbsent(t.division, () => []);
      grouped[t.conference]![t.division]!.add(t);
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Pick your team',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 4),
        Text(
          'All other teams will be CPU-managed.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        for (final conf in grouped.keys.toList()..sort()) ...[
          Text(
            conf,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: Theme.of(context).colorScheme.primary,
            ),
          ),
          const SizedBox(height: 8),
          for (final div in grouped[conf]!.keys.toList()..sort()) ...[
            Text(div, style: Theme.of(context).textTheme.labelMedium),
            const SizedBox(height: 4),
            for (final team in grouped[conf]![div]!)
              Card(
                child: ListTile(
                  title: Text(team.name),
                  trailing: _claiming == team.id
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.sports_football),
                  onTap: _claiming != null ? null : () => _claim(team.id),
                ),
              ),
            const SizedBox(height: 12),
          ],
        ],
      ],
    );
  }
}
