import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _Player {
  final String id;
  final String name;
  final String position;
  final int age;
  final double composite;
  final Map<String, int> namedStats;
  final int injuryGamesRemaining;
  final bool onIr;

  _Player.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        position = j['position'],
        age = j['age'],
        composite = (j['composite'] as num).toDouble(),
        namedStats = (j['named_stats'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, v as int)),
        injuryGamesRemaining = j['injury_games_remaining'],
        onIr = j['on_ir'] as bool? ?? false;

  bool get isInjured       => injuryGamesRemaining > 0;
  bool get isReturnReady   => onIr && injuryGamesRemaining == 0;
}

const _positionGroups = {
  'Offense':       ['QB', 'WR', 'TE', 'RB', 'OL'],
  'Defense':       ['DT', 'DE', 'LB', 'CB', 'S'],
  'Special Teams': ['K', 'P'],
};

class RosterScreen extends StatefulWidget {
  final String leagueId;
  final String teamId;
  final String teamName;

  const RosterScreen({
    super.key,
    required this.leagueId,
    required this.teamId,
    required this.teamName,
  });

  @override
  State<RosterScreen> createState() => _RosterScreenState();
}

class _RosterScreenState extends State<RosterScreen> {
  List<_Player>? _players;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _players = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.teamId}/roster'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load roster');
      final data = jsonDecode(res.body) as List;
      setState(() {
        _players = data.map((j) => _Player.fromJson(j as Map<String, dynamic>)).toList();
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.teamName),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _players == null
              ? const Center(child: CircularProgressIndicator())
              : _buildRoster(),
    );
  }

  Widget _buildRoster() {
    final byPosition = <String, List<_Player>>{};
    for (final p in _players!) {
      byPosition.putIfAbsent(p.position, () => []).add(p);
    }

    return ListView(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom),
      children: [
        for (final entry in _positionGroups.entries) ...[
          _groupHeader(entry.key),
          for (final pos in entry.value)
            if (byPosition.containsKey(pos)) ...[
              _positionHeader(pos),
              for (final player in byPosition[pos]!)
                _playerTile(player),
            ],
        ],
      ],
    );
  }

  Widget _groupHeader(String label) {
    return Container(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Text(
        label.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: Theme.of(context).colorScheme.primary,
          letterSpacing: 1.2,
        ),
      ),
    );
  }

  Widget _positionHeader(String pos) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 2),
      child: Text(pos, style: Theme.of(context).textTheme.labelMedium),
    );
  }

  Widget _playerTile(_Player player) {
    String subtitle = 'Age ${player.age}';
    if (player.isReturnReady)       subtitle += '  ·  Return ready';
    else if (player.onIr)           subtitle += '  ·  IR · OUT ${player.injuryGamesRemaining}g';
    else if (player.isInjured)      subtitle += '  ·  OUT ${player.injuryGamesRemaining}g';

    final Widget trailing;
    if (player.isReturnReady) {
      trailing = FilledButton.tonal(
        onPressed: () => _showActivateDialog(player),
        child: const Text('Activate'),
      );
    } else if (player.onIr) {
      trailing = Row(
        mainAxisSize: MainAxisSize.min,
        children: [_irBadge(), const SizedBox(width: 8), _compositeChip(player.composite)],
      );
    } else {
      trailing = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (player.isInjured)
            const Padding(
              padding: EdgeInsets.only(right: 4),
              child: Icon(Icons.local_hospital, size: 16, color: Colors.red),
            ),
          _compositeChip(player.composite),
          _releaseMenuButton(player),
        ],
      );
    }

    return ListTile(
      dense: true,
      title: Text(player.name),
      subtitle: Text(subtitle),
      trailing: trailing,
      onTap: player.isReturnReady ? null : () => _showPlayerDetail(player),
    );
  }

  Widget _releaseMenuButton(_Player player) {
    return PopupMenuButton<String>(
      icon: const Icon(Icons.more_vert, size: 18),
      onSelected: (val) {
        if (val == 'release') _confirmRelease(player);
      },
      itemBuilder: (_) => const [
        PopupMenuItem(value: 'release', child: Text('Release')),
      ],
    );
  }

  Future<void> _confirmRelease(_Player player) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Release Player'),
        content: Text('Release ${player.name} to free agency?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Release'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    try {
      final auth = context.read<AuthProvider>();
      final res = await http.post(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.teamId}/release'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode({'player_id': player.id}),
      );
      if (!mounted) return;
      if (res.statusCode != 200) {
        final msg = jsonDecode(res.body)['detail'] ?? 'Release failed';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
        return;
      }
      final data   = jsonDecode(res.body) as Map<String, dynamic>;
      final thin   = (data['thin_positions'] as List).cast<String>();
      _load();
      if (thin.isNotEmpty) _showThinWarning(thin);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
        );
      }
    }
  }

  void _showThinWarning(List<String> thin) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Roster Short'),
        content: Text(
          'You are below the active roster limit at: ${thin.join(', ')}.\n\nConsider signing a free agent.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK')),
        ],
      ),
    );
  }

  Widget _irBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.red.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: Colors.red.withValues(alpha: 0.5)),
      ),
      child: const Text('IR', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.red)),
    );
  }

  static const _positionMax = {
    'QB': 2, 'WR': 5, 'TE': 2, 'RB': 3, 'OL': 6,
    'DT': 4, 'DE': 4, 'LB': 5, 'CB': 4, 'S': 4, 'K': 1, 'P': 1,
  };

  void _showActivateDialog(_Player irPlayer) {
    final activeAtPos = _players!
        .where((p) => p.position == irPlayer.position && !p.onIr)
        .toList();
    final max = _positionMax[irPlayer.position] ?? 99;
    final needsDrop = activeAtPos.length >= max;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ActivateSheet(
        irPlayer: irPlayer,
        candidates: needsDrop ? activeAtPos : [],
        needsDrop: needsDrop,
        leagueId: widget.leagueId,
        teamId: widget.teamId,
        onActivated: () { Navigator.pop(context); _load(); },
      ),
    );
  }

  Widget _compositeChip(double composite) {
    final color = composite >= 83
        ? Colors.purple
        : composite >= 73
            ? Colors.green
            : composite >= 63
                ? Colors.blue
                : composite >= 50
                    ? Colors.orange
                    : Colors.grey;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        composite.toStringAsFixed(1),
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: color),
      ),
    );
  }

  void _showPlayerDetail(_Player player) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _PlayerDetailSheet(player: player, leagueId: widget.leagueId),
    );
  }
}

// ── Stat formatting helpers ───────────────────────────────────────────────────

String _fmtN(int n) {
  if (n >= 1000) return '${n ~/ 1000},${(n % 1000).toString().padLeft(3, '0')}';
  return '$n';
}

String _formatStatLine(String position, Map<String, int> s) {
  final parts = <String>[];

  String? passing() {
    final att = s['pass_attempts'] ?? 0;
    if (att == 0) return null;
    final comp = s['pass_completions'] ?? 0;
    final td   = s['pass_tds'] ?? 0;
    final int_ = s['interceptions_thrown'] ?? 0;
    return '$comp/$att, ${_fmtN(s['pass_yards'] ?? 0)} yds, $td TD, $int_ INT';
  }

  String? rushing() {
    final car = s['rush_attempts'] ?? 0;
    if (car == 0) return null;
    final td = s['rush_tds'] ?? 0;
    return '$car car, ${_fmtN(s['rush_yards'] ?? 0)} yds, $td TD';
  }

  String? receiving() {
    final rec = s['receptions'] ?? 0;
    final yds = s['receiving_yards'] ?? 0;
    if (rec == 0 && yds == 0) return null;
    final td = s['receiving_tds'] ?? 0;
    return '$rec rec, ${_fmtN(yds)} yds, $td TD';
  }

  String? defense() {
    final tkl = s['tackles'] ?? 0;
    final sck = s['sacks'] ?? 0;
    final int_ = s['interceptions'] ?? 0;
    final ff  = s['forced_fumbles'] ?? 0;
    final fr  = s['fumble_recoveries'] ?? 0;
    if (tkl == 0 && sck == 0 && int_ == 0 && ff == 0 && fr == 0) return null;
    final p = <String>[];
    if (tkl > 0) p.add('$tkl tkl');
    if (sck > 0) p.add('$sck sck');
    if (int_ > 0) p.add('$int_ INT');
    if (ff > 0) p.add('$ff FF');
    if (fr > 0) p.add('$fr FR');
    return p.join(', ');
  }

  switch (position) {
    case 'QB':
      final p = passing();   if (p != null) parts.add(p);
      final r = rushing();   if (r != null) parts.add(r);
      final c = receiving(); if (c != null) parts.add(c);
    case 'RB':
      final r = rushing();   if (r != null) parts.add(r);
      final c = receiving(); if (c != null) parts.add(c);
      final p = passing();   if (p != null) parts.add(p);
    case 'WR' || 'TE':
      final c = receiving(); if (c != null) parts.add(c);
      final r = rushing();   if (r != null) parts.add(r);
    case 'OL':
      final sa = s['sacks_allowed'] ?? 0;
      if (sa > 0) parts.add('$sa sacks allowed');
    case 'DT' || 'DE' || 'LB' || 'CB' || 'S':
      final d = defense(); if (d != null) parts.add(d);
    default:
      return '—';
  }

  return parts.isEmpty ? '—' : parts.join('  ·  ');
}

// ── Player detail sheet ───────────────────────────────────────────────────────

class _PlayerDetailSheet extends StatefulWidget {
  final _Player player;
  final String leagueId;
  const _PlayerDetailSheet({required this.player, required this.leagueId});

  @override
  State<_PlayerDetailSheet> createState() => _PlayerDetailSheetState();
}

class _PlayerDetailSheetState extends State<_PlayerDetailSheet> {
  Map<String, int>? _ytd;
  Map<String, int>? _career;
  bool _loadingStats = false;
  String? _statsError;

  Future<void> _loadStats() async {
    setState(() { _loadingStats = true; _statsError = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/players/${widget.player.id}/stats'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load stats');
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      setState(() {
        _ytd    = (data['ytd']    as Map<String, dynamic>).map((k, v) => MapEntry(k, v as int));
        _career = (data['career'] as Map<String, dynamic>).map((k, v) => MapEntry(k, v as int));
      });
    } catch (e) {
      setState(() { _statsError = e.toString().replaceFirst('Exception: ', ''); });
    } finally {
      setState(() { _loadingStats = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final player = widget.player;
    return DraggableScrollableSheet(
      initialChildSize: 0.55,
      minChildSize: 0.4,
      maxChildSize: 0.9,
      expand: false,
      builder: (context, scrollController) {
        return ListView(
          controller: scrollController,
          padding: const EdgeInsets.all(24),
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(player.name, style: Theme.of(context).textTheme.titleLarge),
                      Text(
                        '${player.position}  ·  Age ${player.age}',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                      if (player.isReturnReady)
                        const Text('Return ready — activate from roster', style: TextStyle(color: Colors.orange))
                      else if (player.onIr)
                        Text(
                          'IR · OUT ${player.injuryGamesRemaining} game${player.injuryGamesRemaining == 1 ? '' : 's'}',
                          style: const TextStyle(color: Colors.red),
                        )
                      else if (player.isInjured)
                        Text(
                          'OUT ${player.injuryGamesRemaining} game${player.injuryGamesRemaining == 1 ? '' : 's'}',
                          style: const TextStyle(color: Colors.red),
                        ),
                    ],
                  ),
                ),
                _compositeDisplay(context, player.composite),
              ],
            ),
            const Divider(height: 32),
            for (final entry in player.namedStats.entries)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Expanded(child: Text(entry.key)),
                    _statBar(context, entry.value),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: 28,
                      child: Text(
                        '${entry.value}',
                        textAlign: TextAlign.right,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ),
                  ],
                ),
              ),
            const Divider(height: 32),
            if (_ytd == null && !_loadingStats)
              OutlinedButton(
                onPressed: _loadStats,
                child: const Text('Show Stats'),
              )
            else if (_loadingStats)
              const Center(child: Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: CircularProgressIndicator(),
              ))
            else if (_statsError != null)
              Text(_statsError!, style: const TextStyle(color: Colors.red))
            else ...[
              _statSummaryRow(context, 'YTD',    _ytd!,    player.position),
              const SizedBox(height: 8),
              _statSummaryRow(context, 'Career', _career!, player.position),
            ],
            const SizedBox(height: 24),
            OutlinedButton(
              onPressed: null,
              child: const Text('Offer for Trade'),
            ),
          ],
        );
      },
    );
  }

  Widget _statSummaryRow(
    BuildContext context,
    String label,
    Map<String, int> stats,
    String position,
  ) {
    final line = _formatStatLine(position, stats);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 52,
          child: Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: Theme.of(context).colorScheme.primary,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        Expanded(
          child: Text(line, style: Theme.of(context).textTheme.bodySmall),
        ),
      ],
    );
  }

  Widget _compositeDisplay(BuildContext context, double composite) {
    final color = composite >= 83
        ? Colors.purple
        : composite >= 73
            ? Colors.green
            : composite >= 63
                ? Colors.blue
                : composite >= 50
                    ? Colors.orange
                    : Colors.grey;
    return Column(
      children: [
        Text(
          composite.toStringAsFixed(1),
          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: color),
        ),
        Text('OVR', style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }

  Widget _statBar(BuildContext context, int value) {
    final fraction = ((value - 30) / 65).clamp(0.0, 1.0);
    final color = value >= 83
        ? Colors.purple
        : value >= 73
            ? Colors.green
            : value >= 63
                ? Colors.blue
                : value >= 50
                    ? Colors.orange
                    : Colors.grey;
    return SizedBox(
      width: 120,
      height: 6,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(3),
        child: LinearProgressIndicator(
          value: fraction,
          backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
          valueColor: AlwaysStoppedAnimation(color),
        ),
      ),
    );
  }
}

// ── Activate sheet ────────────────────────────────────────────────────────────

class _ActivateSheet extends StatefulWidget {
  final _Player irPlayer;
  final List<_Player> candidates;
  final bool needsDrop;
  final String leagueId;
  final String teamId;
  final VoidCallback onActivated;

  const _ActivateSheet({
    required this.irPlayer,
    required this.candidates,
    required this.needsDrop,
    required this.leagueId,
    required this.teamId,
    required this.onActivated,
  });

  @override
  State<_ActivateSheet> createState() => _ActivateSheetState();
}

class _ActivateSheetState extends State<_ActivateSheet> {
  _Player? _selected;
  bool _loading = false;
  String? _error;

  Future<void> _confirm() async {
    if (widget.needsDrop && _selected == null) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthProvider>();
      final body = <String, dynamic>{'activate_player_id': widget.irPlayer.id};
      if (_selected != null) body['drop_player_id'] = _selected!.id;
      final res = await http.post(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.teamId}/activate'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );
      if (res.statusCode == 204) {
        widget.onActivated();
      } else {
        final msg = jsonDecode(res.body)['detail'] ?? 'Activation failed';
        setState(() { _error = msg; _loading = false; });
      }
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.5,
      minChildSize: 0.35,
      maxChildSize: 0.85,
      expand: false,
      builder: (context, scroll) {
        return Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Activate ${widget.irPlayer.name}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              Text(
                widget.needsDrop
                    ? 'Position is full — drop a ${widget.irPlayer.position} to make room:'
                    : 'You have an open ${widget.irPlayer.position} slot.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              if (widget.needsDrop)
                Expanded(
                  child: ListView(
                    controller: scroll,
                    children: widget.candidates.map((p) {
                      final selected = _selected?.id == p.id;
                      return ListTile(
                        dense: true,
                        title: Text(p.name),
                        subtitle: Text('Age ${p.age}'),
                        trailing: Text(
                          p.composite.toStringAsFixed(1),
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: selected
                                ? Theme.of(context).colorScheme.primary
                                : null,
                          ),
                        ),
                        selected: selected,
                        onTap: () => setState(() => _selected = p),
                      );
                    }).toList(),
                  ),
                ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_error!, style: const TextStyle(color: Colors.red)),
                ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: ((!widget.needsDrop || _selected != null) && !_loading) ? _confirm : null,
                  child: _loading
                      ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : Text(widget.needsDrop ? 'Drop & Activate' : 'Activate'),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
