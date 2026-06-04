import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';

class AuthProvider extends ChangeNotifier {
  String? _accessToken;
  String? _refreshToken;
  String? _leagueId;
  String? _teamId;
  String? _teamName;
  String? _pendingFcmToken;

  bool get isLoggedIn => _accessToken != null;
  String? get leagueId => _leagueId;
  String? get teamId => _teamId;
  String? get teamName => _teamName;

  Map<String, String> get authHeaders => {
    'Content-Type': 'application/json',
    if (_accessToken != null) 'Authorization': 'Bearer $_accessToken',
  };

  String _errorDetail(String body) {
    try {
      return (jsonDecode(body) as Map<String, dynamic>)['detail'] as String;
    } catch (_) {
      return body.isEmpty ? 'No response from server' : body;
    }
  }

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _accessToken  = prefs.getString('access_token');
    _refreshToken = prefs.getString('refresh_token');
    _leagueId     = prefs.getString('league_id');
    _teamId       = prefs.getString('team_id');
    _teamName     = prefs.getString('team_name');

    if (_refreshToken != null) {
      // Silently refresh on every cold start so the access token is always fresh.
      final ok = await _doRefresh();
      if (ok && _teamId == null) await _restoreTeam();
    } else if (_accessToken != null && _teamId == null) {
      await _restoreTeam();
    }
  }

  // Returns true on success, calls logout() and returns false on failure.
  Future<bool> _doRefresh() async {
    if (_refreshToken == null) return false;
    try {
      final res = await http.post(
        Uri.parse('$kBaseUrl/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': _refreshToken}),
      );
      if (res.statusCode != 200) {
        await logout();
        return false;
      }
      final data = jsonDecode(res.body);
      _accessToken  = data['access_token'] as String;
      _refreshToken = data['refresh_token'] as String;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('access_token', _accessToken!);
      await prefs.setString('refresh_token', _refreshToken!);
      return true;
    } catch (_) {
      await logout();
      return false;
    }
  }

  Future<void> _restoreTeam() async {
    if (_accessToken == null) return;
    try {
      final res = await http.get(
        Uri.parse('$kBaseUrl/coaches/me/teams'),
        headers: authHeaders,
      );
      if (res.statusCode != 200) return;
      final teams = jsonDecode(res.body) as List;
      if (teams.isEmpty) return;
      final first = teams.first as Map<String, dynamic>;
      _leagueId = first['league_id'] as String;
      _teamId   = first['team_id'] as String;
      _teamName = first['team_name'] as String;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('league_id', _leagueId!);
      await prefs.setString('team_id', _teamId!);
      await prefs.setString('team_name', _teamName!);
    } catch (_) {}
  }

  Future<void> _saveTokens(Map<String, dynamic> data) async {
    _accessToken  = data['access_token'] as String;
    _refreshToken = data['refresh_token'] as String;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', _accessToken!);
    await prefs.setString('refresh_token', _refreshToken!);
  }

  // Call this from main.dart whenever FCM issues a token.
  // Registers immediately if logged in; otherwise stores it for after login.
  Future<void> setFcmToken(String token) async {
    _pendingFcmToken = token;
    await registerFcmToken(token);
  }

  Future<void> registerFcmToken(String token) async {
    if (_accessToken == null) return;
    try {
      await http.post(
        Uri.parse('$kBaseUrl/auth/fcm-token'),
        headers: authHeaders,
        body: jsonEncode({'token': token}),
      );
    } catch (_) {}
  }

  Future<void> login(String email, String password) async {
    final res = await http.post(
      Uri.parse('$kBaseUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (res.statusCode != 200) throw Exception(_errorDetail(res.body));
    await _saveTokens(jsonDecode(res.body));
    await _restoreTeam();
    if (_pendingFcmToken != null) await registerFcmToken(_pendingFcmToken!);
    notifyListeners();
  }

  Future<void> register(String email, String password, String displayName) async {
    final res = await http.post(
      Uri.parse('$kBaseUrl/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'email': email,
        'password': password,
        'display_name': displayName,
      }),
    );
    if (res.statusCode != 201) throw Exception(_errorDetail(res.body));
    await _saveTokens(jsonDecode(res.body));
    await _restoreTeam();
    if (_pendingFcmToken != null) await registerFcmToken(_pendingFcmToken!);
    notifyListeners();
  }

  Future<void> updateTeamName(String name) async {
    _teamName = name;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('team_name', name);
    notifyListeners();
  }

  Future<void> setActiveTeam(String teamId, String leagueId, String teamName) async {
    _teamId   = teamId;
    _leagueId = leagueId;
    _teamName = teamName;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('team_id', teamId);
    await prefs.setString('league_id', leagueId);
    await prefs.setString('team_name', teamName);
    notifyListeners();
  }

  Future<void> claimTeam(String leagueId, String teamId) async {
    final res = await http.post(
      Uri.parse('$kBaseUrl/leagues/$leagueId/teams/$teamId/claim'),
      headers: authHeaders,
    );
    if (res.statusCode != 200) throw Exception(_errorDetail(res.body));
    final data = jsonDecode(res.body);
    _leagueId  = leagueId;
    _teamId    = teamId;
    _teamName  = data['name'] as String?;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('league_id', leagueId);
    await prefs.setString('team_id', teamId);
    if (_teamName != null) await prefs.setString('team_name', _teamName!);
    notifyListeners();
  }

  Future<void> logout() async {
    _accessToken  = null;
    _refreshToken = null;
    _leagueId     = null;
    _teamId       = null;
    _teamName     = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
    await prefs.remove('league_id');
    await prefs.remove('team_id');
    await prefs.remove('team_name');
    notifyListeners();
  }
}
