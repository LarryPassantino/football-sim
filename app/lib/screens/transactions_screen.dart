import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _Tx {
  final String txType;
  final String teamName;
  final String playerName;
  final String playerPosition;
  final String? otherTeamName;
  final String? otherPlayerName;
  final DateTime createdAt;

  _Tx.fromJson(Map<String, dynamic> j)
      : txType           = j['tx_type'] as String,
        teamName         = j['team_name'] as String,
        playerName       = j['player_name'] as String,
        playerPosition   = j['player_position'] as String,
        otherTeamName    = j['other_team_name'] as String?,
        otherPlayerName  = j['other_player_name'] as String?,
        createdAt        = DateTime.parse(j['created_at'] as String).toLocal();

  String get prefix {
    switch (txType) {
      case 'sign':
        return otherPlayerName != null ? '+-' : '+';
      case 'release':  return '-';
      case 'activate':
        return otherPlayerName != null ? '+-' : '+';
      case 'trade':    return '~';
      default:         return '~';
    }
  }

  Color prefixColor(BuildContext context) {
    switch (txType) {
      case 'sign':
        return otherPlayerName != null ? Colors.orange : Colors.green;
      case 'release':  return Colors.red;
      case 'activate':
        return otherPlayerName != null ? Colors.orange : Colors.green;
      default:         return Theme.of(context).colorScheme.primary;
    }
  }

  String get summary {
    switch (txType) {
      case 'sign':
        if (otherPlayerName != null) {
          return '$teamName: signed $playerName, released $otherPlayerName ($playerPosition)';
        }
        return '$teamName signed $playerName ($playerPosition)';
      case 'release':
        return '$teamName released $playerName ($playerPosition)';
      case 'activate':
        if (otherPlayerName != null) {
          return '$teamName: activated $playerName from IR, released $otherPlayerName ($playerPosition)';
        }
        return '$teamName activated $playerName from IR ($playerPosition)';
      case 'trade':
        return '$teamName traded $playerName ($playerPosition) to ${otherTeamName ?? '?'} for ${otherPlayerName ?? '?'}';
      default:
        return '$teamName — $playerName ($playerPosition)';
    }
  }
}

class TransactionsScreen extends StatefulWidget {
  final String leagueId;

  const TransactionsScreen({super.key, required this.leagueId});

  @override
  State<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends State<TransactionsScreen> {
  static const _pageSize = 25;

  final List<_Tx> _txs = [];
  final ScrollController _scroll = ScrollController();

  bool _mineOnly = false;
  String? _nextCursor;
  bool _initialLoading = true;
  bool _loadingMore = false;
  bool _hasMore = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _load(reset: true);
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    // Load the next page when within 400px of the bottom.
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 400) {
      _load();
    }
  }

  Future<void> _load({bool reset = false}) async {
    if (reset) {
      setState(() {
        _txs.clear();
        _nextCursor = null;
        _hasMore = true;
        _error = null;
        _initialLoading = true;
      });
    } else {
      // Guard against re-entrancy and end-of-feed.
      if (_loadingMore || !_hasMore || _initialLoading) return;
      setState(() { _loadingMore = true; });
    }

    try {
      final auth = context.read<AuthProvider>();
      final params = <String, String>{'limit': '$_pageSize'};
      if (_mineOnly && auth.teamId != null) params['team_id'] = auth.teamId!;
      if (!reset && _nextCursor != null) params['cursor'] = _nextCursor!;

      final uri = Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/transactions')
          .replace(queryParameters: params);
      final res = await http.get(uri, headers: auth.authHeaders);
      if (res.statusCode != 200) throw Exception('Failed to load transactions (${res.statusCode})');

      final body = jsonDecode(res.body) as Map<String, dynamic>;
      final items = (body['items'] as List)
          .map((j) => _Tx.fromJson(j as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      setState(() {
        _txs.addAll(items);
        _nextCursor = body['next_cursor'] as String?;
        _hasMore = _nextCursor != null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    } finally {
      if (mounted) setState(() { _initialLoading = false; _loadingMore = false; });
    }
  }

  void _setScope(bool mineOnly) {
    if (mineOnly == _mineOnly) return;
    setState(() { _mineOnly = mineOnly; });
    _load(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    final canFilterMine = context.read<AuthProvider>().teamId != null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Transactions'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: () => _load(reset: true)),
        ],
      ),
      body: Column(
        children: [
          if (canFilterMine)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: false, label: Text('All'), icon: Icon(Icons.groups)),
                  ButtonSegment(value: true, label: Text('My Team'), icon: Icon(Icons.person)),
                ],
                selected: {_mineOnly},
                onSelectionChanged: (s) => _setScope(s.first),
              ),
            ),
          Expanded(child: _buildFeed(context)),
        ],
      ),
    );
  }

  Widget _buildFeed(BuildContext context) {
    if (_initialLoading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return Center(child: Text(_error!));
    if (_txs.isEmpty) {
      return Center(child: Text(_mineOnly ? 'No moves by your team yet' : 'No transactions this season'));
    }
    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        controller: _scroll,
        itemCount: _txs.length + (_hasMore ? 1 : 0),
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (context, i) {
          if (i >= _txs.length) {
            return const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: SizedBox(
                width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2),
              )),
            );
          }
          final tx = _txs[i];
          return ListTile(
            leading: SizedBox(
              width: 28,
              child: Center(
                child: Text(
                  tx.prefix,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    color: tx.prefixColor(context),
                  ),
                ),
              ),
            ),
            title: Text(tx.summary, style: const TextStyle(fontSize: 13)),
            subtitle: Text(
              _formatDate(tx.createdAt),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Theme.of(context).colorScheme.outline,
              ),
            ),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          );
        },
      ),
    );
  }

  String _formatDate(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays == 1) return 'Yesterday';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${dt.month}/${dt.day}';
  }
}
