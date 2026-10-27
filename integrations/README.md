# Lokaler Codex-Agent über Streamable HTTP

Für die **gehostete Verbindung** in einer normalen Codex-Session siehe die [Haupt-README](../README.md#in-der-codex-app-als-benutzerdefinierten-mcp-hinzufügen) und [codex-hosted.toml](codex-hosted.toml). Die folgenden Schritte betreffen ausschließlich den getrennten lokalen Entwicklungsserver.

Diese Integration verbindet einen eigenständigen Codex-CLI-Agenten direkt mit dem Java-MCP-Server auf diesem Mac. Sie verwendet echte OAuth-Discovery, einen vorregistrierten Public Client und Authorization Code + S256-PKCE. Es gibt keinen Bearer-Token zum Kopieren und keinen stdio-Proxy.

## Voraussetzungen

- Laufende Demo: `./demo status` zeigt Keycloak/PostgreSQL und API/MCP als verfügbar.
- Codex CLI mit den verwendeten OAuth-/Konfigurationsoptionen; geprüft mit **0.160.0** (`codex --version`).
- **Python 3.11+** für den Agenten-Launcher (`tomllib`); die bisherigen API-/MCP-Helfer bleiben mit Python 3.10+ nutzbar.
- Bereits eingerichteter Codex-Modellzugang, beispielsweise `codex login`. `codex login status` prüft diesen Zugang. Das ist vom anschließenden Keycloak-Login getrennt.
- Freier Loopback-Port **8766** für die Keycloak-OAuth-Rückleitung.

## Einrichten und anmelden

Im Repository-Ordner:

```sh
./demo agent setup
./demo agent list
./demo agent login
```

`setup` legt den eigenen Keycloak-Client `codex-demo-client` an bzw. gleicht diesen markierten Demo-Client ab. Auch bei einem vorhandenen Datenbank-Volume funktioniert das ohne Reset oder Secret-Rotation. Ein gleichnamiger fremder Client ohne Ownership-Markierung wird nicht überschrieben. Zusätzlich erhält ausschließlich der bekannte synthetische Benutzer `demo@example.invalid` die für Offline-Refresh erforderliche Realm-Rolle `offline_access`; vorhandene Rollen und alle anderen Benutzer/Clients bleiben erhalten. Die lokale Realm-Importdatei wird für künftige Erststarts passend ergänzt.

`list` zeigt ausschließlich die effektiv verwendete Konfiguration von `ticket_demo`. Sie installiert keinen Eintrag in die globale Codex-Konfigurationsdatei.

`login` startet den **Codex-eigenen** OAuth-Fluss und öffnet Keycloak im Browser. Mit dem synthetischen Benutzer `demo` anmelden. Das lokal erzeugte Passwort steht im Feld `demo_password` in `.local/secrets.json`; lokal öffnen und nicht in Chat oder Konfiguration kopieren. Die Eingabe gehört in die Keycloak-Anmeldeseite. Codex erhält anschließend Token A, kein vertrauliches MCP-Clientsecret.

OAuth-Zugangsdaten werden von Codex im **Betriebssystem-Schlüsselbund** gespeichert (`mcp_oauth_credentials_store="keyring"`). Ein unverschlüsselter Datei-Fallback ist nicht konfiguriert. Login-Tokens dieses Standardclients sind damit gegenüber dem eigenen Python-Testclient bewusst persistent; `logout` entfernt die gespeicherten Codex-MCP-Zugangsdaten. Die Demo speichert sie weder in `.toml` noch unter `.local` oder im Repository.

## Python-Auswahl bei Conda

Der Originalbefehl `./demo agent run` funktioniert auch mit einer älteren aktivierten Conda-Base: Der Launcher prüft vor Projekt-Imports auf **Python 3.11+** und sucht im `PATH` sowie unter `/usr/local/bin`, `/opt/homebrew/bin` und `/usr/bin` nach einer bereits installierten geeigneten Version. Alle Python-Unterprozesse verwenden anschließend denselben Interpreter über `sys.executable`. Es wird nichts installiert und weder Conda noch die Shell-Konfiguration geändert.

Optional lässt sich ein absoluter Interpreter-Pfad angeben:

```sh
DEMO_PYTHON=/absoluter/pfad/python3 ./demo agent run
```

Ein ungeeigneter expliziter Pfad führt zu einer verständlichen Mindestversionsmeldung. Fehlt eine passende Installation, Python 3.11 oder neuer installieren und den Befehl erneut ausführen. Die API-/MCP-Basisbefehle benötigen weiterhin mindestens Python 3.10.

## Agentenlauf

```sh
./demo agent run
```

Ein eigenständiger `codex exec`-Prozess soll `list_tickets(limit=3)` und `get_ticket(id=1)` aufrufen und die Ergebnisse kurz auf Deutsch zusammenfassen. Dieser Lauf ist ein **echter LLM-Agent**, nicht bloß ein weiterer selbst geschriebener Protokollclient.

Die Konfiguration stammt aus [codex.toml](codex.toml) und wird als auf diesen Prozess begrenzte CLI-Overrides geladen. Der Agentlauf ignoriert die globale User-Konfigurationsdatei, deaktiviert Shell/Web, liest keine Projekt-Anweisungsdateien, läuft in Read-only-Sandbox und persistiert keine Codex-Sessiondateien (`--ephemeral`). Seine MCP-Allowlist enthält ausschließlich `list_tickets` und `get_ticket`. Globale MCP-Verbindungen werden nicht geändert und sollen in diesem Lauf nicht geladen werden.

Die Modellinferenz verwendet den bestehenden Codex/OpenAI-Zugang. Dabei werden die öffentliche Toolbeschreibung und die synthetischen Ticketdaten an das Modell übergeben. API, MCP, Keycloak und PostgreSQL bleiben weiterhin ausschließlich lokal; es entsteht keine öffentliche Serverfreigabe. OAuth-Tokens und das vertrauliche Exchange-Secret gelangen nicht in den Modellkontext.

## OAuth- und Serverkonfiguration

| Einstellung | Wert |
|---|---|
| Transport | Streamable HTTP |
| MCP-Ressource | `http://localhost:8082/mcp` |
| Protected Resource Metadata | `http://localhost:8082/.well-known/oauth-protected-resource/mcp` |
| Issuer | `http://localhost:8080/realms/mcp-demo` |
| Public Client | `codex-demo-client` |
| Exakte Redirect-URI | `http://127.0.0.1:8766/callback` |
| Listener-Port | `8766`, zusätzlich zur Callback-URL explizit gesetzt |
| PKCE | S256 erforderlich |
| Default-Scope | ausschließlich `mcp.access` |
| Optionaler Scope | `offline_access`, beim Codex-Login ausdrücklich angefordert |
| Offline-Refresh | nur dieser Public Client; Client Offline Session Idle: 1800 Sekunden |
| Full Scope Allowed / Password Grant / Service Account | jeweils aus |

**Ressourcenbindung:** Codex gewinnt `resource` aus den Protected Resource Metadata. Für die geprüfte CLI wird `oauth_resource` daher nicht zusätzlich gesetzt: Diese Kombination würde dieselbe Ressource zweimal senden; Keycloak weist den doppelten Parameter mit `invalid_request / duplicated parameter` zurück. Issuer- und Audience-Prüfungen bleiben aktiv. Token A enthält die MCP-Ressourcen-Audience; die API lehnt A weiterhin mit 401 ab.

DCR/CIMD wird nicht benötigt, weil die Public Client-ID vorregistriert ist. Wildcard-Redirects und zusätzliche CORS-/Origin-Freigaben sind nicht nötig: Die MCP-Anfragen stammen vom lokalen Codex-Prozess, der Browser dient ausschließlich dem Keycloak-Login. Der vertrauliche `mcp-server`-Requester und seine reine API-Leseberechtigung bleiben unverändert.

Das **lokale Admin-Setup** verwendet zur begrenzten Provisionierung den vorhandenen Keycloak-Administrator über `admin-cli` (Admin-Password-Grant). Das ist getrennt vom Benutzer-/MCP-Login, der weiterhin ausschließlich den Authorization-Code-/PKCE-Weg verwendet. Das Admin-Token bleibt nur im Setup-Prozessspeicher.

Die 1800 Sekunden begrenzen die **Inaktivität**, nicht die gesamte Sitzungsdauer. Refresh verlängert die Sitzung; Offline-Tokens können einen Browser-Logout überleben. Diese Freigabe gilt ausschließlich für den Codex-Public-Client und den synthetischen Demo-Nutzer. Der vertrauliche Exchange-Requester erhält weiterhin weder Offline- noch Schreib-Scopes. Codex 0.160 fordert `offline_access` auch beim Refresh an; ohne diese Konfiguration scheitert der Agent nach Ablauf des Access-Tokens.

## Abmelden und entfernen

```sh
./demo agent logout
```

Das entfernt die lokalen Zugangsdaten dieser MCP-Verbindung aus dem Codex-Credential-Store. Es widerruft keine serverseitige Keycloak-Offline-Sitzung; diese kann in der Keycloak-Adminoberfläche beim Benutzer beendet werden. Für einen neuen Lauf zuerst wieder `./demo agent login` ausführen. Da keine globale Codex-Konfigurationsdatei verändert wird, muss dort kein Servereintrag entfernt werden. Die projektspezifische Konfiguration wirkt nur bei Verwendung des Launchers.

Zum vollständigen Stilllegen kann der eigene Public Client `codex-demo-client` in der lokalen Keycloak-Adminoberfläche deaktiviert oder gelöscht werden. `./demo agent setup` richtet ihn später wieder ein. Der API-/MCP-Server und andere Clientregistrierungen sind davon unabhängig.

## Prüfen und Fehler beheben

```sh
# Für die Tests ausdrücklich einen Python-3.11+-Interpreter verwenden:
python3 -m unittest discover -s scripts -p 'test_*.py' -v
./demo test
```

Die bestehende Live-Sicherheitsmatrix prüft weiterhin Token-Audience-Isolation, echten Exchange, API-Schreibschutz und unveränderte Daten. Sie wird durch die Agentenanbindung nicht ersetzt. Details und tatsächlicher Integrationsstand stehen in [../docs/VERIFICATION.md](../docs/VERIFICATION.md).

- **`ModuleNotFoundError: tomllib` mit älterem Checkout:** Den aktuellen `./demo`-Launcher verwenden. Direkte Aufrufe von `python3 scripts/agent_client.py` umgehen seine Interpreterauswahl; dafür ausdrücklich Python 3.11+ verwenden.
- **Auth required / 401:** `./demo agent login` erneut ausführen. Ein Codex-Modelllogin ersetzt den Keycloak-MCP-Login nicht. Kurzlebige Access-Tokens und Keycloak-Sessions können ablaufen.
- **Offline tokens not allowed / invalid_scope beim Refresh:** `./demo agent setup` und danach `./demo agent login` ausführen. Nur der synthetische `demo`-Benutzer ist für diese Integration vorbereitet.
- **invalid_request / duplicated parameter:** kein zusätzliches `oauth_resource` in die projektbezogene Konfiguration aufnehmen; Codex setzt den Ressourcenparameter aus Discovery.
- **Invalid redirect URI:** Callback exakt `http://127.0.0.1:8766/callback`, nicht `localhost`, anderer Port oder anderer Pfad. `./demo agent setup` erneut ausführen.
- **Port 8766 belegt:** anderen Loginprozess beenden; URL-Port und `callback_port` müssen zusammenpassen.
- **Keyring-Fehler:** Betriebssystem-Schlüsselbund entsperren bzw. den normalen Zugriff erlauben. Nicht auf eine unverschlüsselte Token-Datei oder einen statischen Bearer-Header ausweichen.
- **Unbekannte CLI-Option/Konfiguration:** `codex --version` prüfen; `run` nutzt strikte Konfigurationsprüfung. Nicht unterstützte Optionen werden als Fehler behandelt.
- **Modellzugang scheitert:** `codex login status` prüfen. OAuth/MCP-Verbindung und Modellinferenz sind getrennte Schichten; fehlgeschlagene Inferenz ist kein erfolgreicher Tool-Test.

Der vorhandene Python-Client (`./demo client`) bleibt eine separate deterministische Protokolldemo. Ein MCP Inspector ist hier nicht zusätzlich konfiguriert oder als getestet behauptet. Cloud-Agenten erreichen dieses localhost weiterhin nicht; dafür wäre später eine separat autorisierte Netzwerk-/Hosting-Lösung nötig.

## Offizielle Quellen

- [OpenAI: MCP, vorregistrierte Clients und Callbacks](https://learn.chatgpt.com/docs/extend/mcp)
- [OpenAI: Konfigurationsreferenz](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Keycloak: Offline-Sitzungen](https://www.keycloak.org/docs/latest/server_admin/)
- [Keycloak: Standard Token Exchange](https://www.keycloak.org/securing-apps/token-exchange)
