import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _StatLine {
  final String playerName;
  final String position;
  final int passAttempts, passCompletions, passYards, passTds, interceptionsThrown;
  final int rushAttempts, rushYards, rushTds;
  final int receptions, receivingYards, receivingTds;
  final int fumbles, fumblesLost, sacksAllowed;
  final int tackles, sacks, interceptions, forcedFumbles, fumbleRecoveries;

  _StatLine.fromJson(Map<String, dynamic> j)
      : playerName           = j['player_name'],
        position             = j['position'],
        passAttempts         = j['pass_attempts']        ?? 0,
        passCompletions      = j['pass_completions']     ?? 0,
        passYards            = j['pass_yards']           ?? 0,
        passTds              = j['pass_tds']             ?? 0,
        interceptionsThrown  = j['interceptions_thrown'] ?? 0,
        rushAttempts         = j['rush_attempts']        ?? 0,
        rushYards            = j['rush_yards']           ?? 0,
        rushTds              = j['rush_tds']             ?? 0,
        receptions           = j['receptions']           ?? 0,
        receivingYards       = j['receiving_yards']      ?? 0,
        receivingTds         = j['receiving_tds']        ?? 0,
        fumbles              = j['fumbles']              ?? 0,
        fumblesLost          = j['fumbles_lost']         ?? 0,
        sacksAllowed         = j['sacks_allowed']        ?? 0,
        tackles              = j['tackles']              ?? 0,
        sacks                = j['sacks']                ?? 0,
        interceptions        = j['interceptions']        ?? 0,
        forcedFumbles        = j['forced_fumbles']       ?? 0,
        fumbleRecoveries     = j['fumble_recoveries']    ?? 0;

  bool get hasPassing   => passAttempts > 0;
  bool get hasRushing   => rushAttempts > 0;
  bool get hasReceiving => receptions > 0 || receivingYards > 0;
  bool get hasDefense   => tackles > 0 || sacks > 0 || interceptions > 0 ||
                           forcedFumbles > 0 || fumbleRecoveries > 0;
}

class _ScoringPlay {
  final int quarter;
  final String team; // 'home' or 'away'
  final String type; // 'touchdown' or 'field_goal'
  final int scoreHome;
  final int scoreAway;
  final String? playerName;
  final String? tdType; // 'rushing' or 'receiving'

  _ScoringPlay.fromJson(Map<String, dynamic> j)
      : quarter    = j['quarter'],
        team       = j['team'],
        type       = j['type'],
        scoreHome  = j['score_home'],
        scoreAway  = j['score_away'],
        playerName = j['player_name'] as String?,
        tdType     = j['td_type'] as String?;
}

class _GameDetail {
  final int week;
  final bool isPlayoff;
  final String homeTeamName;
  final int? homeScore;
  final String awayTeamName;
  final int? awayScore;
  final String status;
  final List<_StatLine> homeStats;
  final List<_StatLine> awayStats;
  final List<_ScoringPlay>? scoringPlays;

  _GameDetail.fromJson(Map<String, dynamic> j)
      : week         = j['week'],
        isPlayoff    = j['is_playoff'],
        homeTeamName = j['home_team_name'],
        homeScore    = j['home_score'],
        awayTeamName = j['away_team_name'],
        awayScore    = j['away_score'],
        status       = j['status'],
        homeStats    = (j['home_stats'] as List)
            .map((s) => _StatLine.fromJson(s as Map<String, dynamic>))
            .toList(),
        awayStats    = (j['away_stats'] as List)
            .map((s) => _StatLine.fromJson(s as Map<String, dynamic>))
            .toList(),
        scoringPlays = j['scoring_plays'] == null
            ? null
            : (j['scoring_plays'] as List)
                .map((p) => _ScoringPlay.fromJson(p as Map<String, dynamic>))
                .toList();
}

class GameDetailScreen extends StatefulWidget {
  final String leagueId;
  final String gameId;

  const GameDetailScreen({super.key, required this.leagueId, required this.gameId});

  @override
  State<GameDetailScreen> createState() => _GameDetailScreenState();
}

class _GameDetailScreenState extends State<GameDetailScreen> {
  _GameDetail? _game;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _game = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/games/${widget.gameId}'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load game');
      setState(() {
        _game = _GameDetail.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  String get _weekLabel {
    final g = _game!;
    if (!g.isPlayoff) return 'Week ${g.week}';
    if (g.week == 18) return 'Divisional Round';
    if (g.week == 19) return 'Conference Championship';
    return 'League Championship';
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: _game == null
              ? const Text('Game')
              : Text('${_game!.awayTeamName}  @  ${_game!.homeTeamName}'),
          actions: [
            IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
          ],
          bottom: _game == null
              ? null
              : TabBar(tabs: [
                  const Tab(text: 'Scoring'),
                  Tab(text: _game!.awayTeamName),
                  Tab(text: _game!.homeTeamName),
                ]),
        ),
        body: _error != null
            ? Center(child: Text(_error!))
            : _game == null
                ? const Center(child: CircularProgressIndicator())
                : Column(
                    children: [
                      _buildScoreHeader(),
                      Expanded(
                        child: TabBarView(children: [
                          _buildScoringTab(),
                          _buildBoxScore(_game!.awayStats),
                          _buildBoxScore(_game!.homeStats),
                        ]),
                      ),
                    ],
                  ),
      ),
    );
  }

  Widget _buildScoreHeader() {
    final g = _game!;
    final isComplete = g.status == 'complete';
    return Container(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: Row(
        children: [
          Expanded(
            child: Text(
              g.awayTeamName,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
            ),
          ),
          if (isComplete)
            Text(
              '${g.awayScore}  –  ${g.homeScore}',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
            )
          else
            Text(
              _weekLabel,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          Expanded(
            child: Text(
              g.homeTeamName,
              textAlign: TextAlign.end,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildScoringTab() {
    final plays = _game!.scoringPlays;
    if (plays == null) {
      return Center(
        child: Text(
          'No scoring data for this game',
          style: TextStyle(color: Theme.of(context).colorScheme.outline),
        ),
      );
    }
    if (plays.isEmpty) {
      return Center(
        child: Text(
          '0 – 0',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
      );
    }

    final quarterLabels = {1: '1ST QUARTER', 2: '2ND QUARTER', 3: '3RD QUARTER', 4: '4TH QUARTER', 5: 'OVERTIME'};
    final items = <Widget>[];
    int? lastQuarter;

    for (final play in plays) {
      if (play.quarter != lastQuarter) {
        lastQuarter = play.quarter;
        items.add(Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Text(
            quarterLabels[play.quarter] ?? 'OT',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: Theme.of(context).colorScheme.primary,
              letterSpacing: 1.2,
            ),
          ),
        ));
      }

      final isHome = play.team == 'home';
      final teamName = isHome ? _game!.homeTeamName : _game!.awayTeamName;
      final scoreStr = '${play.scoreAway}–${play.scoreHome}';

      String description;
      if (play.type == 'field_goal') {
        description = 'Field Goal';
      } else if (play.playerName != null) {
        final typeLabel = play.tdType == 'rushing' ? 'Rushing TD' : 'Receiving TD';
        description = '${play.playerName} · $typeLabel';
      } else {
        description = 'Touchdown';
      }

      items.add(Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        child: Row(
          children: [
            SizedBox(
              width: 44,
              child: Text(
                scoreStr,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Icon(
              play.type == 'field_goal' ? Icons.sports_score : Icons.sports_football,
              size: 16,
              color: Theme.of(context).colorScheme.outline,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(teamName, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                  Text(description, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                ],
              ),
            ),
          ],
        ),
      ));
    }

    return ListView(
      padding: EdgeInsets.only(bottom: 24 + MediaQuery.of(context).padding.bottom),
      children: items,
    );
  }

  Widget _buildBoxScore(List<_StatLine> stats) {
    final passing   = stats.where((s) => s.hasPassing).toList()
        ..sort((a, b) => b.passYards.compareTo(a.passYards));
    final rushing   = stats.where((s) => s.hasRushing).toList()
        ..sort((a, b) => b.rushYards.compareTo(a.rushYards));
    final receiving = stats.where((s) => s.hasReceiving).toList()
        ..sort((a, b) => b.receivingYards.compareTo(a.receivingYards));
    final defense   = stats.where((s) => s.hasDefense).toList()
        ..sort((a, b) => b.tackles.compareTo(a.tackles));

    if (passing.isEmpty && rushing.isEmpty && receiving.isEmpty && defense.isEmpty) {
      return const Center(child: Text('No stats recorded'));
    }

    return ListView(
      padding: EdgeInsets.only(bottom: 24 + MediaQuery.of(context).padding.bottom),
      children: [
        if (passing.isNotEmpty) ...[
          _sectionHeader('Passing'),
          _passingHeader(),
          for (final p in passing) _passingRow(p),
        ],
        if (rushing.isNotEmpty) ...[
          _sectionHeader('Rushing'),
          _rushingHeader(),
          for (final p in rushing) _rushingRow(p),
        ],
        if (receiving.isNotEmpty) ...[
          _sectionHeader('Receiving'),
          _receivingHeader(),
          for (final p in receiving) _receivingRow(p),
        ],
        if (defense.isNotEmpty) ...[
          _sectionHeader('Defense'),
          _defenseHeader(),
          for (final p in defense) _defenseRow(p),
        ],
      ],
    );
  }

  Widget _sectionHeader(String label) {
    return Container(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
      child: Text(
        label.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: Theme.of(context).colorScheme.primary,
          letterSpacing: 1.2,
        ),
      ),
    );
  }

  // ── Passing ──────────────────────────────────────────────────

  Widget _passingHeader() => _statRow(
    name: 'Player', pos: '',
    cols: ['C/ATT', 'YDS', 'TD', 'INT'],
    isHeader: true,
  );

  Widget _passingRow(_StatLine p) => _statRow(
    name: p.playerName, pos: p.position,
    cols: [
      '${p.passCompletions}/${p.passAttempts}',
      '${p.passYards}',
      '${p.passTds}',
      '${p.interceptionsThrown}',
    ],
  );

  // ── Rushing ───────────────────────────────────────────────────

  Widget _rushingHeader() => _statRow(
    name: 'Player', pos: '',
    cols: ['CAR', 'YDS', 'TD'],
    isHeader: true,
  );

  Widget _rushingRow(_StatLine p) => _statRow(
    name: p.playerName, pos: p.position,
    cols: ['${p.rushAttempts}', '${p.rushYards}', '${p.rushTds}'],
  );

  // ── Receiving ─────────────────────────────────────────────────

  Widget _receivingHeader() => _statRow(
    name: 'Player', pos: '',
    cols: ['REC', 'YDS', 'TD'],
    isHeader: true,
  );

  Widget _receivingRow(_StatLine p) => _statRow(
    name: p.playerName, pos: p.position,
    cols: ['${p.receptions}', '${p.receivingYards}', '${p.receivingTds}'],
  );

  // ── Defense ───────────────────────────────────────────────────

  Widget _defenseHeader() => _statRow(
    name: 'Player', pos: '',
    cols: ['TKL', 'SCK', 'INT', 'FF', 'FR'],
    isHeader: true,
  );

  Widget _defenseRow(_StatLine p) => _statRow(
    name: p.playerName, pos: p.position,
    cols: [
      '${p.tackles}',
      '${p.sacks}',
      '${p.interceptions}',
      '${p.forcedFumbles}',
      '${p.fumbleRecoveries}',
    ],
  );

  // ── Generic stat row ─────────────────────────────────────────

  Widget _statRow({
    required String name,
    required String pos,
    required List<String> cols,
    bool isHeader = false,
  }) {
    final style = isHeader
        ? Theme.of(context).textTheme.labelSmall?.copyWith(fontWeight: FontWeight.bold)
        : Theme.of(context).textTheme.bodySmall;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
      child: Row(
        children: [
          if (!isHeader && pos.isNotEmpty)
            Container(
              width: 30,
              margin: const EdgeInsets.only(right: 8),
              child: Text(
                pos,
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
            )
          else
            const SizedBox(width: 38),
          Expanded(child: Text(name, style: style, overflow: TextOverflow.ellipsis)),
          for (final col in cols)
            SizedBox(
              width: 38,
              child: Text(col, style: style, textAlign: TextAlign.center),
            ),
        ],
      ),
    );
  }
}
