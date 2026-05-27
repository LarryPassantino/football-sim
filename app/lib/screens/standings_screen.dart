import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';
import 'roster_screen.dart';
import 'scout_screen.dart';

class _StandingRow {
  final String teamId;
  final String name;
  final String conference;
  final String division;
  final int wins;
  final int losses;
  final int ties;
  final int pointDifferential;

  _StandingRow.fromJson(Map<String, dynamic> j)
      : teamId = j['team_id'],
        name = j['name'],
        conference = j['conference'],
        division = j['division'],
        wins = j['wins'],
        losses = j['losses'],
        ties = j['ties'],
        pointDifferential = j['point_differential'];
}

class StandingsScreen extends StatefulWidget {
  final String leagueId;
  final String myTeamId;
  const StandingsScreen({super.key, required this.leagueId, required this.myTeamId});

  @override
  State<StandingsScreen> createState() => _StandingsScreenState();
}

class _StandingsScreenState extends State<StandingsScreen> {
  List<_StandingRow>? _standings;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/standings'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load standings');
      final data = jsonDecode(res.body);
      setState(() {
        _standings = (data['standings'] as List)
            .map((j) => _StandingRow.fromJson(j as Map<String, dynamic>))
            .toList();
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Standings'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _standings == null
              ? const Center(child: CircularProgressIndicator())
              : _buildStandings(),
    );
  }

  Widget _buildStandings() {
    final Map<String, Map<String, List<_StandingRow>>> grouped = {};
    for (final row in _standings!) {
      grouped.putIfAbsent(row.conference, () => {});
      grouped[row.conference]!.putIfAbsent(row.division, () => []);
      grouped[row.conference]![row.division]!.add(row);
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (final conf in grouped.keys.toList()..sort()) ...[
          Text(
            conf,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              color: Theme.of(context).colorScheme.primary,
            ),
          ),
          const SizedBox(height: 8),
          for (final div in grouped[conf]!.keys.toList()..sort()) ...[
            Text(div, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            _buildDivisionTable(grouped[conf]![div]!),
            const SizedBox(height: 20),
          ],
        ],
      ],
    );
  }

  Widget _buildDivisionTable(List<_StandingRow> rows) {
    const headerStyle = TextStyle(fontWeight: FontWeight.bold, fontSize: 12);

    return Column(
      children: [
        Container(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          child: _tableRow(
            isHeader: true,
            teamName: 'Team',
            w: 'W',
            l: 'L',
            t: 'T',
            diff: '+/-',
            nameStyle: headerStyle,
            diffColor: null,
          ),
        ),
        for (final row in rows)
          InkWell(
            onTap: () => _onTeamTap(row),
            child: _tableRow(
              teamName: row.name,
              w: '${row.wins}',
              l: '${row.losses}',
              t: '${row.ties}',
              diff: '${row.pointDifferential > 0 ? '+' : ''}${row.pointDifferential}',
              nameStyle: row.teamId == widget.myTeamId
                  ? TextStyle(fontWeight: FontWeight.bold, color: Theme.of(context).colorScheme.primary)
                  : null,
              diffColor: row.pointDifferential > 0
                  ? Colors.green
                  : row.pointDifferential < 0
                      ? Colors.red
                      : null,
            ),
          ),
      ],
    );
  }

  Widget _tableRow({
    bool isHeader = false,
    required String teamName,
    required String w,
    required String l,
    required String t,
    required String diff,
    TextStyle? nameStyle,
    Color? diffColor,
  }) {
    final boldSmall = isHeader ? const TextStyle(fontWeight: FontWeight.bold, fontSize: 12) : null;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: Padding(
              padding: const EdgeInsets.all(6),
              child: Text(teamName, style: nameStyle),
            ),
          ),
          SizedBox(width: 36, child: Padding(padding: const EdgeInsets.all(6), child: Text(w, style: boldSmall))),
          SizedBox(width: 36, child: Padding(padding: const EdgeInsets.all(6), child: Text(l, style: boldSmall))),
          SizedBox(width: 36, child: Padding(padding: const EdgeInsets.all(6), child: Text(t, style: boldSmall))),
          SizedBox(
            width: 52,
            child: Padding(
              padding: const EdgeInsets.all(6),
              child: Text(diff, style: isHeader ? boldSmall : TextStyle(color: diffColor)),
            ),
          ),
        ],
      ),
    );
  }

  void _onTeamTap(_StandingRow row) {
    final auth = context.read<AuthProvider>();
    if (row.teamId == widget.myTeamId) {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => RosterScreen(
            leagueId: widget.leagueId,
            teamId: row.teamId,
            teamName: row.name,
          ),
        ),
      );
    } else {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ScoutScreen(
            leagueId: widget.leagueId,
            teamId: row.teamId,
            title: row.name,
            myTeamId: auth.teamId!,
          ),
        ),
      );
    }
  }
}
