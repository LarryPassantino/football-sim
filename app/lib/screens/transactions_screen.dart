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

  String get summary {
    switch (txType) {
      case 'sign':
        return '$teamName picked up $playerName ($playerPosition)';
      case 'release':
        return '$teamName released $playerName ($playerPosition)';
      case 'trade':
        return '$teamName traded $playerName ($playerPosition) to ${otherTeamName ?? '?'} for ${otherPlayerName ?? '?'}';
      default:
        return '$teamName — $playerName ($playerPosition)';
    }
  }

  IconData get icon {
    switch (txType) {
      case 'sign':    return Icons.add_circle_outline;
      case 'release': return Icons.remove_circle_outline;
      case 'trade':   return Icons.swap_horiz;
      default:        return Icons.swap_horiz;
    }
  }

  Color iconColor(BuildContext context) {
    switch (txType) {
      case 'sign':    return Colors.green;
      case 'release': return Colors.red;
      case 'trade':   return Theme.of(context).colorScheme.primary;
      default:        return Theme.of(context).colorScheme.outline;
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
  List<_Tx>? _txs;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _txs = null; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.get(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/transactions'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 200) throw Exception('Failed to load transactions (${res.statusCode})');
      final data = jsonDecode(res.body) as List;
      setState(() {
        _txs = data.map((j) => _Tx.fromJson(j as Map<String, dynamic>)).toList();
      });
    } catch (e) {
      setState(() { _error = e.toString().replaceFirst('Exception: ', ''); });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Transactions'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _txs == null && _error == null
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : _txs!.isEmpty
                  ? const Center(child: Text('No transactions this season'))
                  : ListView.separated(
                      itemCount: _txs!.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, i) {
                        final tx = _txs![i];
                        return ListTile(
                          leading: Icon(tx.icon, color: tx.iconColor(context), size: 22),
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
