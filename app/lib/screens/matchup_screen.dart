import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';
import 'roster_screen.dart';
import 'scout_screen.dart';

class _GroupData {
  final double composite;
  final String label;

  _GroupData.fromJson(Map<String, dynamic> j)
      : composite = (j['composite'] as num).toDouble(),
        label = j['label'] as String;
}

class _TeamSide {
  final String teamId;
  final String name;
  final int wins;
  final int losses;
  final int ties;
  final Map<String, _GroupData> groups;

  _TeamSide.fromJson(Map<String, dynamic> j)
      : teamId = j['team_id'] as String,
        name = j['name'] as String,
        wins = j['wins'] as int,
        losses = j['losses'] as int,
        ties = j['ties'] as int,
        groups = {
          for (final e in (j['groups'] as Map<String, dynamic>).entries)
            e.key: _GroupData.fromJson(e.value as Map<String, dynamic>)
        };
}

class MatchupScreen extends StatefulWidget {
  final String leagueId;
  final String gameId;
  final String myTeamId;
  final bool isHome;
  final String weekLabel;

  const MatchupScreen({
    super.key,
    required this.leagueId,
    required this.gameId,
    required this.myTeamId,
    required this.isHome,
    required this.weekLabel,
  });

  @override
  State<MatchupScreen> createState() => _MatchupScreenState();
}

class _MatchupScreenState extends State<MatchupScreen> {
  _TeamSide? _home;
  _TeamSide? _away;
  bool _loading = true;
  String? _error;

  static const _offensePositions = ['QB', 'WR', 'TE', 'RB', 'OL'];
  static const _defensePositions = ['DT', 'DE', 'LB', 'CB', 'S'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    final auth = context.read<AuthProvider>();
    try {
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/games/${widget.gameId}/matchup'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load matchup');
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      setState(() {
        _home    = _TeamSide.fromJson(data['home_team'] as Map<String, dynamic>);
        _away    = _TeamSide.fromJson(data['away_team'] as Map<String, dynamic>);
        _loading = false;
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
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.weekLabel),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : _buildContent(),
    );
  }

  Widget _buildContent() {
    final home = _home!;
    final away = _away!;
    final myTeam  = widget.isHome ? home : away;
    final oppTeam = widget.isHome ? away : home;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildHeader(myTeam, oppTeam),
        const SizedBox(height: 24),
        _sectionLabel('OFFENSE'),
        ..._buildGroupRows(_offensePositions, myTeam, oppTeam),
        const SizedBox(height: 20),
        _sectionLabel('DEFENSE'),
        ..._buildGroupRows(_defensePositions, myTeam, oppTeam),
      ],
    );
  }

  Widget _buildHeader(_TeamSide myTeam, _TeamSide oppTeam) {
    String rec(_TeamSide t) =>
        t.ties > 0 ? '${t.wins}-${t.losses}-${t.ties}' : '${t.wins}-${t.losses}';

    return Column(
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(child: _teamNameButton(myTeam, isMine: true)),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text(
                widget.isHome ? 'vs' : '@',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
            Expanded(child: _teamNameButton(oppTeam, isMine: false)),
          ],
        ),
        const SizedBox(height: 4),
        Row(
          children: [
            Expanded(
              child: Text(
                rec(myTeam),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            const SizedBox(width: 48),
            Expanded(
              child: Text(
                rec(oppTeam),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _teamNameButton(_TeamSide team, {required bool isMine}) {
    final auth = context.read<AuthProvider>();
    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => isMine
              ? RosterScreen(
                  leagueId: widget.leagueId,
                  teamId: team.teamId,
                  teamName: team.name,
                )
              : ScoutScreen(
                  leagueId: widget.leagueId,
                  teamId: team.teamId,
                  title: team.name,
                  myTeamId: widget.myTeamId,
                ),
        ),
      ),
      child: Text(
        team.name,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
          color: Theme.of(context).colorScheme.primary,
          decoration: TextDecoration.underline,
          decorationColor: Theme.of(context).colorScheme.primary,
        ),
      ),
    );
  }

  Widget _sectionLabel(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Text(
        text,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: Theme.of(context).colorScheme.primary,
          letterSpacing: 1.5,
        ),
      ),
    );
  }

  List<Widget> _buildGroupRows(
    List<String> positions,
    _TeamSide myTeam,
    _TeamSide oppTeam,
  ) {
    final rows = <Widget>[];
    for (final pos in positions) {
      final mine = myTeam.groups[pos];
      final opp  = oppTeam.groups[pos];
      if (mine == null || opp == null) continue;
      rows.add(_GroupRow(
        position: pos,
        myComposite: mine.composite,
        oppComposite: opp.composite,
        oppLabel: opp.label,
      ));
    }
    return rows;
  }
}

class _GroupRow extends StatelessWidget {
  final String position;
  final double myComposite;
  final double oppComposite;
  final String oppLabel;

  static const _min = 30.0;
  static const _max = 95.0;

  const _GroupRow({
    required this.position,
    required this.myComposite,
    required this.oppComposite,
    required this.oppLabel,
  });

  double _frac(double composite) =>
      ((composite - _min) / (_max - _min)).clamp(0.0, 1.0);

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    final muted   = Theme.of(context).colorScheme.outlineVariant;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          // My side: number on far left, bar grows right-to-left from center
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  myComposite.toStringAsFixed(1),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: LayoutBuilder(
                      builder: (_, constraints) => Container(
                        width: constraints.maxWidth * _frac(myComposite),
                        height: 8,
                        decoration: BoxDecoration(
                          color: primary,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Position label
          SizedBox(
            width: 40,
            child: Text(
              position,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
          ),

          // Opponent side: bar grows left-to-right from center, label on far right
          Expanded(
            child: Row(
              children: [
                Expanded(
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: LayoutBuilder(
                      builder: (_, constraints) => Container(
                        width: constraints.maxWidth * _frac(oppComposite),
                        height: 8,
                        decoration: BoxDecoration(
                          color: muted,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  oppLabel,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
