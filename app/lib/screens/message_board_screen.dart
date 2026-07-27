import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../config.dart';
import '../providers/auth_provider.dart';

class _Message {
  final String id;
  final String? teamId;
  final String teamName;
  final String coachName;
  final String body;
  final DateTime createdAt;
  final bool isMine;

  _Message.fromJson(Map<String, dynamic> j)
      : id        = j['id'] as String,
        teamId    = j['team_id'] as String?,
        teamName  = j['team_name'] as String,
        coachName = j['coach_name'] as String,
        body      = j['body'] as String,
        createdAt = DateTime.parse(j['created_at'] as String).toLocal(),
        isMine    = j['is_mine'] as bool;
}

class MessageBoardScreen extends StatefulWidget {
  final String leagueId;

  const MessageBoardScreen({super.key, required this.leagueId});

  @override
  State<MessageBoardScreen> createState() => _MessageBoardScreenState();
}

class _MessageBoardScreenState extends State<MessageBoardScreen> {
  static const _pageSize = 25;

  final List<_Message> _messages = [];
  final ScrollController _scroll = ScrollController();
  final TextEditingController _composer = TextEditingController();

  String? _nextCursor;
  bool _initialLoading = true;
  bool _loadingMore = false;
  bool _hasMore = true;
  bool _sending = false;
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
    _composer.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 400) {
      _load();
    }
  }

  Future<void> _load({bool reset = false}) async {
    if (reset) {
      setState(() {
        _messages.clear();
        _nextCursor = null;
        _hasMore = true;
        _error = null;
        _initialLoading = true;
      });
    } else {
      if (_loadingMore || !_hasMore || _initialLoading) return;
      setState(() { _loadingMore = true; });
    }

    try {
      final auth = context.read<AuthProvider>();
      final params = <String, String>{'limit': '$_pageSize'};
      if (!reset && _nextCursor != null) params['cursor'] = _nextCursor!;

      final uri = Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/messages')
          .replace(queryParameters: params);
      final res = await http.get(uri, headers: auth.authHeaders);
      if (res.statusCode != 200) throw Exception('Failed to load messages (${res.statusCode})');

      final body = jsonDecode(res.body) as Map<String, dynamic>;
      final items = (body['items'] as List)
          .map((j) => _Message.fromJson(j as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      setState(() {
        _messages.addAll(items);
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

  Future<void> _send() async {
    final text = _composer.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() { _sending = true; });
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.post(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/messages'),
        headers: {...auth.authHeaders, 'Content-Type': 'application/json'},
        body: jsonEncode({'body': text}),
      );
      if (res.statusCode != 201) throw Exception('Failed to post (${res.statusCode})');
      final msg = _Message.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
      if (!mounted) return;
      setState(() {
        _messages.insert(0, msg);
        _composer.clear();
      });
      if (_scroll.hasClients) {
        _scroll.animateTo(0,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() { _sending = false; });
    }
  }

  Future<void> _delete(_Message m) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete message?'),
        content: const Text('This removes your message from the board.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete')),
        ],
      ),
    );
    if (confirm != true || !mounted) return;
    try {
      final auth = context.read<AuthProvider>();
      final res = await http.delete(
        Uri.parse('$kBaseUrl/leagues/${widget.leagueId}/messages/${m.id}'),
        headers: auth.authHeaders,
      );
      if (res.statusCode != 204) throw Exception('Failed to delete (${res.statusCode})');
      if (!mounted) return;
      setState(() { _messages.removeWhere((x) => x.id == m.id); });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Message Board'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: () => _load(reset: true)),
        ],
      ),
      body: Column(
        children: [
          Expanded(child: _buildFeed(context)),
          const Divider(height: 1),
          _buildComposer(context),
        ],
      ),
    );
  }

  Widget _buildFeed(BuildContext context) {
    if (_initialLoading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return Center(child: Text(_error!));
    if (_messages.isEmpty) {
      return const Center(child: Text('No messages yet — say something.'));
    }
    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        controller: _scroll,
        itemCount: _messages.length + (_hasMore ? 1 : 0),
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (context, i) {
          if (i >= _messages.length) {
            return const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: SizedBox(
                width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2),
              )),
            );
          }
          return _messageTile(context, _messages[i]);
        },
      ),
    );
  }

  Widget _messageTile(BuildContext context, _Message m) {
    final theme = Theme.of(context);
    return ListTile(
      title: Row(
        children: [
          Expanded(
            child: Text.rich(
              TextSpan(children: [
                TextSpan(
                  text: m.teamName,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                ),
                TextSpan(
                  text: '  ${m.coachName}',
                  style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
                ),
              ]),
            ),
          ),
          Text(
            _formatDate(m.createdAt),
            style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
          ),
          if (m.isMine)
            InkWell(
              onTap: () => _delete(m),
              child: Padding(
                padding: const EdgeInsets.only(left: 8),
                child: Icon(Icons.delete_outline, size: 16, color: theme.colorScheme.outline),
              ),
            ),
        ],
      ),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Text(m.body, style: const TextStyle(fontSize: 14)),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
    );
  }

  Widget _buildComposer(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: _composer,
                minLines: 1,
                maxLines: 4,
                maxLength: 500,
                textInputAction: TextInputAction.newline,
                decoration: const InputDecoration(
                  hintText: 'Message the league…',
                  border: OutlineInputBorder(),
                  isDense: true,
                  counterText: '',
                ),
              ),
            ),
            IconButton(
              icon: _sending
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.send),
              onPressed: _sending ? null : _send,
            ),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return 'now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m';
    if (diff.inHours < 24) return '${diff.inHours}h';
    if (diff.inDays == 1) return 'Yesterday';
    if (diff.inDays < 7) return '${diff.inDays}d';
    return '${dt.month}/${dt.day}';
  }
}
