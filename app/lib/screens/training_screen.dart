import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _TrainPlayer {
  final String id;
  final String name;
  final String position;
  final int age;
  final double composite;
  final Map<String, int> namedStats;
  final int sessionsUsed;
  final int sessionsRemaining;
  final bool trainedThisWeek;
  final int injuryGamesRemaining;

  _TrainPlayer.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        position = j['position'],
        age = j['age'],
        composite = (j['composite'] as num).toDouble(),
        namedStats = (j['named_stats'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, v as int)),
        sessionsUsed = j['train_sessions_used'],
        sessionsRemaining = j['sessions_remaining'],
        trainedThisWeek = j['trained_this_week'] as bool,
        injuryGamesRemaining = j['injury_games_remaining'];

  bool get isInjured => injuryGamesRemaining > 0;
  bool get canTrain => !isInjured && sessionsRemaining > 0 && !trainedThisWeek;
}

const _positionGroups = {
  'Offense':       ['QB', 'WR', 'TE', 'RB', 'OL'],
  'Defense':       ['DT', 'DE', 'LB', 'CB', 'S'],
  'Special Teams': ['K', 'P'],
};

class TrainingScreen extends StatefulWidget {
  final String leagueId;
  final String teamId;
  final String teamName;

  const TrainingScreen({
    super.key,
    required this.leagueId,
    required this.teamId,
    required this.teamName,
  });

  @override
  State<TrainingScreen> createState() => _TrainingScreenState();
}

class _TrainingScreenState extends State<TrainingScreen> {
  List<_TrainPlayer>? _players;
  int _trainPoints = 0;
  int _sessionsPerPlayer = 3;
  bool _inRegularSeason = false;
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
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.teamId}/training'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load training');
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      setState(() {
        _trainPoints      = data['train_points'];
        _sessionsPerPlayer = data['sessions_per_player'];
        _inRegularSeason  = data['in_regular_season'] as bool;
        _players = (data['players'] as List)
            .map((j) => _TrainPlayer.fromJson(j as Map<String, dynamic>))
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
        title: const Text('Training'),
        actions: [
          IconButton(icon: const Icon(Icons.info_outline), onPressed: _showHelp),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _players == null
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  children: [
                    _header(),
                    Expanded(child: _buildList()),
                  ],
                ),
    );
  }

  Widget _header() {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      color: theme.colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!_inRegularSeason)
            Text(
              'Training is available during the regular season.',
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.error),
            )
          else
            Row(
              children: [
                Text('TRAINING POINTS', style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.primary, letterSpacing: 1.2,
                )),
                const SizedBox(width: 10),
                for (int i = 0; i < 3; i++)
                  Padding(
                    padding: const EdgeInsets.only(right: 4),
                    child: Icon(
                      i < _trainPoints ? Icons.circle : Icons.circle_outlined,
                      size: 14,
                      color: i < _trainPoints
                          ? theme.colorScheme.primary
                          : theme.colorScheme.outline,
                    ),
                  ),
                const Spacer(),
                Text('$_trainPoints left this week', style: theme.textTheme.bodySmall),
              ],
            ),
          const SizedBox(height: 4),
          Text(
            'Develop a player, or leave points unspent — they refresh each week.',
            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
          ),
        ],
      ),
    );
  }

  Widget _buildList() {
    final byPosition = <String, List<_TrainPlayer>>{};
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
              for (final player in byPosition[pos]!) _playerTile(player),
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
          color: Theme.of(context).colorScheme.primary, letterSpacing: 1.2,
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

  Widget _playerTile(_TrainPlayer player) {
    final theme = Theme.of(context);
    final tappable = _inRegularSeason && _trainPoints > 0 && player.canTrain;

    String status;
    Color? statusColor;
    if (player.isInjured) {
      status = 'OUT ${player.injuryGamesRemaining}g';
      statusColor = Colors.red;
    } else if (player.trainedThisWeek) {
      status = 'Trained this week';
      statusColor = theme.colorScheme.outline;
    } else if (player.sessionsRemaining == 0) {
      status = 'No sessions left this season';
      statusColor = theme.colorScheme.outline;
    } else {
      status = '${player.sessionsRemaining} of $_sessionsPerPlayer sessions left';
      statusColor = null;
    }

    return ListTile(
      dense: true,
      enabled: tappable,
      title: Text(player.name),
      subtitle: Text(
        'Age ${player.age}  ·  $status',
        style: statusColor != null ? TextStyle(color: statusColor) : null,
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _sessionPips(player),
          const SizedBox(width: 8),
          _compositeChip(player.composite),
        ],
      ),
      onTap: tappable ? () => _openTrainSheet(player) : null,
    );
  }

  Widget _sessionPips(_TrainPlayer player) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (int i = 0; i < _sessionsPerPlayer; i++)
          Padding(
            padding: const EdgeInsets.only(right: 2),
            child: Icon(
              i < player.sessionsRemaining ? Icons.fitness_center : Icons.remove,
              size: 12,
              color: i < player.sessionsRemaining
                  ? Theme.of(context).colorScheme.primary
                  : Theme.of(context).colorScheme.outline.withValues(alpha: 0.4),
            ),
          ),
      ],
    );
  }

  void _openTrainSheet(_TrainPlayer player) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _TrainSheet(
        player: player,
        leagueId: widget.leagueId,
        teamId: widget.teamId,
        trainPoints: _trainPoints,
        onResult: (result) {
          Navigator.pop(context);
          _load();
          _showResult(result);
        },
      ),
    );
  }

  void _showResult(Map<String, dynamic> r) {
    final outcome = r['outcome'] as String;
    final color = switch (outcome) {
      'upgrade' => Colors.green,
      'decline' => Colors.orange,
      'injury'  => Colors.red,
      _         => Theme.of(context).colorScheme.inverseSurface,
    };
    var msg = r['message'] as String;
    if (outcome == 'upgrade') {
      msg += '  (OVR ${(r['composite'] as num).toStringAsFixed(1)})';
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: color,
      behavior: SnackBarBehavior.floating,
    ));
  }

  void _showHelp() {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('How Training Works'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('• You get $_sessionsPerPlayer training points each week — spend them '
                'on your players or lose them; they refresh next week.'),
            const SizedBox(height: 8),
            Text('• Each player can train up to $_sessionsPerPlayer times per season, '
                'once per week.'),
            const SizedBox(height: 8),
            const Text('• More points on a session means a better chance to improve — '
                'but a higher chance of injury.'),
            const SizedBox(height: 8),
            const Text('• Young players have the most room to grow. A player near his '
                'ceiling gains little, and older players get hurt more easily.'),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Got it')),
        ],
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
}

// ── Train sheet ───────────────────────────────────────────────────────────────

class _TrainSheet extends StatefulWidget {
  final _TrainPlayer player;
  final String leagueId;
  final String teamId;
  final int trainPoints;
  final void Function(Map<String, dynamic> result) onResult;

  const _TrainSheet({
    required this.player,
    required this.leagueId,
    required this.teamId,
    required this.trainPoints,
    required this.onResult,
  });

  @override
  State<_TrainSheet> createState() => _TrainSheetState();
}

class _TrainSheetState extends State<_TrainSheet> {
  late int _points;
  bool _loading = false;
  String? _error;

  int get _maxPoints => widget.trainPoints.clamp(1, 3);

  @override
  void initState() {
    super.initState();
    _points = _maxPoints; // default to the most aggressive available
  }

  static const _labels = {1: 'Light', 2: 'Moderate', 3: 'Intense'};
  static const _blurbs = {
    1: 'Lowest injury risk — slow, steady gains.',
    2: 'A balanced session — moderate risk and reward.',
    3: 'Best chance to improve — highest injury risk.',
  };

  Future<void> _train() async {
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.post(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.teamId}/train'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode({'player_id': widget.player.id, 'points': _points}),
      );
      if (!mounted) return;
      if (res.statusCode != 200) {
        final msg = jsonDecode(res.body)['detail'] ?? 'Training failed';
        setState(() { _error = msg; _loading = false; });
        return;
      }
      widget.onResult(jsonDecode(res.body) as Map<String, dynamic>);
    } catch (e) {
      if (mounted) {
        setState(() { _error = e.toString().replaceFirst('Exception: ', ''); _loading = false; });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final p = widget.player;
    return Padding(
      padding: EdgeInsets.only(
        left: 24, right: 24, top: 24,
        bottom: 24 + MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(p.name, style: theme.textTheme.titleLarge),
                    Text('${p.position}  ·  Age ${p.age}  ·  ${p.sessionsRemaining} sessions left',
                        style: theme.textTheme.bodySmall),
                  ],
                ),
              ),
              Text(p.composite.toStringAsFixed(1),
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: theme.colorScheme.primary)),
            ],
          ),
          const Divider(height: 28),
          Text('SESSION INTENSITY', style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.primary, letterSpacing: 1.2,
          )),
          const SizedBox(height: 10),
          SegmentedButton<int>(
            segments: [
              for (int n = 1; n <= 3; n++)
                ButtonSegment(
                  value: n,
                  enabled: n <= _maxPoints,
                  label: Text('${_labels[n]}\n$n pt${n > 1 ? 's' : ''}', textAlign: TextAlign.center),
                ),
            ],
            selected: {_points},
            onSelectionChanged: (s) => setState(() => _points = s.first),
          ),
          const SizedBox(height: 12),
          Text(_blurbs[_points]!, style: theme.textTheme.bodyMedium),
          if (_maxPoints < 3)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('Only $_maxPoints training point${_maxPoints > 1 ? 's' : ''} left this week.',
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline)),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _loading ? null : _train,
              child: _loading
                  ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text('Train ($_points pt${_points > 1 ? 's' : ''})'),
            ),
          ),
        ],
      ),
    );
  }
}
