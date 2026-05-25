import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';

class AuthProvider extends ChangeNotifier {
  String? _accessToken;
  String? _leagueId;
  String? _teamId;

  bool get isLoggedIn => _accessToken != null;
  String? get leagueId => _leagueId;
  String? get teamId => _teamId;

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
    _accessToken = prefs.getString('access_token');
    _leagueId    = prefs.getString('league_id');
    _teamId      = prefs.getString('team_id');
  }

  Future<void> login(String email, String password) async {
    final res = await http.post(
      Uri.parse('$kBaseUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (res.statusCode != 200) throw Exception(_errorDetail(res.body));
    final data = jsonDecode(res.body);
    _accessToken = data['access_token'] as String;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', _accessToken!);
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
    final data = jsonDecode(res.body);
    _accessToken = data['access_token'] as String;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', _accessToken!);
    notifyListeners();
  }

  Future<void> claimTeam(String leagueId, String teamId) async {
    final res = await http.post(
      Uri.parse('$kBaseUrl/leagues/$leagueId/teams/$teamId/claim'),
      headers: authHeaders,
    );
    if (res.statusCode != 200) throw Exception(_errorDetail(res.body));
    _leagueId = leagueId;
    _teamId   = teamId;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('league_id', leagueId);
    await prefs.setString('team_id', teamId);
    notifyListeners();
  }

  Future<void> logout() async {
    _accessToken = null;
    _leagueId    = null;
    _teamId      = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
    await prefs.remove('league_id');
    await prefs.remove('team_id');
    notifyListeners();
  }
}
