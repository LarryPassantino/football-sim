import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _StandingRow {
  final String name;
  final String conference;
  final String division;
  final int wins;
  final int losses;
  final int pointDifferential;

  _StandingRow.fromJson(Map<String, dynamic> j)
      : name = j['name'],
        conference = j['conference'],
        division = j['division'],
        wins = j['wins'],
        losses = j['losses'],
        pointDifferential = j['point_differential'];
}

class StandingsScreen extends StatefulWidget {
  final String leagueId;
  const StandingsScreen({super.key, required this.leagueId});

  @override
  State<StandingsScreen> createState() => _StandingsScreenState();
}

class _StandingsScreenState extends State<StandingsScreen> {
  List<_StandingRow>? _standings;
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
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/standings'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load standings');
      final data = jsonDecode(res.body);
      setState(() {
        _standings = (data['standings'] as List)
            .map((j) => _StandingRow.fromJson(j as Map<String, dynamic>))
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
        title: const Text('Standings'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : _standings == null
              ? const Center(child: CircularProgressIndicator())
              : _buildStandings(),
    );
  }

  Widget _buildStandings() {
    final Map<String, Map<String, List<_StandingRow>>> grouped = {};
    for (final row in _standings!) {
      grouped.putIfAbsent(row.conference, () => {});
      grouped[row.conference]!.putIfAbsent(row.division, () => []);
      grouped[row.conference]![row.division]!.add(row);
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (final conf in grouped.keys.toList()..sort()) ...[
          Text(
            conf,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              color: Theme.of(context).colorScheme.primary,
            ),
          ),
          const SizedBox(height: 8),
          for (final div in grouped[conf]!.keys.toList()..sort()) ...[
            Text(div, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            _buildDivisionTable(grouped[conf]![div]!),
            const SizedBox(height: 20),
          ],
        ],
      ],
    );
  }

  Widget _buildDivisionTable(List<_StandingRow> rows) {
    final headerStyle = const TextStyle(fontWeight: FontWeight.bold);
    final headerBg = Theme.of(context).colorScheme.surfaceContainerHighest;

    return Table(
      columnWidths: const {
        0: FlexColumnWidth(3),
        1: FixedColumnWidth(36),
        2: FixedColumnWidth(36),
        3: FixedColumnWidth(48),
      },
      children: [
        TableRow(
          decoration: BoxDecoration(color: headerBg),
          children: [
            Padding(padding: const EdgeInsets.all(6), child: Text('Team', style: headerStyle)),
            Padding(padding: const EdgeInsets.all(6), child: Text('W', style: headerStyle)),
            Padding(padding: const EdgeInsets.all(6), child: Text('L', style: headerStyle)),
            Padding(padding: const EdgeInsets.all(6), child: Text('+/-', style: headerStyle)),
          ],
        ),
        for (final row in rows)
          TableRow(children: [
            Padding(padding: const EdgeInsets.all(6), child: Text(row.name)),
            Padding(padding: const EdgeInsets.all(6), child: Text('${row.wins}')),
            Padding(padding: const EdgeInsets.all(6), child: Text('${row.losses}')),
            Padding(
              padding: const EdgeInsets.all(6),
              child: Text(
                '${row.pointDifferential > 0 ? '+' : ''}${row.pointDifferential}',
                style: TextStyle(
                  color: row.pointDifferential > 0
                      ? Colors.green
                      : row.pointDifferential < 0
                          ? Colors.red
                          : null,
                ),
              ),
            ),
          ]),
      ],
    );
  }
}
