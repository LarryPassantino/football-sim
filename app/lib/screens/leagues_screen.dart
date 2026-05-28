import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';
import 'game_detail_screen.dart';
import 'matchup_screen.dart';
import 'roster_screen.dart';
import 'schedule_screen.dart';
import 'scout_screen.dart';
import 'standings_screen.dart';

class _LeagueDetail {
  final String name;
  final int? currentWeek;
  final String? seasonStatus;

  _LeagueDetail.fromJson(Map<String, dynamic> j)
      : name = j['name'],
        currentWeek = j['current_week'],
        seasonStatus = j['season_status'];
}

class _MyRecord {
  final int wins;
  final int losses;
  final int ties;
  final String conference;
  final String division;

  _MyRecord({required this.wins, required this.losses, required this.ties, required this.conference, required this.division});
}

class _GameSummary {
  final String gameId;
  final bool isHome;
  final String opponentId;
  final String opponentName;
  final int? myScore;
  final int? opponentScore;
  final bool isPlayed;
  final bool isPlayoff;

  _GameSummary({
    required this.gameId,
    required this.isHome,
    required this.opponentId,
    required this.opponentName,
    required this.myScore,
    required this.opponentScore,
    required this.isPlayed,
    required this.isPlayoff,
  });
}

class _IrPlayer {
  final String id;
  final String name;
  final String position;
  final int injuryGamesRemaining;
  final bool onIr;

  _IrPlayer.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        position = j['position'],
        injuryGamesRemaining = j['injury_games_remaining'],
        onIr = j['on_ir'] as bool? ?? false;

  bool get isReturnReady => onIr && injuryGamesRemaining == 0;
}

class LeaguesScreen extends StatefulWidget {
  const LeaguesScreen({super.key});

  @override
  State<LeaguesScreen> createState() => _LeaguesScreenState();
}

class _LeaguesScreenState extends State<LeaguesScreen> {
  _LeagueDetail? _league;
  _MyRecord? _record;
  _GameSummary? _currentGame;
  List<_IrPlayer> _irPlayers = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    final auth = context.read<AuthProvider>();
    final leagueId = auth.leagueId!;
    final teamId   = auth.teamId!;

    try {
      // Fetch league detail, standings, and roster in parallel
      final responses = await Future.wait([
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId'), headers: auth.authHeaders),
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId/standings'), headers: auth.authHeaders),
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId/teams/$teamId/roster'), headers: auth.authHeaders),
      ]);

      if (responses[0].statusCode != 200) throw Exception('Failed to load league');
      if (responses[1].statusCode != 200) throw Exception('Failed to load standings');

      final leagueJson   = jsonDecode(responses[0].body) as Map<String, dynamic>;
      final standingsJson = jsonDecode(responses[1].body);
      final league = _LeagueDetail.fromJson(leagueJson);

      // Find my record from standings
      _MyRecord? record;
      final Map<String, String> teamNames = {};
      for (final row in standingsJson['standings'] as List) {
        final r = row as Map<String, dynamic>;
        teamNames[r['team_id'] as String] = r['name'] as String;
        if (r['team_id'] == teamId) {
          record = _MyRecord(
            wins: r['wins'],
            losses: r['losses'],
            ties: r['ties'],
            conference: r['conference'],
            division: r['division'],
          );
        }
      }

      // Fetch current week's schedule
      _GameSummary? gameSummary;
      if (league.currentWeek != null) {
        final scheduleRes = await http.get(
          Uri.parse('$kBaseUrl/leagues/$leagueId/schedule?week=${league.currentWeek}'),
          headers: auth.authHeaders,
        );
        if (scheduleRes.statusCode == 200) {
          final games = jsonDecode(scheduleRes.body) as List;
          for (final g in games) {
            final game = g as Map<String, dynamic>;
            final homeId = game['home_team_id'] as String;
            final awayId = game['away_team_id'] as String;
            if (homeId == teamId || awayId == teamId) {
              final isHome   = homeId == teamId;
              final oppId    = isHome ? awayId : homeId;
              final isPlayed = game['status'] == 'complete';
              gameSummary = _GameSummary(
                gameId: game['id'] as String,
                isHome: isHome,
                opponentId: oppId,
                opponentName: teamNames[oppId] ?? 'Unknown',
                myScore: isPlayed ? (isHome ? game['home_score'] : game['away_score']) as int? : null,
                opponentScore: isPlayed ? (isHome ? game['away_score'] : game['home_score']) as int? : null,
                isPlayed: isPlayed,
                isPlayoff: game['is_playoff'] as bool? ?? false,
              );
              break;
            }
          }
        }
      }

      // Extract IR players from roster
      List<_IrPlayer> irPlayers = [];
      if (responses[2].statusCode == 200) {
        final rosterData = jsonDecode(responses[2].body) as List;
        irPlayers = rosterData
            .map((j) => _IrPlayer.fromJson(j as Map<String, dynamic>))
            .where((p) => p.onIr)
            .toList();
        // Return-ready first, then injured IR sorted by games remaining
        irPlayers.sort((a, b) {
          if (a.isReturnReady != b.isReturnReady) return a.isReturnReady ? -1 : 1;
          return a.injuryGamesRemaining.compareTo(b.injuryGamesRemaining);
        });
      }

      setState(() {
        _league      = league;
        _record      = record;
        _currentGame = gameSummary;
        _irPlayers   = irPlayers;
        _loading     = false;
      });
    } catch (e) {
      setState(() {
        _error   = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      appBar: AppBar(
        title: Text(auth.teamName ?? 'My Team'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
          IconButton(icon: const Icon(Icons.logout), onPressed: () => auth.logout()),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : _buildHome(auth),
    );
  }

  Widget _buildHome(AuthProvider auth) {
    final leagueId = auth.leagueId!;
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        _buildRecordCard(),
        const SizedBox(height: 16),
        _buildCurrentGameCard(),
        _buildAlertsSection(auth),
        const SizedBox(height: 24),
        FilledButton.icon(
          icon: const Icon(Icons.people),
          label: const Text('Roster'),
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => RosterScreen(
                leagueId: leagueId,
                teamId: auth.teamId!,
                teamName: auth.teamName ?? 'My Team',
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          icon: const Icon(Icons.bar_chart),
          label: const Text('Standings'),
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => StandingsScreen(
                leagueId: leagueId,
                myTeamId: auth.teamId!,
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          icon: const Icon(Icons.calendar_today),
          label: const Text('Full Schedule'),
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => ScheduleScreen(
                leagueId: leagueId,
                myTeamId: auth.teamId!,
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          icon: const Icon(Icons.person_search),
          label: const Text('Free Agents'),
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => ScoutScreen(
                leagueId: leagueId,
                title: 'Free Agents',
                myTeamId: auth.teamId!,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildAlertsSection(AuthProvider auth) {
    final alerts = <Widget>[];

    // Season phase
    final status = _league?.seasonStatus;
    if (status == 'playoffs') {
      alerts.add(_alertTile(
        icon: Icons.emoji_events,
        color: Colors.amber,
        title: 'Playoffs underway',
        subtitle: _weekLabel(_league),
      ));
    } else if (status == 'offseason') {
      alerts.add(_alertTile(
        icon: Icons.sports_football,
        color: Theme.of(context).colorScheme.primary,
        title: 'Offseason',
        subtitle: 'Prepare for the draft',
      ));
    } else if (status == 'complete') {
      alerts.add(_alertTile(
        icon: Icons.check_circle,
        color: Colors.green,
        title: 'Season complete',
      ));
    }

    // IR players — return-ready first, then injured
    for (final p in _irPlayers) {
      if (p.isReturnReady) {
        alerts.add(_alertTile(
          icon: Icons.arrow_circle_up,
          color: Colors.green,
          title: '${p.name} (${p.position})',
          subtitle: 'Return ready — activate from roster',
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => RosterScreen(
                leagueId: auth.leagueId!,
                teamId: auth.teamId!,
                teamName: auth.teamName ?? 'My Team',
              ),
            ),
          ).then((_) => _load()),
        ));
      } else {
        alerts.add(_alertTile(
          icon: Icons.local_hospital,
          color: Colors.red,
          title: '${p.name} (${p.position})',
          subtitle: 'On IR · OUT ${p.injuryGamesRemaining}g',
        ));
      }
    }

    if (alerts.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'ALERTS',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: Theme.of(context).colorScheme.primary,
                  letterSpacing: 1.5,
                ),
              ),
              ...alerts,
            ],
          ),
        ),
      ),
    );
  }

  Widget _alertTile({
    required IconData icon,
    required Color color,
    required String title,
    String? subtitle,
    VoidCallback? onTap,
  }) {
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon, color: color, size: 20),
      title: Text(title, style: const TextStyle(fontSize: 14)),
      subtitle: subtitle != null
          ? Text(subtitle, style: const TextStyle(fontSize: 12))
          : null,
      trailing: onTap != null
          ? Icon(Icons.chevron_right, size: 18, color: Theme.of(context).colorScheme.outline)
          : null,
      onTap: onTap,
    );
  }

  Widget _buildRecordCard() {
    final record = _record;
    final league = _league;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            const Icon(Icons.sports_football, size: 36),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    league?.name ?? '—',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (record != null)
                    Text(
                      '${record.conference} · ${record.division}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                ],
              ),
            ),
            if (record != null)
              Text(
                '${record.wins}–${record.losses}–${record.ties}',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildCurrentGameCard() {
    final game = _currentGame;
    final league = _league;
    final weekLabel = _weekLabel(league);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              weekLabel,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(height: 8),
            if (game == null)
              const Text('No game this week')
            else if (game.isPlayed)
              GestureDetector(
                onTap: () {
                  final auth = context.read<AuthProvider>();
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => GameDetailScreen(
                        leagueId: auth.leagueId!,
                        gameId: game.gameId,
                      ),
                    ),
                  );
                },
                child: _buildScoreLine(game),
              )
            else
              InkWell(
                onTap: () {
                  final auth = context.read<AuthProvider>();
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => MatchupScreen(
                        leagueId: auth.leagueId!,
                        gameId: game.gameId,
                        myTeamId: auth.teamId!,
                        isHome: game.isHome,
                        weekLabel: weekLabel,
                      ),
                    ),
                  );
                },
                child: Row(
                  children: [
                    Text(
                      '${game.isHome ? 'vs' : '@'}  ',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    Text(
                      game.opponentName,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const Spacer(),
                    Icon(
                      Icons.chevron_right,
                      size: 18,
                      color: Theme.of(context).colorScheme.outline,
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildScoreLine(_GameSummary game) {
    final myScore  = game.myScore  ?? 0;
    final oppScore = game.opponentScore ?? 0;
    final won  = myScore > oppScore;
    final lost = myScore < oppScore;
    return Row(
      children: [
        Text(
          won ? 'W' : lost ? 'L' : 'T',
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            color: won ? Colors.green : lost ? Colors.red : Colors.grey,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(width: 12),
        Text(
          '${game.myScore}–${game.opponentScore}  ${game.isHome ? 'vs' : '@'}  ',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        _opponentLink(game),
      ],
    );
  }

  Widget _opponentLink(_GameSummary game) {
    final auth = context.read<AuthProvider>();
    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ScoutScreen(
            leagueId: auth.leagueId!,
            teamId: game.opponentId,
            title: game.opponentName,
            myTeamId: auth.teamId!,
          ),
        ),
      ),
      child: Text(
        game.opponentName,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
          color: Theme.of(context).colorScheme.primary,
          decoration: TextDecoration.underline,
          decorationColor: Theme.of(context).colorScheme.primary,
        ),
      ),
    );
  }

  String _weekLabel(_LeagueDetail? league) {
    if (league == null) return 'This Week';
    final w = league.currentWeek;
    if (w == null) return 'This Week';
    if (w <= 17) return 'Week $w';
    if (w == 18) return 'Divisional Round';
    if (w == 19) return 'Conference Championship';
    if (w == 20) return 'League Championship';
    return 'Offseason';
  }
}
