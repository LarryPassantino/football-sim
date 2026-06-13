import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _ScoutPlayer {
  final String id;
  final String name;
  final String position;
  final int age;
  final String compositeLabel;
  final Map<String, String> namedStatLabels;
  final int injuryGamesRemaining;

  _ScoutPlayer.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        position = j['position'],
        age = j['age'],
        compositeLabel = j['composite_label'],
        namedStatLabels = (j['named_stat_labels'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, v as String)),
        injuryGamesRemaining = j['injury_games_remaining'];

  bool get isInjured => injuryGamesRemaining > 0;
}

const _positionGroups = {
  'Offense':       ['QB', 'WR', 'TE', 'RB', 'OL'],
  'Defense':       ['DT', 'DE', 'LB', 'CB', 'S'],
  'Special Teams': ['K', 'P'],
};

Color _labelColor(String label) {
  switch (label) {
    case 'Elite':      return Colors.purple;
    case 'Above Avg':  return Colors.green;
    case 'Average':    return Colors.blue;
    case 'Below Avg':  return Colors.orange;
    default:           return Colors.grey;
  }
}

class ScoutScreen extends StatefulWidget {
  final String leagueId;
  final String? teamId;  // null = free agents
  final String title;
  final String myTeamId;

  const ScoutScreen({
    super.key,
    required this.leagueId,
    required this.title,
    required this.myTeamId,
    this.teamId,
  });

  @override
  State<ScoutScreen> createState() => _ScoutScreenState();
}

class _ScoutScreenState extends State<ScoutScreen> {
  List<_ScoutPlayer>? _players;
  String? _selectedPosition;
  String? _error;

  bool get _isFreeAgents => widget.teamId == null;

  static const _filterPositions = [
    'ALL', 'QB', 'WR', 'TE', 'RB', 'OL', 'DT', 'DE', 'LB', 'CB', 'S', 'K', 'P',
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _players = null; });
    try {
      final auth = context.read<AuthProvider>();
      final url = _isFreeAgents
          ? '$kBaseUrl/leagues/${widget.leagueId}/free-agents'
          : '$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.teamId}/scout';
      final res = await http.get(Uri.parse(url), headers: auth.authHeaders);
      if (res.statusCode != 200) throw Exception('Failed to load');
      final data = jsonDecode(res.body) as List;
      setState(() {
        _players = data.map((j) => _ScoutPlayer.fromJson(j as Map<String, dynamic>)).toList();
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _players == null
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  children: [
                    _buildFilterRow(),
                    Expanded(child: _buildRoster()),
                  ],
                ),
    );
  }

  Widget _buildFilterRow() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: _filterPositions.map((pos) {
          final isAll     = pos == 'ALL';
          final selected  = isAll ? _selectedPosition == null : _selectedPosition == pos;
          return Padding(
            padding: const EdgeInsets.only(right: 6),
            child: FilterChip(
              label: Text(pos),
              selected: selected,
              onSelected: (_) => setState(() => _selectedPosition = isAll ? null : pos),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildRoster() {
    final visible = _selectedPosition == null
        ? _players!
        : _players!.where((p) => p.position == _selectedPosition).toList();

    // Flat list when filtered to a single position
    if (_selectedPosition != null) {
      return ListView(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom),
        children: visible.map(_playerTile).toList(),
      );
    }

    // Grouped view for ALL
    final byPosition = <String, List<_ScoutPlayer>>{};
    for (final p in visible) {
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

  Widget _playerTile(_ScoutPlayer player) {
    final color = _labelColor(player.compositeLabel);
    return ListTile(
      dense: true,
      title: Text(player.name),
      subtitle: Text('Age ${player.age}${player.isInjured ? '  ·  OUT ${player.injuryGamesRemaining}g' : ''}'),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (player.isInjured)
            const Icon(Icons.local_hospital, size: 16, color: Colors.red),
          const SizedBox(width: 8),
          _labelChip(player.compositeLabel, color),
        ],
      ),
      onTap: () => _showPlayerDetail(player),
    );
  }

  Widget _labelChip(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color),
      ),
    );
  }

  void _showPlayerDetail(_ScoutPlayer player) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ScoutPlayerSheet(
        player: player,
        isFreeAgents: _isFreeAgents,
        leagueId: widget.leagueId,
        myTeamId: widget.myTeamId,
        onSigned: () { Navigator.pop(context); _load(); },
        onTraded: () { Navigator.pop(context); _load(); },
      ),
    );
  }
}

class _ScoutPlayerSheet extends StatefulWidget {
  final _ScoutPlayer player;
  final bool isFreeAgents;
  final String leagueId;
  final String myTeamId;
  final VoidCallback onSigned;
  final VoidCallback onTraded;

  const _ScoutPlayerSheet({
    required this.player,
    required this.isFreeAgents,
    required this.leagueId,
    required this.myTeamId,
    required this.onSigned,
    required this.onTraded,
  });

  @override
  State<_ScoutPlayerSheet> createState() => _ScoutPlayerSheetState();
}

class _ScoutPlayerSheetState extends State<_ScoutPlayerSheet> {
  bool _signing = false;
  bool _trading = false;
  String? _error;
  String? _tradeError;

  Future<void> _signPlayer() async {
    final auth = context.read<AuthProvider>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Sign Player'),
        content: Text(
          'Add ${widget.player.name} (${widget.player.position}) to your active roster?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Sign')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() { _signing = true; _error = null; });
    try {
      final res = await http.post(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.myTeamId}/sign-fa'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode({'player_id': widget.player.id}),
      );
      if (res.statusCode == 204) {
        widget.onSigned();
      } else if (res.statusCode == 409) {
        setState(() { _signing = false; });
        if (mounted) await _showSwapFlow();
      } else {
        final msg = (jsonDecode(res.body) as Map<String, dynamic>)['detail'] ?? 'Signing failed';
        setState(() { _error = msg as String; _signing = false; });
      }
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _signing = false; });
    }
  }

  Future<void> _showSwapFlow() async {
    setState(() { _signing = true; });
    List<Map<String, dynamic>> roster;
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.myTeamId}/roster'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load roster');
      roster = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
    } catch (e) {
      setState(() { _error = 'Could not load roster for swap'; _signing = false; });
      return;
    }
    setState(() { _signing = false; });

    final atPos = roster
        .where((p) =>
            p['position'] == widget.player.position &&
            !(p['on_ir'] as bool? ?? false))
        .toList();

    if (!mounted) return;
    final drop = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _SwapPickerDialog(
        incoming: widget.player.name,
        position: widget.player.position,
        players: atPos,
      ),
    );
    if (drop == null || !mounted) return;

    setState(() { _signing = true; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.post(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.myTeamId}/sign-fa'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode({
          'player_id':      widget.player.id,
          'drop_player_id': drop['id'],
        }),
      );
      if (res.statusCode == 204) {
        widget.onSigned();
      } else {
        final msg = (jsonDecode(res.body) as Map<String, dynamic>)['detail'] ?? 'Signing failed';
        setState(() { _error = msg as String; _signing = false; });
      }
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _signing = false; });
    }
  }

  Future<void> _requestTrade() async {
    setState(() { _trading = true; _tradeError = null; });
    List<Map<String, dynamic>> myRoster;
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.myTeamId}/roster'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load your roster');
      myRoster = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
    } catch (e) {
      setState(() { _tradeError = e.toString().replaceFirst('Exception: ', ''); _trading = false; });
      return;
    }
    setState(() { _trading = false; });

    final active = myRoster.where((p) => !(p['on_ir'] as bool? ?? false)).toList();
    if (!mounted) return;

    final picked = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _TradePickerDialog(players: active),
    );
    if (picked == null || !mounted) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Confirm Trade'),
        content: Text('Offer ${picked['name']} for ${widget.player.name}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Offer')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() { _trading = true; });
    try {
      final auth = context.read<AuthProvider>();
      final scaffoldMessenger = ScaffoldMessenger.of(context);
      final res = await http.post(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.myTeamId}/trade'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode({
          'my_player_id':    picked['id'],
          'their_player_id': widget.player.id,
        }),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        final data     = jsonDecode(res.body) as Map<String, dynamic>;
        final accepted = data['accepted'] as bool;
        final reason   = data['reason'] as String;
        if (accepted) {
          widget.onTraded();
          scaffoldMessenger.showSnackBar(SnackBar(
            content: Text('Trade accepted! ${picked['name']} ↔ ${widget.player.name}'),
            backgroundColor: Colors.green,
          ));
        } else {
          setState(() { _tradeError = reason; _trading = false; });
        }
      } else {
        final msg = jsonDecode(res.body)['detail'] ?? 'Trade request failed';
        setState(() { _tradeError = msg; _trading = false; });
      }
    } catch (e) {
      setState(() { _tradeError = e.toString().replaceFirst('Exception: ', ''); _trading = false; });
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
                      if (player.isInjured)
                        Text(
                          'OUT ${player.injuryGamesRemaining} game${player.injuryGamesRemaining == 1 ? '' : 's'}',
                          style: const TextStyle(color: Colors.red),
                        ),
                    ],
                  ),
                ),
                _compositeDisplay(context, player.compositeLabel),
              ],
            ),
            const Divider(height: 32),
            for (final entry in player.namedStatLabels.entries)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Expanded(child: Text(entry.key)),
                    _labelChip(context, entry.value),
                  ],
                ),
              ),
            const SizedBox(height: 24),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(_error!, style: const TextStyle(color: Colors.red)),
              ),
            if (_tradeError != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(_tradeError!, style: const TextStyle(color: Colors.red)),
              ),
            if (widget.isFreeAgents)
              FilledButton(
                onPressed: _signing ? null : _signPlayer,
                child: _signing
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Sign Player'),
              )
            else
              OutlinedButton(
                onPressed: _trading ? null : _requestTrade,
                child: _trading
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Request Trade'),
              ),
          ],
        );
      },
    );
  }

  Widget _compositeDisplay(BuildContext context, String label) {
    final color = _labelColor(label);
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: color),
        ),
        Text('OVR', style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }

  Widget _labelChip(BuildContext context, String label) {
    final color = _labelColor(label);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: color),
      ),
    );
  }
}

class _SwapPickerDialog extends StatelessWidget {
  final String incoming;
  final String position;
  final List<Map<String, dynamic>> players;

  const _SwapPickerDialog({
    required this.incoming,
    required this.position,
    required this.players,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Drop a $position'),
      content: SizedBox(
        width: double.maxFinite,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '$position slot is full. Select a player to release to make room for $incoming.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            Flexible(
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: players.length,
                itemBuilder: (_, i) {
                  final p = players[i];
                  final composite = (p['composite'] as num).toDouble();
                  return ListTile(
                    dense: true,
                    title: Text(p['name'] as String),
                    subtitle: Text('Age ${p['age']}'),
                    trailing: Text(
                      composite.toStringAsFixed(1),
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    onTap: () => Navigator.pop(context, p),
                  );
                },
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      ],
    );
  }
}


class _TradePickerDialog extends StatelessWidget {
  final List<Map<String, dynamic>> players;
  const _TradePickerDialog({required this.players});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Select your offer'),
      content: SizedBox(
        width: double.maxFinite,
        child: ListView.builder(
          shrinkWrap: true,
          itemCount: players.length,
          itemBuilder: (_, i) {
            final p         = players[i];
            final composite = (p['composite'] as num).toDouble();
            return ListTile(
              dense: true,
              title: Text(p['name'] as String),
              subtitle: Text('${p['position']}  ·  Age ${p['age']}'),
              trailing: Text(
                composite.toStringAsFixed(1),
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              onTap: () => Navigator.pop(context, p),
            );
          },
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      ],
    );
  }
}
