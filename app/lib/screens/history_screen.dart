import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _SeasonEntry {
  final int seasonNumber;
  final int wins;
  final int losses;
  final int ties;
  final String playoffResult;

  _SeasonEntry.fromJson(Map<String, dynamic> j)
      : seasonNumber  = j['season_number'],
        wins          = j['wins'],
        losses        = j['losses'],
        ties          = j['ties'],
        playoffResult = j['playoff_result'];
}

class HistoryScreen extends StatefulWidget {
  final String leagueId;
  final String teamId;
  final String teamName;

  const HistoryScreen({
    super.key,
    required this.leagueId,
    required this.teamId,
    required this.teamName,
  });

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<_SeasonEntry>? _seasons;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/teams/${widget.teamId}/history'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load history');
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final entries = (data['seasons'] as List)
          .map((j) => _SeasonEntry.fromJson(j as Map<String, dynamic>))
          .toList()
          .reversed
          .toList();
      setState(() { _seasons = entries; });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.teamName} History'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _seasons == null
              ? const Center(child: CircularProgressIndicator())
              : _seasons!.isEmpty
                  ? const Center(child: Text('No completed seasons yet.'))
                  : _buildList(),
    );
  }

  Widget _buildList() {
    return ListView.separated(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + MediaQuery.of(context).padding.bottom),
      itemCount: _seasons!.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (_, i) => _buildSeasonCard(_seasons![i]),
    );
  }

  Widget _buildSeasonCard(_SeasonEntry s) {
    final (label, color) = _playoffLabel(s.playoffResult, context);
    final record = s.ties > 0 ? '${s.wins}-${s.losses}-${s.ties}' : '${s.wins}-${s.losses}';

    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Expanded(
              child: Text(
                'Season ${s.seasonNumber}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            Text(
              record,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(width: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: color.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: color.withOpacity(0.5)),
              ),
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  (String, Color) _playoffLabel(String result, BuildContext context) {
    return switch (result) {
      'champion'   => ('Champion', const Color(0xFFD4A017)),
      'runner_up'  => ('Runner-Up', Colors.blueGrey),
      'conf_champ' => ('Conf. Champ', Theme.of(context).colorScheme.primary),
      'first_round' => ('Playoffs', Theme.of(context).colorScheme.secondary),
      _             => ('Missed Playoffs', Colors.grey),
    };
  }
}
