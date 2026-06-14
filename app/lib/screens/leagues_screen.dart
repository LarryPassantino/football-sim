import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';
import 'game_detail_screen.dart';
import 'history_screen.dart';
import 'league_leaders_screen.dart';
import 'matchup_screen.dart';
import 'roster_screen.dart';
import 'draft_screen.dart';
import 'schedule_screen.dart';
import 'scout_screen.dart';
import 'standings_screen.dart';

class _LeagueDetail {
  final String name;
  final int? currentWeek;
  final String? seasonStatus;
  final int? offseasonDaysRemaining;
  final int? preseasonDaysRemaining;

  _LeagueDetail.fromJson(Map<String, dynamic> j)
      : name = j['name'],
        currentWeek = j['current_week'],
        seasonStatus = j['season_status'],
        offseasonDaysRemaining = j['offseason_days_remaining'],
        preseasonDaysRemaining = j['preseason_days_remaining'];
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
  final int week;
  final bool isHome;
  final String opponentId;
  final String opponentName;
  final int? myScore;
  final int? opponentScore;
  final bool isPlayed;
  final bool isPlayoff;

  _GameSummary({
    required this.gameId,
    required this.week,
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
  Map<String, _MyRecord> _teamRecords = {};
  _GameSummary? _lastGame;
  _GameSummary? _nextGame;
  String? _headline;
  List<_IrPlayer> _irPlayers = [];
  List<Map<String, dynamic>> _myDraftPicks = [];
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
      // Fetch league detail, standings, roster, news, and draft results in parallel
      final responses = await Future.wait([
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId'), headers: auth.authHeaders),
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId/standings'), headers: auth.authHeaders),
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId/teams/$teamId/roster'), headers: auth.authHeaders),
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId/teams/$teamId/news'), headers: auth.authHeaders),
        http.get(Uri.parse('$kBaseUrl/leagues/$leagueId/draft/results'), headers: auth.authHeaders),
      ]);

      if (responses[0].statusCode != 200) throw Exception('Failed to load league');
      if (responses[1].statusCode != 200) throw Exception('Failed to load standings');

      final headline = responses[3].statusCode == 200
          ? (jsonDecode(responses[3].body) as Map<String, dynamic>)['headline'] as String?
          : null;

      final leagueJson   = jsonDecode(responses[0].body) as Map<String, dynamic>;
      final standingsJson = jsonDecode(responses[1].body);
      final league = _LeagueDetail.fromJson(leagueJson);

      // Find my record from standings; store all records for opponent display
      _MyRecord? record;
      final Map<String, String> teamNames = {};
      final Map<String, _MyRecord> teamRecords = {};
      for (final row in standingsJson['standings'] as List) {
        final r = row as Map<String, dynamic>;
        final tid = r['team_id'] as String;
        teamNames[tid] = r['name'] as String;
        final rec = _MyRecord(
          wins: r['wins'],
          losses: r['losses'],
          ties: r['ties'],
          conference: r['conference'],
          division: r['division'],
        );
        teamRecords[tid] = rec;
        if (tid == teamId) record = rec;
      }

      // Fetch full schedule to find last result and next game
      _GameSummary? lastGame, nextGame;
      final scheduleRes = await http.get(
        Uri.parse('$kBaseUrl/leagues/$leagueId/schedule'),
        headers: auth.authHeaders,
      );
      if (scheduleRes.statusCode == 200) {
        final games = jsonDecode(scheduleRes.body) as List;
        for (final g in games) {
          final game   = g as Map<String, dynamic>;
          final homeId = game['home_team_id'] as String;
          final awayId = game['away_team_id'] as String;
          if (homeId != teamId && awayId != teamId) continue;
          final isHome   = homeId == teamId;
          final oppId    = isHome ? awayId : homeId;
          final isPlayed = game['status'] == 'complete';
          final gs = _GameSummary(
            gameId:        game['id'] as String,
            week:          game['week'] as int,
            isHome:        isHome,
            opponentId:    oppId,
            opponentName:  teamNames[oppId] ?? 'Unknown',
            myScore:       isPlayed ? (isHome ? game['home_score'] : game['away_score']) as int? : null,
            opponentScore: isPlayed ? (isHome ? game['away_score'] : game['home_score']) as int? : null,
            isPlayed:      isPlayed,
            isPlayoff:     game['is_playoff'] as bool? ?? false,
          );
          if (isPlayed) {
            lastGame = gs;
          } else {
            nextGame ??= gs;
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

      List<Map<String, dynamic>> myDraftPicks = [];
      if (responses[4].statusCode == 200) {
        final draftData = jsonDecode(responses[4].body) as Map<String, dynamic>;
        myDraftPicks = (draftData['my_picks'] as List)
            .map((p) => p as Map<String, dynamic>)
            .toList();
      }

      setState(() {
        _league        = league;
        _record        = record;
        _teamRecords   = teamRecords;
        _lastGame      = lastGame;
        _nextGame      = nextGame;
        _headline      = headline;
        _irPlayers     = irPlayers;
        _myDraftPicks  = myDraftPicks;
        _loading       = false;
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
          IconButton(icon: const Icon(Icons.edit), onPressed: () => _showRenameDialog(auth)),
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

  Future<void> _showRenameDialog(AuthProvider auth) async {
    final controller = TextEditingController(text: auth.teamName);
    final newName = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Rename Team'),
        content: TextField(
          controller: controller,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(labelText: 'Team name'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (newName == null || newName.isEmpty || newName == auth.teamName || !mounted) return;

    try {
      final res = await http.patch(
        Uri.parse('$kBaseUrl/leagues/${auth.leagueId}/teams/${auth.teamId}'),
        headers: auth.authHeaders,
        body: jsonEncode({'name': newName}),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        await auth.updateTeamName(newName);
      } else {
        final msg = jsonDecode(res.body)['detail'] ?? 'Rename failed';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
        );
      }
    }
  }

  Widget _buildHome(AuthProvider auth) {
    final leagueId = auth.leagueId!;
    return ListView(
      padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + MediaQuery.of(context).padding.bottom),
      children: [
        _buildRecordCard(),
        if (_headline != null) ...[
          const SizedBox(height: 12),
          _buildHeadlineCard(_headline!),
        ],
        const SizedBox(height: 16),
        if (_lastGame != null) ...[
          _buildLastResultCard(_lastGame!),
          const SizedBox(height: 12),
        ],
        if (_nextGame != null) _buildNextGameCard(_nextGame!),
        _buildAlertsSection(auth),
        if (_myDraftPicks.isNotEmpty) ...[
          const SizedBox(height: 16),
          _buildDraftPicksCard(),
        ],
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
          icon: const Icon(Icons.leaderboard),
          label: const Text('League Leaders'),
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => LeagueLeadersScreen(leagueId: leagueId),
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
                initialWeek: _lastGame?.week ?? _league?.currentWeek,
              ),
            ),
          ),
        ),
        if (_league?.seasonStatus == 'offseason' || _league?.seasonStatus == 'preseason') ...[
          const SizedBox(height: 12),
          FilledButton.icon(
            icon: const Icon(Icons.how_to_vote),
            label: const Text('Draft Board'),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => DraftScreen(leagueId: leagueId, myTeamId: auth.teamId!)),
            ),
          ),
        ],
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
        const SizedBox(height: 12),
        OutlinedButton.icon(
          icon: const Icon(Icons.history),
          label: const Text('Team History'),
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => HistoryScreen(
                leagueId: leagueId,
                teamId: auth.teamId!,
                teamName: auth.teamName ?? 'My Team',
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
        subtitle: _league?.currentWeek != null ? _weekLabel(_league!.currentWeek!) : null,
      ));
    } else if (status == 'offseason') {
      final days = _league?.offseasonDaysRemaining;
      final subtitle = days == null || days <= 0
          ? 'Draft running soon'
          : days == 1
              ? 'Draft tomorrow — set your board'
              : 'Draft in $days days — set your board';
      alerts.add(_alertTile(
        icon: Icons.sports_football,
        color: Theme.of(context).colorScheme.primary,
        title: 'Offseason',
        subtitle: subtitle,
      ));
    } else if (status == 'preseason') {
      final days = _league?.preseasonDaysRemaining;
      final subtitle = days == null || days <= 0
          ? 'Season starting soon'
          : days == 1
              ? 'Season starts tomorrow'
              : 'Season starts in $days days';
      alerts.add(_alertTile(
        icon: Icons.how_to_vote,
        color: Theme.of(context).colorScheme.primary,
        title: 'Preseason — roster finalization',
        subtitle: subtitle,
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

  Widget _buildHeadlineCard(String headline) {
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainerLowest,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.newspaper,
              size: 16,
              color: Theme.of(context).colorScheme.outline,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                headline,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  fontStyle: FontStyle.italic,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLastResultCard(_GameSummary game) {
    final auth = context.read<AuthProvider>();
    final label = _weekLabel(game.week);
    final myScore  = game.myScore  ?? 0;
    final oppScore = game.opponentScore ?? 0;
    final won  = myScore > oppScore;
    final lost = myScore < oppScore;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'LAST RESULT · $label',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(height: 8),
            InkWell(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => GameDetailScreen(
                    leagueId: auth.leagueId!,
                    gameId: game.gameId,
                  ),
                ),
              ),
              child: Row(
                children: [
                  Text(
                    won ? 'W' : lost ? 'L' : 'T',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: won ? Colors.green : lost ? Colors.red : Colors.grey,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '${game.myScore}–${game.opponentScore}  ${game.isHome ? 'vs' : '@'}  ${game.opponentName}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const Spacer(),
                  Icon(
                    Icons.open_in_new,
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

  Widget _buildNextGameCard(_GameSummary game) {
    final auth = context.read<AuthProvider>();
    final label = _weekLabel(game.week);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'NEXT · $label',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(height: 8),
            InkWell(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => MatchupScreen(
                    leagueId: auth.leagueId!,
                    gameId: game.gameId,
                    myTeamId: auth.teamId!,
                    isHome: game.isHome,
                    weekLabel: label,
                  ),
                ),
              ),
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
                  if (_teamRecords[game.opponentId] case final opp?) ...[
                    const SizedBox(width: 8),
                    Text(
                      opp.ties > 0
                          ? '${opp.wins}–${opp.losses}–${opp.ties}'
                          : '${opp.wins}–${opp.losses}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.outline,
                      ),
                    ),
                  ],
                  const Spacer(),
                  Icon(
                    Icons.open_in_new,
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


  Widget _buildDraftPicksCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'DRAFT PICKS',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Theme.of(context).colorScheme.primary,
                letterSpacing: 1.5,
              ),
            ),
            const SizedBox(height: 4),
            ..._myDraftPicks.map((p) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(children: [
                SizedBox(
                  width: 64,
                  child: Text(
                    'Rd ${p['round']}  #${p['pick']}',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: Theme.of(context).colorScheme.outline,
                    ),
                  ),
                ),
                Text(
                  '${p['position']}  ',
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                ),
                Expanded(
                  child: Text(p['player_name'] as String, style: const TextStyle(fontSize: 13)),
                ),
                Text(
                  p['composite_label'] as String,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: Theme.of(context).colorScheme.outline,
                  ),
                ),
              ]),
            )),
          ],
        ),
      ),
    );
  }

  String _weekLabel(int week) {
    if (week <= 17) return 'Week $week';
    if (week == 18) return 'Divisional Round';
    if (week == 19) return 'Conference Championship';
    if (week == 20) return 'League Championship';
    return 'Postseason';
  }
}
