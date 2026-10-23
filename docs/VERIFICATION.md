# Verifikation der lokalen Demo

Geprüft am **23.10.2026**, lokal auf diesem Mac mit JDK 21.0.8, Docker und den im Repository festgelegten Versionen. Kein Deployment, kein Push und keine DNS-Änderung.

| Prüfebene | Tatsächlich ausgeführt | Ergebnis |
|---|---|---|
| Maven-Build | `./demo build`, alle drei Module, JAR-Paketierung | Erfolgreich |
| Java-Unit-/MockMvc-Tests | 9 gemeinsame JWT-/Rollenprüfungen, 5 API-Prüfungen, 6 MCP-Prüfungen | **20/20 bestanden** |
| Python-Supervisor | `python3 -m unittest discover -s scripts -p 'test_*.py' -v` | **5/5 bestanden** |
| Lokale Dienste | Keycloak 26.8.1, PostgreSQL 17.11, separate API/MCP-Java-Prozesse | Tatsächlich gestartet, Health/HTTP geprüft |
| Vollständiger Live-Lauf | `./demo test` mit echtem Keycloak Authorization Code + S256-PKCE, HTTP-Formular und Loopback-Callback | **59/59 bestanden** |
| Erststart/Reproduzierbarkeit | Eigenes Compose-Projekt `mcp-demo-repro` mit frischem PostgreSQL-Volume; keine Admin-Nachkonfiguration nach Import | Dieselben **59/59 bestanden** |
| Persistenter Standardstart | Temporäres Projekt beendet, Standardprojekt mit vorhandenem Volume erneut gestartet | Dieselben **59/59 erneut bestanden** |
| Echter Browser | Headless Chromium 156 mit lokal vorhandenem Playwright 1.62.1; tatsächliches Keycloak-Formular statt HTTP-Formulartreiber | Login → Callback → PKCE-Code-Einlösung → MCP-Initialisierung → Tool-Liste → Ticketabruf bestanden |
| OpenAPI | YAML geparst, Antwortschema gegen die drei tatsächlich gelieferten API-Tickets geprüft | Erfolgreich |
| Obsidian | Neue Notiz über guarded CLI/App-API im richtigen Google-Drive-Vault angelegt; Inhalt/YAML und native Reading View geprüft | Richtige aktive Datei, Preview-Modus, Mermaid-SVG gerendert, keine erkannten Mermaid-Fehler; native Ansicht per Screenshot geprüft |
| Unabhängige Reviews | code-reviewer, security-reviewer, german-eu-legal-reviewer | Befunde behoben; keine offenen bestätigten Sicherheitsbefunde im lokalen Scope |

Der bereinigte maschinenlesbare letzte Live-Lauf steht in [verification.json](verification.json). Er enthält ausschließlich Zeitpunkt, Checknamen und Ergebnisse. Die lokale Ausführung legt denselben Bericht unter `.local/verification.json` ab. Die temporären Testcontainer und das ausschließlich für die Importprüfung erzeugte Volume wurden anschließend entfernt; das persistente Standard-Volume blieb erhalten.

## Entscheidender Rechtebeweis

- Derselbe synthetische Benutzer erhielt über zwei echte PKCE-Anmeldungen das direkte API-Token und Token A für MCP.
- Mit dem direkten API-Token waren GET, POST **201**, PATCH **200** und DELETE **204** erfolgreich. Datenänderung und tatsächliches Löschen wurden nachgelesen.
- Im Testprozess wurde **ein echtes Standard-V2-Exchange-Token B** über den vertraulichen Requester `mcp-server` angefordert. Genau diese Tokeninstanz wurde für erfolgreiches GET und für POST/PATCH/DELETE/Reset verwendet. Alle vier Schreibversuche lieferten **403**; nach jedem Versuch war der vollständige Demo-Datenbestand unverändert.
- Über beide MCP-Tools wurde das zuvor direkt erzeugte und geänderte API-Ticket zurückgelesen. Der MCP-Pfad liefert damit tatsächliche Backend-Daten.
- Token A an API sowie direktes und ausgetauschtes API-Token an MCP lieferten **401**. Fehlende/fehlerhafte Tokens und eine manipulierte Signatur wurden ebenfalls mit 401 abgewiesen.
- Echte kurzlebige Keycloak-Tokens wurden nach Ablauf abgewiesen. Das API-Token hatte dabei die richtige Audience und durfte unmittelbar vor Ablauf noch erfolgreich lesen.
- Ein Benutzer mit korrekt adressiertem Token, aber fehlender Rolle erhielt **403**. Benutzeridentität blieb beim Exchange erhalten und für zwei Benutzer getrennt.
- Alle vier Exchange-Anforderungen `tickets.write`, `tickets.read tickets.write`, `offline_access tickets.write` und `roles tickets.write` wurden von Keycloak abgewiesen.
- Die während des Testprozesses ausgestellten Tokens und die lokal erzeugten Geheimnisse wurden gegen MCP-Ausgaben und Anwendungslogs geprüft: keine Treffer. Der Test hat sie weder in Bericht noch Modellkontext ausgegeben.

Das im Test angeforderte Token B wird nicht aus dem laufenden MCP-Server exportiert. Test und Server verwenden denselben echten Keycloak-Requester und dieselbe begrenzte Policy. Der Server hat keinen Token-Ausgabeendpunkt und keine Schreibtools.

## Browserbeleg

Die Screenshots enthalten keine Passwörter, Tokens oder Callback-URLs:

![Echte Keycloak-Anmeldeseite vor Eingabe der synthetischen Zugangsdaten](evidence/keycloak-login.png)

![Erfolgreicher OAuth-Callback](evidence/oauth-callback.png)

Der Browsertest nutzte den enthaltenen Python-OAuth-/MCP-Client mit einem temporären Playwright-Browseröffner. Playwright ist keine Laufzeitabhängigkeit der Demo und nicht für `./demo client` oder `./demo test` erforderlich. Für die normale Vorführung öffnet `./demo client` den eigenen Standardbrowser.

## Beweisgrenzen

MockMvc verwendet für Endpunktregeln einen ersetzten JWT-Decoder. Der kryptografische und dienstübergreifende Nachweis stammt aus den separat ausgeführten Live-Tests. Die Claim-Prüfung allein ist kein Schreibschutzbeweis.

Der Browserlauf war automatisiert und headless; ein manueller Klicktest im persönlichen Standardbrowser sowie externe Agent-/Inspector-Integrationen wurden nicht ausgeführt. Es wurden kein öffentlicher Betrieb, kein vollständiger Dependency-CVE-Scan und keine produktive Mandantenisolation geprüft. Diese Punkte sind nicht Teil des vereinbarten lokalen Demo-Scope.
