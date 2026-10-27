# Verifikation des gehosteten MCP

> Historischer Nachweis vom 26./27.10.2026. Den aktuellen Stand mit öffentlicher REST-API, anbieterunabhängiger Registrierung und tatsächlicher Claude-Web-Nutzung beschreibt [PUBLIC-DEMO-VERIFICATION.md](PUBLIC-DEMO-VERIFICATION.md). Frühere Aussagen zur internen API und zur `chatgpt.com`-Beschränkung gelten nicht mehr.

Geprüft am **26.10.2026** gegen **https://srv1424016.hstgr.cloud/mcp** auf dem vorhandenen VPS. Der ursprüngliche lokale Nachweis bleibt separat in [VERIFICATION.md](VERIFICATION.md).

| Prüfebene | Ergebnis |
|---|---|
| Java-Build und Tests | **23/23** bestanden: JWT/Rollen, Backend, lokale MCP-Regeln und neue Regeln für öffentliche Ressourcen/Origins |
| Python-Tests | **37/37** bestanden, einschließlich vorhandener Agent-Recovery-Tests und neuer Hosting-/Konfigurationstests |
| Öffentliche Routen und TLS | **8/8**: Health, Metadaten, OAuth-Discovery; Backend, Admin und Master-Realm ohne öffentliches Routing; fremder Host **421**; HTTP → HTTPS **308** |
| Echte OAuth-/Rechte-Matrix über den gehosteten MCP | **59/59** bestanden, nach erneutem Deployment wiederholt |
| Native Codex-Anmeldung | Codex CLI **0.160.0**, echte Discovery und Authorization Code + S256-PKCE, feste Ressource und Callback, Speicherung im OS-Keyring |
| Echter Codex-Agent | `get_ticket(id=1)` und `list_tickets(limit=3)` als erfolgreiche `mcp_tool_call`-Ereignisse mit strukturierten Backend-Ergebnissen |
| Erneutes Deployment | Vorhandenen Realm und Secrets erhalten; Caddy und beide Java-Anwendungen neu erstellt; Keycloak/PostgreSQL weiterverwendet |
| Erneuter Codex-Agent nach Deployment | Mehrere Minuten nach der Anmeldung ohne erneuten Login erfolgreich; beide Tools lieferten erneut die drei synthetischen Seed-Tickets |
| Ausgelieferte JARs | SHA-256 der lokalen Buildartefakte und der JARs auf dem VPS stimmen überein |
| Andere Dienste | Vorhandener Tailscale-Listener auf Port 443 blieb erhalten; öffentliche Ports nur an die öffentliche IPv4-Adresse gebunden |

Maschinenlesbare, auf Secrets/JWTs geprüfte Ergebnisse: [hosted-verification.json](hosted-verification.json). Die pro Lauf erzeugten Operatorberichte liegen Git-ignoriert unter `.hosted/verification.json` und `.hosted/codex-verification.json`. Zugangsdaten sind nicht Teil dieser öffentlichen Belege.

## Nachgewiesene Grenze

Derselbe synthetische Benutzer darf im Test direkt im Backend schreiben. Über MCP bietet der Server trotzdem genau `list_tickets` und `get_ticket` an. Der Codex-Client hat keine Tool-Allowlist, die zusätzliche serverseitige Tools verbergen könnte.

Ein echtes Keycloak-Exchange-Token B wurde erfolgreich zum Lesen verwendet. **Genau dieselbe Tokeninstanz** erhielt bei POST, PATCH, DELETE und Reset jeweils **403**. Nach jedem Schreibversuch wurde der vollständige Datenbestand auf Unverändertheit geprüft. Die Grenze hängt damit nicht nur von sichtbaren Toolnamen oder JWT-Claims ab.

Zusätzlich bestanden falsche Audiences, fehlende Rollen, manipulierte Signaturen, abgelaufene Tokens, vier Versuche zur Anforderung von Schreib-Scopes, getrennte Benutzerkontexte und ungültige Toolargumente die erwarteten Negativprüfungen. Ein fremder Browser-Origin wird mit 403 abgewiesen. Gegen die während des Laufs tatsächlich ausgestellten Tokens und generierten Secrets wurden MCP-Ergebnisse sowie die aktuellen Logs aller sechs Container geprüft; keine Treffer.

## Behobener Proxy-Befund

Der erste Lauf zeigte bei falschem HTTP-Host eine leere 200-Antwort des Caddy-Defaultservers. Der Request erreichte dabei kein MCP-Tool. Mit explizitem `strict_sni_host on` weist Caddy einen Widerspruch zwischen TLS-SNI und Host mit **421** ab. Der vollständige Live-Lauf bestand anschließend und wurde nach einem erneuten Deployment wiederholt.

Caddy filtert außerdem Request-URI und Header aus Runtime-Fehlerlogs. Dies verhindert, dass bei einem Upstream-Ausfall vollständige OAuth-Querys in den Proxy-Fehlerlogs landen. Es sind keine Access-Logs aktiviert.

## Beweisgrenzen und Betrieb

- Der native Codex-OAuth-Test nutzte den tatsächlichen CLI-Codefluss mit `--no-browser` und einem automatisierten HTTP-Loginformular. Ein manueller Klicktest im persönlichen Standardbrowser oder ein UI-Test einer neu geöffneten Desktop-Session wurde nicht durchgeführt. Der echte CLI-Agent und seine Toolereignisse wurden geprüft.
- MockMvc ersetzt den JWT-Decoder; der Signatur- und dienstübergreifende Nachweis stammt aus dem separaten Live-Lauf mit Keycloak.
- Zertifikatsausstellung und gültige TLS-Verbindungen sind geprüft. Eine zukünftige Zertifikatserneuerung oder ein kompletter VPS-Neustart wurden nicht vorweggenommen. `restart: unless-stopped` und persistente Caddy-Volumes sind eingerichtet.
- Kein vollständiger Dependency-CVE-Scan, Lasttest oder produktiver Mandantenbetrieb. Diese Installation dient einer kleinen Präsentation mit synthetischen Daten.
- Der VPS hat nach Einrichtung rund **1,1 GB freien Plattenplatz**. Fremde Images, Dienste und Daten wurden nicht bereinigt. Vor größeren Updates muss die Kapazität geprüft werden.
- Die Ticketdaten liegen im RAM und werden beim Backend-Neustart auf drei Seed-Tickets zurückgesetzt. Die Anmeldung bleibt im eigenen Keycloak/PostgreSQL-Volume erhalten.

## App-Registrierung am 27.10.2026

Der erste gehostete Stand war ausschließlich mit einem vorregistrierten CLI-Client geprüft. Beim Hinzufügen über **Plugins → Benutzerdefinierter MCP-Server** mit URL, Name und OAuth meldete die App „Einige App-Einstellungen wurden abgelehnt“. Im Keycloak-Log stand passend dazu `CLIENT_REGISTER_ERROR`, `not_allowed`, Policy `Trusted Hosts`: Die automatisch angefragte OAuth-Clientregistrierung wurde verweigert. Die frühere CLI-Abnahme belegte diesen App-Einrichtungsweg nicht.

Die idempotente Migration `scripts/hosted_registration.py` richtet dafür begrenzte Dynamic Client Registration ein:

- Rückleitungs-/Client-URLs dürfen nur den Host `chatgpt.com` verwenden; HTTPS ohne Wildcards ist durch ein Keycloak-Clientprofil erzwungen.
- Neue Clients erhalten den Default-Scope `mcp.access` einschließlich fester MCP-Audience und Subject-Mapping. Zulässige angefragte Scopes: `openid`, `mcp.access`, `offline_access`.
- S256-PKCE ist bei neu registrierten Clients erzwungen; Password- und Implicit-Grant werden beim Registrieren bzw. Ändern per Registrierungstoken abgeschaltet.
- Eigene Protocol Mapper und Backend-/Schreib-Scopes sind nicht zulässig. Die bestehende Policy `Full Scope Disabled` bleibt aktiv; ebenso der Consent-Schritt und die begrenzte Clientanzahl (32 im gesamten Realm).
- Der vertrauliche Exchange-Client und seine reine Leseberechtigung bleiben unverändert. Die vorregistrierten CLI-Clients behalten ihre festen Loopback-Callbacks.

Geprüft nach dieser Änderung:

| Prüfung | Ergebnis |
|---|---|
| Python-Regressionstests | **40/40** bestanden |
| Bestehende Live-Rechte-Matrix | **59/59** erneut bestanden |
| Zusätzlicher App-Registrierungstest | **43/43** bestanden: neue Public- und Confidential-Clients, echte Anmeldung/Consent/PKCE, beide MCP-Tools, falsche Audience, verweigerter Password Grant, exakt dasselbe Exchange-Token bei vier Schreibversuchen mit unveränderten Daten, abgewiesene Scope-Erweiterung und bereinigte Logs |
| Erneuter Migrationsaufruf | Erfolgreich wiederholt; keine Rotation oder Neuerstellung vorhandener Clients/Secrets |

Die eigens für die Live-Tests registrierten Clients wurden anschließend wieder gelöscht. Reports enthalten keine Clientsecrets, Registrierungstokens, JWTs oder vollständigen OAuth-URLs. Es wurden keine neuen Java-Abhängigkeiten und keine weiteren Dienste benötigt; der Java-Code und die 23 am Vortag ausgeführten Java-Tests blieben unverändert.

**UI-Stand:** Der Benutzer hat am 27.10.2026 bestätigt, dass das Hinzufügen im Plugin-Dialog jetzt den Browser für die Authentifizierung öffnet. Der bisherige Registrierungsfehler ist damit auch über die persönliche App-Oberfläche überwunden. Die gehostete Instanz verwendet ein eigenes Passwort für `demo`; das localhost-Passwort gilt dort nicht. Der vollständige Abschluss des persönlichen Browser-Logins und die Toolnutzung dieser App-Verbindung sind noch offen. Der native App-Dialog lässt sich in dieser Sitzung nicht per Computersteuerung bedienen; die Protokollstrecke mit neu registrierten Clients und die frühere CLI-Agentennutzung sind separat geprüft.
