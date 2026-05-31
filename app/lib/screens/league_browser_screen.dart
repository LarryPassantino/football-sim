import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';
import 'team_picker_screen.dart';

class _LeagueItem {
  final String id;
  final String name;
  final int humanCoachCount;
  final int openTeamCount;

  _LeagueItem.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        humanCoachCount = j['human_coach_count'],
        openTeamCount = j['open_team_count'];
}

class LeagueBrowserScreen extends StatefulWidget {
  const LeagueBrowserScreen({super.key});

  @override
  State<LeagueBrowserScreen> createState() => _LeagueBrowserScreenState();
}

class _LeagueBrowserScreenState extends State<LeagueBrowserScreen> {
  List<_LeagueItem>? _leagues;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _leagues = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/available'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load leagues');
      final data = jsonDecode(res.body);
      setState(() {
        _leagues = (data['leagues'] as List)
            .map((j) => _LeagueItem.fromJson(j as Map<String, dynamic>))
            .toList();
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  void _logout() {
    context.read<AuthProvider>().logout();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Join a League'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _leagues == null
              ? const Center(child: CircularProgressIndicator())
              : _buildList(),
    );
  }

  Widget _buildList() {
    if (_leagues!.isEmpty) {
      return const Center(child: Text('No leagues available'));
    }
    return ListView.separated(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + MediaQuery.of(context).padding.bottom),
      itemCount: _leagues!.length,
      separatorBuilder: (context, index) => const SizedBox(height: 8),
      itemBuilder: (context, i) {
        final league = _leagues![i];
        return Card(
          child: ListTile(
            title: Text(league.name),
            subtitle: Text(
              '${league.humanCoachCount} human coach${league.humanCoachCount == 1 ? '' : 'es'} · ${league.openTeamCount} open slot${league.openTeamCount == 1 ? '' : 's'}',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => TeamPickerScreen(
                  leagueId: league.id,
                  leagueName: league.name,
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
