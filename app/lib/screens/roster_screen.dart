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

  _Player.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        position = j['position'],
        age = j['age'],
        composite = (j['composite'] as num).toDouble(),
        namedStats = (j['named_stats'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, v as int)),
        injuryGamesRemaining = j['injury_games_remaining'];

  bool get isInjured => injuryGamesRemaining > 0;
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
          _compositeChip(player.composite),
        ],
      ),
      onTap: () => _showPlayerDetail(player),
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
      builder: (_) => _PlayerDetailSheet(player: player),
    );
  }
}

class _PlayerDetailSheet extends StatelessWidget {
  final _Player player;
  const _PlayerDetailSheet({required this.player});

  @override
  Widget build(BuildContext context) {
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
          ],
        );
      },
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
