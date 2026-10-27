# Prüfung der öffentlichen Demo – 27.10.2026

Dieser Stand ersetzt die früheren Einschränkungen auf einen OAuth-Anbieter und ein ausschließlich internes Backend.

## Reale Nutzung über Claude Web

Der vorhandene benutzerdefinierte Connector wurde in **Claude Web → Anpassungen → Konnektoren** mit der öffentlichen MCP-URL verbunden. Der reguläre Web-Ablauf führte zu Keycloak, zur Anmeldung mit dem synthetischen Demo-Benutzer und zum Consent für `mcp.access` und `offline_access`, anschließend zurück zu Claude.

Claude zeigte **„Mit Demo MCP verbunden“** und genau zwei **schreibgeschützte Tools**: „Get ticket“ und „List tickets“. In einem neuen Claude-Web-Chat wurden beide Tools tatsächlich ausgeführt. Die aufgeklappten Toolereignisse zeigten `limit=3` mit den drei Seed-Tickets und `id=1` mit dem erwarteten Einzelticket. Der Nachweis beruht auf den sichtbaren Toolanfragen und Antworten.

Die Verbindung wird über das Claude-Konto verwaltet; sie verwendet den Remote-Connector für Web und Desktop. Die separate native Desktop-Oberfläche wurde nicht zusätzlich geprüft. In dem verfügbaren Gemini-Web-Konto zeigte „Verbundene Apps“ keine Option für benutzerdefinierte MCP-Apps. Ein vollständiger Gemini-Web-UI-Nachweis bleibt deshalb von Googles Freischaltung abhängig.

## Serverseitige und automatisierte Prüfungen

| Ebene | Ergebnis |
|---|---|
| Java-Build und Sicherheitstests | 26 Tests bestanden, einschließlich Callback-Validierung und getrenntem Umgang mit Registrierungstokens |
| Python-Regressionstests | 40 Tests bestanden |
| Öffentliche API-/MCP-Rechtematrix | 59 Prüfungen bestanden; direkte API-Schreiboperationen erfolgreich, MCP-Schreibversuche mit exakt demselben Exchange-Token jeweils `403`, Daten unverändert |
| Anbieterunabhängige OAuth-Registrierung und API-Login | 159 Prüfungen bestanden: HTTPS-Callbacks für ChatGPT, Claude, Gemini und einen weiteren Client sowie lokale IPv4-/IPv6-Callbacks mit echtem Authorization Code, S256-PKCE, Consent und Toolaufrufen geprüft |
| Öffentliche REST-Authentifizierung | Separater API-Client mit Postman-Callbacks; Lesen, Erstellen, Ändern und Löschen über HTTPS geprüft |
| Ausgelieferte Anwendungen | SHA-256 beider gehosteten JARs stimmt mit dem getesteten lokalen Build überein |
| Secrets | Gitleaks ohne Treffer im veröffentlichbaren Dateistand und in der vorhandenen Git-Historie; private Laufzeitdaten bleiben Git-ignoriert |

Zusätzlich wurden Claude Codes nativer OAuth-Login und dessen Verbindungsprüfung sowie das OAuth-Modul der installierten Gemini CLI mit echten MCP-Toolaufrufen geprüft. Diese ergänzenden Prüfungen ersetzen den oben getrennt beschriebenen Web-Nachweis nicht.

Die maschinenlesbaren aktuellen Ergebnisse stehen in [public-demo-verification.json](public-demo-verification.json). Die Live-Prüfung liegt in `scripts/e2e.py` und `scripts/verify_hosted_registration.py`; sie verwendet synthetische Daten und bereinigt die von ihr angelegten Tickets und OAuth-Testclients.

## Durchgesetzte Grenzen

- Neue MCP-Clients erhalten ausschließlich MCP-Scopes; API-Schreib-Scopes und nachträgliche Erweiterungen werden abgewiesen.
- Öffentliches DCR läuft durch den Registrierungscontroller. Er erlaubt exakte HTTPS-Callbacks sowie HTTP ausschließlich für `localhost`, `127.0.0.1` und `[::1]`; keine Wildcards, Fragmente oder Benutzerinformationen. Andere Keycloak-Registrierungsprovider sind öffentlich gesperrt.
- Keycloak erzwingt S256-PKCE und deaktiviert Password-/Implicit-Grant für dynamisch registrierte MCP-Clients.
- Der Exchange-Client bleibt auf `tickets.read` begrenzt. Die öffentlich erreichbare REST-API prüft ihre eigenen Token-Audiences und Rollen.
- Keycloak-Administration, Master-Realm und Datenbank sind weiterhin nicht öffentlich geroutet.

Die Demo verwendet gemeinsame synthetische Tickets im Arbeitsspeicher. Die Ergebnisse belegen diesen geprüften Stand; sie sind kein Lasttest und keine Zusage für KI-Produkte, deren Oberfläche keine eigenen Remote-MCP-Verbindungen unterstützt.
