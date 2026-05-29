import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class LeagueLeadersScreen extends StatefulWidget {
  final String leagueId;
  const LeagueLeadersScreen({super.key, required this.leagueId});

  @override
  State<LeagueLeadersScreen> createState() => _LeagueLeadersScreenState();
}

class _LeagueLeadersScreenState extends State<LeagueLeadersScreen> {
  Map<String, dynamic>? _data;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _data = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/leaders'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load leaders');
      setState(() { _data = jsonDecode(res.body) as Map<String, dynamic>; });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('League Leaders'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _data == null
              ? const Center(child: CircularProgressIndicator())
              : _buildContent(),
    );
  }

  Widget _buildContent() {
    return ListView(
      children: [
        _sectionHeader('Passing'),
        ...(_data!['passing'] as List).asMap().entries.map(
          (e) => _leaderRow(e.key + 1, e.value as Map<String, dynamic>, _passingStats(e.value)),
        ),
        _sectionHeader('Rushing'),
        ...(_data!['rushing'] as List).asMap().entries.map(
          (e) => _leaderRow(e.key + 1, e.value as Map<String, dynamic>, _rushingStats(e.value)),
        ),
        _sectionHeader('Receiving'),
        ...(_data!['receiving'] as List).asMap().entries.map(
          (e) => _leaderRow(e.key + 1, e.value as Map<String, dynamic>, _receivingStats(e.value)),
        ),
        _sectionHeader('Defense'),
        ...(_data!['defense'] as List).asMap().entries.map(
          (e) => _leaderRow(e.key + 1, e.value as Map<String, dynamic>, _defenseStats(e.value)),
        ),
      ],
    );
  }

  Widget _sectionHeader(String label) {
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

  Widget _leaderRow(int rank, Map<String, dynamic> p, String stats) {
    return ListTile(
      dense: true,
      leading: SizedBox(
        width: 28,
        child: Text(
          '#$rank',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: Theme.of(context).colorScheme.outline,
          ),
          textAlign: TextAlign.right,
        ),
      ),
      title: Text(p['player_name'] as String),
      subtitle: Text(
        '${p['team_name']} · ${p['position']}  ·  $stats',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );
  }

  String _fmtN(int n) {
    if (n >= 1000) return '${n ~/ 1000},${(n % 1000).toString().padLeft(3, '0')}';
    return '$n';
  }

  String _passingStats(Map<String, dynamic> p) {
    final yds  = p['pass_yards'] as int;
    final tds  = p['pass_tds'] as int;
    final comp = p['pass_completions'] as int;
    final att  = p['pass_attempts'] as int;
    final ints = p['interceptions_thrown'] as int;
    final pct  = att > 0 ? (comp / att * 100).toStringAsFixed(1) : '0.0';
    return '${_fmtN(yds)} yds · $tds TD · $comp/$att ($pct%) · $ints INT';
  }

  String _rushingStats(Map<String, dynamic> p) {
    final yds = p['rush_yards'] as int;
    final tds = p['rush_tds'] as int;
    final car = p['rush_attempts'] as int;
    return '${_fmtN(yds)} yds · $tds TD · $car car';
  }

  String _receivingStats(Map<String, dynamic> p) {
    final rec = p['receptions'] as int;
    final yds = p['receiving_yards'] as int;
    final tds = p['receiving_tds'] as int;
    return '$rec rec · ${_fmtN(yds)} yds · $tds TD';
  }

  String _defenseStats(Map<String, dynamic> p) {
    final tkl  = p['tackles'] as int;
    final sck  = p['sacks'] as int;
    final int_ = p['interceptions'] as int;
    final ff   = p['forced_fumbles'] as int;
    final fr   = p['fumble_recoveries'] as int;
    final parts = <String>[];
    if (tkl  > 0) parts.add('$tkl tkl');
    if (sck  > 0) parts.add('$sck sck');
    if (int_ > 0) parts.add('$int_ INT');
    if (ff   > 0) parts.add('$ff FF');
    if (fr   > 0) parts.add('$fr FR');
    return parts.join(' · ');
  }
}
