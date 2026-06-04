import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

const _kPositions = ['QB', 'WR', 'TE', 'RB', 'OL', 'DT', 'DE', 'LB', 'CB', 'S', 'K', 'P'];

class _DraftPlayer {
  final String id;
  final String name;
  final String position;
  final int age;
  final String composite;
  final Map<String, String> stats;

  _DraftPlayer.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        name = j['name'],
        position = j['position'],
        age = j['age'],
        composite = j['composite'],
        stats = Map<String, String>.from(j['stats'] as Map);
}

class _PickRecord {
  final int pick;
  final int round;
  final String teamId;
  final String teamName;
  final String playerName;
  final String position;
  final String compositeLabel;

  _PickRecord.fromJson(Map<String, dynamic> j)
      : pick = j['pick'],
        round = j['round'],
        teamId = j['team_id'] as String? ?? '',
        teamName = j['team_name'] as String? ?? '',
        playerName = j['player_name'],
        position = j['position'],
        compositeLabel = j['composite_label'];
}

class DraftScreen extends StatefulWidget {
  final String leagueId;
  final String myTeamId;

  const DraftScreen({super.key, required this.leagueId, required this.myTeamId});

  @override
  State<DraftScreen> createState() => _DraftScreenState();
}

class _DraftScreenState extends State<DraftScreen> with SingleTickerProviderStateMixin {
  late TabController _tabs;

  // Board
  List<String?> _board = [null, null, null, null, null];
  bool _boardLoading = true;
  bool _boardSaving = false;

  // Class
  List<_DraftPlayer> _draftClass = [];
  bool _classLoading = true;
  String? _classFilter;

  // Results
  List<_PickRecord> _allPicks = [];
  bool _resultsLoading = true;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _loadBoard();
    _loadClass();
    _loadResults();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _loadBoard() async {
    setState(() => _boardLoading = true);
    final auth = context.read<AuthProvider>();
    try {
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/draft/board'),
        headers: auth.authHeaders,
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final priority = data['position_priority'] as List;
        setState(() {
          _board = priority.map((e) => e as String?).toList();
        });
      }
    } finally {
      if (mounted) setState(() => _boardLoading = false);
    }
  }

  Future<void> _loadClass() async {
    setState(() => _classLoading = true);
    final auth = context.read<AuthProvider>();
    try {
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/draft/class'),
        headers: auth.authHeaders,
      );
      if (res.statusCode == 200) {
        final list = jsonDecode(res.body) as List;
        setState(() {
          _draftClass = list.map((j) => _DraftPlayer.fromJson(j as Map<String, dynamic>)).toList();
        });
      }
    } finally {
      if (mounted) setState(() => _classLoading = false);
    }
  }

  Future<void> _loadResults() async {
    setState(() => _resultsLoading = true);
    final auth = context.read<AuthProvider>();
    try {
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/draft/results'),
        headers: auth.authHeaders,
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        setState(() {
          _allPicks = (data['picks'] as List)
              .map((j) => _PickRecord.fromJson(j as Map<String, dynamic>))
              .toList();
        });
      }
    } finally {
      if (mounted) setState(() => _resultsLoading = false);
    }
  }

  Future<void> _saveBoard() async {
    setState(() => _boardSaving = true);
    final auth = context.read<AuthProvider>();
    try {
      final res = await http.put(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/draft/board'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode({'position_priority': _board}),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Draft board saved')),
        );
      } else {
        final msg = (jsonDecode(res.body) as Map<String, dynamic>)['detail'] ?? 'Save failed';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg as String)));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => _boardSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Draft Board'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              _loadBoard();
              _loadClass();
              _loadResults();
            },
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          tabs: const [Tab(text: 'Board'), Tab(text: 'Draft Class'), Tab(text: 'Results')],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _buildBoardTab(),
          _buildClassTab(),
          _buildResultsTab(),
        ],
      ),
    );
  }

  // ── Board ────────────────────────────────────────────────────────────────

  Widget _buildBoardTab() {
    if (_boardLoading) return const Center(child: CircularProgressIndicator());
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 40),
      children: [
        Text(
          'Set your position priorities for the upcoming draft. '
          'The draft runs automatically — these guide picks on your behalf.',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 20),
        for (int i = 0; i < 5; i++) ...[
          _buildPriorityRow(i),
          const SizedBox(height: 12),
        ],
        const SizedBox(height: 24),
        FilledButton(
          onPressed: _boardSaving ? null : _saveBoard,
          child: _boardSaving
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Save Board'),
        ),
      ],
    );
  }

  Widget _buildPriorityRow(int index) {
    return Row(
      children: [
        SizedBox(
          width: 88,
          child: Text('Priority ${index + 1}', style: Theme.of(context).textTheme.bodyMedium),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: DropdownButtonFormField<String?>(
            initialValue: _board[index],
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              hintText: 'Best available',
            ),
            items: [
              const DropdownMenuItem<String?>(value: null, child: Text('Best available')),
              ..._kPositions.map(
                (pos) => DropdownMenuItem<String?>(value: pos, child: Text(pos)),
              ),
            ],
            onChanged: (val) => setState(() => _board[index] = val),
          ),
        ),
      ],
    );
  }

  // ── Draft Class ──────────────────────────────────────────────────────────

  Widget _buildClassTab() {
    if (_classLoading) return const Center(child: CircularProgressIndicator());
    if (_draftClass.isEmpty) {
      return Center(
        child: Text(
          'No draft class available',
          style: TextStyle(color: Theme.of(context).colorScheme.outline),
        ),
      );
    }
    final filtered = _classFilter == null
        ? _draftClass
        : _draftClass.where((p) => p.position == _classFilter).toList();
    return Column(
      children: [
        _buildPositionFilter(),
        Expanded(
          child: filtered.isEmpty
              ? Center(
                  child: Text(
                    'No $_classFilter in draft class',
                    style: TextStyle(color: Theme.of(context).colorScheme.outline),
                  ),
                )
              : ListView.builder(
                  padding: EdgeInsets.only(bottom: 16 + MediaQuery.of(context).padding.bottom),
                  itemCount: filtered.length,
                  itemBuilder: (_, i) => _buildClassRow(filtered[i]),
                ),
        ),
      ],
    );
  }

  Widget _buildPositionFilter() {
    return SizedBox(
      height: 44,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        children: [
          FilterChip(
            label: const Text('All'),
            selected: _classFilter == null,
            onSelected: (_) => setState(() => _classFilter = null),
          ),
          ..._kPositions.map((pos) => Padding(
            padding: const EdgeInsets.only(left: 6),
            child: FilterChip(
              label: Text(pos),
              selected: _classFilter == pos,
              onSelected: (_) => setState(() => _classFilter = pos == _classFilter ? null : pos),
            ),
          )),
        ],
      ),
    );
  }

  Widget _buildClassRow(_DraftPlayer player) {
    return ListTile(
      title: Text(player.name),
      subtitle: Text('${player.position}  ·  Age ${player.age}  ·  ${player.composite}'),
      trailing: Icon(Icons.info_outline, size: 18, color: Theme.of(context).colorScheme.outline),
      onTap: () => _showPlayerDetail(player),
    );
  }

  void _showPlayerDetail(_DraftPlayer player) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(player.name, style: Theme.of(context).textTheme.titleLarge),
            Text(
              '${player.position}  ·  Age ${player.age}  ·  ${player.composite}',
              style: TextStyle(color: Theme.of(context).colorScheme.outline),
            ),
            const SizedBox(height: 16),
            ...player.stats.entries.map((e) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(children: [
                SizedBox(
                  width: 140,
                  child: Text(e.key, style: const TextStyle(fontSize: 13)),
                ),
                Text(
                  e.value,
                  style: TextStyle(
                    fontSize: 13,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
              ]),
            )),
            SizedBox(height: 16 + MediaQuery.of(context).padding.bottom),
          ],
        ),
      ),
    );
  }

  // ── Results ──────────────────────────────────────────────────────────────

  Widget _buildResultsTab() {
    if (_resultsLoading) return const Center(child: CircularProgressIndicator());
    if (_allPicks.isEmpty) {
      return Center(
        child: Text(
          'No draft results yet',
          style: TextStyle(color: Theme.of(context).colorScheme.outline),
        ),
      );
    }
    return ListView.builder(
      padding: EdgeInsets.only(bottom: 16 + MediaQuery.of(context).padding.bottom),
      itemCount: _allPicks.length,
      itemBuilder: (_, i) {
        final p = _allPicks[i];
        final isMe = p.teamId == widget.myTeamId;
        final showHeader = i == 0 || _allPicks[i - 1].round != p.round;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (showHeader)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 2),
                child: Text(
                  'ROUND ${p.round}',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: Theme.of(context).colorScheme.primary,
                    letterSpacing: 1.2,
                  ),
                ),
              ),
            ListTile(
              dense: true,
              leading: SizedBox(
                width: 32,
                child: Text(
                  '#${p.pick}',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: Theme.of(context).colorScheme.outline,
                  ),
                ),
              ),
              title: Text(
                '${p.position}  ${p.playerName}',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: isMe ? FontWeight.bold : FontWeight.normal,
                  color: isMe ? Theme.of(context).colorScheme.primary : null,
                ),
              ),
              subtitle: Text(
                '${p.teamName}  ·  ${p.compositeLabel}',
                style: const TextStyle(fontSize: 12),
              ),
            ),
          ],
        );
      },
    );
  }
}
