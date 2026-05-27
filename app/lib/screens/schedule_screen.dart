import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _Game {
  final String id;
  final int week;
  final String homeTeamId;
  final String awayTeamId;
  final int? homeScore;
  final int? awayScore;
  final bool isComplete;
  final bool isPlayoff;

  _Game.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        week = j['week'],
        homeTeamId = j['home_team_id'],
        awayTeamId = j['away_team_id'],
        homeScore = j['home_score'],
        awayScore = j['away_score'],
        isComplete = j['status'] == 'complete',
        isPlayoff = j['is_playoff'] as bool? ?? false;
}

class ScheduleScreen extends StatefulWidget {
  final String leagueId;
  final String myTeamId;

  const ScheduleScreen({super.key, required this.leagueId, required this.myTeamId});

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  List<_Game>? _games;
  Map<String, String>? _teamNames;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _games = null; });
    final auth = context.read<AuthProvider>();
    try {
      final responses = await Future.wait([
        http.get(Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/schedule'), headers: auth.authHeaders),
        http.get(Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams'), headers: auth.authHeaders),
      ]);
      if (responses[0].statusCode != 200) throw Exception('Failed to load schedule');
      if (responses[1].statusCode != 200) throw Exception('Failed to load teams');

      final games = (jsonDecode(responses[0].body) as List)
          .map((j) => _Game.fromJson(j as Map<String, dynamic>))
          .toList();
      final names = <String, String>{};
      for (final t in jsonDecode(responses[1].body) as List) {
        final team = t as Map<String, dynamic>;
        names[team['id'] as String] = team['name'] as String;
      }

      setState(() { _games = games; _teamNames = names; });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Schedule'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _games == null
              ? const Center(child: CircularProgressIndicator())
              : _buildSchedule(),
    );
  }

  Widget _buildSchedule() {
    // Group by week
    final Map<int, List<_Game>> byWeek = {};
    for (final g in _games!) {
      byWeek.putIfAbsent(g.week, () => []).add(g);
    }

    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 8),
      children: [
        for (final week in byWeek.keys.toList()..sort()) ...[
          _weekHeader(week),
          for (final game in byWeek[week]!) _gameRow(game),
        ],
      ],
    );
  }

  Widget _weekHeader(int week) {
    final String label;
    if (week <= 17) {
      label = 'Week $week';
    } else if (week == 18) {
      label = 'Divisional Round';
    } else if (week == 19) {
      label = 'Conference Championship';
    } else {
      label = 'League Championship';
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
          color: Theme.of(context).colorScheme.primary,
        ),
      ),
    );
  }

  Widget _gameRow(_Game game) {
    final isMyGame = game.homeTeamId == widget.myTeamId || game.awayTeamId == widget.myTeamId;
    final homeName = _teamNames?[game.homeTeamId] ?? '—';
    final awayName = _teamNames?[game.awayTeamId] ?? '—';

    Widget scoreWidget;
    if (game.isComplete) {
      final myScore  = game.homeTeamId == widget.myTeamId ? game.homeScore : game.awayScore;
      final oppScore = game.homeTeamId == widget.myTeamId ? game.awayScore : game.homeScore;
      final won = isMyGame && (myScore ?? 0) > (oppScore ?? 0);
      final lost = isMyGame && (myScore ?? 0) < (oppScore ?? 0);
      scoreWidget = Text(
        '${game.homeScore}–${game.awayScore}',
        style: TextStyle(
          fontWeight: isMyGame ? FontWeight.bold : FontWeight.normal,
          color: isMyGame ? (won ? Colors.green : lost ? Colors.red : null) : null,
        ),
      );
    } else {
      scoreWidget = Text(
        'Upcoming',
        style: TextStyle(color: Theme.of(context).colorScheme.outline),
      );
    }

    return Container(
      color: isMyGame ? Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.4) : null,
      child: ListTile(
        dense: true,
        title: Text('$awayName  @  $homeName'),
        trailing: scoreWidget,
      ),
    );
  }
}
